#!/usr/bin/env python3
"""Evaluation framework CLI for Deep Research Lite.

Commands:
  run    -- Run the agent against test cases and produce a report + HTML viewer.
  score  -- Re-score saved traces without calling the agent.
  diff   -- Compare two run reports.
  view   -- Open the HTML viewer for a run.

Examples:
  python main.py run --cases cases/ --concurrency 5
  python main.py run --case cases/01_happy_r1_payload.yaml
  python main.py run --cases cases/ --repeats 3 --pass-mode soft --pass-threshold 0.6
  python main.py score --traces traces/abc123/ --cases cases/
  python main.py diff --prev reports/run_abc.json --curr reports/run_xyz.json
  python main.py view --run-id abc123
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path


def cmd_run(args: argparse.Namespace) -> None:
    from eval.reporter import build_report, print_report, save_report
    from eval.runner import run_suite_sync
    from eval.viewer import build_viewer

    cases_dir = Path(args.cases) if args.cases else Path("cases")
    single_case = Path(args.case) if args.case else None
    prev_report_path = Path("reports/latest.json") if Path("reports/latest.json").exists() else None

    print(f"Running eval suite (concurrency={args.concurrency}, repeats={args.repeats})...")

    run_id, results = run_suite_sync(
        cases_dir=cases_dir,
        concurrency=args.concurrency,
        repeats=args.repeats,
        model=args.model,
        single_case_path=single_case,
    )

    report = build_report(
        run_id=run_id,
        results=results,
        repeats=args.repeats,
        model=args.model,
        pass_mode=args.pass_mode,
        pass_threshold=args.pass_threshold,
        prev_report_path=prev_report_path,
    )

    report_path = save_report(report)
    print_report(report)
    print(f"\nReport saved: {report_path}")

    viewer_path = build_viewer(report, run_id)
    print(f"Viewer  saved: {viewer_path}")

    if args.open:
        webbrowser.open(viewer_path.resolve().as_uri())


def cmd_score(args: argparse.Namespace) -> None:
    from eval.reporter import build_report, print_report, save_report
    from eval.runner import rescore_from_traces
    from eval.viewer import build_viewer

    traces_dir = Path(args.traces)
    cases_dir = Path(args.cases) if args.cases else Path("cases")

    print(f"Re-scoring traces from {traces_dir} (hard_only={args.hard_only})...")
    results = rescore_from_traces(traces_dir, cases_dir, hard_only=args.hard_only)

    if not results:
        print("No traces found.", file=sys.stderr)
        sys.exit(1)

    # Infer run_id from the traces directory name
    run_id = traces_dir.name if traces_dir.name != "traces" else "rescore"

    report = build_report(
        run_id=f"rescore_{run_id}",
        results=results,
        repeats=1,
        model="(rescore)",
        pass_mode="strict",
        pass_threshold=1.0,
    )
    report_path = save_report(report)
    print_report(report)
    print(f"\nReport saved: {report_path}")
    viewer_path = build_viewer(report, report.run_id)
    print(f"Viewer  saved: {viewer_path}")


def cmd_diff(args: argparse.Namespace) -> None:
    from eval.reporter import compute_diff

    prev_path = Path(args.prev)
    curr_path = Path(args.curr)

    with prev_path.open() as f:
        prev = json.load(f)
    with curr_path.open() as f:
        curr = json.load(f)

    # Reconstruct results-by-case from curr report cases list
    from collections import defaultdict
    from eval.models import CaseRepeatResult

    by_case: dict[str, list] = defaultdict(list)
    for c in curr.get("cases", []):
        by_case[c["case_id"]].append(c)

    diff = compute_diff(prev, dict(by_case), "strict", 1.0)

    print(f"\nDiff: {prev['run_id']} → {curr['run_id']}")
    print(f"  Regressions  : {diff.regressions or ['none']}")
    print(f"  Improvements : {diff.improvements or ['none']}")
    print(f"  Latency +20% : {diff.latency_regression_cases or ['none']}")
    print(f"  Cost +20%    : {diff.cost_regression_cases or ['none']}")

    for d in diff.deltas:
        if d.latency_delta_pct is not None or d.cost_delta_pct is not None:
            print(
                f"  {d.case_id}: "
                f"lat={_fmt_pct(d.latency_delta_pct)} "
                f"cost={_fmt_pct(d.cost_delta_pct)} "
                f"tools={_fmt_delta(d.tool_calls_delta)} "
                f"judge={_fmt_delta(d.judge_score_delta)}"
            )


def cmd_view(args: argparse.Namespace) -> None:
    run_id = args.run_id
    path = Path("reports") / f"view_{run_id}.html"
    if not path.exists():
        print(f"Viewer not found: {path}", file=sys.stderr)
        sys.exit(1)
    webbrowser.open(path.resolve().as_uri())
    print(f"Opened: {path}")


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "n/a"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v * 100:.1f}%"


def _fmt_delta(v: float | None) -> str:
    if v is None:
        return "n/a"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.3f}"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Deep Research Lite — Evaluation Framework",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- run ---
    p_run = sub.add_parser("run", help="Run the eval suite against the agent")
    p_run.add_argument("--cases", default="cases/", help="Directory of YAML test cases")
    p_run.add_argument("--case", default=None, help="Run a single YAML case")
    p_run.add_argument("--concurrency", type=int, default=5, help="Max parallel cases")
    p_run.add_argument("--repeats", type=int, default=1, help="Repeats per case (flakiness)")
    p_run.add_argument("--model", default="claude-haiku-4-5", help="Agent model")
    p_run.add_argument(
        "--pass-mode", choices=["strict", "soft"], default="strict",
        help="strict=K==N, soft=K/N>=threshold"
    )
    p_run.add_argument("--pass-threshold", type=float, default=1.0,
                       help="Pass threshold for soft mode")
    p_run.add_argument("--open", action="store_true", help="Open viewer after run")

    # --- score ---
    p_score = sub.add_parser("score", help="Re-score saved traces without calling the agent")
    p_score.add_argument("--traces", required=True, help="Path to traces/{run_id}/ directory")
    p_score.add_argument("--cases", default="cases/", help="Directory of YAML test cases")
    p_score.add_argument("--hard-only", action="store_true",
                         help="Skip soft (LLM-judge) assertions — useful for offline re-score")

    # --- diff ---
    p_diff = sub.add_parser("diff", help="Diff two run reports")
    p_diff.add_argument("--prev", required=True, help="Path to previous report JSON")
    p_diff.add_argument("--curr", required=True, help="Path to current report JSON")

    # --- view ---
    p_view = sub.add_parser("view", help="Open HTML viewer for a run")
    p_view.add_argument("--run-id", required=True, help="Run ID")

    args = parser.parse_args()

    dispatch = {
        "run": cmd_run,
        "score": cmd_score,
        "diff": cmd_diff,
        "view": cmd_view,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
