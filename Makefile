# Usage: make all GCP_PROJECT=my-project
SCALE ?= 1.0
DATA  ?= data

.PHONY: generate load ingest build recon golden evals evals-full agent dashboard all bench-smoke bench-pilot bench bench-v2 analyze

generate:            ## synthetic company, through the snapshot date
	uv run python -m generator --scale $(SCALE) --out $(DATA)

load:                ## parquet -> BigQuery raw_* and eval_truth
	GCP_PROJECT=$(GCP_PROJECT) scripts/load_bq.sh $(DATA)

ingest:              ## real data: PyPI downloads + GitHub releases
	uv run python ingest/pypi_downloads.py --project $(GCP_PROJECT) --dry-run
	uv run python ingest/pypi_downloads.py --project $(GCP_PROJECT)
	uv run python ingest/github_releases.py

build:               ## dbt seeds, models, snapshots, tests, semantic validation
	cd dbt && uv run dbt deps && uv run dbt build && uv run mf validate-configs

recon:               ## reconciliation tests only (models vs answer key)
	cd dbt && uv run dbt test --select tag:reconciliation

golden:              ## answer key -> evals/golden.jsonl
	uv run python evals/build_golden.py --data $(DATA)

evals:               ## all three context levels in LangSmith
	uv run python evals/run_evals.py --levels raw docs full

baseline:            ## save the current full-context run as the CI baseline
	uv run python evals/run_evals.py --levels full --out evals/baseline.json

agent:               ## make agent Q="What was total ARR at the end of September 2026?"
	uv run python -m agent "$(Q)"

# ---- Phase 2 benchmark: model x context (evals/benchmark.py, evals/analyze.py) ----
HAIKU ?= anthropic:claude-haiku-5-5
GEMMA ?= ollama:gemma4:26b
RUN   ?= phase2

bench-smoke:         ## 3 questions x 3 levels per model: checks keys, tool calling, and BigQuery access
	rm -rf evals/results/smoke
	uv run python evals/benchmark.py --run-id smoke --models $(HAIKU) $(GEMMA) --qids arr_total_sep26 x_nrr_sep x_sh_trace_share

bench-pilot:         ## Haiku, full context, hard split, 1 rep: ceiling check and answer-key audit (about $0.10)
	uv run python evals/benchmark.py --run-id pilot --models $(HAIKU) --levels full --splits hard

bench:               ## full run; resumable. Run the two models in separate terminals to overlap them.
	uv run python evals/benchmark.py --run-id $(RUN) --models $(HAIKU) --repetitions 3 --cost-cap 8
	uv run python evals/benchmark.py --run-id $(RUN) --models $(GEMMA) --repetitions 3

bench-v2:            ## rerun docs and full after a context change; raw is reused because raw cannot see the context layer
	mkdir -p evals/results/$(RUN)-v2
	test -s evals/results/$(RUN)-v2/runs.jsonl || jq -c 'select(.level=="raw")' evals/results/$(RUN)/runs.jsonl > evals/results/$(RUN)-v2/runs.jsonl
	uv run python evals/benchmark.py --run-id $(RUN)-v2 --models $(HAIKU) --levels docs full --repetitions 3 --cost-cap 8
	uv run python evals/benchmark.py --run-id $(RUN)-v2 --models $(GEMMA) --levels docs full --repetitions 3
	uv run python evals/compare_runs.py evals/results/$(RUN) evals/results/$(RUN)-v2

analyze:             ## tables, mixed-effects model, and figures for a run
	uv run python evals/analyze.py evals/results/$(RUN) --figures docs/figures

dashboard:           ## attach benchmark scores to LangSmith traces, then build the LangSmith dashboard
	uv run python dashboards/langsmith/backfill_feedback.py --apply
	uv run python dashboards/langsmith/push_dashboard.py

all: generate load ingest build golden evals
