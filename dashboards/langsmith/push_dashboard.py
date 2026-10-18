"""Create the LangSmith custom dashboard defined in dashboard.json.

Builds every chart through the LangSmith REST API (/api/v1/charts/...), so the
dashboard lives in version control instead of being clicked together. Running it
again replaces the dashboard with the same title. Charts appear in spec order on
LangSmith's two-column grid.

  uv run python dashboards/langsmith/push_dashboard.py --dry-run           # print payloads, no API calls
  uv run python dashboards/langsmith/push_dashboard.py --list-experiments  # Phase 1 candidates
  uv run python dashboards/langsmith/push_dashboard.py                     # create or replace

Spec notes
- LangSmith's `bar` is always stacked, and `top-k` (ranked bar), `pie` (donut) and
  `table` keep only one series. Comparisons are therefore one series plus a group-by.
- group_by: context_level | run_id | split (trace metadata), project, outcome (feedback label).
- source "phase1" points a series at the Phase 1 Sonnet experiments (one project per
  context level), picked by `phase1.pattern` or pinned in `phase1.pin`.

Needs LANGSMITH_API_KEY (or LANGCHAIN_API_KEY). Optional: LANGSMITH_ENDPOINT,
LANGSMITH_WORKSPACE_ID. Run backfill_feedback.py --apply first.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SPEC = Path(__file__).with_name("dashboard.json")
CHART_TYPES = {"line", "bar", "table", "kpi", "top-k", "pie"}
SINGLE_SERIES = {"top-k", "pie", "table", "kpi"}
GROUP_BY = {
    "context_level": {"attribute": "metadata", "path": "context_level"},
    "run_id": {"attribute": "metadata", "path": "run_id"},
    "split": {"attribute": "metadata", "path": "split"},
    "project": {"attribute": "project"},
    "outcome": {"attribute": "feedback_label", "path": "outcome"},
}


# ---------- spec -> API payloads ----------

def charts_in_order(spec: dict) -> list[dict]:
    return [item for row in spec["rows"] for item in row["items"]]


def run_filter(spec: dict, s: dict) -> str:
    if s.get("source") == "phase1":
        return "eq(is_root, true)"
    parts = ["eq(is_root, true)"]
    if s.get("run"):
        parts.append(f'has(tags, "run:{s["run"]}")')
    if s.get("model"):
        parts.append(f'has(tags, "model:{spec["models"][s["model"]]}")')
    if s.get("level"):
        parts.append(f'has(tags, "context:{s["level"]}")')
    if s.get("split"):
        parts.append(f'and(eq(metadata_key, "split"), eq(metadata_value, "{s["split"]}"))')
    parts.append(f'eq(feedback_key, "{spec["feedback_key"]}")')
    return "and(" + ", ".join(parts) + ")"


def metric_definition(spec: dict, metric: str) -> dict:
    if metric == "run_count":
        return {"type": "count"}
    if metric == "feedback_score_avg":
        return {"type": "avg", "field": "feedback_score", "params": {"feedback_key": spec["feedback_key"]}}
    if metric == "error_rate":
        return {"type": "ratio", "numerator": {"type": "count", "filter": 'eq(status, "error")'},
                "denominator": {"type": "count"}}
    if metric == "total_cost":
        return {"type": "sum", "field": "total_cost"}
    if metric == "median_tokens":
        return {"type": "percentile", "field": "total_tokens", "params": {"p": 0.5}}
    if metric == "latency_p50":
        return {"type": "percentile", "field": "latency_seconds", "params": {"p": 0.5}}
    raise ValueError(f"unsupported metric {metric!r}; add it to metric_definition()")


def series_payload(spec: dict, s: dict, ids: dict) -> dict:
    projects = ids["phase1"] if s.get("source") == "phase1" else [ids["project"]]
    out = {"name": s["name"], "metric_definition": metric_definition(spec, s["metric"]),
           "filter_definition": {"source_type": "tracing_project", "project_ids": projects,
                                 "run_filter": run_filter(spec, s)}}
    if s.get("group_by"):
        out["group_by_definitions"] = [GROUP_BY[s["group_by"]]]
    return out


def chart_payload(spec: dict, chart: dict, index: int, ids: dict, section_id: str) -> dict:
    if chart["chart_type"] == "text":
        return {"chart_type": "text", "markdown": chart["markdown"], "index": index, "section_id": section_id}
    if chart["chart_type"] not in CHART_TYPES:
        raise ValueError(f"unknown chart_type {chart['chart_type']!r}")
    series = chart["series"] if isinstance(chart["series"], list) else [chart["series"]]
    if chart["chart_type"] in SINGLE_SERIES and len(series) > 1:
        raise ValueError(f"{chart['title']!r}: {chart['chart_type']} charts keep only one series; use group_by")
    projects = sorted({p for s in series for p in series_payload(spec, s, ids)["filter_definition"]["project_ids"]})
    return {"title": chart["title"], "description": chart.get("description"), "chart_type": chart["chart_type"],
            "index": index, "section_id": section_id, "common_filters": {"session": projects},
            "series": [series_payload(spec, s, ids) for s in series]}


# ---------- HTTP ----------

class Api:
    def __init__(self):
        import requests
        key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
        if not key:
            sys.exit("Set LANGSMITH_API_KEY (source the project env file first).")
        self.base = os.environ.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com").rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"X-API-Key": key, "Content-Type": "application/json"})
        if os.environ.get("LANGSMITH_WORKSPACE_ID"):
            self.s.headers["X-Tenant-Id"] = os.environ["LANGSMITH_WORKSPACE_ID"]

    def call(self, method: str, path: str, **kw):
        r = self.s.request(method, self.base + path, timeout=120, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:800]}")
        return r.json() if r.content else None

    def project_id(self, name: str) -> str:
        hits = [p for p in self.call("GET", "/api/v1/sessions", params={"name": name}) if p.get("name") == name]
        if not hits:
            raise RuntimeError(f"No tracing project named {name!r}.")
        return hits[0]["id"]


# ---------- Phase 1 experiments ----------

def experiment_candidates(spec: dict) -> list:
    from langsmith import Client
    pat = re.compile(spec["phase1"]["pattern"])
    out = []
    for p in Client().list_projects(name_contains="context-", include_stats=True):
        m = pat.match(p.name or "")
        if not m or not p.reference_dataset_id:
            continue
        fb = (p.feedback_stats or {}).get(spec["feedback_key"]) or {}
        out.append({"level": m.group(1), "name": p.name, "id": str(p.id), "start": p.start_time,
                    "scored": fb.get("n") or 0, "accuracy": fb.get("avg"), "cost": p.total_cost})
    return sorted(out, key=lambda c: c["start"])


def pick_phase1(spec: dict, cands: list) -> dict:
    """Pinned names win; otherwise the earliest fully scored experiment per level (the original Phase 1 run)."""
    chosen = {}
    for level in ("raw", "docs", "full"):
        pin = spec["phase1"]["pin"].get(level)
        pool = [c for c in cands if c["level"] == level]
        pick = next((c for c in pool if c["name"] == pin), None) if pin else \
            next((c for c in pool if c["scored"] >= spec["phase1"]["min_scored_runs"]), None)
        if not pick:
            raise RuntimeError(f"No Phase 1 experiment for {level!r} (pin={pin!r}). Run --list-experiments.")
        chosen[level] = pick
    return chosen


def print_experiments(cands: list, chosen: dict | None = None) -> None:
    picked = {c["id"] for c in (chosen or {}).values()}
    for c in cands:
        acc = f"{c['accuracy']:.2f}" if c["accuracy"] is not None else "  - "
        print(f"  {'*' if c['id'] in picked else ' '} {c['name']:<26} {str(c['start'])[:16]}  "
              f"scored={c['scored']:<3} accuracy={acc}  cost=${float(c['cost'] or 0):.2f}")


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", type=Path, default=SPEC)
    ap.add_argument("--dry-run", action="store_true", help="print payloads only")
    ap.add_argument("--list-experiments", action="store_true", help="list Phase 1 experiment candidates")
    args = ap.parse_args()
    spec = json.loads(args.spec.read_text())
    charts = charts_in_order(spec)

    if args.dry_run:
        ids = {"project": "<project_id>", "phase1": ["<raw_exp>", "<docs_exp>", "<full_exp>"]}
        print(json.dumps({"charts": [chart_payload(spec, c, i, ids, "<section_id>") for i, c in enumerate(charts)]},
                         indent=2))
        return 0

    cands = experiment_candidates(spec)
    if args.list_experiments:
        print_experiments(cands)
        return 0
    chosen = pick_phase1(spec, cands)
    print("Phase 1 experiments (* = used; pin others in dashboard.json -> phase1.pin):")
    print_experiments(cands, chosen)

    api = Api()
    ids = {"project": api.project_id(spec["project"]), "phase1": [chosen[l]["id"] for l in ("raw", "docs", "full")]}

    for sec in api.call("GET", "/api/v1/charts/section", params={"title_contains": spec["title"], "limit": 100}):
        if sec["title"] == spec["title"]:
            api.call("DELETE", f"/api/v1/charts/section/{sec['id']}")
            print(f"deleted old dashboard {sec['id']}")
    sec = api.call("POST", "/api/v1/charts/section", json={"title": spec["title"], "description": spec["description"]})
    chart_ids = []
    try:
        for i, chart in enumerate(charts):
            res = api.call("POST", "/api/v1/charts/create", json=chart_payload(spec, chart, i, ids, sec["id"]))
            chart_ids.append(res["id"])
    except RuntimeError as e:
        api.call("DELETE", f"/api/v1/charts/section/{sec['id']}")
        print(f"failed on block {i} ({chart.get('title', 'text')}); removed the partial dashboard\n{e}")
        return 1
    print(f"created dashboard {sec['id']} with {len(chart_ids)} blocks")

    host = api.base.replace("api.smith", "smith")
    print(f"\nopen: {host}  ->  Monitoring  ->  {spec['title']}")
    print(f"time range: {spec['window']['start'][:10]} to {spec['window']['end'][:10]} (must include the Phase 1 dates above)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        sys.exit(str(e))
