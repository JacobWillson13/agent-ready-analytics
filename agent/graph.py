from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

from .prompts import system_prompt
from .settings import MODEL
from .tools import build_tools

AS_OF = "2026-10-14"


def build_agent(level: str = "full", model: str = MODEL):
    llm = init_chat_model(model, temperature=0, max_tokens=4096)
    return create_agent(llm, build_tools(level), system_prompt=system_prompt(level, AS_OF),
                        name=f"agent-ready-analytics-{level}")


def ask(question: str, level: str = "full", **config) -> str:
    agent = build_agent(level)
    out = agent.invoke({"messages": [{"role": "user", "content": question}]},
                       config={"recursion_limit": 40, "tags": [f"context:{level}"],
                               "metadata": {"context_level": level}, **config})
    msg = out["messages"][-1]
    return msg.content if isinstance(msg.content, str) else "".join(
        b.get("text", "") for b in msg.content if isinstance(b, dict))
