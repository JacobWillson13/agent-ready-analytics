# agent-ready-analytics

Modeled on the agent-first data stack LangChain's data team described in Emily Hawkins'
[How we built LangChain's agent-first data stack](https://langchain.com/blog/agent-data-stack)
and Hex's [LangChain customer story](https://hex.tech/customers/langchain/).

The data belongs to a fictional company, Lanternfly Labs, which sells an LLM observability platform
through a free Developer plan, a self-serve Plus plan ($39/seat plus trace overage), and enterprise
contracts (including hybrid and self-hosted deployments).

> **All company data is synthetic.** Lanternfly Labs is fictional. Its business shape is loosely
> calibrated to LangChain's public pricing and scale, but every number here (ARR, customers, churn,
> usage) is generated and is not a LangChain figure or estimate. The PyPI and GitHub data is real.

The thesis: a data agent is only as reliable as the context around the data. This repo builds that
context in git, then proves it with evals that score the same agent at three context levels against an
independent answer key.

## Stack

| Layer | Tool |
|---|---|
| Synthetic sources | Seeded Python generator: Salesforce, product DB, Segment, Metronome, support desk |
| Real sources | PyPI downloads (BigQuery public dataset) and GitHub releases (dlt) for the upstream LangChain packages |
| Warehouse | BigQuery (billing on, free tier) |
| Modeling | dbt Core 1.12: contracts, unit tests, incremental Segment model, SCD2 snapshot, exposures |
| Metrics | MetricFlow, dbt 1.12 Semantic Layer spec (annotations next to each column) |
| Business context | `guides/*.md`, versioned and code-owned |
| Trust signals | `meta.endorsed` on marts, gated by CODEOWNERS |
| Agent | LangChain `create_agent` on LangGraph; CLI and MCP server |
| Observability and evals | LangSmith experiments; GitHub Action posts eval deltas on context PRs |
| Dashboard | Self-hosted Lightdash (SQL Runner on marts; MetricFlow stays the only metric definition) |

## How it flows

1. `generator/` simulates 33 months (2024-01-01 to 2026-10-14) and writes raw parquet plus an answer key.
2. `scripts/load_bq.sh` loads raw tables into `raw_*` datasets and the answer key into `eval_truth`.
3. `ingest/` pulls real PyPI and GitHub data.
4. dbt builds staging, intermediate, and endorsed marts, then runs tests, including reconciliation
   tests that compare marts to the answer key.
5. The agent answers questions with tools that read dbt docs, endorsements, guides, and metrics.
6. `evals/` asks 25 golden questions at three context levels and scores them in code.

## Context levels

| Level | Agent can see |
|---|---|
| raw | Raw source tables only |
| docs | dbt models and their documentation (no endorsements, guides, or metrics) |
| full | Endorsement ranking, guides, governed metrics via MetricFlow, endorsed marts |

Each golden question is tagged with the traps it exercises (TCV vs ARR, stale Salesforce status,
self-hosted telemetry gap, upgrade is not churn, and others), so results break down by trap.

## Run it

```
uv sync
cp dbt/profiles.yml.example ~/.dbt/profiles.yml        # set your GCP project
gcloud auth application-default login
export GCP_PROJECT=... ANTHROPIC_API_KEY=... LANGSMITH_API_KEY=... LANGSMITH_TRACING=true GITHUB_TOKEN=...

make generate            # ~3 min, ~320 MB parquet
make load GCP_PROJECT=$GCP_PROJECT
make ingest GCP_PROJECT=$GCP_PROJECT
make build               # dbt build + semantic validation
make golden              # answer key -> evals/golden.jsonl (always rebuild after generate)
make agent Q="What was total ARR at the end of September 2026?"
make evals               # raw vs docs vs full in LangSmith
make baseline            # commit evals/baseline.json for CI
make lightdash
```

Use `--scale 0.05` on the generator for fast iteration.

## Credentials

Use two service accounts. The CI/dbt account can read everything, including `eval_truth`. The agent
account (also used by Lightdash) must not be able to read `eval_truth`; the agent's SQL tool also
enforces a dataset allowlist per context level.

## Numbers (seed 42, full scale, end of September 2026)

ARR $36.2M ($18.7M enterprise, $17.4M self-serve), 6,048 paying customers, 251 enterprise, about 80k
orgs created since 2024. These are calibrated assumptions loosely based on LangChain's public figures,
not LangChain data or estimates of it.
