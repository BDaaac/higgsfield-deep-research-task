.PHONY: setup test score-fixtures validate-judge view-fixtures diff-fixtures help

# One-command setup
setup:
	pip install -r requirements.txt
	pip install -r requirements-eval.txt

# Run full suite against the agent (requires ANTHROPIC_API_KEY)
test:
	python main.py run --cases cases/ --concurrency 5 --repeats 1

# Re-score committed fixture traces without calling the agent
score-fixtures:
	python main.py score --traces fixtures/run_fixture01 --cases cases/

# Validate the LLM judge against hand-labeled cases
validate-judge:
	python scripts/validate_judge.py

# Open HTML viewer for committed fixture run
view-fixtures:
	python main.py view --run-id fixture01

# Diff fixture01 vs latest run report
diff-fixtures:
	python main.py diff --prev reports/fixture01.json --curr reports/latest.json

help:
	@echo "Targets:"
	@echo "  setup           Install dependencies"
	@echo "  test            Run full eval suite (needs ANTHROPIC_API_KEY)"
	@echo "  score-fixtures  Re-score committed traces (no API key needed)"
	@echo "  validate-judge  Run judge validation against hand-labeled cases"
	@echo "  view-fixtures   Open HTML trace viewer for fixture01"
	@echo "  diff-fixtures   Diff fixture01 vs latest run"
