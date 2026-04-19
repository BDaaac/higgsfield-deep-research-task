"""Plugin base class and registry for eval metrics."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from eval.models import AssertionResult, SoftAssertion, TraceSummary, TestCase

METRIC_REGISTRY: dict[str, type["BaseMetric"]] = {}


def register_metric(cls: type["BaseMetric"]) -> type["BaseMetric"]:
    METRIC_REGISTRY[cls.name] = cls
    return cls


class BaseMetric(ABC):
    """Each subclass handles one soft assertion metric.

    Subclasses must set `name` (matches SoftAssertion.metric field)
    and implement `score()`.
    """

    name: str

    @abstractmethod
    def score(
        self,
        case: TestCase,
        assertion: SoftAssertion,
        summary: TraceSummary,
        extra: dict[str, Any],
    ) -> AssertionResult:
        """Return an AssertionResult with a 0–1 score and passed flag."""
        ...
