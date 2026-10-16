"""Run the golden questions against one or more context levels as LangSmith experiments.

  uv run python evals/run_evals.py --levels raw docs full
  uv run python evals/run_evals.py --levels full --out evals/results/pr.json      # CI
Needs LANGSMITH_API_KEY, ANTHROPIC_API_KEY, GCP credentials, and a parsed dbt project (dbt parse).
"""
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from langsmith import Client, evaluate

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.graph import ask  # noqa: E402
from agent.settings import MODEL  # noqa: E402
from evals.scoring import score  # noqa: E402

HERE = Path(__file__).parent


def golden(split: str = "core") -> list[dict]:
    qs = [json.loads(l) for l in (HERE / "golden.jsonl").read_text().splitlines() if l.strip()]
    return qs if split == "all" else [q for q in qs if q.get("split", "core") == split]


def ensure_dataset(client: Client, qs: list[dict]) -> str:
    digest = hashlib.sha1(json.dumps(qs, sort_keys=True).encode()).hexdigest()[:8]
    name = f"lanternfly-golden-{digest}"
    if not client.has_dataset(dataset_name=name):
        ds = client.create_dataset(name, description="Lanternfly data agent golden questions (answers from generator truth)")
        client.create_examples(dataset_id=ds.id, examples=[
            {"inputs": {"question": q["question"]},
             "outputs": {k: q[k] for k in ("id", "answer", "kind", "tol", "traps")}} for q in qs])
    return name


def correct(outputs: dict, reference_outputs: dict) -> dict:
    ok, why = score(outputs.get("answer", ""), reference_outputs["answer"], reference_outputs["kind"],
                    reference_outputs["tol"])
    return {"key": "correct", "score": int(ok), "comment": why}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", nargs="+", default=["raw", "docs", "full"])
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--repetitions", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--split", choices=["core", "holdout", "all"], default="core")
    ap.add_argument("--out", type=Path, default=HERE / "results" / "latest.json")
    a = ap.parse_args()
    client = Client()
    qs = golden(a.split)
    dataset = ensure_dataset(client, qs)
    summary = {}
    for level in a.levels:
        res = evaluate(lambda inputs, lvl=level: {"answer": ask(inputs["question"], lvl, a.model)},
                       data=dataset, evaluators=[correct], experiment_prefix=f"context-{level}" + ("" if a.split == "core" else f"-{a.split}"),
                       metadata={"context_level": level, "split": a.split, "model": a.model}, num_repetitions=a.repetitions,
                       max_concurrency=a.concurrency, client=client)
        by_q, by_trap = defaultdict(list), defaultdict(list)
        for row in res:
            ref = row["example"].outputs
            s = row["evaluation_results"]["results"][0].score
            by_q[ref["id"]].append(s)
            for t in ref["traps"]:
                by_trap[t].append(s)
        acc = sum(sum(v) for v in by_q.values()) / sum(len(v) for v in by_q.values())
        summary[level] = dict(accuracy=round(acc, 3), experiment=res.experiment_name,
                              per_question={k: sum(v) / len(v) for k, v in by_q.items()},
                              per_trap={k: round(sum(v) / len(v), 3) for k, v in by_trap.items()})
        print(f"{level:5s} accuracy {acc:.1%}  ({res.experiment_name})")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
