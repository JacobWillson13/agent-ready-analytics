"""uv run python -m agent "What was total ARR at the end of September 2026?" [--level full|docs|raw] [--model ollama:gemma4:26b]"""
import argparse

from .graph import ask
from .settings import MODEL


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--level", choices=["raw", "docs", "full"], default="full")
    ap.add_argument("--model", default=MODEL)
    a = ap.parse_args()
    print(ask(a.question, a.level, a.model))


if __name__ == "__main__":
    main()
