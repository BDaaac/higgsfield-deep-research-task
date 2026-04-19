"""Data contracts for the evaluation framework.

Traces live on disk as separate JSON files.
RunReport holds only a path reference + compact summary per case.
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Test-case schema (loaded from YAML)
# ---------------------------------------------------------------------------


class HardAssertion(BaseModel):
    check: str
    params: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    critical: bool = True  # False = log warning only, don't fail case


class SoftAssertion(BaseModel):
    metric: str            # key in METRIC_REGISTRY
    rubric: str            # path to .md rubric file
    threshold: float = 0.7
    weight: float = 1.0
    description: str = ""


class TestCase(BaseModel):
    id: str
    input: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    hard_assertions: list[HardAssertion] = Field(default_factory=list)
    soft_assertions: list[SoftAssertion] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-assertion result
# ---------------------------------------------------------------------------


class AssertionResult(BaseModel):
    check: str
    passed: bool
    reason: str
    score: float | None = None   # 0-1 for soft assertions; None for hard
    critical: bool = True


# ---------------------------------------------------------------------------
# Compact trace summary (what goes inside the report)
# ---------------------------------------------------------------------------


class TraceSummary(BaseModel):
    """Lightweight snapshot extracted from a full trace for the report."""
    run_id: str
    stopped_reason: str
    final_answer: str | None
    citations: list[str]
    total_tokens: dict[str, int]
    cost_usd: float
    wall_time_ms: int
    tool_calls: list[dict[str, Any]]  # [{name, args}] for hard assertion checks
    error: str | None = None


# ---------------------------------------------------------------------------
# Single repeat result
# ---------------------------------------------------------------------------


class CaseRepeatResult(BaseModel):
    case_id: str
    repeat_idx: int
    trace_path: str          # relative path: traces/{run_id}/{case_id}/repeat_{i}.json
    summary: TraceSummary
    assertion_results: list[AssertionResult]
    passed: bool
    failure_reason: str | None = None
    # Soft score: weighted average of soft assertions (None if no soft assertions)
    soft_score: float | None = None


# ---------------------------------------------------------------------------
# Stats helper (for flakiness reporting)
# ---------------------------------------------------------------------------


class Stats(BaseModel):
    mean: float
    stddev: float
    minimum: float
    maximum: float

    @classmethod
    def from_values(cls, values: list[float]) -> "Stats":
        if not values:
            return cls(mean=0.0, stddev=0.0, minimum=0.0, maximum=0.0)
        m = statistics.mean(values)
        std = statistics.stdev(values) if len(values) > 1 else 0.0
        return cls(mean=m, stddev=std, minimum=min(values), maximum=max(values))


# ---------------------------------------------------------------------------
# Flakiness summary (when repeats > 1)
# ---------------------------------------------------------------------------


class CaseFlakiness(BaseModel):
    case_id: str
    k_passed: int
    n_total: int
    pass_rate: float
    judge_score: Stats
    latency_ms: Stats
    tool_count: Stats
    cost_usd: Stats


# ---------------------------------------------------------------------------
# Diff report
# ---------------------------------------------------------------------------


class CaseDelta(BaseModel):
    case_id: str
    prev_passed: bool | None
    curr_passed: bool | None
    latency_delta_pct: float | None = None   # positive = slower
    cost_delta_pct: float | None = None
    tool_calls_delta: float | None = None
    judge_score_delta: float | None = None


class DiffReport(BaseModel):
    prev_run_id: str
    regressions: list[str]    # case_id: pass → fail
    improvements: list[str]   # case_id: fail → pass
    deltas: list[CaseDelta]
    latency_regression_cases: list[str]   # latency worsened > 20%
    cost_regression_cases: list[str]      # cost worsened > 20%


# ---------------------------------------------------------------------------
# Aggregate run report
# ---------------------------------------------------------------------------


class RunReport(BaseModel):
    run_id: str
    timestamp: str
    model: str
    repeats: int
    pass_mode: Literal["strict", "soft"]   # strict=K==N, soft=K/N>=threshold
    pass_threshold: float = 1.0            # used only in soft mode

    total_cases: int
    passed: int
    failed: int
    pass_rate: float

    total_cost_usd: float
    p50_latency_ms: float
    p95_latency_ms: float
    mean_tool_calls: float

    cases: list[CaseRepeatResult]          # all individual repeat results
    flakiness: list[CaseFlakiness]         # populated when repeats > 1
    diff: DiffReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


# ---------------------------------------------------------------------------
# Judge verdict (returned by eval/judge.py)
# ---------------------------------------------------------------------------


class JudgeVerdict(BaseModel):
    score: float                              # 0.0–1.0
    passed: bool
    rationale: str
    confidence: Literal["high", "medium", "low"]
