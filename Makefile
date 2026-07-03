.PHONY: up down logs test test-unit test-integration spike-tables spike-run spike-grade eval-tables lint

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api worker

test: test-unit

test-unit:
	pytest tests/unit -q

test-integration:
	RUN_INTEGRATION=1 pytest tests/integration -q -m integration

# ---- Phase 0 spike (run on the deployment machine) ----------
# Generate the synthetic table test set (images + ground truth)
spike-tables:
	python spike/make_test_tables.py

# Parse every table in spike/tables/ with the configured parser VLM
spike-run:
	python spike/parse_table.py --all

# Grade parsed output against ground truth, cell by cell
spike-grade:
	python spike/grade.py

# ---- Phase 2+ (placeholder targets, wired later) -------------
eval-tables:
	@echo "eval-tables arrives in Phase 2 (tests/eval/tables). For Phase 0 use: make spike-grade"

lint:
	ruff check tablerag tests spike
