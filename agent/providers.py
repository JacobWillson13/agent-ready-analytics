"""Chat model construction and per-call cost accounting for every benchmarked backend.

Model strings use "provider:model", e.g. "anthropic:claude-haiku-5-5" or "ollama:gemma4:26b".
"""
from __future__ import annotations

from .settings import OLLAMA_BASE_URL, OLLAMA_NUM_CTX, REQUEST_TIMEOUT_S

# USD per million tokens: input, output, cache read, cache write (5 min).
# Anthropic charges a higher tier on every line when a single request's prompt exceeds the threshold.
PRICES = {
    "anthropic:claude-haiku-5-5": dict(tiers=[(100_000, (0.10, 0.50, 0.01, 0.125)), (None, (0.50, 2.50, 0.05, 0.625))]),
}
LOCAL_PROVIDERS = {"ollama"}


def provider(model: str) -> str:
    return model.split(":", 1)[0]


def make_llm(model: str, max_tokens: int = 4096):
    prov, name = model.split(":", 1)
    if prov == "ollama":
        from langchain_ollama import ChatOllama
        # temperature 0 and a fixed seed for local models; num_ctx must be explicit (Ollama defaults to 4k).
        return ChatOllama(model=name, base_url=OLLAMA_BASE_URL, num_ctx=OLLAMA_NUM_CTX, num_predict=max_tokens,
                          temperature=0, seed=42, client_kwargs={"timeout": REQUEST_TIMEOUT_S})
    from langchain.chat_models import init_chat_model
    # Newer Claude models reject non-default temperature; variance is handled with repetitions instead.
    return init_chat_model(model, max_tokens=max_tokens, timeout=REQUEST_TIMEOUT_S, max_retries=4)


def call_cost(model: str, usage: dict) -> float:
    """Dollar cost of one model call from LangChain usage_metadata. Local models report 0 (compute is
    reported separately as latency, not as a price)."""
    price = PRICES.get(model)
    if not price or not usage:
        return 0.0
    inp = usage.get("input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    det = usage.get("input_token_details", {}) or {}
    cread = det.get("cache_read", 0) or 0
    cwrite = det.get("cache_creation", 0) or 0
    fresh = max(inp - cread - cwrite, 0)
    for limit, (pi, po, pr, pw) in price["tiers"]:
        if limit is None or inp <= limit:
            return (fresh * pi + out * po + cread * pr + cwrite * pw) / 1e6
    return 0.0
