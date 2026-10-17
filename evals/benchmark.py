"""Model x context benchmark. One JSONL row per agent execution, plus a run manifest.

  uv run python evals/benchmark.py --run-id smoke --models ollama:gemma4:26b --limit 10 --repetitions 1
  uv run python evals/benchmark.py --run-id phase2 --models anthropic:claude-haiku-5-5 --repetitions 3
  uv run python evals/benchmark.py --run-id phase2 --models ollama:gemma4:26b --repetitions 2

Design choices (see docs/REPORT.md):
- Every (model, level, question, rep) is an independent execution with a fresh agent; no shared state.
- Execution order is shuffled with a fixed seed so time-of-day effects (API load, GPU thermals, warehouse
  caching) do not line up with one condition.
- Failures count: timeouts, recursion-limit hits, tool or API errors, and missing FINAL ANSWER lines are
  recorded and scored wrong, never dropped from the denominator.
- Runs are resumable. Re-running the same command skips executions already in runs.jsonl, so an
  interrupted overnight run continues where it stopped. Different models can run in parallel into the
  same run directory (for example Haiku in one terminal and Gemma in another).
- A hard cost cap stops submitting new API executions once the model's spend reaches --cost-cap.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import platform
import random
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.graph import run  # noqa: E402
from agent.providers import LOCAL_PROVIDERS, provider  # noqa: E402
from agent.settings import AS_OF, LEVELS, OLLAMA_BASE_URL, OLLAMA_MAX_TOKENS, OLLAMA_NUM_CTX, OLLAMA_THINK  # noqa: E402
from evals.scoring import extract, score  # noqa: E402

HERE = Path(__file__).parent
_lock = threading.Lock()


def load_questions(splits: list[str]) -> list[dict]:
    qs = [json.loads(l) for l in (HERE / "golden.jsonl").read_text().splitlines() if l.strip()]
    return [q for q in qs if q.get("split", "core") in splits]


def key(model, level, qid, rep) -> str:
    return f"{model}|{level}|{qid}|{rep}"


def git_sha() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=HERE).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=HERE).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"


def ollama_info(model: str) -> dict:
    import requests
    name = model.split(":", 1)[1]
    info = {"ollama_host": OLLAMA_BASE_URL, "num_ctx": OLLAMA_NUM_CTX, "think": OLLAMA_THINK,
            "max_output_tokens": OLLAMA_MAX_TOKENS, "temperature": 0, "seed": 42}
    try:
        info["ollama_version"] = requests.get(f"{OLLAMA_BASE_URL}/api/version", timeout=10).json().get("version")
        show = requests.post(f"{OLLAMA_BASE_URL}/api/show", json={"model": name}, timeout=30).json()
        d = show.get("details", {})
        info.update(quantization=d.get("quantization_level"), parameter_size=d.get("parameter_size"),
                    family=d.get("family"), format=d.get("format"), capabilities=show.get("capabilities"))
        tags = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10).json().get("models", [])
        info["digest"] = next((t.get("digest") for t in tags if t.get("name") in (name, f"{name}:latest")), None)
    except Exception as e:
        info["error"] = f"could not query Ollama: {e}"
    return info


def write_manifest(out_dir: Path, args, questions: list[dict]):
    path = out_dir / "manifest.json"
    man = json.loads(path.read_text()) if path.exists() else {"run_id": args.run_id, "models": {}, "invocations": []}
    golden_bytes = (HERE / "golden.jsonl").read_bytes()
    pkgs = {}
    for p in ("langchain", "langchain-core", "langchain-anthropic", "langchain-ollama", "langgraph", "langsmith",
              "dbt-core", "dbt-metricflow", "google-cloud-bigquery"):
        try:
            pkgs[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            pkgs[p] = None
    for m in args.models:
        entry = {"provider": provider(m), "model": m}
        if provider(m) in LOCAL_PROVIDERS:
            entry.update(ollama_info(m))
        man["models"][m] = entry
    man["invocations"].append(dict(
        started_at=datetime.now(timezone.utc).isoformat(), argv=sys.argv[1:], git_sha=git_sha(), as_of=AS_OF,
        golden_sha256=hashlib.sha256(golden_bytes).hexdigest(), n_questions=len(questions),
        splits=args.splits, levels=args.levels, repetitions=args.repetitions, seed=args.seed,
        timeout_s=args.timeout, recursion_limit=args.recursion_limit, packages=pkgs,
        host=platform.node(), python=platform.python_version()))
    path.write_text(json.dumps(man, indent=2))


def preflight(models: list[str]):
    """Stop before any execution if credentials or services are missing, so a bad environment cannot
    write a run full of failures. The env file uses shell exports: `source ~/.config/ara/env` first."""
    import os
    problems = []
    if not os.getenv("GCP_PROJECT"):
        problems.append("GCP_PROJECT is not set")
    if any(provider(m) == "anthropic" for m in models) and not os.getenv("ANTHROPIC_API_KEY"):
        problems.append("ANTHROPIC_API_KEY is not set")
    if os.getenv("LANGSMITH_TRACING", "").lower() == "true" and not os.getenv("LANGSMITH_API_KEY"):
        problems.append("LANGSMITH_TRACING is true but LANGSMITH_API_KEY is not set")
    if any(provider(m) in LOCAL_PROVIDERS for m in models):
        import requests
        try:
            names = [t["name"] for t in requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5).json()["models"]]
            for m in models:
                if provider(m) in LOCAL_PROVIDERS and m.split(":", 1)[1] not in names:
                    problems.append(f"Ollama does not have {m.split(':', 1)[1]}; run: ollama pull {m.split(':', 1)[1]}")
        except Exception as e:
            problems.append(f"Ollama is not reachable at {OLLAMA_BASE_URL}: {e}")
    if problems:
        sys.exit("Preflight failed, nothing was run:\n  - " + "\n  - ".join(problems)
                 + "\nLoad your environment with: source ~/.config/ara/env")


def execute(task: dict, args) -> dict:
    q, model, level, rep = task["q"], task["model"], task["level"], task["rep"]
    row = dict(run_id=args.run_id, model=model, level=level, qid=q["id"], split=q.get("split", "core"), rep=rep,
               traps=q["traps"], expected=q["answer"], kind=q["kind"],
               started_at=datetime.now(timezone.utc).isoformat())
    try:
        res = run(q["question"], level, model, recursion_limit=args.recursion_limit,
                  metadata={"qid": q["id"], "rep": rep, "run_id": args.run_id, "split": row["split"]},
                  tags=[f"run:{args.run_id}"])
        ok, why = score(res["answer"], q["answer"], q["kind"], q["tol"])
        row.update(res, status="ok" if extract(res["answer"]) is not None else "no_final_answer",
                   final_answer=extract(res["answer"]), correct=int(ok), reason=why)
        row["answer_tail"] = res["answer"][-500:]
        # Ollama silently drops the oldest context past num_ctx; flag runs that came close.
        row["context_near_limit"] = int(provider(model) in LOCAL_PROVIDERS
                                        and res["max_prompt_tokens"] >= 0.95 * OLLAMA_NUM_CTX)
        del row["answer"]
    except Exception as e:
        name = type(e).__name__
        status = "recursion_limit" if "Recursion" in name else "error"
        row.update(status=status, correct=0, reason=f"{name}: {str(e)[:300]}",
                   traceback=traceback.format_exc()[-1500:])
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--levels", nargs="+", default=list(LEVELS), choices=list(LEVELS))
    ap.add_argument("--splits", nargs="+", default=["core", "holdout", "hard"])
    ap.add_argument("--repetitions", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0, help="first N questions only (smoke tests)")
    ap.add_argument("--qids", nargs="*", default=[], help="only these question ids")
    ap.add_argument("--concurrency", type=int, default=4, help="parallel executions for API models")
    ap.add_argument("--local-concurrency", type=int, default=1, help="parallel executions for local models")
    ap.add_argument("--timeout", type=float, default=900, help="wall-clock seconds per execution")
    ap.add_argument("--recursion-limit", type=int, default=60, help="LangGraph steps; about half are tool calls")
    ap.add_argument("--cost-cap", type=float, default=8.0, help="USD per API model, across the whole run id")
    ap.add_argument("--seed", type=int, default=20261016)
    a = ap.parse_args()

    preflight(a.models)
    questions = load_questions(a.splits)
    if a.qids:
        questions = [q for q in questions if q["id"] in set(a.qids)]
    if a.limit:
        questions = questions[: a.limit]
    out_dir = HERE / "results" / a.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_path = out_dir / "runs.jsonl"
    write_manifest(out_dir, a, questions)

    done, spent = set(), {}
    if runs_path.exists():
        for line in runs_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add(key(r["model"], r["level"], r["qid"], r["rep"]))
                spent[r["model"]] = spent.get(r["model"], 0.0) + (r.get("cost_usd") or 0.0)

    for model in a.models:
        tasks = [dict(q=q, model=model, level=lvl, rep=rep)
                 for q, lvl, rep in itertools.product(questions, a.levels, range(a.repetitions))
                 if key(model, lvl, q["id"], rep) not in done]
        random.Random(f"{a.seed}|{model}").shuffle(tasks)
        local = provider(model) in LOCAL_PROVIDERS
        workers = a.local_concurrency if local else a.concurrency
        total = len(tasks)
        print(f"\n{model}: {total} executions to run ({len(questions)} questions x {len(a.levels)} levels x "
              f"{a.repetitions} reps, minus completed), {workers} parallel, spent so far ${spent.get(model, 0):.2f}")
        if not total:
            continue
        stop = threading.Event()
        n_done, n_correct, t_start = 0, 0, time.time()

        def handle(row):
            nonlocal n_done, n_correct
            with _lock:
                with runs_path.open("a") as f:
                    f.write(json.dumps(row, default=str) + "\n")
                n_done += 1
                n_correct += row["correct"]
                spent[model] = spent.get(model, 0.0) + (row.get("cost_usd") or 0.0)
                if not local and spent[model] >= a.cost_cap:
                    stop.set()
                rate = (time.time() - t_start) / n_done
                print(f"[{n_done}/{total}] {row['level']:4s} {row['qid']:24s} rep{row['rep']} "
                      f"{'OK ' if row['correct'] else 'BAD'} {row['status']:15s} "
                      f"acc {n_correct / n_done:.0%}  ${spent[model]:.2f}  eta {rate * (total - n_done) / 60:.0f} min",
                      flush=True)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            it = iter(tasks)
            inflight = {}
            while True:
                while not stop.is_set() and len(inflight) < workers:
                    t = next(it, None)
                    if t is None:
                        break
                    inflight[pool.submit(execute, t, a)] = (t, time.time())
                if not inflight:
                    break
                time.sleep(0.5)
                for fut, (t, t0) in list(inflight.items()):
                    if fut.done():
                        del inflight[fut]
                        handle(fut.result())
                    elif time.time() - t0 > a.timeout:
                        # The worker thread cannot be killed; its client timeout ends it. Record the timeout now.
                        del inflight[fut]
                        q = t["q"]
                        handle(dict(run_id=a.run_id, model=model, level=t["level"], qid=q["id"],
                                    split=q.get("split", "core"), rep=t["rep"], traps=q["traps"],
                                    expected=q["answer"], kind=q["kind"], status="timeout", correct=0,
                                    reason=f"exceeded {a.timeout:.0f}s", latency_s=a.timeout,
                                    started_at=datetime.fromtimestamp(t0, timezone.utc).isoformat()))
        if stop.is_set():
            print(f"STOPPED {model}: cost cap ${a.cost_cap:.2f} reached. Raise --cost-cap to continue.")
    print(f"\nresults: {runs_path}")


if __name__ == "__main__":
    main()
