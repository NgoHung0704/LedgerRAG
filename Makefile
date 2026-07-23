.PHONY: up down logs test test-unit test-integration spike-tables spike-run spike-grade eval-tables eval-qa eval-routing eval-followup lint

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

# ---- Phase 3: confidence-flag gate (needs a live parser endpoint) ----
# Clean tables must not be flagged (<=10%), corrupted ones must be (>=90%).
eval-flags:
	python spike/make_hard_tables.py
	python tests/eval/tables/run_flag_eval.py

# ---- Phase 4: answer-quality gate (needs the full live stack) --------
# Usage: make eval-qa KB=<kb_id>   (questions: tests/eval/qa/questions.jsonl)
eval-qa:
	python tests/eval/qa/run_eval_qa.py --kb $(KB)

# ---- Phase 5: routing gate (needs several KBs; scores router, not answers) --
# Split the 3 sample PDFs into 3 KBs whose names contain CETIAT / Avenant /
# Glossaire, then auto-route each question via POST /api/chat.
eval-routing:
	python tests/eval/qa/run_eval_routing.py --questions tests/eval/qa/routing.jsonl

# ---- Phase 5: multi-turn gate (does condensing recover a follow-up?) --------
# Each line is a conversation; the follow-up is a fragment that only resolves
# with the thread. Add --ablate to measure the lift over a stateless ask.
eval-followup:
	python tests/eval/qa/run_eval_followup.py --questions tests/eval/qa/followups.jsonl

# ---- Phase 4: hybrid migration (run INSIDE the api container) --------
# docker compose exec api python -m tablerag.scripts.reindex_all

lint:
	ruff check tablerag tests spike
