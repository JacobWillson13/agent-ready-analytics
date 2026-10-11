"""Compare a PR eval run to the committed baseline and write a markdown PR comment.

  python evals/compare.py --baseline evals/baseline.json --current evals/results/pr.json --out comment.md
Exits 1 if full-context accuracy drops by more than --max-drop.
"""
import argparse
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--current", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--level", default="full")
    ap.add_argument("--max-drop", type=float, default=0.04)
    a = ap.parse_args()
    base = json.loads(a.baseline.read_text())[a.level] if a.baseline.exists() else None
    cur = json.loads(a.current.read_text())[a.level]
    lines = [f"### Context eval ({a.level} context)", ""]
    if base is None:
        lines.append(f"No baseline yet. Accuracy: **{cur['accuracy']:.1%}**.")
        drop = 0
    else:
        drop = base["accuracy"] - cur["accuracy"]
        lines += [f"| | Baseline | This PR | Change |", "|---|---|---|---|",
                  f"| Accuracy | {base['accuracy']:.1%} | {cur['accuracy']:.1%} | {-drop:+.1%} |", ""]
        changed = [(q, base["per_question"].get(q), s) for q, s in cur["per_question"].items()
                   if base["per_question"].get(q) != s]
        if changed:
            lines += ["Questions that changed:", ""] + [f"- `{q}`: {b} to {s}" for q, b, s in changed]
    lines += ["", f"LangSmith experiment: `{cur['experiment']}`"]
    a.out.write_text("\n".join(lines))
    print("\n".join(lines))
    sys.exit(1 if drop > a.max_drop else 0)


if __name__ == "__main__":
    main()
