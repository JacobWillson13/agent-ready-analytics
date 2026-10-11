"""uv run python -m agent "What was total ARR at the end of September 2026?" [--level full|docs|raw]"""
import argparse

from .graph import ask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--level", choices=["raw", "docs", "full"], default="full")
    a = ap.parse_args()
    print(ask(a.question, a.level))


if __name__ == "__main__":
    main()
