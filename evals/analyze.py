"""Analyze a benchmark run: accuracy with uncertainty, paired contrasts, a mixed-effects model, and figures.

  uv run python evals/analyze.py evals/results/phase2            # writes summary.md, summary.json, figures
  uv run python evals/analyze.py evals/results/phase2 --figures docs/figures

Uncertainty is clustered by question: repeated runs of one question are correlated, so the bootstrap
resamples questions (keeping all of a question's runs together), never individual runs.
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

LEVEL_ORDER = ["raw", "docs", "full"]
SPLIT_GROUPS = {"all": ["core", "holdout", "hard"], "original": ["core", "holdout"], "hard": ["hard"]}
B = 2000
NI_MARGIN = 10.0  # percentage points: the local model "matches" the API model only if the CI excludes -10

# Reference palette (validated: CVD and contrast checks pass for these two series on the light surface).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0"
SEQ = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#104281"]


def short(model: str) -> str:
    name = model.split(":", 1)[1]
    return {"claude-haiku-5-5": "Claude Haiku 5.5", "gemma4:26b": "Gemma 4 26B (local)"}.get(name, name)


def load(run_dir: Path) -> pd.DataFrame:
    rows = [json.loads(l) for l in (run_dir / "runs.jsonl").read_text().splitlines() if l.strip()]
    df = pd.DataFrame(rows)
    df["level"] = pd.Categorical(df["level"], LEVEL_ORDER, ordered=True)
    for c in ("input_tokens", "output_tokens", "tool_calls", "cost_usd", "latency_s"):
        if c not in df:
            df[c] = np.nan
    return df


def boot_mean(per_q: pd.Series, rng) -> tuple[float, float, float]:
    """per_q: one value per question (that question's mean over reps). Returns mean and 95% CI in points."""
    v = per_q.to_numpy(dtype=float)
    if len(v) == 0:
        return (np.nan, np.nan, np.nan)
    idx = rng.integers(0, len(v), size=(B, len(v)))
    bs = v[idx].mean(axis=1)
    return 100 * v.mean(), 100 * np.percentile(bs, 2.5), 100 * np.percentile(bs, 97.5)


def _order(df: pd.DataFrame) -> pd.DataFrame:
    """Sort rows raw -> docs -> full regardless of dtype (groupby can drop the categorical order)."""
    return df.assign(_o=df["level"].astype(str).map(LEVEL_ORDER.index)).sort_values("_o").drop(columns="_o")


def accuracy_table(df, rng) -> pd.DataFrame:
    out = []
    for group, splits in SPLIT_GROUPS.items():
        sub = df[df.split.isin(splits)]
        for (model, level), g in sub.groupby(["model", "level"], observed=True):
            per_q = g.groupby("qid").correct.mean()
            m, lo, hi = boot_mean(per_q, rng)
            out.append(dict(group=group, model=model, level=level, n_questions=len(per_q), n_runs=len(g),
                            accuracy=m, ci_low=lo, ci_high=hi))
    return pd.DataFrame(out)


def paired(df, a: dict, b: dict, rng) -> tuple[float, float, float, int]:
    """Mean of (B - A) per question, over questions present in both, with clustered bootstrap CI."""
    qa = df[(df.model == a["model"]) & (df.level == a["level"])].groupby("qid").correct.mean()
    qb = df[(df.model == b["model"]) & (df.level == b["level"])].groupby("qid").correct.mean()
    common = qa.index.intersection(qb.index)
    m, lo, hi = boot_mean(qb[common] - qa[common], rng)
    return m, lo, hi, len(common)


def contrasts(df, rng) -> pd.DataFrame:
    out = []
    models = sorted(df.model.unique())
    for group, splits in SPLIT_GROUPS.items():
        sub = df[df.split.isin(splits)]
        for model in models:
            for x, y in (("raw", "docs"), ("raw", "full"), ("docs", "full")):
                m, lo, hi, n = paired(sub, dict(model=model, level=x), dict(model=model, level=y), rng)
                out.append(dict(group=group, contrast=f"{y} - {x}", model=model, diff=m, ci_low=lo, ci_high=hi, n=n))
        if len(models) == 2:
            api, local = sorted(models, key=lambda s: s.startswith("ollama:"))
            for level in LEVEL_ORDER:
                m, lo, hi, n = paired(sub, dict(model=api, level=level), dict(model=local, level=level), rng)
                out.append(dict(group=group, contrast=f"{short(local)} - {short(api)}", model=level,
                                diff=m, ci_low=lo, ci_high=hi, n=n))
    return pd.DataFrame(out)


def mixed_model(df) -> str:
    """Logistic model with a random intercept per question: correct ~ model * level + (1 | question).
    Fit by variational Bayes (statsmodels); coefficients are on the log-odds scale."""
    try:
        from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
    except ImportError:
        return "statsmodels not installed; skipped."
    d = df.copy()
    d["level"] = d["level"].astype(str)
    api = sorted(d.model.unique(), key=lambda s: s.startswith("ollama:"))[0]
    d["model_c"] = np.where(d.model == api, "a_api", "b_" + d.model.str.replace(r"\W", "_", regex=True))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mod = BinomialBayesMixedGLM.from_formula(
            "correct ~ C(model_c) * C(level, Treatment('raw'))", {"question": "0 + C(qid)"}, d)
        res = mod.fit_vb()
    names = res.model.exog_names
    lines = ["| Term | Estimate (log-odds) | SD | Approx. 95% interval |", "|---|---|---|---|"]
    for i, n in enumerate(names):
        mean, sd = res.fe_mean[i], res.fe_sd[i]
        label = (n.replace("C(model_c)[T.", "model=").replace("C(level, Treatment('raw'))[T.", "level=")
                 .replace("]", "").replace(":", " x "))
        lines.append(f"| {label} | {mean:+.2f} | {sd:.2f} | {mean - 1.96 * sd:+.2f} to {mean + 1.96 * sd:+.2f} |")
    lines.append(f"\nQuestion random-intercept SD (log-odds): {float(np.exp(res.vcp_mean[0])):.2f}. "
                 f"Reference cell: {short(api)} at raw context.")
    return "\n".join(lines)


def efficiency(df) -> pd.DataFrame:
    g = df.groupby(["model", "level"], observed=True)
    return pd.DataFrame(dict(
        runs=g.size(),
        failure_rate=g.apply(lambda x: 100 * (x.status != "ok").mean(), include_groups=False),
        tool_calls_median=g.tool_calls.median(),
        input_tokens_median=g.input_tokens.median(),
        output_tokens_median=g.output_tokens.median(),
        latency_p50=g.latency_s.median(),
        latency_p95=g.latency_s.quantile(0.95),
        cost_per_question=g.cost_usd.mean(),
        total_cost=g.cost_usd.sum(),
    )).reset_index()


def trap_table(df) -> pd.DataFrame:
    t = df.explode("traps").dropna(subset=["traps"])
    t = t[t.traps != ""]
    tab = t.groupby(["traps", "model", "level"], observed=True).correct.mean().mul(100).unstack(["model", "level"])
    return tab.sort_index()


# ------------------------------------------------------------------------------------------- figures
def _style(plt):
    plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
                         "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                         "text.color": INK, "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True})


