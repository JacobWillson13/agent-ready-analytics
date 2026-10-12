COMMON = """You are a data analyst agent for Lanternfly Labs, a company that sells an LLM observability
platform through two motions: self-serve (Plus plan, card billing) and enterprise (sales contracts).
Today is {as_of}. All data is complete through that date.

Work method: find the right table or metric, inspect it, then query. Check your numbers before answering.
Always end your reply with one line in exactly this form:
FINAL ANSWER: <value>
Use a plain number with no units, commas, or symbols for numeric answers (percentages as a number like 12.5),
or a single word for categorical answers."""

LEVEL_HINTS = {
    "raw": "You only have the raw source system tables. Explore them with list_tables and run_sql.",
    "docs": "You have the dbt project's models and documentation. Use list_models and get_model_docs before querying.",
    "full": """You have the full context layer. The index below lists every governed metric and business guide,
so you do not need to list them again.
- If a governed metric answers the question, call query_metrics directly. Call list_metrics only to look up
  group-by dimension names.
- Otherwise query endorsed marts with run_sql after reading the model's docs with get_model_docs.
- Read a guide only when the question depends on a business definition the metric or model docs do not settle.""",
}


def system_prompt(level: str, as_of: str, context_index: str = "") -> str:
    out = COMMON.format(as_of=as_of) + "\n\n" + LEVEL_HINTS[level]
    return out + ("\n\n" + context_index if context_index else "")
