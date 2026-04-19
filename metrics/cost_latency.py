"""Cost & latency metric: hard budget checks (no LLM call needed)."""

from __future__ import annotations

from typing import Any

from eval.models import AssertionResult, SoftAssertion, TestCase, TraceSummary
from metrics.base import BaseMetric, register_metric


@register_metric
class CostLatencyMetric(BaseMetric):
    name = "cost_latency"

    def score(
        self,
        case: TestCase,
        assertion: SoftAssertion,
        summary: TraceSummary,
        extra: dict[str, Any],
    ) -> AssertionResult:
        max_cost_usd: float = extra.get("max_cost_usd", 0.05)
        max_latency_ms: int = extra.get("max_latency_ms", 30_000)

        violations = []
        if summary.cost_usd > max_cost_usd:
            violations.append(
                f"cost ${summary.cost_usd:.4f} exceeds budget ${max_cost_usd:.4f}"
            )
        if summary.wall_time_ms > max_latency_ms:
            violations.append(
                f"latency {summary.wall_time_ms}ms exceeds budget {max_latency_ms}ms"
            )

        passed = len(violations) == 0
        score = 1.0 if passed else max(0.0, 1.0 - 0.5 * len(violations))
        reason = "Within budget." if passed else "; ".join(violations)

        return AssertionResult(
            check="cost_latency",
            passed=passed,
            reason=reason,
            score=score,
            critical=False,
        )
