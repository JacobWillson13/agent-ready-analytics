from __future__ import annotations

import re
import time

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from . import catalog
from .prompts import system_prompt
from .providers import call_cost, make_llm
from .settings import AS_OF, MODEL
from .tools import build_tools

FINAL_RE = re.compile(r"FINAL ANSWER:", re.IGNORECASE)
NUDGE = "Give your final answer now, as the last line, in exactly this form: FINAL ANSWER: <value>"


def context_index() -> str:
    """Compact map of governed metrics and guides, injected into the full-context prompt.
    Saves the agent a discovery round trip on every question."""
    metrics = "\n".join(f"- {m['name']}: {m['description']}" for m in catalog.metrics())
    guides = "\n".join(f"- {k}: {v.splitlines()[0].lstrip('# ')}" for k, v in catalog.guides().items())
    return f"Governed metrics:\n{metrics}\n\nGuides (read_guide):\n{guides}"


def build_agent(level: str = "full", model: str = MODEL):
    return create_agent(make_llm(model), build_tools(level),
                        system_prompt=system_prompt(level, AS_OF, context_index() if level == "full" else ""),
                        name=f"agent-ready-analytics-{level}")


def _text(msg) -> str:
    c = msg.content
    return c if isinstance(c, str) else "".join(b.get("text", "") for b in c if isinstance(b, dict))


def run(question: str, level: str = "full", model: str = MODEL, recursion_limit: int = 40, **config) -> dict:
    """Answer one question and return the answer plus the measurements the benchmark records."""
    agent = build_agent(level, model)
    t0 = time.perf_counter()
    out = agent.invoke({"messages": [{"role": "user", "content": question}]},
                       config={"recursion_limit": recursion_limit,
                               "tags": [f"context:{level}", f"model:{model}"] + config.pop("tags", []),
                               "metadata": {"context_level": level, "model": model, **config.pop("metadata", {})},
                               **config})
    # One uniform follow-up, for every model, when the agent stops without the required answer line. The
    # benchmark measures analysis, not format compliance; the retry is recorded so its effect can be reported.
    format_retry = 0
    if not FINAL_RE.search(_text(out["messages"][-1])):
        format_retry = 1
        out = agent.invoke({"messages": out["messages"] + [HumanMessage(NUDGE)]},
                           config={"recursion_limit": 10, "tags": ["format_retry"]})
    latency = time.perf_counter() - t0
    ai = [m for m in out["messages"] if isinstance(m, AIMessage)]
    usages = [m.usage_metadata or {} for m in ai]
    return dict(
        answer=_text(out["messages"][-1]),
        latency_s=round(latency, 2),
        llm_calls=len(ai),
        tool_calls=sum(len(m.tool_calls or []) for m in ai),
        input_tokens=sum(u.get("input_tokens", 0) or 0 for u in usages),
        output_tokens=sum(u.get("output_tokens", 0) or 0 for u in usages),
        max_prompt_tokens=max((u.get("input_tokens", 0) or 0 for u in usages), default=0),
        cost_usd=round(sum(call_cost(model, u) for u in usages), 6),
        format_retry=format_retry,
    )


def ask(question: str, level: str = "full", model: str = MODEL, **config) -> str:
    return run(question, level, model, **config)["answer"]
