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

# ---- Phase 2: table-accuracy gate (needs a live parser endpoint) ----
# Runs every table in spike/tables/ through the PLATFORM parsing path and
# grades per cell. Run after any prompt/model/parsing change (prompt is code).
eval-tables:
	python tests/eval/tables/run_eval.py

lint:
	ruff check tablerag tests spike
