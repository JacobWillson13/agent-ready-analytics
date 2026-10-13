"""Accuracy, tokens, cost, and latency per context level, from saved eval results + LangSmith stats.

  uv run python evals/experiment_stats.py evals/results/run3_raw_full.json evals/results/run1_docs.json
"""
import json
import sys
from pathlib import Path

from langsmith import Client


def main():
    client = Client()
    rows = []
    for f in sys.argv[1:]:
        for level, r in json.loads(Path(f).read_text()).items():
            p = client.read_project(project_name=r["experiment"], include_stats=True)
            n = p.run_count or 1
            rows.append((level, r["accuracy"], p.run_count, (p.total_tokens or 0) / n,
                         float(p.total_cost or 0) / n, p.latency_p50, r["experiment"]))
    print(f"{'level':6} {'accuracy':>8} {'runs':>5} {'tokens/q':>9} {'cost/q':>8} {'p50 s':>6}  experiment")
    for lvl, acc, runs, tok, cost, lat, exp in rows:
        lat_s = lat.total_seconds() if hasattr(lat, "total_seconds") else (lat or 0)
        print(f"{lvl:6} {acc:>8.0%} {runs or 0:>5} {tok:>9,.0f} {cost:>8.3f} {lat_s:>6.1f}  {exp}")


if __name__ == "__main__":
    main()
