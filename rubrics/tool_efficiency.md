# Tool Efficiency Rubric

## Task
Evaluate whether the agent used its tools efficiently: no unnecessary calls, no skipped required steps.

## Scoring Guide

| Score | Meaning |
|-------|---------|
| 1.0   | Optimal tool use. Agent searched, fetched only relevant pages, and stopped when it had sufficient information. |
| 0.8   | Mostly efficient. One redundant call (e.g., fetched an irrelevant page) but core flow was correct. |
| 0.6   | Somewhat inefficient. Multiple redundant fetches, or fetched pages unrelated to the query. |
| 0.4   | Inefficient. Many wasted calls, or skipped a required step (e.g., answered without fetching). |
| 0.2   | Very inefficient. Agent looped, fetched the same page multiple times, or skipped both search and fetch. |
| 0.0   | No meaningful tool use, or tool use was entirely counter-productive. |

## Rules

1. **Required sequence is: web_search → fetch_url → (optionally extract_quotes) → finish.**
   Skipping search or fetch when information was needed scores ≤ 0.4.
2. **Fetching a page that was never cited** in the final answer is a minor inefficiency (−0.1).
3. **Searching for the same query twice** without new information is redundant (−0.1 per occurrence).
4. **Using extract_quotes on a clearly small page** where the full text was already fetched is minor over-use.
5. **For ambiguous prompts**, fetching multiple sources to check for conflicts is efficient and correct behavior.

## Output
Call submit_verdict with:
- score: float 0.0–1.0
- passed: true if score >= threshold
- rationale: list each tool call, note whether it was necessary, and summarize the overall efficiency verdict
- confidence: high/medium/low
