"""Create the LangSmith custom dashboard defined in dashboard.json.

Builds every chart and the grid layout through the LangSmith REST API
(/api/v1/charts/...), so the dashboard lives in version control instead of being
clicked together. Running it again replaces the dashboard with the same title.

  uv run python dashboards/langsmith/push_dashboard.py --dry-run           # print payloads, no API calls
  uv run python dashboards/langsmith/push_dashboard.py --list-experiments  # Phase 1 candidates
  uv run python dashboards/langsmith/push_dashboard.py                     # create or replace, then check

After creating the dashboard it reads every chart back the way the UI does and
compares the Phase 2 numbers with evals/results/*/runs.jsonl.

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
import statistics
import sys
from collections import Counter
from pathlib import Path

SPEC = Path(__file__).with_name("dashboard.json")
DEFAULT_RUNS = ["evals/results/phase2/runs.jsonl", "evals/results/phase2-v2/runs.jsonl"]
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


def layout_payload(spec: dict, chart_ids: list[str], unit_w: float, unit_h: float) -> dict:
    rows, i = [], 0
    for row in spec["rows"]:
        items = []
        for item in row["items"]:
            items.append({"chart_id": chart_ids[i], "width_units": max(20, round(item["width"] * unit_w))})
            i += 1
        rows.append({"height_units": max(1, round(row["height"] * unit_h)), "items": items})
    bp = {"rows": rows}
    return {"version": 1, "breakpoints": {"sm": bp, "md": bp}}


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


# ---------- check against jsonl ----------

def load_rows(paths):
    rows = {}
    for p in paths:
        for line in open(p):
            if line.strip():
                r = json.loads(line)
                rows[(r["run_id"], r["model"], r["level"], r["qid"], r["rep"])] = r
    return list(rows.values())


def outcome(r) -> str:
    return "step_limit" if r["status"] in ("recursion_limit", "error") else ("correct" if r["correct"] else "wrong")


def expected(spec, s, rows) -> dict | None:
    """Expected value per group label ('' when ungrouped), or None if the jsonl can't say."""
    if s.get("source") == "phase1":
        return None
    rs = [r for r in rows if (not s.get("run") or r["run_id"] == s["run"])
          and (not s.get("model") or r["model"] == spec["models"][s["model"]])
          and (not s.get("level") or r["level"] == s["level"])
          and (not s.get("split") or r["split"] == s["split"])]
    key = {"context_level": lambda r: r["level"], "run_id": lambda r: r["run_id"], "split": lambda r: r["split"],
           "outcome": outcome, None: lambda r: ""}.get(s.get("group_by"))
    if key is None:
        return None
    groups: dict[str, list] = {}
    for r in rs:
        groups.setdefault(key(r), []).append(r)
    m = s["metric"]
    agg = {
        "run_count": len,
        "feedback_score_avg": lambda g: sum(r["correct"] for r in g) / len(g),
        "error_rate": lambda g: sum(outcome(r) == "step_limit" for r in g) / len(g),
        "total_cost": lambda g: sum(r.get("cost_usd") or 0 for r in g),
        "median_tokens": lambda g: statistics.median([r["input_tokens"] + r["output_tokens"] for r in g
                                                       if r.get("input_tokens")] or [0]),
        "latency_p50": lambda g: statistics.median([r["latency_s"] for r in g if r.get("latency_s")] or [0]),
    }[m]
    return {k: agg(g) for k, g in groups.items()}


def num(v):
    if isinstance(v, dict):
        v = next(iter(v.values()), None)
    return v if isinstance(v, (int, float)) else None


