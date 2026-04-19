"""Correctness metric: LLM-judge checks factual accuracy against corpus."""

from __future__ import annotations

from typing import Any

from eval.models import AssertionResult, SoftAssertion, TestCase, TraceSummary
from metrics.base import BaseMetric, register_metric


@register_metric
class CorrectnessMetric(BaseMetric):
    name = "correctness"

    def score(
        self,
        case: TestCase,
        assertion: SoftAssertion,
        summary: TraceSummary,
        extra: dict[str, Any],
    ) -> AssertionResult:
        from eval.judge import call_judge

        verdict = call_judge(
            rubric_path=assertion.rubric,
            question=case.input,
            answer=summary.final_answer or "",
            citations=summary.citations,
            corpus_snippets=extra.get("corpus_snippets", []),
            threshold=assertion.threshold,
        )
        return AssertionResult(
            check=f"correctness[{assertion.metric}]",
            passed=verdict.passed,
            reason=verdict.rationale,
            score=verdict.score,
            critical=False,
        )
