# Correctness Rubric

## Task
Evaluate whether the agent's answer is factually correct and well-grounded in the provided corpus snippets.

## Scoring Guide

| Score | Meaning |
|-------|---------|
| 1.0   | Answer is completely correct. Every factual claim can be traced to a corpus snippet. No errors or omissions. |
| 0.8   | Answer is mostly correct. Minor omission or imprecision that does not mislead the user. |
| 0.6   | Answer is partially correct. Contains at least one factual error or significant omission, but the core answer is not wrong. |
| 0.4   | Answer has more wrong than right. Misleading or significantly incomplete. |
| 0.2   | Answer is largely incorrect. Claims are not supported by, or contradict, the corpus. |
| 0.0   | Answer is completely wrong, fabricated, or refuses to answer when the corpus clearly contains the information. |

## Rules

1. **Only use corpus snippets as ground truth.** Do not rely on your own knowledge of the real world.
2. **An answer that correctly says "the corpus does not contain this information" scores 1.0** if the corpus snippets indeed do not contain it.
3. **An answer that guesses or invents data not in the corpus scores ≤ 0.2**, even if the invented data happens to be true.
4. **Partial credit** applies when the answer is directionally correct but missing key qualifying details (e.g., unit labels, dates, conditions).
5. **Ambiguous cases** (two corpus sources that conflict): reward the agent for disclosing the conflict rather than picking one silently.

## Output
Call submit_verdict with:
- score: float 0.0–1.0 per the guide above
- passed: true if score >= threshold (threshold is stated in the evaluation prompt)
- rationale: one paragraph citing specific evidence from the corpus snippets
- confidence: high/medium/low based on how clearly the corpus supports your verdict
