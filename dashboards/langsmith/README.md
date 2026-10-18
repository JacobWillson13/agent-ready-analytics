# LangSmith dashboard

The Phase 2 benchmark dashboard, defined as code. `dashboard.json` is the spec; `push_dashboard.py` builds it through the LangSmith REST API, so nothing is configured by hand.

## Why a backfill step

The benchmark scored each run locally and wrote the result to `evals/results/*/runs.jsonl`. LangSmith never received those scores, so it can't chart accuracy. `backfill_feedback.py` attaches each score to its trace as feedback key `correct` (1 or 0). It matches on the trace tags `run:`, `model:` and `context:`, plus the `qid` and `rep` metadata.

Every chart filters on traces that carry this feedback. Aborted attempts that were traced but never logged therefore drop out, and the dashboard's counts match the jsonl exactly.

## Run order

```
source ~/.config/ara/env
R="evals/results/phase2/runs.jsonl evals/results/phase2-v2/runs.jsonl"

uv run python dashboards/langsmith/backfill_feedback.py $R            # dry run: expect 1920 matched, 0 missing
uv run python dashboards/langsmith/backfill_feedback.py $R --apply
uv run python dashboards/langsmith/push_dashboard.py --check $R       # LangSmith vs jsonl, chart by chart
uv run python dashboards/langsmith/push_dashboard.py                  # create or replace the dashboard
```

Then open LangSmith, go to Monitoring, and open "Phase 2 benchmark: model x context". Set the time range to 2026-10-16 16:00 through 2026-10-18 03:00 UTC.

## Notes

- **Retention.** The SDK upgrades a trace to long-lived retention, which is billed, whenever feedback is added, unless told not to. The backfill turns that off. Add `--extend-retention` only if you want the traces kept past the 14-day base retention.
- **Re-running is safe.** Feedback ids are deterministic, so existing feedback is skipped. `push_dashboard.py` deletes and recreates the dashboard with the same title.
- **Changing a chart.** Edit `dashboard.json`, then rerun the push. Valid chart types are `line`, `bar`, `table`, `kpi`, `top-k`, `pie` and `text`.
- **Format retries.** `agent/graph.py` invokes a format retry separately, tagged only `format_retry`, so it lands as its own trace. The filters exclude those traces. The 7 affected rows keep their final score on the first trace, but that trace's latency and token count leave out the retry.
- **Haiku cost** comes from LangSmith's model price map. If Haiku 5.5 isn't in that map, the cost tile shows $0, and `--check` will reveal it (the jsonl total is $2.84).
