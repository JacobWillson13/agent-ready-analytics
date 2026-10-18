# LangSmith dashboard

The benchmark dashboard, defined as code. `dashboard.json` is the spec: rows of charts with relative widths and heights. `push_dashboard.py` builds the charts and the grid layout through the LangSmith REST API, then reads every chart back and checks the Phase 2 numbers against `evals/results/*/runs.jsonl`.

## What it shows

It's laid out as two screenshots.

1. **Accuracy.**
   - A headline row: findings, Phase 2 run count, Haiku cost and Sonnet cost.
   - Accuracy by context for Haiku, Gemma and Sonnet (Phase 1).
   - Gemma's outcomes (correct, wrong, step limit), Gemma on the 33 hard questions, and the context fix for Gemma.
2. **Efficiency.**
   - Median tokens by context for each model.
   - Haiku latency, Gemma's step-limit rate, and the context fix for Haiku.
   - A notes row.

## Data sources

- **Phase 2:** the benchmark scored runs locally, so `backfill_feedback.py` attaches two feedback keys to each root trace. `correct` is 1 or 0, and `outcome` is correct, wrong or step_limit. Runs are matched on the `run:`, `model:` and `context:` tags plus the `qid` and `rep` metadata. Every Phase 2 chart filters on `correct`, so aborted, never-logged attempts drop out.
- **Phase 1 (Sonnet):** the `context-raw|docs|full-<hash>` LangSmith experiments, which `evals/run_evals.py` already scored as `correct`. The push script picks the earliest fully scored experiment per level, which is the original Phase 1 run. To use a different one, set its name in `phase1.pin`. `--list-experiments` shows the candidates.

## Run order

```
source ~/.config/ara/env
uv run python dashboards/langsmith/backfill_feedback.py                    # dry run
uv run python dashboards/langsmith/backfill_feedback.py --apply --replace  # writes correct + outcome
uv run python dashboards/langsmith/push_dashboard.py                       # create, lay out, check
```

Then open LangSmith, go to Monitoring, and open "Agent benchmark: model x context". Set the time range to cover the Phase 1 dates the script prints through 2026-10-18.

## Chart rules learned the hard way

- `bar` is always a stacked bar, so several series pile into one column.
- `top-k` (ranked bar), `pie` (donut) and `table` keep only one series. To compare, use one series plus `group_by`: `context_level`, `run_id` or `split` (trace metadata), `project`, or `outcome` (feedback label).
- The API accepts only V2 series (`metric_definition` + `filter_definition`) and needs `common_filters.session`.
- Run filters can't `or()` across tag comparisons.
- Feedback must carry the trace's `session_id`, or chart queries can't join it to the trace.

## Notes

- **Retention.** The SDK upgrades a trace to long-lived retention, which is billed, whenever feedback is added, unless told not to. The backfill turns that off. Add `--extend-retention` only if you want the Phase 2 traces kept past the 14-day base retention.
- **Layout.** Widths are percentages of a row, and heights are relative to LangSmith's default row height. The script scales both from the default layout it reads back. `--no-layout` keeps the default grid.
- **Format retries.** `agent/graph.py` invokes a format retry separately, tagged only `format_retry`, so it lands as its own trace. The filters exclude those traces. The 7 affected rows keep their final score on the first trace, but that trace's latency and token count leave out the retry.
- **Cost** comes from LangSmith's model price map, so it can differ slightly from the harness's own cost. LangSmith shows $2.7 for Haiku's Phase 2 runs; the jsonl total is $2.84.
