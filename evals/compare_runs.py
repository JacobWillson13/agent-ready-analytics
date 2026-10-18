"""Compare two benchmark runs question by question: did a context change help, and did it break anything?

  uv run python evals/compare_runs.py evals/results/phase2 evals/results/phase2-v2 --levels docs full

Differences are paired by question, with a question-clustered bootstrap interval. Questions that changed
are listed so a gain on the targeted questions can be told apart from a regression elsewhere.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

B = 2000


def load(d: Path) -> pd.DataFrame:
    return pd.DataFrame([json.loads(l) for l in (d / "runs.jsonl").read_text().splitlines() if l.strip()])


def short(m: str) -> str:
    return {"anthropic:claude-haiku-5-5": "Haiku", "ollama:gemma4:26b": "Gemma"}.get(m, m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("--levels", nargs="+", default=["docs", "full"])
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    b, c = load(a.before), load(a.after)
    lines = [f"# {a.after.name} vs {a.before.name}", "",
             "| Model | Level | Before | After | Change (pts) | 95% CI | Steps capped before | after |",
             "|---|---|---|---|---|---|---|---|"]
    changed = []
    for model in sorted(set(b.model) & set(c.model)):
        for level in a.levels:
            pb = b[(b.model == model) & (b.level == level)]
            pc = c[(c.model == model) & (c.level == level)]
            qb, qc = pb.groupby("qid").correct.mean(), pc.groupby("qid").correct.mean()
            common = qb.index.intersection(qc.index)
            if not len(common):
                continue
            d = (qc[common] - qb[common]).to_numpy()
            bs = d[rng.integers(0, len(d), size=(B, len(d)))].mean(axis=1)
            cap = lambda x: 100 * (x.status == "recursion_limit").mean()
            lines.append(f"| {short(model)} | {level} | {100 * qb[common].mean():.1f} | {100 * qc[common].mean():.1f} | "
                         f"{100 * d.mean():+.1f} | {100 * np.percentile(bs, 2.5):+.1f} to {100 * np.percentile(bs, 97.5):+.1f} | "
                         f"{cap(pb):.1f}% | {cap(pc):.1f}% |")
            for q in common:
                if abs(qc[q] - qb[q]) > 1e-9:
                    changed.append((short(model), level, q, qb[q], qc[q]))
    lines += ["", "Questions that changed (share of runs correct):", ""]
    lines += [f"- {m} {lvl} `{q}`: {x:.2f} to {y:.2f}" for m, lvl, q, x, y in sorted(changed, key=lambda r: r[4] - r[3])]
    out = "\n".join(lines)
    (a.after / f"compare_vs_{a.before.name}.md").write_text(out)
    print(out)


if __name__ == "__main__":
    main()
