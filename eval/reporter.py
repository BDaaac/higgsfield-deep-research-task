"""Build RunReport and compute diffs against a previous run."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from eval.models import (
    CaseDelta,
    CaseFlakiness,
    CaseRepeatResult,
    DiffReport,
    RunReport,
    Stats,
)

_REPORTS_DIR = Path("reports")
_LATENCY_REGRESSION_THRESHOLD = 0.20   # 20% slower = regression
_COST_REGRESSION_THRESHOLD = 0.20


# ---------------------------------------------------------------------------
# Pass / fail aggregation for repeats
# ---------------------------------------------------------------------------


def _case_passes(
    results: list[Any],   # CaseRepeatResult objects or dicts
    mode: Literal["strict", "soft"],
    threshold: float,
) -> bool:
    def _passed(r: Any) -> bool:
        return r.get("passed", False) if isinstance(r, dict) else r.passed

    k = sum(1 for r in results if _passed(r))
    n = len(results)
    if mode == "strict":
        return k == n
    return (k / n) >= threshold if n else False


# ---------------------------------------------------------------------------
# Flakiness stats
# ---------------------------------------------------------------------------


def _build_flakiness(
    case_id: str,
    results: list[CaseRepeatResult],
) -> CaseFlakiness:
    k = sum(1 for r in results if r.passed)
    n = len(results)
    judge_scores = [
        r.soft_score for r in results if r.soft_score is not None
    ]
    latencies = [r.summary.wall_time_ms for r in results]
    tool_counts = [len(r.summary.tool_calls) for r in results]
    costs = [r.summary.cost_usd for r in results]

    return CaseFlakiness(
        case_id=case_id,
        k_passed=k,
        n_total=n,
        pass_rate=k / n if n else 0.0,
        judge_score=Stats.from_values([float(s) for s in judge_scores]),
        latency_ms=Stats.from_values([float(v) for v in latencies]),
        tool_count=Stats.from_values([float(v) for v in tool_counts]),
        cost_usd=Stats.from_values([float(v) for v in costs]),
    )


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------


def _safe_delta_pct(prev: float, curr: float) -> float | None:
    if prev == 0:
        return None
    return (curr - prev) / prev


def _case_as_dict(c: Any) -> dict[str, Any]:
    """Normalise a case result that may be a Pydantic object or a plain dict."""
    if isinstance(c, dict):
        return c
    return c.model_dump()


def compute_diff(
    prev_report: dict[str, Any],
    curr_results_by_case: dict[str, list[Any]],   # list of CaseRepeatResult OR dict
    pass_mode: str,
    pass_threshold: float,
) -> DiffReport:
    prev_run_id = prev_report.get("run_id", "unknown")
    prev_cases: dict[str, list[dict[str, Any]]] = {}
    for c in prev_report.get("cases", []):
        case_id = c.get("case_id")
        if case_id:
            prev_cases.setdefault(case_id, []).append(c)

    regressions: list[str] = []
    improvements: list[str] = []
    deltas: list[CaseDelta] = []
    latency_regressions: list[str] = []
    cost_regressions: list[str] = []

    for case_id, curr_raw in curr_results_by_case.items():
        # Normalise to dicts so both Pydantic objects and raw JSON work.
        curr_dicts = [_case_as_dict(r) for r in curr_raw]

        curr_passed_list = [d.get("passed", False) for d in curr_dicts]
        k = sum(curr_passed_list)
        n = len(curr_passed_list)
        if pass_mode == "strict":
            curr_passed = k == n
        else:
            curr_passed = (k / n) >= pass_threshold if n else False

        def _summary_val(d: dict, key: str, default: float = 0.0) -> float:
            return float(d.get("summary", {}).get(key, default))

        curr_latency = statistics.mean(_summary_val(d, "wall_time_ms") for d in curr_dicts)
        curr_cost = statistics.mean(_summary_val(d, "cost_usd") for d in curr_dicts)
        curr_tools = statistics.mean(
            len(d.get("summary", {}).get("tool_calls", [])) for d in curr_dicts
        )
        curr_judge_vals = [
            d["soft_score"] for d in curr_dicts if d.get("soft_score") is not None
        ]
        curr_judge = statistics.mean(curr_judge_vals) if curr_judge_vals else None

        prev_list = prev_cases.get(case_id, [])
        if not prev_list:
            deltas.append(CaseDelta(case_id=case_id, prev_passed=None, curr_passed=curr_passed))
            continue

        prev_passed = all(c.get("passed", False) for c in prev_list)
        prev_latency = statistics.mean(_summary_val(c, "wall_time_ms") for c in prev_list)
        prev_cost = statistics.mean(_summary_val(c, "cost_usd") for c in prev_list)
        prev_tools = statistics.mean(
            len(c.get("summary", {}).get("tool_calls", [])) for c in prev_list
        )
        prev_judge_vals = [c["soft_score"] for c in prev_list if c.get("soft_score") is not None]
        prev_judge = statistics.mean(prev_judge_vals) if prev_judge_vals else None

        if prev_passed and not curr_passed:
            regressions.append(case_id)
        elif not prev_passed and curr_passed:
            improvements.append(case_id)

        lat_delta = _safe_delta_pct(prev_latency, curr_latency)
        cost_delta = _safe_delta_pct(prev_cost, curr_cost)

        if lat_delta is not None and lat_delta > _LATENCY_REGRESSION_THRESHOLD:
            latency_regressions.append(case_id)
        if cost_delta is not None and cost_delta > _COST_REGRESSION_THRESHOLD:
            cost_regressions.append(case_id)

        deltas.append(
            CaseDelta(
                case_id=case_id,
                prev_passed=prev_passed,
                curr_passed=curr_passed,
                latency_delta_pct=lat_delta,
                cost_delta_pct=cost_delta,
                tool_calls_delta=curr_tools - prev_tools,
                judge_score_delta=(
                    (curr_judge - prev_judge)
                    if curr_judge is not None and prev_judge is not None
                    else None
                ),
            )
        )

    return DiffReport(
        prev_run_id=prev_run_id,
        regressions=regressions,
        improvements=improvements,
        deltas=deltas,
        latency_regression_cases=latency_regressions,
        cost_regression_cases=cost_regressions,
    )


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------


def build_report(
    run_id: str,
    results: list[CaseRepeatResult],
    repeats: int,
    model: str,
    pass_mode: Literal["strict", "soft"] = "strict",
    pass_threshold: float = 1.0,
    prev_report_path: Path | None = None,
) -> RunReport:
    # Group results by case_id
    by_case: dict[str, list[CaseRepeatResult]] = defaultdict(list)
    for r in results:
        by_case[r.case_id].append(r)

    # Aggregate pass/fail per case
    case_passed: dict[str, bool] = {
        cid: _case_passes(rs, pass_mode, pass_threshold)
        for cid, rs in by_case.items()
    }
    total_cases = len(by_case)
    passed = sum(1 for v in case_passed.values() if v)

    all_latencies = [r.summary.wall_time_ms for r in results]
    all_latencies_sorted = sorted(all_latencies)
    p50 = _percentile(all_latencies_sorted, 0.50)
    p95 = _percentile(all_latencies_sorted, 0.95)

    total_cost = sum(r.summary.cost_usd for r in results)
    mean_tools = statistics.mean(len(r.summary.tool_calls) for r in results) if results else 0.0

    flakiness = []
    if repeats > 1:
        for cid, rs in by_case.items():
            flakiness.append(_build_flakiness(cid, rs))

    # Diff
    diff: DiffReport | None = None
    if prev_report_path and prev_report_path.exists():
        with prev_report_path.open(encoding="utf-8") as f:
            prev_report = json.load(f)
        diff = compute_diff(prev_report, dict(by_case), pass_mode, pass_threshold)

    return RunReport(
        run_id=run_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=model,
        repeats=repeats,
        pass_mode=pass_mode,
        pass_threshold=pass_threshold,
        total_cases=total_cases,
        passed=passed,
        failed=total_cases - passed,
        pass_rate=passed / total_cases if total_cases else 0.0,
        total_cost_usd=total_cost,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        mean_tool_calls=mean_tools,
        cases=results,
        flakiness=flakiness,
        diff=diff,
    )


def save_report(report: RunReport) -> Path:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _REPORTS_DIR / f"{report.run_id}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    # Update latest.json
    latest = _REPORTS_DIR / "latest.json"
    latest.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    return path


def print_report(report: RunReport) -> None:
    """Print a human-readable summary to stdout."""
    _sep = "-" * 60
    print(_sep)
    print(f"Run ID  : {report.run_id}")
    print(f"Model   : {report.model}")
    print(f"Time    : {report.timestamp}")
    print(_sep)
    print(
        f"Results : {report.passed}/{report.total_cases} passed "
        f"({report.pass_rate * 100:.1f}%)"
    )
    print(f"Cost    : ${report.total_cost_usd:.4f}")
    print(f"Latency : p50={report.p50_latency_ms}ms  p95={report.p95_latency_ms}ms")
    print(f"Tools   : {report.mean_tool_calls:.1f} avg per case")
    print(_sep)

    for case_result in report.cases:
        status = "PASS" if case_result.passed else "FAIL"
        line = f"  {status} {case_result.case_id}"
        if not case_result.passed and case_result.failure_reason:
            reason = case_result.failure_reason[:80]
            line += f"\n      ? {reason}"
        print(line)

    if report.diff:
        d = report.diff
        print(_sep)
        print(f"Diff vs {d.prev_run_id}:")
        if d.regressions:
            print(f"  ? Regressions  : {', '.join(d.regressions)}")
        if d.improvements:
            print(f"  ? Improvements : {', '.join(d.improvements)}")
        if d.latency_regression_cases:
            print(f"  ??  Latency +20% : {', '.join(d.latency_regression_cases)}")
        if d.cost_regression_cases:
            print(f"  ??  Cost +20%    : {', '.join(d.cost_regression_cases)}")
        if not any([d.regressions, d.improvements, d.latency_regression_cases, d.cost_regression_cases]):
            print("  No regressions detected.")

    if report.flakiness:
        print(_sep)
        print("Flakiness:")
        for fl in report.flakiness:
            print(
                f"  {fl.case_id}: {fl.k_passed}/{fl.n_total} "
                f"(score ?={fl.judge_score.mean:.2f} ?={fl.judge_score.stddev:.2f})"
            )
    print(_sep)


def _percentile(sorted_vals: list[int], p: float) -> int:
    if not sorted_vals:
        return 0
    idx = int(len(sorted_vals) * p)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]