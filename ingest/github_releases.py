"""dlt pipeline: REAL GitHub releases for the upstream LangChain repos -> raw_github.releases.

  uv run python ingest/github_releases.py                 # BigQuery (uses ADC + GCP_PROJECT)
  uv run python ingest/github_releases.py --duckdb        # local test
Set GITHUB_TOKEN to avoid the 60 requests/hour anonymous limit.
"""
import argparse
import os

import dlt
import requests

REPOS = ["langchain-ai/langchain", "langchain-ai/langgraph", "langchain-ai/deepagents", "langchain-ai/langsmith-sdk"]


@dlt.resource(name="releases", write_disposition="merge", primary_key="id")
def releases(max_pages: int = 30):
    headers = {"Accept": "application/vnd.github+json"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    for repo in REPOS:
        url = f"https://api.github.com/repos/{repo}/releases?per_page=100"
        for _ in range(max_pages):
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            for rel in r.json():
                yield {"id": rel["id"], "repo": repo, "tag_name": rel["tag_name"], "name": rel["name"],
                       "prerelease": rel["prerelease"], "published_at": rel["published_at"]}
            url = r.links.get("next", {}).get("url")
            if not url:
                break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duckdb", action="store_true")
    ap.add_argument("--max-pages", type=int, default=30)
    a = ap.parse_args()
    pipe = dlt.pipeline(pipeline_name="github_releases",
                        destination="duckdb" if a.duckdb else "bigquery",
                        dataset_name="raw_github")
    print(pipe.run(releases(a.max_pages)))


if __name__ == "__main__":
    main()
