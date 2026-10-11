"""Load REAL daily PyPI downloads for the upstream LangChain packages into raw_pypi.daily_downloads.

Source: bigquery-public-data.pypi.file_downloads (huge; partitioned by timestamp, clustered by project).
Runs one month per query, dry-runs each first, and hard-caps bytes billed so a mistake can't burn
the 1 TB/month free query tier.

  uv run python ingest/pypi_downloads.py --project $GCP_PROJECT --start 2023-01-01 --end 2026-10-14 --dry-run
  uv run python ingest/pypi_downloads.py --project $GCP_PROJECT --start 2023-01-01 --end 2026-10-14
"""
import argparse
from datetime import date, timedelta

from google.cloud import bigquery

PROJECTS = ["langchain", "langchain-core", "langgraph", "deepagents", "langsmith"]
SQL = """
select file.project as project, date(timestamp) as download_date, count(*) as downloads
from `bigquery-public-data.pypi.file_downloads`
where timestamp >= timestamp(@start) and timestamp < timestamp(@end_excl)
  and file.project in unnest(@projects)
group by 1, 2
"""


def months(start: date, end: date):
    m = start.replace(day=1)
    while m <= end:
        nxt = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        yield max(m, start), min(nxt - timedelta(days=1), end)
        m = nxt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--start", type=date.fromisoformat, default=date(2023, 1, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2026, 10, 14))
    ap.add_argument("--max-gb-per-month", type=float, default=80)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    client = bigquery.Client(project=a.project)
    dest = f"{a.project}.raw_pypi.daily_downloads"
    total_gb, first = 0.0, True
    for s, e in months(a.start, a.end):
        params = [bigquery.ScalarQueryParameter("start", "DATE", s),
                  bigquery.ScalarQueryParameter("end_excl", "DATE", e + timedelta(days=1)),
                  bigquery.ArrayQueryParameter("projects", "STRING", PROJECTS)]
        dry = client.query(SQL, job_config=bigquery.QueryJobConfig(
            query_parameters=params, dry_run=True, use_query_cache=False))
        gb = dry.total_bytes_processed / 1e9
        total_gb += gb
        print(f"{s} to {e}: estimate {gb:,.1f} GB (upper bound; clustering usually bills less)")
        if a.dry_run:
            continue
        cfg = bigquery.QueryJobConfig(
            query_parameters=params, destination=dest,
            write_disposition="WRITE_TRUNCATE" if first else "WRITE_APPEND",
            maximum_bytes_billed=int(a.max_gb_per_month * 1e9))
        job = client.query(SQL, job_config=cfg)
        job.result()
        print(f"   billed {job.total_bytes_billed / 1e9:,.1f} GB")
        first = False
    print(f"total estimate {total_gb:,.0f} GB")


if __name__ == "__main__":
    main()
