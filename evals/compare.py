"""Compare a PR eval run to the committed baseline and write a markdown PR comment.

  python evals/compare.py --baseline evals/baseline.json --current evals/results/pr.json --out comment.md
Exits 1 if full-context accuracy drops by more than --max-drop.
"""
import argparse
import json
import sys
from pathlib import Path


def run_stats(experiment: str) -> dict | None:
    """Tokens, cost, and p50 latency per question for one LangSmith experiment (None if unavailable)."""
    try:
        from langsmith import Client
        p = Client().read_project(project_name=experiment, include_stats=True)
        n = p.run_count or 1
        lat = p.latency_p50
        return dict(tokens=(p.total_tokens or 0) / n, cost=float(p.total_cost or 0) / n,
                    latency=lat.total_seconds() if hasattr(lat, "total_seconds") else float(lat or 0))
    except Exception:
        return None


def pct_change(before: float, after: float) -> str:
    if not before:
        return "n/a"
    d = (after - before) / before
    return "no change" if abs(d) < 0.005 else f"{d:+.0%}"


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
        acc_change = "no change" if abs(drop) < 0.0005 else f"{-drop * 100:+.1f} pts"
        lines += ["| | Baseline | This PR | Change |", "|---|---|---|---|",
                  f"| Accuracy | {base['accuracy']:.1%} | {cur['accuracy']:.1%} | {acc_change} |"]
        bs, cs = run_stats(base["experiment"]), run_stats(cur["experiment"])
        if bs and cs:
            lines += [f"| Tokens / question | {bs['tokens']:,.0f} | {cs['tokens']:,.0f} | {pct_change(bs['tokens'], cs['tokens'])} |",
                      f"| Cost / question | ${bs['cost']:.3f} | ${cs['cost']:.3f} | {pct_change(bs['cost'], cs['cost'])} |",
                      f"| p50 latency | {bs['latency']:.1f}s | {cs['latency']:.1f}s | {pct_change(bs['latency'], cs['latency'])} |"]
        changed = [(q, base["per_question"].get(q), s) for q, s in cur["per_question"].items()
                   if base["per_question"].get(q) != s]
        if changed:
            lines += ["", "Questions that changed:", ""] + [f"- `{q}`: {b} to {s}" for q, b, s in changed]
    lines += ["", f"LangSmith experiment: `{cur['experiment']}`"]
    a.out.write_text("\n".join(lines))
    print("\n".join(lines))
    sys.exit(1 if drop > a.max_drop else 0)


if __name__ == "__main__":
    main()
