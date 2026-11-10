"""Choose a vision model from OpenRouter's public catalog.

Prices come from GET /models, which does not bill the account. A model counts
as capable when it accepts an image, returns text, publishes a positive
completion price, and describes itself as a vision-language or multimodal
model. Routers, free-tier aliases, and batch-only ids are skipped: a zero
price would always win and then fail or stall on the free pool.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger("videomind.openrouter")

# One caption is a short instruction plus one JPEG, and a short JSON reply.
# OpenRouter bills images inside prompt tokens for most VLMs; pricing.image
# is added when the catalog publishes a per-image fee.
CAPTION_PROMPT_TOKENS = 800
CAPTION_COMPLETION_TOKENS = 150

_SKIP_TAGS = (":free", ":batch", ":beta", ":extended", ":nitro")
_SKIP_IDS = (
    "guard",
    "extract",
    "summarize",
    "lyria",
    "dall-e",
    "flux",
    "stable-diffusion",
    "-image",
    "clip-preview",
)
_STRONG = re.compile(
    r"vision-language|vision language|multimodal|image understanding|"
    r"(?:^|[/\-])vl(?:[./:\-]|$)|pixtral|llava|internvl|gemma-3|gemma-4",
    re.IGNORECASE,
)


def estimated_caption_usd(pricing: dict) -> float:
    prompt = float(pricing.get("prompt") or 0)
    completion = float(pricing.get("completion") or 0)
    image = float(pricing.get("image") or 0)
    return prompt * CAPTION_PROMPT_TOKENS + completion * CAPTION_COMPLETION_TOKENS + image


def usage_cost_usd(usage: dict | None, pricing: dict | None) -> float:
    """Prefer the cost OpenRouter reports. Otherwise multiply reported tokens by the catalog price."""
    usage = usage or {}
    if usage.get("cost") is not None:
        return float(usage["cost"])
    if not pricing:
        raise RuntimeError("OpenRouter response did not include usage.cost")
    prompt_tokens = float(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion_tokens = float(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    if prompt_tokens == 0 and completion_tokens == 0:
        raise RuntimeError("OpenRouter response did not include usage.cost or token counts")
    return (
        prompt_tokens * float(pricing.get("prompt") or 0)
        + completion_tokens * float(pricing.get("completion") or 0)
    )


def is_capable_vision(model: dict) -> bool:
    arch = model.get("architecture") or {}
    incoming = set(arch.get("input_modalities") or [])
    outgoing = set(arch.get("output_modalities") or [])
    model_id = (model.get("id") or "").strip()
    low = model_id.lower()
    if "image" not in incoming or "text" not in outgoing:
        return False
    if not low or low.startswith("openrouter/") or low.startswith("~"):
        return False
    if any(tag in low for tag in _SKIP_TAGS):
        return False
    if any(bad in low for bad in _SKIP_IDS):
        return False
    if int(model.get("context_length") or 0) < 32000:
        return False
    pricing = model.get("pricing") or {}
    try:
        prompt = float(pricing.get("prompt") or 0)
        completion = float(pricing.get("completion") or 0)
    except (TypeError, ValueError):
        return False
    if prompt < 0 or completion <= 0:
        return False
    blob = f"{low}\n{(model.get('description') or '').lower()}"
    return _STRONG.search(blob) is not None


def select_cheapest_vision_model(models: list[dict]) -> dict:
    capable = [model for model in models if is_capable_vision(model)]
    if not capable:
        raise RuntimeError("OpenRouter catalog has no capable vision model under the selection rules")
    return min(capable, key=lambda model: (estimated_caption_usd(model.get("pricing") or {}), model["id"]))


def fetch_models(base_url: str) -> list[dict]:
    import httpx

    response = httpx.get(
        f"{base_url.rstrip('/')}/models",
        timeout=30,
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    models = payload.get("data")
    if not isinstance(models, list):
        raise RuntimeError("OpenRouter /models did not return a list")
    return models


def resolve_vlm_model(base_url: str, requested: str) -> tuple[str, dict | None]:
    """Return (model id, pricing or None).

    An explicit OPENROUTER_VLM_MODEL is used as-is. "auto" or an empty value
    picks the cheapest capable model from the live catalog.
    """
    if requested and requested.strip().lower() != "auto":
        return requested.strip(), None
    chosen = select_cheapest_vision_model(fetch_models(base_url))
    pricing = {
        "prompt": float((chosen.get("pricing") or {}).get("prompt") or 0),
        "completion": float((chosen.get("pricing") or {}).get("completion") or 0),
        "image": float((chosen.get("pricing") or {}).get("image") or 0),
    }
    estimate = estimated_caption_usd(chosen.get("pricing") or {})
    log.info(
        "selected OpenRouter vision model %s (about $%.6f per caption before the real usage cost)",
        chosen["id"],
        estimate,
    )
    return chosen["id"], pricing
