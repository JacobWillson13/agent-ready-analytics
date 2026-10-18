"""Create the LangSmith custom dashboard defined in dashboard.json.

Builds every chart through the LangSmith REST API (/api/v1/charts/...), so the
dashboard lives in version control instead of being clicked together. Running it
again replaces the dashboard with the same title.

  # 1. print the payloads; no API calls
  uv run python dashboards/langsmith/push_dashboard.py --dry-run

  # 2. preview every chart from LangSmith and compare it with the jsonl results
  uv run python dashboards/langsmith/push_dashboard.py --check

  # 3. create (or replace) the dashboard
  uv run python dashboards/langsmith/push_dashboard.py

Needs LANGSMITH_API_KEY (or LANGCHAIN_API_KEY). Optional: LANGSMITH_ENDPOINT,
LANGSMITH_WORKSPACE_ID (only if your key spans several workspaces).
Run backfill_feedback.py --apply first: every chart filters on the feedback it writes.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

SPEC = Path(__file__).with_name("dashboard.json")
DEFAULT_RUNS = ["evals/results/phase2/runs.jsonl", "evals/results/phase2-v2/runs.jsonl"]
STRICT = {"run_count", "feedback_score_avg", "error_rate"}  # must match the jsonl
CHART_TYPES = {"line", "bar", "table", "kpi", "top-k", "pie"}


# ---------- spec -> API payloads ----------

def series_filter(spec: dict, s: dict) -> str:
    parts = ["eq(is_root, true)", f'has(tags, "run:{s["run"]}")']
    if s.get("model"):
        parts.append(f'has(tags, "model:{spec["models"][s["model"]]}")')
    if s.get("level"):
        parts.append(f'has(tags, "context:{s["level"]}")')
    parts.append(f'eq(feedback_key, "{spec["feedback_key"]}")')
    if s.get("outcome"):
        parts.append(spec["outcomes"][s["outcome"]])
    return "and(" + ", ".join(parts) + ")"


def metric_definition(spec: dict, metric: str) -> dict:
    """Map the spec's metric names to LangSmith V2 metric definitions."""
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


def series_payload(spec: dict, s: dict, project_id: str, sid: str | None = None) -> dict:
    out = {"name": s["name"],
           "metric_definition": metric_definition(spec, s["metric"]),
           "filter_definition": {"source_type": "tracing_project", "project_ids": [project_id],
                                 "run_filter": series_filter(spec, s)}}
    if sid:
        out["id"] = sid
    return out


def chart_payload(spec: dict, chart: dict, index: int, project_id: str, section_id: str) -> dict:
    if chart["chart_type"] == "text":
        return {"chart_type": "text", "markdown": chart["markdown"], "index": index, "section_id": section_id}
    if chart["chart_type"] not in CHART_TYPES:
        raise ValueError(f"unknown chart_type {chart['chart_type']!r}")
    return {"title": chart["title"], "description": chart.get("description"), "chart_type": chart["chart_type"],
            "index": index, "section_id": section_id,
            "common_filters": {"session": [project_id]},
            "series": [series_payload(spec, s, project_id) for s in chart["series"]]}


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
        r = self.s.request(method, self.base + path, timeout=60, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:800]}")
        return r.json() if r.content else None

    def project_id(self, name: str) -> str:
        res = self.call("GET", "/api/v1/sessions", params={"name": name})
        hits = [p for p in res if p.get("name") == name]
        if not hits:
            sys.exit(f"No tracing project named {name!r}.")
        return hits[0]["id"]


# ---------- check against jsonl ----------

def load_rows(paths):
    rows = {}
    for p in paths:
        for line in open(p):
            if line.strip():
                r = json.loads(line)
                rows[(r["run_id"], r["model"], r["level"], r["qid"], r["rep"])] = r
    return list(rows.values())


def expected(spec, s, rows):
    rs = [r for r in rows if r["run_id"] == s["run"]
          and (not s.get("model") or r["model"] == spec["models"][s["model"]])
          and (not s.get("level") or r["level"] == s["level"])]
    failed = lambda r: r["status"] in ("recursion_limit", "error")
    if s.get("outcome") == "correct":
        rs = [r for r in rs if r["correct"] == 1]
    elif s.get("outcome") == "wrong":
        rs = [r for r in rs if r["correct"] == 0 and not failed(r)]
    elif s.get("outcome") == "step_limit":
        rs = [r for r in rs if failed(r)]
    if not rs:
        return 0
    m = s["metric"]
    if m == "run_count":
        return len(rs)
    if m == "feedback_score_avg":
        return sum(r["correct"] for r in rs) / len(rs)
    if m == "error_rate":
        return sum(failed(r) for r in rs) / len(rs)
    if m == "total_cost":
        return sum(r.get("cost_usd") or 0 for r in rs)
    if m == "median_tokens":
        return statistics.median(r["input_tokens"] + r["output_tokens"] for r in rs if r.get("input_tokens"))
    if m == "latency_p50":
        return statistics.median(r["latency_s"] for r in rs if r.get("latency_s"))
    return None


