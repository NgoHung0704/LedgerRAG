.PHONY: up down logs test test-unit test-integration spike-tables spike-run spike-grade eval-tables eval-figures eval-funds eval-parser eval-visuals eval-qa eval-accords eval-convention eval-routing eval-followup eval-adversarial eval-attacks lint docs-relink docs-test docs-build

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
# Extra flags via ARGS, e.g. make eval-qa KB=<id> ARGS="--api http://host:8000"
eval-qa:
	python tests/eval/qa/run_eval_qa.py --kb $(KB) $(ARGS)

# Same gate, ACCORDS question set (retraite / prévoyance / accords CETIAT).
# Usage: make eval-accords KB=<accords kb id>
eval-accords:
	python tests/eval/qa/run_eval_qa.py --kb $(KB) \
		--questions tests/eval/qa/accords.jsonl $(ARGS)

# Same gate, Convention Collective question set (CCN métallurgie, cotation,
# épargne salariale, accords d'entreprise CETIAT).
# Usage: make eval-convention KB=<convention kb id>
eval-convention:
	python tests/eval/qa/run_eval_qa.py --kb $(KB) \
		--questions tests/eval/qa/convention.jsonl $(ARGS)

# ---- figure RETRIEVAL gate (needs the full live stack) ---------------------
# The other half of eval-figures: that one scores how well a chart is
# DESCRIBED, this one whether the right chart comes back when a question is
# asked. Graded on the citation alone — the assistant is not asked to read a
# figure, only to put it in front of a human.
# Usage: make eval-visuals KB=<kb holding the EPSENS documents>
eval-visuals:
	python tests/eval/qa/run_eval_qa.py --kb $(KB) \
		--questions tests/eval/qa/visuals.jsonl $(ARGS)

# ---- sibling-table gate (needs the full live stack) ------------------------
# Six EPSENS fund factsheets built from one template: their tables share a
# structure exactly and differ only in the numbers and in WHICH FUND they
# describe. Kept OUT of questions.jsonl because that set targets the CETIAT HR
# documents - run against the wrong KB, every question fails for the honest
# reason that its document is not there, and the output says nothing.
#
# The KB holds THREE editions of most funds - 30/09/2021, 31/08/2023 and
# 30/09/2024 - built from the same template, so a question naming only the fund
# has several correct answers. f1-f10, f13, f14 pin the period and check a
# value. f11, f12, f15-f17 name no period on purpose and are graded as traps.
#
# READ THOSE BY HAND when they fail. The trap grader passes on a refusal, so an
# answer that enumerates each edition WITH ITS DATE - which is the behaviour
# OVERLAP_RULE actually asks for, and better than refusing - is scored FAIL.
# That is a limit of substring grading, not a wrong answer.
#
# Usage: make eval-funds KB=<kb holding the EPSENS factsheets>
eval-funds:
	python tests/eval/qa/run_eval_qa.py --kb $(KB) \
		--questions tests/eval/qa/funds.jsonl $(ARGS)

# ---- figure-reading gate (needs a live parser endpoint) --------------------
# Charts are the one thing with no text to fall back on. Scores three things:
# are the printed values in the description, is anything INVENTED for a chart
# that prints none, and is a logo told apart from a chart.
# Drop the documents named in figures.jsonl into tests/eval/figures/pdfs/.
eval-figures:
	python tests/eval/figures/run_eval_figures.py $(ARGS)

# ---- trying a different parsing model (needs the candidate served) ---------
# Runs both parser-facing gates against a candidate WITHOUT changing config,
# so a swap is decided by what the model scores on OUR tables, not by the
# benchmark shipped with it. Run --baseline first for the number to beat.
#   make eval-parser ARGS="--baseline"
#   make eval-parser ARGS="--at http://localhost:8010 --model PaddlePaddle/PaddleOCR-VL"
eval-parser:
	python scripts/eval_parser.py $(ARGS)

# ---- Phase 5: routing gate (needs several KBs; scores router, not answers) --
# Split the 3 sample PDFs into 3 KBs whose names contain CETIAT / Avenant /
# Glossaire, then auto-route each question via POST /api/chat.
eval-routing:
	python tests/eval/qa/run_eval_routing.py --questions tests/eval/qa/routing.jsonl $(ARGS)

# ---- Phase 5: multi-turn gate (does condensing recover a follow-up?) --------
# Each line is a conversation; the follow-up is a fragment that only resolves
# with the thread. make eval-followup ARGS=--ablate  measures the lift.
eval-followup:
	python tests/eval/qa/run_eval_followup.py --questions tests/eval/qa/followups.jsonl $(ARGS)

# ---- Phase 4: hybrid migration (run INSIDE the api container) --------
# docker compose exec api python -m tablerag.scripts.reindex_all

# ---- Red-team: guardrail invariants (deterministic, no model, CI-safe) ------
# Attack inputs vs the real guardrail code (verifier, safety-core prompt,
# router bounds, refusal detector). Target 100%. Re-run on any prompt change.
eval-adversarial:
	python tests/eval/adversarial/invariants.py

# ---- Red-team: behavioural attacks (needs the full live stack) --------------
# Usage: make eval-attacks KB=<kb_id>   (dataset: tests/eval/adversarial/attacks.jsonl)
# Pushes injection / override / leak attacks through the pipeline, graded as traps.
eval-attacks:
	python tests/eval/adversarial/run_attacks.py --kb $(KB) $(ARGS)

lint:
	ruff check tablerag tests spike

# ---- docs site: repair citation line numbers that merely drifted ----------
# Refuses to touch a citation whose TEXT changed — that needs a human.
docs-relink:
	python docs-site/tools/relink.py --write

# ---- docs site ------------------------------------------------------------
docs-test:
	cd docs-site && npx vitest run

docs-build:
	cd docs-site && npx vite build
