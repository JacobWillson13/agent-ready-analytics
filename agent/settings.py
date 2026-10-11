import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = Path(os.getenv("ARA_DBT_DIR", ROOT / "dbt"))
GUIDES_DIR = Path(os.getenv("ARA_GUIDES_DIR", ROOT / "guides"))
GCP_PROJECT = os.getenv("GCP_PROJECT", "")
MODEL = os.getenv("ARA_AGENT_MODEL", "anthropic:claude-sonnet-5-5")
MAX_BYTES_BILLED = int(float(os.getenv("ARA_MAX_GB_PER_QUERY", "2")) * 1e9)
MAX_ROWS = 200

# Context levels used by the eval. Each level adds one layer of context.
LEVELS = ("raw", "docs", "full")
DATASETS = {
    "raw": {"raw_salesforce", "raw_app", "raw_segment", "raw_metronome", "raw_support", "raw_pypi", "raw_github"},
    "docs": {"raw_salesforce", "raw_app", "raw_segment", "raw_metronome", "raw_support", "raw_pypi", "raw_github",
             "staging", "intermediate", "marts", "seeds"},
    "full": {"staging", "intermediate", "marts", "seeds", "raw_pypi", "raw_github"},
}
# eval_truth is never in any allowlist; the agent's service account should not be able to read it either.
