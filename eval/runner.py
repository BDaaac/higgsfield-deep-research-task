"""Async parallel runner for the evaluation suite.

Key design decisions:
- asyncio.to_thread() wraps the synchronous run_agent() call so it doesn't
  block the event loop. Each case runs in a thread-pool worker.
- asyncio.Semaphore caps concurrency to avoid thundering-herd on the API.
- Retry logic targets transient provider errors detected in trace.error
  (because run_agent catches exceptions internally and returns stopped_reason=error).
- Retry budget per case: max 3 attempts, exponential backoff, never retried
  on assertion failures or non-transient errors.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from agent import run_agent
from eval.models import CaseRepeatResult, TestCase
from eval.scorer import score_case

_TRANSIENT_PATTERNS = [
    "429",
    "529",
    "503",
    "overloaded",
    "rate_limit",
    "ratelimit",
    "timeout",
    "connection",
    "network",
]
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0   # seconds


def _is_transient(error: str | None) -> bool:
    if not error:
        return False
    lower = error.lower()
    return any(p in lower for p in _TRANSIENT_PATTERNS)


def _load_case(path: Path) -> TestCase:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return TestCase(**data)


def _load_cases(cases_dir: Path) -> list[TestCase]:
    cases = []
    for p in sorted(cases_dir.glob("*.yaml")):
        cases.append(_load_case(p))
    return cases


def _save_trace(trace_dict: dict[str, Any], run_id: str, case_id: str, repeat_idx: int) -> str:
    out_dir = Path("traces") / run_id / case_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"repeat_{repeat_idx}.json"
    path.write_text(json.dumps(trace_dict, indent=2, default=str), encoding="utf-8")
    return str(path)


async def _run_one(
    case: TestCase,
    repeat_idx: int,
    run_id: str,
    sem: asyncio.Semaphore,
    model: str,
) -> CaseRepeatResult:
    async with sem:
        trace_dict: dict[str, Any] | None = None

        for attempt in range(_MAX_RETRIES):
            result = await asyncio.to_thread(run_agent, case.input, model)
            trace_dict = result.to_dict()

            if result.stopped_reason == "error" and _is_transient(result.error):
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                await asyncio.sleep(delay)
                continue
            break  # success or non-transient error — don't retry

        trace_path = _save_trace(trace_dict, run_id, case.id, repeat_idx)
        return score_case(case, trace_dict, trace_path, repeat_idx)


async def run_suite(
    cases_dir: Path | str,
    *,
    run_id: str | None = None,
    concurrency: int = 5,
    repeats: int = 1,
    model: str = "claude-haiku-4-5",
    single_case_path: Path | None = None,
) -> tuple[str, list[CaseRepeatResult]]:
    """Run the full evaluation suite. Returns (run_id, results)."""
    run_id = run_id or str(uuid.uuid4())[:8]

    if single_case_path:
        cases = [_load_case(single_case_path)]
    else:
        cases = _load_cases(Path(cases_dir))

    sem = asyncio.Semaphore(concurrency)
    tasks = [
        _run_one(case, i, run_id, sem, model)
        for case in cases
        for i in range(repeats)
    ]
    results = await asyncio.gather(*tasks)
    return run_id, list(results)


def run_suite_sync(
    cases_dir: Path | str,
    **kwargs: Any,
) -> tuple[str, list[CaseRepeatResult]]:
    """Synchronous wrapper for CLI use."""
    return asyncio.run(run_suite(cases_dir, **kwargs))


# ---------------------------------------------------------------------------
# Re-score from saved traces (no API calls)
# ---------------------------------------------------------------------------


def rescore_from_traces(
    traces_dir: Path | str,
    cases_dir: Path | str,
    hard_only: bool = False,
) -> list[CaseRepeatResult]:
    """Load saved traces and re-score without calling the agent."""
    traces_dir = Path(traces_dir)
    cases = {c.id: c for c in _load_cases(Path(cases_dir))}
    results = []

    for trace_path in sorted(traces_dir.rglob("repeat_*.json")):
        with trace_path.open(encoding="utf-8") as f:
            trace_dict = json.load(f)

        # Infer case_id from directory structure: traces/{run_id}/{case_id}/repeat_{i}.json
        case_id = trace_path.parent.name
        repeat_idx = int(trace_path.stem.split("_")[-1])
        case = cases.get(case_id)
        if case is None:
            continue

        result = score_case(case, trace_dict, str(trace_path), repeat_idx, hard_only=hard_only)
        results.append(result)

    return results