def fig_interaction(acc, models, path, plt):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), sharey=True)
    for ax, group, title in zip(axes, ("original", "hard"), ("Original questions (core + holdout)", "Hard questions")):
        sub = acc[acc.group == group]
        for i, model in enumerate(models):
            s = _order(sub[sub.model == model])
            if s.empty:
                continue
            x = np.arange(len(s)) + (i - (len(models) - 1) / 2) * 0.06
            err = [s.accuracy - s.ci_low, s.ci_high - s.accuracy]
            ax.errorbar(x, s.accuracy, yerr=err, color=SERIES[i], lw=2, marker="o", ms=8, capsize=0, elinewidth=1.5,
                        mec=SURFACE, mew=2, label=short(model))
            ax.annotate(f"{s.accuracy.iloc[-1]:.0f}%", (x[-1], s.accuracy.iloc[-1]), xytext=(8, 0),
                        textcoords="offset points", va="center", color=INK2, fontsize=9)
        ax.set_xticks(range(3), ["raw tables", "dbt docs", "full context"])
        ax.set_title(title, loc="left", fontsize=10, color=INK)
        ax.set_xlim(-0.4, 2.5)
    axes[0].set_ylim(0, 105)
    axes[0].set_ylabel("Accuracy (%), 95% CI by question")
    axes[0].legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def fig_efficiency(acc, eff, models, path, plt):
    a = acc[acc.group == "all"].merge(eff, on=["model", "level"])
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), sharey=True)
    for ax, col, label in ((axes[0], "latency_p50", "Median latency per question (s)"),
                           (axes[1], "input_tokens_median", "Median input tokens per question")):
        for i, model in enumerate(models):
            s = _order(a[a.model == model])
            ax.plot(s[col], s.accuracy, color=SERIES[i], lw=1.5, alpha=0.5)
            ax.scatter(s[col], s.accuracy, color=SERIES[i], s=64, edgecolor=SURFACE, linewidth=2, zorder=3,
                       label=short(model))
            for _, r in s.iterrows():
                ax.annotate(str(r.level), (r[col], r.accuracy), xytext=(7, 7 if i == 0 else -13),
                            textcoords="offset points", color=INK2, fontsize=8)
        ax.set_xlabel(label)
    axes[0].set_ylabel("Accuracy, all questions (%)")
    axes[0].set_ylim(0, 105)
    axes[0].legend(frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def fig_traps(traps, models, path, plt):
    from matplotlib.colors import LinearSegmentedColormap
    cols = [(m, l) for m in models for l in LEVEL_ORDER if (m, l) in traps.columns]
    data = traps[cols]
    fig, ax = plt.subplots(figsize=(1.0 * len(cols) + 3.2, 0.36 * len(data) + 1.4))
    ax.grid(False)
    cmap = LinearSegmentedColormap.from_list("seq", SEQ[1:])
    ax.imshow(data.to_numpy(dtype=float), cmap=cmap, vmin=0, vmax=100, aspect="auto")
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data.iat[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8, color=SURFACE if v >= 60 else INK)
    ax.set_yticks(range(len(data)), [t.replace("_", " ") for t in data.index])
    ax.set_xticks(range(len(cols)), [f"{short(m).split(' (')[0]}\n{l}" for m, l in cols], fontsize=8)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("Accuracy (%) on questions that exercise each trap", loc="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


# ------------------------------------------------------------------------------------------- report
def md_table(df: pd.DataFrame, fmt: dict | None = None) -> str:
    fmt = fmt or {}
    cols = list(df.columns)
    out = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(fmt.get(c, "{}").format(r[c]) if pd.notna(r[c]) else "" for c in cols) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--figures", type=Path, default=None, help="default: <run_dir>/figures")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    df = load(a.run_dir)
    models = sorted(df.model.unique(), key=lambda s: s.startswith("ollama:"))
    acc = accuracy_table(df, rng)
    con = contrasts(df, rng)
    eff = efficiency(df)
    traps = trap_table(df)
    mm = mixed_model(df)

    figdir = a.figures or (a.run_dir / "figures")
    figdir.mkdir(parents=True, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _style(plt)
    fig_interaction(acc, models, figdir / "fig1_model_x_context.png", plt)
    fig_efficiency(acc, eff, models, figdir / "fig2_accuracy_vs_cost.png", plt)
    fig_traps(traps, models, figdir / "fig3_traps.png", plt)

    ni = ""
    if len(models) == 2:
        row = con[(con.group == "all") & (con.model == "full") & con.contrast.str.contains(" - ")]
        row = row[~row.contrast.str.startswith(("docs", "full"))]
        if not row.empty:
            r = row.iloc[0]
            verdict = ("meets" if r.ci_low > -NI_MARGIN else "does not meet")
            ni = (f"At full context, {r.contrast} = {r['diff']:+.1f} points (95% CI {r.ci_low:+.1f} to {r.ci_high:+.1f}). "
                  f"With a non-inferiority margin of {NI_MARGIN:.0f} points, the local model {verdict} the bar.")

    acc_show = acc.assign(model=acc.model.map(short), CI=acc.apply(lambda r: f"{r.ci_low:.0f} to {r.ci_high:.0f}", axis=1))
    con_show = con.assign(model=con.model.map(lambda m: short(m) if ":" in m else m),
                          CI=con.apply(lambda r: f"{r.ci_low:+.1f} to {r.ci_high:+.1f}", axis=1))
    eff_show = eff.assign(model=eff.model.map(short))
    status = df.groupby(["model", "status"]).size().unstack(fill_value=0).rename(index=short)
    md = [f"# Benchmark results: {a.run_dir.name}", "",
          f"{df.qid.nunique()} questions, {len(df)} executions, models: {', '.join(map(short, models))}.", "",
          "## Accuracy", "", md_table(acc_show[["group", "model", "level", "n_questions", "n_runs", "accuracy", "CI"]],
                                      {"accuracy": "{:.1f}"}), "",
          "## Paired contrasts (percentage points, question-clustered bootstrap)", "",
          md_table(con_show[["group", "contrast", "model", "diff", "CI", "n"]], {"diff": "{:+.1f}"}), "", ni, "",
          "## Mixed-effects logistic model (all questions)", "", mm, "",
          "## Cost, latency, and tool use", "",
          md_table(eff_show, {"failure_rate": "{:.1f}", "tool_calls_median": "{:.0f}", "input_tokens_median": "{:,.0f}",
                              "output_tokens_median": "{:,.0f}", "latency_p50": "{:.1f}", "latency_p95": "{:.1f}",
                              "cost_per_question": "${:.4f}", "total_cost": "${:.2f}"}), "",
          "## Execution status", "", md_table(status.reset_index()), "",
          "## Accuracy by trap (%)", "", md_table(traps.set_axis([f"{short(m)} {l}" for m, l in traps.columns], axis=1).rename_axis("trap").reset_index(),
                   {f"{short(m)} {l}": "{:.0f}" for m, l in traps.columns}), ""]
    (a.run_dir / "summary.md").write_text("\n".join(md))
    (a.run_dir / "summary.json").write_text(json.dumps(dict(
        accuracy=acc.assign(level=acc.level.astype(str)).to_dict("records"), contrasts=con.to_dict("records"),
        efficiency=eff.assign(level=eff.level.astype(str)).to_dict("records")), indent=2, default=float))
    print("\n".join(md[:40]))
    print(f"\nwrote {a.run_dir / 'summary.md'} and figures in {figdir}")


if __name__ == "__main__":
    main()