def check(api, spec, project_id, rows) -> int:
    w = spec["window"]
    bucket = {"start_time": w["start"], "end_time": w["end"], "timezone": "UTC", "stride": {"days": 7}}
    bad = 0
    for chart in spec["charts"]:
        if chart["chart_type"] == "text":
            continue
        series = [series_payload(spec, s, project_id, sid=f"s{i}") for i, s in enumerate(chart["series"])]
        chart_body = {"series": series, "common_filters": {"session": [project_id]}}
        res = api.call("POST", "/api/v1/charts/preview", json={"bucket_info": bucket, "chart": chart_body})
        got = {}
        for pt in res["data"]:
            v = pt["value"]
            if isinstance(v, dict):  # some metrics return {stat: value}
                v = next(iter(v.values()), None)
            if v is not None:
                got.setdefault(pt["series_id"], []).append(v)
        print(f"\n{chart['title']}  [{chart['chart_type']}]")
        for i, s in enumerate(chart["series"]):
            vals = got.get(f"s{i}", [])
            g = sum(vals) if s["metric"] == "run_count" else (vals[0] if len(vals) == 1 else vals or None)
            e = expected(spec, s, rows)
            ok = ""
            if s["metric"] in STRICT and isinstance(g, (int, float)) and e is not None:
                ok = "ok" if abs(g - e) <= (0.5 if s["metric"] == "run_count" else 0.005) else "MISMATCH"
                bad += ok == "MISMATCH"
            elif s["metric"] in STRICT:
                ok, bad = "NO DATA", bad + 1
            fmt = lambda x: f"{x:,.3f}" if isinstance(x, float) else str(x)
            print(f"  {s['name']:<22} langsmith={fmt(g):<14} jsonl={fmt(e):<14} {ok}")
    print(f"\n{bad} strict mismatches" if bad else "\nAll strict metrics match the jsonl.")
    return 1 if bad else 0


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", type=Path, default=SPEC)
    ap.add_argument("--dry-run", action="store_true", help="print payloads only")
    ap.add_argument("--check", nargs="*", metavar="RUNS_JSONL",
                    help="preview charts and compare with the jsonl results (default: phase2 and phase2-v2)")
    args = ap.parse_args()
    spec = json.loads(args.spec.read_text())

    if args.dry_run:
        payloads = [chart_payload(spec, c, i, "<project_id>", "<section_id>") for i, c in enumerate(spec["charts"])]
        print(json.dumps({"section": {"title": spec["title"], "description": spec["description"]},
                          "charts": payloads}, indent=2))
        return 0

    api = Api()
    pid = api.project_id(spec["project"])
    if args.check is not None:
        return check(api, spec, pid, load_rows(args.check or DEFAULT_RUNS))

    for sec in api.call("GET", "/api/v1/charts/section", params={"title_contains": spec["title"], "limit": 100}):
        if sec["title"] == spec["title"]:
            api.call("DELETE", f"/api/v1/charts/section/{sec['id']}")
            print(f"deleted old dashboard {sec['id']}")
    sec = api.call("POST", "/api/v1/charts/section",
                   json={"title": spec["title"], "description": spec["description"]})
    try:
        for i, chart in enumerate(spec["charts"]):
            api.call("POST", "/api/v1/charts/create", json=chart_payload(spec, chart, i, pid, sec["id"]))
    except RuntimeError as e:
        api.call("DELETE", f"/api/v1/charts/section/{sec['id']}")
        print(f"failed on block {i} ({chart.get('title', 'text')}); removed the partial dashboard\n{e}")
        return 1
    host = api.base.replace("api.smith", "smith").replace("/api", "")
    print(f"created dashboard {sec['id']} with {len(spec['charts'])} blocks")
    print(f"open: {host}/  ->  Monitoring  ->  {spec['title']}")
    print(f"set the time range to {spec['window']['start']} .. {spec['window']['end']} before screenshotting")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        sys.exit(str(e))