def check(api, spec, section_id, rows) -> int:
    """Read the saved charts the way the UI does and compare Phase 2 values with the jsonl."""
    w = spec["window"]
    sec = api.call("POST", f"/api/v1/charts/section/{section_id}",
                   json={"start_time": w["start"], "end_time": w["end"], "timezone": "UTC", "stride": {"days": 31}})
    by_title = {c.get("title"): c for c in sec.get("charts", []) if c.get("chart_type") != "text"}
    strict = {"run_count", "feedback_score_avg", "error_rate"}
    bad = 0
    for chart in charts_in_order(spec):
        if chart["chart_type"] == "text":
            continue
        s = chart["series"] if isinstance(chart["series"], dict) else chart["series"][0]
        got: dict[str, float] = {}
        for pt in (by_title.get(chart["title"]) or {}).get("data", []):
            v = num(pt.get("value"))
            if v is not None:
                g = pt.get("group") or ""
                got[g] = got.get(g, 0) + v if s["metric"] in ("run_count", "total_cost") else v
        exp = expected(spec, s, rows)
        print(f"\n{chart['title']}  [{chart['chart_type']}]")
        for g in sorted(set(got) | set(exp or {})):
            gv, ev = got.get(g), (exp or {}).get(g)
            mark = ""
            if s["metric"] in strict and ev is not None:
                tol = 0.5 if s["metric"] == "run_count" else 0.005
                mark = "ok" if gv is not None and abs(gv - ev) <= tol else "MISMATCH"
                bad += mark == "MISMATCH"
            fmt = lambda x: "-" if x is None else (f"{x:,.3f}" if isinstance(x, float) else f"{x:,}")
            print(f"  {g or '(all)':<36} langsmith={fmt(gv):<12} jsonl={fmt(ev):<12} {mark}")
    print(f"\n{bad} strict mismatches" if bad else "\nAll Phase 2 accuracy, count and step-limit values match the jsonl.")
    return 1 if bad else 0


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", type=Path, default=SPEC)
    ap.add_argument("--dry-run", action="store_true", help="print payloads only")
    ap.add_argument("--list-experiments", action="store_true", help="list Phase 1 experiment candidates")
    ap.add_argument("--no-layout", action="store_true", help="keep LangSmith's default grid")
    ap.add_argument("--runs", nargs="*", default=DEFAULT_RUNS, help="jsonl files for the check")
    args = ap.parse_args()
    spec = json.loads(args.spec.read_text())
    charts = charts_in_order(spec)

    if args.dry_run:
        ids = {"project": "<project_id>", "phase1": ["<raw_exp>", "<docs_exp>", "<full_exp>"]}
        print(json.dumps({"charts": [chart_payload(spec, c, i, ids, "<section_id>") for i, c in enumerate(charts)],
                          "layout": layout_payload(spec, [f"<chart_{i}>" for i in range(len(charts))], 1, 1)},
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

    if not args.no_layout:
        default = (api.call("POST", f"/api/v1/charts/section/{sec['id']}", json={"omit_data": True}) or {}).get("layout")
        print("default layout:", json.dumps(default)[:600])
        unit_w, unit_h = 1.0, None
        try:
            first = default["breakpoints"]["md"]["rows"][0]
            unit_w = sum(it["width_units"] for it in first["items"]) / 100
            unit_h = first["height_units"]
        except (TypeError, KeyError, IndexError):
            pass
        if unit_h:
            try:
                api.call("PATCH", f"/api/v1/charts/section/{sec['id']}",
                         json={"layout": layout_payload(spec, chart_ids, unit_w, unit_h)})
                print(f"applied layout: {len(spec['rows'])} rows (width scale {unit_w:g}, row height {unit_h})")
            except RuntimeError as e:
                print(f"layout not applied, default grid kept: {e}")
        else:
            print("no default layout to scale from; default grid kept (send this output to calibrate)")

    rc = check(api, spec, sec["id"], load_rows(args.runs))
    host = api.base.replace("api.smith", "smith")
    print(f"\nopen: {host}  ->  Monitoring  ->  {spec['title']}")
    print(f"time range: {spec['window']['start'][:10]} to {spec['window']['end'][:10]} (must include the Phase 1 dates above)")
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        sys.exit(str(e))
