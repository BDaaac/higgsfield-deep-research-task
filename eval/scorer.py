"""Score a single agent run against a TestCase.

Hard / soft mixing formula (deterministic contract):
1. Any CRITICAL hard assertion failure → case immediately fails (soft skipped).
2. Non-critical hard failures are recorded but do not block soft scoring.
3. soft_score = weighted average of individual soft scores.
4. soft_pass  = soft_score >= SoftAssertion.threshold (per-assertion).
5. Case passes if: no critical hard failures AND all soft assertions pass.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from eval.models import (
    AssertionResult,
    CaseRepeatResult,
    HardAssertion,
    SoftAssertion,
    TestCase,
    TraceSummary,
)

# ---------------------------------------------------------------------------
# Corpus loader (for passing ground-truth snippets to the judge)
# ---------------------------------------------------------------------------

_CORPUS_DIR = Path(__file__).parent.parent / "corpus"
_INDEX_PATH = _CORPUS_DIR / "index.json"


def _load_corpus_texts() -> dict[str, str]:
    with _INDEX_PATH.open() as f:
        index = json.load(f)
    texts: dict[str, str] = {}
    for entry in index["pages"]:
        path = _CORPUS_DIR / entry["file"]
        texts[entry["url"]] = path.read_text(encoding="utf-8")
    return texts


_CORPUS: dict[str, str] = _load_corpus_texts()


def _corpus_snippets_for(citations: list[str]) -> list[str]:
    snippets = []
    for url in citations:
        text = _CORPUS.get(url)
        if text:
            snippets.append(f"[{url}]\n{text[:2000]}")
    return snippets


# ---------------------------------------------------------------------------
# Hard assertion dispatch
# ---------------------------------------------------------------------------


def _extract_tool_calls(trace_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten all tool_calls from the trace messages."""
    calls = []
    for msg in trace_dict.get("messages", []):
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []):
                calls.append({"name": tc.get("name"), "args": tc.get("args", {})})
    return calls


def _fetched_urls(tool_calls: list[dict]) -> set[str]:
    return {
        tc["args"].get("url", "")
        for tc in tool_calls
        if tc["name"] == "fetch_url"
    }


def _check_hard(
    assertion: HardAssertion,
    summary: TraceSummary,
    tool_calls: list[dict],
) -> AssertionResult:
    check = assertion.check
    p = assertion.params

    def ok(reason: str) -> AssertionResult:
        return AssertionResult(check=check, passed=True, reason=reason, critical=assertion.critical)

    def fail(reason: str) -> AssertionResult:
        return AssertionResult(check=check, passed=False, reason=reason, critical=assertion.critical)

    if check == "tool_called":
        tool = p["tool"]
        names = [tc["name"] for tc in tool_calls]
        if tool in names:
            return ok(f"'{tool}' was called.")
        return fail(f"'{tool}' was never called. Calls: {names}")

    if check == "tool_called_with":
        tool = p["tool"]
        match_args = {k: v for k, v in p.items() if k != "tool"}
        for tc in tool_calls:
            if tc["name"] == tool:
                if all(tc["args"].get(k) == v for k, v in match_args.items()):
                    return ok(f"'{tool}' called with {match_args}.")
        return fail(f"'{tool}' never called with args {match_args}.")

    if check == "tool_count_lte":
        n = p["n"]
        count = len(tool_calls)
        if count <= n:
            return ok(f"{count} tool calls <= {n}.")
        return fail(f"{count} tool calls exceeds limit of {n}.")

    if check == "tool_count_gte":
        n = p["n"]
        count = len(tool_calls)
        if count >= n:
            return ok(f"{count} tool calls >= {n}.")
        return fail(f"Only {count} tool calls, expected >= {n}.")

    if check == "stopped_reason":
        expected = p["value"]
        actual = summary.stopped_reason
        if actual == expected:
            return ok(f"stopped_reason == '{expected}'.")
        return fail(f"stopped_reason is '{actual}', expected '{expected}'.")

    if check == "answer_contains":
        sub = p["substring"]
        ans = summary.final_answer or ""
        if sub.lower() in ans.lower():
            return ok(f"Answer contains '{sub}'.")
        return fail(f"Answer does not contain '{sub}'. Answer: {ans[:200]!r}")

    if check == "answer_not_contains":
        sub = p["substring"]
        ans = summary.final_answer or ""
        if sub.lower() not in ans.lower():
            return ok(f"Answer does not contain '{sub}'.")
        return fail(f"Answer contains forbidden substring '{sub}'.")

    if check == "answer_word_count_lte":
        n = p["n"]
        ans = summary.final_answer or ""
        count = len(ans.split())
        if count <= n:
            return ok(f"Answer has {count} words <= {n}.")
        return fail(f"Answer has {count} words, exceeds limit of {n}.")

    if check == "citation_not_contains":
        sub = p["substring"]
        bad = [c for c in summary.citations if sub in c]
        if not bad:
            return ok(f"No citation contains '{sub}'.")
        return fail(f"Citations contain forbidden pattern '{sub}': {bad}")

    if check == "citations_fetched":
        fetched = _fetched_urls(tool_calls)
        missing = [c for c in summary.citations if c not in fetched]
        if not missing:
            return ok("All citations were fetched via fetch_url.")
        return fail(f"Citations not fetched: {missing}")

    if check == "tool_sequence_includes":
        required: list[str] = p["sequence"]
        names = [tc["name"] for tc in tool_calls]
        # Check subsequence (order matters, gaps allowed).
        it = iter(names)
        matched = all(t in it for t in required)
        if matched:
            return ok(f"Tool sequence {required} found in {names}.")
        return fail(f"Required tool sequence {required} not found in {names}.")

    if check == "answer_matches_regex":
        pattern = p["pattern"]
        ans = summary.final_answer or ""
        if re.search(pattern, ans, re.IGNORECASE):
            return ok(f"Answer matches pattern '{pattern}'.")
        return fail(f"Answer does not match pattern '{pattern}'.")

    return fail(f"Unknown hard assertion check: '{check}'")


