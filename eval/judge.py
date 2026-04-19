"""LLM-as-judge using claude-3-5-haiku-20241022 with structured output via tool_use.

Design notes:
- Judge is claude-3-5-haiku ($0.80/$4 per MTok) — cheaper than the agent under
  test (claude-haiku-4-5, $1/$5) and a different model generation, which partially
  mitigates self-preference bias. Override via EVAL_JUDGE_MODEL env var.
- Structured output enforced via Anthropic tool_use — no third-party libraries.
- Rubric is per-metric (checked-in .md files), never a generic prompt.
- Known failure modes documented in README: position bias, self-preference,
  injection through agent output, rubric ambiguity.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from anthropic import Anthropic

from eval.models import JudgeVerdict

JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "claude-3-5-haiku-20241022")

_VERDICT_TOOL = {
    "name": "submit_verdict",
    "description": "Submit your evaluation verdict as structured JSON.",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {
                "type": "number",
                "description": "Float 0.0–1.0. 1.0 = fully passes rubric.",
            },
            "passed": {
                "type": "boolean",
                "description": "True if score >= threshold.",
            },
            "rationale": {
                "type": "string",
                "description": "One-paragraph explanation citing specific evidence.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Your confidence in this verdict.",
            },
        },
        "required": ["score", "passed", "rationale", "confidence"],
    },
}

_JUDGE_SYSTEM = (
    "You are an impartial evaluation judge for an AI research assistant. "
    "You will be given a rubric, a user question, the agent's answer, and optionally "
    "ground-truth snippets from the knowledge corpus. "
    "Apply the rubric strictly and call submit_verdict with your structured verdict. "
    "Do not be lenient. Do not consider information outside the provided corpus snippets."
)


@lru_cache(maxsize=64)
def _load_rubric(rubric_path: str) -> str:
    path = Path(rubric_path)
    if not path.is_absolute():
        # Resolve relative to repo root (parent of eval/)
        path = Path(__file__).parent.parent / rubric_path
    return path.read_text(encoding="utf-8")


def call_judge(
    rubric_path: str,
    question: str,
    answer: str,
    citations: list[str],
    corpus_snippets: list[str],
    threshold: float = 0.7,
) -> JudgeVerdict:
    """Call the LLM judge and return a structured verdict."""
    rubric = _load_rubric(rubric_path)
    citations_text = "\n".join(f"- {c}" for c in citations) or "(none)"
    snippets_text = (
        "\n\n---\n\n".join(corpus_snippets)
        if corpus_snippets
        else "(no corpus snippets provided)"
    )

    user_message = f"""## Evaluation Rubric
{rubric}

## User Question
{question}

## Agent Answer
{answer}

## Agent Citations
{citations_text}

## Corpus Ground-Truth Snippets
{snippets_text}

---
Apply the rubric above. Call submit_verdict with score (0.0–1.0), passed (score >= {threshold}), rationale, and confidence."""

    client = Anthropic()
    resp = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=512,
        system=_JUDGE_SYSTEM,
        tools=[_VERDICT_TOOL],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": user_message}],
    )

    for block in resp.content:
        if block.type == "tool_use" and block.name == "submit_verdict":
            inp = block.input
            return JudgeVerdict(
                score=float(inp["score"]),
                passed=bool(inp["passed"]),
                rationale=str(inp["rationale"]),
                confidence=inp["confidence"],
            )

    # Fallback if judge didn't call the tool (shouldn't happen with tool_choice=any).
    return JudgeVerdict(
        score=0.0,
        passed=False,
        rationale="Judge did not return a structured verdict.",
        confidence="low",
    )
