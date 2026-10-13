"""Read dbt artifacts (manifest + semantic manifest) and guides: the agent's context layer."""
from __future__ import annotations

import json
from functools import lru_cache

from .settings import DBT_DIR, GUIDES_DIR


@lru_cache
def manifest() -> dict:
    return json.loads((DBT_DIR / "target" / "manifest.json").read_text())


@lru_cache
def semantic_manifest() -> dict:
    return json.loads((DBT_DIR / "target" / "semantic_manifest.json").read_text())


def models() -> list[dict]:
    out = []
    for n in manifest()["nodes"].values():
        if n["resource_type"] != "model" or n["name"] == "metricflow_time_spine":
            continue
        meta = n.get("config", {}).get("meta", {}) or n.get("meta", {})
        out.append(dict(name=n["name"], dataset=n["schema"], relation=f'{n["schema"]}.{n["alias"] or n["name"]}',
                        layer=meta.get("layer", ""), endorsed=bool(meta.get("endorsed", False)),
                        description=(n.get("description") or "").strip(), columns=n.get("columns", {})))
    return out


def model(name: str) -> dict | None:
    return next((m for m in models() if m["name"] == name), None)


def metrics() -> list[dict]:
    sm = semantic_manifest()
    return [dict(name=m["name"], label=m.get("label"), type=m["type"], description=(m.get("description") or "").strip())
            for m in sm["metrics"]]


def dimensions() -> list[str]:
    """Group-by names MetricFlow accepts, e.g. customer__region, org__deployment_type, metric_time__month."""
    sm = semantic_manifest()
    out = {"metric_time__day", "metric_time__week", "metric_time__month", "metric_time__quarter", "metric_time__year"}
    for s in sm["semantic_models"]:
        prim = next((e["name"] for e in s["entities"] if e["type"] == "primary"), None)
        for d in s["dimensions"]:
            if prim and d["type"] == "categorical":
                out.add(f"{prim}__{d['name']}")
    return sorted(out)


def guides() -> dict[str, str]:
    return {p.stem: p.read_text() for p in sorted(GUIDES_DIR.glob("*.md"))}
