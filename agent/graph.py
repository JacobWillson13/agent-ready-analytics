from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

from . import catalog
from .prompts import system_prompt
from .settings import MODEL
from .tools import build_tools

AS_OF = "2026-10-14"


def context_index() -> str:
    """Compact map of governed metrics and guides, injected into the full-context prompt.
    Saves the agent a discovery round trip on every question."""
    metrics = "\n".join(f"- {m['name']}: {m['description']}" for m in catalog.metrics())
    guides = "\n".join(f"- {k}: {v.splitlines()[0].lstrip('# ')}" for k, v in catalog.guides().items())
    return f"Governed metrics:\n{metrics}\n\nGuides (read_guide):\n{guides}"


def build_agent(level: str = "full", model: str = MODEL):
    # Newer Claude models reject non-default temperature; eval variance is handled with repetitions instead.
    llm = init_chat_model(model, max_tokens=4096)
    return create_agent(llm, build_tools(level), system_prompt=system_prompt(level, AS_OF, context_index() if level == "full" else ""),
                        name=f"agent-ready-analytics-{level}")


def ask(question: str, level: str = "full", **config) -> str:
    agent = build_agent(level)
    out = agent.invoke({"messages": [{"role": "user", "content": question}]},
                       config={"recursion_limit": 40, "tags": [f"context:{level}"],
                               "metadata": {"context_level": level}, **config})
    msg = out["messages"][-1]
    return msg.content if isinstance(msg.content, str) else "".join(
        b.get("text", "") for b in msg.content if isinstance(b, dict))
