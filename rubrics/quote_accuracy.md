# Quote Accuracy Rubric

## Task
Evaluate whether quotes attributed to corpus sources appear verbatim (or near-verbatim) in those sources.
This rubric specifically targets the extract_quotes tool, which is known to occasionally paraphrase.

## Scoring Guide

| Score | Meaning |
|-------|---------|
| 1.0   | All quotes appear verbatim or with only trivial whitespace/punctuation differences in the cited source. |
| 0.8   | Most quotes are verbatim; at most one quote is lightly paraphrased but semantically identical. |
| 0.6   | Some quotes are paraphrased. The meaning is preserved but the wording differs significantly. |
| 0.3   | Most quotes are paraphrased or the agent "quotes" text that cannot be found in the cited source. |
| 0.0   | Agent presents invented text as direct quotes, or all quotes are fabricated. |

## Rules

1. **Verbatim means the exact words appear in the corpus snippet**, not a summary or rewording.
2. **Minor normalization is acceptable**: stripping leading/trailing whitespace, normalizing line breaks.
3. **If the agent doesn't claim to quote** (uses "according to" without quote marks), apply the correctness rubric instead.
4. **If the cited source was not provided** in the corpus snippets, note this and score 0.0 for those quotes.
5. **Partial credit** when some quotes are accurate but others are paraphrased.

## How to check
For each quote in the answer:
- Search for it (or a close variant) in the corpus snippets provided.
- Mark it as: VERBATIM / PARAPHRASED / NOT FOUND.
- Score based on the ratio of VERBATIM to total quotes.

## Output
Call submit_verdict with:
- score: float 0.0–1.0
- passed: true if score >= threshold
- rationale: list each quote, classify it as VERBATIM/PARAPHRASED/NOT FOUND, and explain your scoring
- confidence: high/medium/low
