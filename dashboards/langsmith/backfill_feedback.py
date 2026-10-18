"""Attach benchmark correctness to LangSmith traces as feedback.

The benchmark scored every run locally (evals/results/*/runs.jsonl) but never
sent the score to LangSmith, so dashboards there cannot chart accuracy. This
script matches each jsonl row to its root trace and writes feedback
`correct` = 1/0, with the scorer's reason as the comment.

Match key: (run_id, model, level, qid, rep)
  - run_id, model, level come from the trace tags run:<id>, model:<m>, context:<lvl>
  - qid, rep come from the trace metadata
If a key has several traces (an aborted attempt that was traced but not kept),
the trace whose start time is closest to the row's started_at wins.

Dry run by default. Re-running is safe: feedback ids are deterministic, so
existing feedback is skipped, not duplicated.

  uv run python dashboards/langsmith/backfill_feedback.py            # dry run, phase2 + phase2-v2
  uv run python dashboards/langsmith/backfill_feedback.py --apply    # write

Retention: the LangSmith SDK extends a trace to long-lived retention (billed as
an upgrade) whenever feedback is created, unless told not to. This script turns
that off. Pass --extend-retention only if you want these traces kept past the
14-day base retention and accept the upgrade charge.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

DEFAULT_RUNS = ["evals/results/phase2/runs.jsonl", "evals/results/phase2-v2/runs.jsonl"]
NAMESPACE = uuid.UUID("6f1d3c3e-5a8b-4c55-9a43-6b0f6f2a7d10")  # fixed: makes feedback ids reproducible


def row_key(run_id, model, level, qid, rep) -> tuple:
    return (str(run_id), str(model), str(level), str(qid), int(rep))


def load_rows(paths: list[str]) -> dict[tuple, dict]:
    rows: dict[tuple, dict] = {}
    for p in paths:
        with open(p) as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                k = row_key(r["run_id"], r["model"], r["level"], r["qid"], r["rep"])
                rows[k] = r  # rows copied between files (phase2 raw in phase2-v2) are identical
    return rows


def trace_key(run) -> tuple | None:
    tags = run.tags or []
    t = {}
    for tag in tags:
        for prefix in ("run:", "model:", "context:"):
            if tag.startswith(prefix):
                t[prefix[:-1]] = tag[len(prefix):]
    meta = (run.extra or {}).get("metadata", {}) or {}
    if not all(k in t for k in ("run", "model", "context")) or "qid" not in meta or "rep" not in meta:
        return None
    return row_key(t["run"], t["model"], t["context"], meta["qid"], meta["rep"])


def parse_ts(s: str) -> datetime:
    return aware(datetime.fromisoformat(s.replace("Z", "+00:00")))


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", default=DEFAULT_RUNS, help="runs.jsonl files (default: phase2 and phase2-v2)")
    ap.add_argument("--project", default="agent-ready-analytics")
    ap.add_argument("--key", default="correct", help="feedback key")
    ap.add_argument("--apply", action="store_true", help="write feedback (default is a dry run)")
    ap.add_argument("--extend-retention", action="store_true", help="also upgrade traces to long-lived retention (billed)")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    from langsmith import Client

    rows = load_rows(args.runs)
    run_ids = sorted({k[0] for k in rows})
    print(f"jsonl rows: {len(rows)}  run_ids: {run_ids}")

    client = Client()
    tag_filter = "or(" + ", ".join(f'has(tags, "run:{r}")' for r in run_ids) + ")" if len(run_ids) > 1 \
        else f'has(tags, "run:{run_ids[0]}")'
    candidates: dict[tuple, list] = defaultdict(list)
    untagged = 0
    for run in client.list_runs(project_name=args.project, is_root=True, filter=tag_filter):
        k = trace_key(run)
        if k is None:
            untagged += 1
            continue
        candidates[k].append(run)
    n_traces = sum(len(v) for v in candidates.values())
    print(f"root traces found: {n_traces}  (missing tags/metadata: {untagged})")

    matched, missing = [], []
    dupes = 0
    for k, r in rows.items():
        cands = candidates.get(k)
        if not cands:
            missing.append(k)
            continue
        if len(cands) > 1:
            dupes += 1
            t0 = parse_ts(r["started_at"])
            cands = sorted(cands, key=lambda c: abs(aware(c.start_time) - t0))
        matched.append((r, cands[0]))
    extra_traces = n_traces - len(matched)

    missing_set = set(missing)
    by_cell = Counter((k[0], k[1], k[2]) for k in rows if k not in missing_set)
    print(f"matched: {len(matched)}  missing trace: {len(missing)}  keys with >1 trace: {dupes}  "
          f"traces left without feedback: {extra_traces}")
    for cell, n in sorted(by_cell.items()):
        print(f"  {cell[0]:<10} {cell[1]:<28} {cell[2]:<5} {n}")
    if missing:
        print("first missing keys:", missing[:5])
        if len(missing) > 0.05 * len(rows):
            print("More than 5% of rows have no trace. Check the tag/metadata names before applying.")
            return 1

    if not args.apply:
        print("\nDry run. Re-run with --apply to write feedback.")
        return 0

    def write(pair):
        r, run = pair
        fid = uuid.uuid5(NAMESPACE, f"{args.key}|{run.id}")
        try:
            client.create_feedback(
                run.id, args.key, score=int(r["correct"]), comment=r.get("reason"),
                trace_id=run.trace_id or run.id, feedback_id=fid,
                extend_trace_retention=args.extend_retention,
            )
            return "created"
        except Exception as e:  # existing id -> conflict; anything else is reported
            msg = str(e)
            return "exists" if ("409" in msg or "already exists" in msg.lower()) else f"error: {msg[:200]}"

    results = Counter()
    errors = []
    with ThreadPoolExecutor(args.workers) as pool:
        for fut in as_completed(pool.submit(write, p) for p in matched):
            res = fut.result()
            results[res if not res.startswith("error") else "error"] += 1
            if res.startswith("error"):
                errors.append(res)
    print(dict(results))
    for e in errors[:5]:
        print(" ", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
