"""Tools, assembled per context level. Same SQL engine at every level; only the context differs."""
from __future__ import annotations

import csv
import io
import subprocess
import tempfile

from google.cloud import bigquery
from langchain.tools import tool

from . import catalog
from .settings import DATASETS, DBT_DIR, GCP_PROJECT, MAX_BYTES_BILLED, MAX_ROWS

_bq = None


def bq() -> bigquery.Client:
    global _bq
    if _bq is None:
        _bq = bigquery.Client(project=GCP_PROJECT or None)
    return _bq


def _run_sql(sql: str, level: str) -> str:
    client = bq()
    dry = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
    if dry.statement_type != "SELECT":
        return "Rejected: only SELECT statements are allowed."
    bad = sorted({t.dataset_id for t in (dry.referenced_tables or [])} - DATASETS[level])
    if bad:
        return f"Rejected: datasets not available at this access level: {', '.join(bad)}."
    rows = client.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED)).result(
        max_results=MAX_ROWS)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f.name for f in rows.schema])
    for r in rows:
        w.writerow(list(r.values()))
    note = f"\n(showing up to {MAX_ROWS} rows of {rows.total_rows})" if rows.total_rows and rows.total_rows > MAX_ROWS else ""
    return buf.getvalue() + note


def build_tools(level: str) -> list:
    tools = []

    @tool
    def run_sql(sql: str) -> str:
        """Run a read-only BigQuery Standard SQL SELECT. Reference tables as dataset.table. Returns CSV."""
        try:
            return _run_sql(sql, level)
        except Exception as e:  # surface errors so the agent can fix its query
            return f"SQL error: {e}"
    tools.append(run_sql)

    if level == "raw":
        @tool
        def list_tables() -> str:
            """List raw source tables and their columns."""
            out = []
            for ds in sorted(DATASETS["raw"]):
                try:
                    for t in bq().list_tables(ds):
                        schema = bq().get_table(t).schema
                        out.append(f"{ds}.{t.table_id}: " + ", ".join(f"{c.name} {c.field_type}" for c in schema))
                except Exception:
                    continue
            return "\n".join(out)
        tools.append(list_tables)
        return tools

    show_endorsement = level == "full"

    @tool
    def list_models() -> str:
        """List dbt models with their dataset, layer, and one-line description."""
        ms = catalog.models()
        if show_endorsement:
            ms = sorted(ms, key=lambda m: (not m["endorsed"], m["layer"] != "marts", m["name"]))
        lines = []
        for m in ms:
            tag = " [ENDORSED]" if (show_endorsement and m["endorsed"]) else ""
            first = m["description"].split(". ")[0][:160]
            lines.append(f"{m['relation']}{tag} ({m['layer']}): {first}")
        return "\n".join(lines)
    tools.append(list_models)

    @tool
    def get_model_docs(name: str) -> str:
        """Full documentation for one dbt model: description, grain, and every column's description."""
        m = catalog.model(name)
        if not m:
            return f"No model named {name}."
        head = f"{m['relation']}" + (" [ENDORSED]" if show_endorsement and m["endorsed"] else "")
        cols = "\n".join(f"- {c}: {v.get('description', '')}" for c, v in m["columns"].items())
        return f"{head}\n{m['description']}\nColumns:\n{cols}"
    tools.append(get_model_docs)

    if level != "full":
        return tools

    @tool
    def list_guides() -> str:
        """List business guides (definitions and rules written by the data team)."""
        return "\n".join(f"{k}: {v.splitlines()[0].lstrip('# ')}" for k, v in catalog.guides().items())
    tools.append(list_guides)

    @tool
    def read_guide(name: str) -> str:
        """Read one business guide in full."""
        return catalog.guides().get(name, f"No guide named {name}.")
    tools.append(read_guide)

    @tool
    def list_metrics() -> str:
        """List governed metrics (with type) and the group-by dimensions MetricFlow accepts, with descriptions."""
        ms = ", ".join(f"{m['name']} ({m['type']})" for m in catalog.metrics())
        dims = "\n".join(f"- {k}: {v}" if v else f"- {k}" for k, v in catalog.dimension_docs().items())
        return (f"Metrics: {ms}\n\nTime dimensions: metric_time__day, __week, __month, __quarter, __year\n\n"
                f"Dimensions:\n{dims}")
    tools.append(list_metrics)

    @tool
    def query_metrics(metrics: str, group_by: str = "", where: str = "", start_time: str = "",
                      end_time: str = "", order_by: str = "", limit: int = 100) -> str:
        """Query governed metrics through MetricFlow. Preferred over SQL for any listed metric.
        metrics: comma-separated metric names. group_by: comma-separated, e.g. metric_time__month,customer__region.
        where: MetricFlow filter, e.g. {{ Dimension('customer__motion') }} = 'enterprise'.
        start_time/end_time: ISO dates bounding metric_time. order_by: e.g. -metric_time__month."""
        with tempfile.NamedTemporaryFile(suffix=".csv") as f:
            cmd = ["mf", "query", "--metrics", metrics, "--csv", f.name, "--limit", str(limit)]
            for flag, val in (("--group-by", group_by), ("--where", where), ("--start-time", start_time),
                              ("--end-time", end_time), ("--order", order_by)):
                if val:
                    cmd += [flag, val]
            p = subprocess.run(cmd, cwd=DBT_DIR, capture_output=True, text=True, timeout=300)
            if p.returncode != 0:
                return f"MetricFlow error:\n{(p.stderr or p.stdout)[-2000:]}"
            return open(f.name).read() or p.stdout[-2000:]
    tools.append(query_metrics)
    return tools
