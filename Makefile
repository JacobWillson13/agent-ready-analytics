# Usage: make all GCP_PROJECT=my-project
SCALE ?= 1.0
DATA  ?= data

.PHONY: generate load ingest build recon golden evals evals-full agent lightdash all

generate:            ## synthetic company, through the recording date
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

lightdash:
	docker compose -f lightdash/docker-compose.yml up -d

all: generate load ingest build golden evals
