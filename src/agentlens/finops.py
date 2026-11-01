"""Snapshot provider pricing on each actual model call, never derive spend from spans."""

import hashlib
import json
from datetime import datetime
from decimal import Decimal

import yaml

from agentlens.config import ROOT


def gateway_model(settings):
    path = ROOT / "configs/gateway/litellm.yaml"
    if settings.model_base_url != "http://127.0.0.1:4000/v1":
        return None
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    entry = next((m for m in config["model_list"] if m["model_name"] == settings.model), None)
    if entry is None:
        return None
    model = entry["litellm_params"]["model"]
    return {
        "alias": settings.model,
        "model": settings.configured_upstream_model
        if model == "os.environ/DEEPSEEK_MODEL"
        else model,
        "config_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def price_call(usage, response_model, timestamp, configured=None):
    path = ROOT / "configs/observability/pricing.json"
    price = json.loads(path.read_text(encoding="utf-8"))
    result = {
        "currency": price["currency"],
        "pricing_version": price["version"],
        "pricing_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source": price["source"],
        "cost": None,
        "cache_read_tokens": None,
        "reason": "unknown_model_or_usage",
    }
    model = (response_model or "").removeprefix("openai/")
    if model not in price["models"] and configured and response_model == configured["alias"]:
        model = configured["model"].removeprefix("openai/")
        result["model_source"] = "local_gateway_configuration; response_contains_alias"
        result["gateway_config_sha256"] = configured["config_sha256"]
    else:
        result["model_source"] = "response_model"
    result["priced_model"] = model
    rates = price["models"].get(model)
    if usage is None or rates is None:
        return result
    if not (
        datetime.fromisoformat(price["valid_from"])
        <= timestamp
        < datetime.fromisoformat(price["valid_until"])
    ):
        return {**result, "reason": "pricing_outside_verified_window"}
    cached = usage.get("input_token_details", {}).get("cache_read")
    result["cache_read_tokens"] = cached
    if cached is None:
        return {**result, "reason": "cache_breakdown_unobserved"}
    if not 0 <= cached <= usage["input_tokens"]:
        raise ValueError("Provider cache tokens exceed input tokens")
    amounts = [
        (cached, "cache_hit"),
        (usage["input_tokens"] - cached, "cache_miss"),
        (usage["output_tokens"], "output"),
    ]
    amount = sum(Decimal(count) * Decimal(str(rates[key])) for count, key in amounts)
    return {
        **result,
        "cost": str(amount / Decimal(1_000_000)),
        "reason": None,
        "cache_read_tokens": cached,
        "rates_per_million": rates,
    }


def cost_summary(steps):
    calls = [s for s in steps if s.kind == "model"]
    prices = [(s.output or {}).get("billing") for s in calls]
    unknown = sum(p is None or p.get("cost") is None for p in prices)
    known = sum(Decimal(p["cost"]) for p in prices if p and p.get("cost") is not None)
    return {
        "currency": "USD",
        "model_calls": len(calls),
        "unknown_calls": unknown,
        "known_subtotal": str(known),
        "total": None if unknown else str(known),
    }
