# LangSmith dashboard

The benchmark dashboard, defined as code. `dashboard.json` is the spec: charts in display order. `push_dashboard.py` builds them through the LangSmith REST API on LangSmith's two-column grid. `backfill_feedback.py --verify` confirms every scored run carries its feedback.

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
- **Phase 1 (Sonnet):** the `context-raw|docs|full-<hash>` LangSmith experiments, which `evals/run_evals.py` already scored as `correct`. `phase1.pin` names the three experiments the README reports: raw `b872a827` (0.76, 3 reps), docs `a3d446a7` (1.00, 1 rep), full `aa66fbf5` (1.00, 3 reps). Without pins, the script picks the earliest fully scored experiment per level. `--list-experiments` shows the candidates.

## Run order

```
source ~/.config/ara/env
uv run python dashboards/langsmith/backfill_feedback.py            # dry run: expect 1920 matched, 0 missing
uv run python dashboards/langsmith/backfill_feedback.py --apply    # writes correct + outcome where missing
uv run python dashboards/langsmith/backfill_feedback.py --verify   # a minute later: 1920/1920 for both keys
uv run python dashboards/langsmith/push_dashboard.py               # create or replace the dashboard
```

`make dashboard` runs the apply and push steps.

Then open LangSmith, go to Monitoring, and open "Agent benchmark: model x context". Set the time range to cover the Phase 1 dates the script prints through 2026-10-18.

## Chart rules learned the hard way

- `bar` is always a stacked bar, so several series pile into one column.
- `top-k` (ranked bar), `pie` (donut) and `table` keep only one series. To compare, use one series plus `group_by`: `context_level`, `run_id` or `split` (trace metadata), `project`, or `outcome` (feedback label).
- The API accepts only V2 series (`metric_definition` + `filter_definition`) and needs `common_filters.session`.
- Run filters can't `or()` across tag comparisons.
- Feedback must carry the trace's `session_id`, or chart queries can't join it to the trace.
- Never recreate feedback under an id you just deleted. Deletes are applied asynchronously, so a late delete can remove the replacement; `--replace` uses fresh ids for that reason.

## Notes

- **Retention.** The SDK upgrades a trace to long-lived retention, which is billed, whenever feedback is added, unless told not to. The backfill turns that off. Add `--extend-retention` only if you want the Phase 2 traces kept past the 14-day base retention.
- **Layout.** The section API accepts a `layout`, but a new dashboard has none to read back, so the script keeps LangSmith's default two-column grid; charts appear in spec order.
- **Format retries.** `agent/graph.py` invokes a format retry separately, tagged only `format_retry`, so it lands as its own trace. The filters exclude those traces. The 7 affected rows keep their final score on the first trace, but that trace's latency and token count leave out the retry.
- **Cost** comes from LangSmith's model price map, so it can differ slightly from the harness's own cost. The dashboard shows $2.8 for Haiku's Phase 2 runs; the jsonl total is $2.84.
