"""Tool efficiency metric: LLM-judge evaluates over- or under-use of tools."""

from __future__ import annotations

from typing import Any

from eval.models import AssertionResult, SoftAssertion, TestCase, TraceSummary
from metrics.base import BaseMetric, register_metric


@register_metric
class ToolEfficiencyMetric(BaseMetric):
    name = "tool_efficiency"

    def score(
        self,
        case: TestCase,
        assertion: SoftAssertion,
        summary: TraceSummary,
        extra: dict[str, Any],
    ) -> AssertionResult:
        from eval.judge import call_judge

        tool_summary = _format_tool_calls(summary.tool_calls)

        verdict = call_judge(
            rubric_path=assertion.rubric,
            question=case.input,
            answer=summary.final_answer or "",
            citations=summary.citations,
            corpus_snippets=[f"Tool calls made:\n{tool_summary}"],
            threshold=assertion.threshold,
        )
        return AssertionResult(
            check=f"tool_efficiency[{assertion.metric}]",
            passed=verdict.passed,
            reason=verdict.rationale,
            score=verdict.score,
            critical=False,
        )


def _format_tool_calls(tool_calls: list[dict]) -> str:
    lines = []
    for i, tc in enumerate(tool_calls, 1):
        name = tc.get("name", "?")
        args = tc.get("args", {})
        lines.append(f"{i}. {name}({args})")
    return "\n".join(lines) if lines else "(no tool calls)"