# ---------------------------------------------------------------------------
# Main scorer entry point
# ---------------------------------------------------------------------------


def score_case(
    case: TestCase,
    trace_dict: dict[str, Any],
    trace_path: str,
    repeat_idx: int,
    hard_only: bool = False,
) -> CaseRepeatResult:
    """Score one agent run against a TestCase. Returns CaseRepeatResult."""
    import metrics  # noqa: F401 — triggers auto-registration

    from metrics.base import METRIC_REGISTRY

    tool_calls = _extract_tool_calls(trace_dict)

    summary = TraceSummary(
        run_id=trace_dict.get("run_id", ""),
        stopped_reason=trace_dict.get("stopped_reason", ""),
        final_answer=trace_dict.get("final_answer"),
        citations=trace_dict.get("citations", []),
        total_tokens=trace_dict.get("total_tokens", {}),
        cost_usd=trace_dict.get("cost_usd", 0.0),
        wall_time_ms=trace_dict.get("wall_time_ms", 0),
        tool_calls=tool_calls,
        error=trace_dict.get("error"),
    )

    assertion_results: list[AssertionResult] = []
    critical_hard_failure = False

    # --- Hard assertions ---
    for assertion in case.hard_assertions:
        result = _check_hard(assertion, summary, tool_calls)
        assertion_results.append(result)
        if not result.passed and result.critical:
            critical_hard_failure = True

    # --- Soft assertions (skip if critical hard failure or hard_only mode) ---
    soft_scores: list[tuple[float, float]] = []  # (score, weight)
    soft_passed_all = True

    if not critical_hard_failure and not hard_only:
        corpus_snippets = _corpus_snippets_for(summary.citations)
        extra = {"corpus_snippets": corpus_snippets}

        for assertion in case.soft_assertions:
            metric_cls = METRIC_REGISTRY.get(assertion.metric)
            if metric_cls is None:
                assertion_results.append(
                    AssertionResult(
                        check=f"soft[{assertion.metric}]",
                        passed=False,
                        reason=f"Unknown metric '{assertion.metric}'.",
                        score=0.0,
                        critical=False,
                    )
                )
                soft_passed_all = False
                continue

            result = metric_cls().score(case, assertion, summary, extra)
            assertion_results.append(result)
            score = result.score if result.score is not None else (1.0 if result.passed else 0.0)
            soft_scores.append((score, assertion.weight))
            if not result.passed:
                soft_passed_all = False

    # --- Compute overall soft_score ---
    soft_score: float | None = None
    if soft_scores:
        total_weight = sum(w for _, w in soft_scores)
        soft_score = sum(s * w for s, w in soft_scores) / total_weight if total_weight else 0.0

    # --- Overall case pass/fail ---
    if critical_hard_failure:
        passed = False
        failure_reason = next(
            (r.reason for r in assertion_results if not r.passed and r.critical),
            "Critical hard assertion failed.",
        )
    elif not soft_passed_all:
        passed = False
        failure_reason = next(
            (r.reason for r in assertion_results if not r.passed and r.score is not None),
            "Soft assertion failed.",
        )
    else:
        passed = True
        failure_reason = None

    return CaseRepeatResult(
        case_id=case.id,
        repeat_idx=repeat_idx,
        trace_path=trace_path,
        summary=summary,
        assertion_results=assertion_results,
        passed=passed,
        failure_reason=failure_reason,
        soft_score=soft_score,
    )
