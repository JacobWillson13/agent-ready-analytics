import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = Path(os.getenv("ARA_DBT_DIR", ROOT / "dbt"))
GUIDES_DIR = Path(os.getenv("ARA_GUIDES_DIR", ROOT / "guides"))
GCP_PROJECT = os.getenv("GCP_PROJECT", "")
MODEL = os.getenv("ARA_AGENT_MODEL", "anthropic:claude-sonnet-5-5")
MAX_BYTES_BILLED = int(float(os.getenv("ARA_MAX_GB_PER_QUERY", "2")) * 1e9)
MAX_ROWS = 200

# Local models served by Ollama. Ollama's default context window is 4k tokens, which silently truncates
# tool results, so the benchmark always sets it explicitly and records it in the run manifest.
OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_NUM_CTX = int(os.getenv("ARA_OLLAMA_NUM_CTX", "32768"))
REQUEST_TIMEOUT_S = float(os.getenv("ARA_REQUEST_TIMEOUT_S", "300"))
# Thinking mode for local models: "off" (default) matches the API model, which runs without extended
# thinking; thinking tokens also count against the output cap. "on" keeps reasoning out of the message history.
OLLAMA_THINK = os.getenv("ARA_OLLAMA_THINK", "off").lower()
OLLAMA_MAX_TOKENS = int(os.getenv("ARA_OLLAMA_MAX_TOKENS", "8192"))


def _as_of() -> str:
    """The data snapshot date. One source of truth: dbt's as_of_date var (override with ARA_AS_OF)."""
    if os.getenv("ARA_AS_OF"):
        return os.environ["ARA_AS_OF"]
    m = re.search(r'as_of_date:\s*"?(\d{4}-\d{2}-\d{2})', (DBT_DIR / "dbt_project.yml").read_text())
    if not m:
        raise RuntimeError("as_of_date not found in dbt_project.yml; set ARA_AS_OF")
    return m.group(1)


AS_OF = _as_of()

# Context levels used by the eval. Each level adds one layer of context.
LEVELS = ("raw", "docs", "full")
DATASETS = {
    "raw": {"raw_salesforce", "raw_app", "raw_segment", "raw_metronome", "raw_support", "raw_pypi", "raw_github"},
    "docs": {"raw_salesforce", "raw_app", "raw_segment", "raw_metronome", "raw_support", "raw_pypi", "raw_github",
             "staging", "intermediate", "marts", "seeds"},
    "full": {"staging", "intermediate", "marts", "seeds", "raw_pypi", "raw_github"},
}
# eval_truth is never in any allowlist; the agent's service account should not be able to read it either.
