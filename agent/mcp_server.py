"""MCP server so Claude Code (or any MCP client) can use the data agent and its context tools.

  claude mcp add lanternfly-data -- uv run --directory /path/to/agent-ready-analytics python -m agent.mcp_server
"""
from mcp.server.mcpserver import MCPServer

from . import catalog
from .graph import ask

server = MCPServer("lanternfly-data", instructions="Lanternfly Labs analytics: ask questions, browse endorsed models and metrics.")


@server.tool(description="Ask the Lanternfly data agent a question. Uses governed metrics, endorsed models, and guides.")
def ask_data_agent(question: str) -> str:
    return ask(question, "full", tags=["surface:mcp"])


@server.tool(description="List endorsed dbt models with descriptions.")
def endorsed_models() -> str:
    return "\n".join(f"{m['relation']}: {m['description'][:200]}" for m in catalog.models() if m["endorsed"])


@server.tool(description="List governed metrics.")
def governed_metrics() -> str:
    return "\n".join(f"{m['name']}: {m['description']}" for m in catalog.metrics())


if __name__ == "__main__":
    server.run()
