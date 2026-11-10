from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from pathlib import Path

from pipeline.budget import BudgetExceeded, UsdBudget
from pipeline.config import Settings
from pipeline.openrouter_models import resolve_vlm_model, usage_cost_usd
from pipeline.tracing import Tracer
from pipeline.types import Keyframe

log = logging.getLogger("videomind.captions")

PROMPT = (
    "You are captioning one video frame for search. "
    'Reply with JSON only: {"description": "1-2 sentences of what is on screen", '
    '"visible_text": "slide titles, code, labels, or empty string"}. '
    "Do not invent text that is not visible."
)
PROMPT_VERSION = "v1"


class Caption:
    def __init__(
        self,
        description: str,
        ocr_text: str,
        backend: str,
        model: str,
        cost_usd: float = 0.0,
    ) -> None:
        self.description = description
        self.ocr_text = ocr_text
        self.backend = backend
        self.model = model
        self.cost_usd = cost_usd


def image_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


class MockCaptioner:
    backend = "mock"
    model = "mock-v1"

    def caption(self, image_path: str, timestamp: float) -> Caption:
        del image_path
        return Caption(
            description=f"Frame at {timestamp:.1f} seconds.",
            ocr_text="",
            backend=self.backend,
            model=self.model,
            cost_usd=0.0,
        )


class TesseractCaptioner:
    backend = "tesseract"
    model = "tesseract"

    def caption(self, image_path: str, timestamp: float) -> Caption:
        del timestamp
        import pytesseract
        from PIL import Image

        with Image.open(image_path) as image:
            text = pytesseract.image_to_string(image).strip()
        collapsed = " ".join(text.split())
        description = (
            f"Frame with visible text: {collapsed}" if collapsed else "Frame with no readable text."
        )
        return Caption(description, collapsed, self.backend, self.model, 0.0)


class OpenAICompatibleCaptioner:
    def __init__(
        self,
        *,
        backend: str,
        model: str,
        base_url: str,
        api_key: str,
        pricing: dict | None = None,
    ) -> None:
        self.backend = backend
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.pricing = pricing

    def caption(self, image_path: str, timestamp: float) -> Caption:
        del timestamp
        import httpx

        raw = Path(image_path).read_bytes()
        b64 = base64.b64encode(raw).decode()
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                }
            ],
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.backend == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/videomind"
            headers["X-Title"] = "VideoMind"
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        description, visible = _parse_caption_json(str(content))
        usage = body.get("usage") or {}
        if self.backend == "openrouter":
            cost = usage_cost_usd(usage, self.pricing)
        else:
            cost = float(usage.get("cost") or 0.0)
        return Caption(description, visible, self.backend, self.model, cost)


def _parse_caption_json(content: str) -> tuple[str, str]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
        return str(data.get("description", "")).strip(), str(data.get("visible_text", "")).strip()
    except json.JSONDecodeError:
        return text[:500], ""


def build_captioner(settings: Settings):
    backend = settings.caption_backend
    if backend == "mock":
        return MockCaptioner()
    if backend == "tesseract":
        return TesseractCaptioner()
    if backend == "openrouter":
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for caption_backend=openrouter")
        model, pricing = resolve_vlm_model(settings.openrouter_base_url, settings.openrouter_vlm_model)
        return OpenAICompatibleCaptioner(
            backend="openrouter",
            model=model,
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            pricing=pricing,
        )
    if backend == "vllm":
        return OpenAICompatibleCaptioner(
            backend="vllm",
            model=settings.vllm_model,
            base_url=settings.vllm_base_url,
            api_key=settings.vllm_api_key or "local",
        )
    raise ValueError(f"unknown caption backend {backend}")


class CachingCaptioner:
    def __init__(self, inner, settings: Settings, tracer: Tracer, budget: UsdBudget | None = None) -> None:
        self.inner = inner
        self.tracer = tracer
        self.budget = budget
        self.path = Path(settings.data_dir) / "caption_cache.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.cache = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.cache = {}

    def caption(self, image_path: str, timestamp: float) -> tuple[Caption, bool, str]:
        digest = image_sha256(image_path)
        cache_key = f"{PROMPT_VERSION}:{getattr(self.inner, 'model', '')}:{digest}"
        started = time.perf_counter()
        if cache_key in self.cache:
            stored = self.cache[cache_key]
            caption = Caption(
                stored["description"],
                stored["ocr_text"],
                stored["backend"],
                stored["model"],
                0.0,
            )
            self.tracer.record(
                name="caption",
                model=caption.model,
                input={"image_sha256": digest, "timestamp": timestamp},
                output={"description": caption.description, "visible_text": caption.ocr_text},
                latency_s=time.perf_counter() - started,
                cost_usd=0.0,
                cache_hit=True,
                metadata={"backend": caption.backend},
            )
            return caption, True, digest
        if self.budget is not None:
            self.budget.ensure_open()
        caption = self.inner.caption(image_path, timestamp)
        if self.budget is not None:
            self.budget.note(caption.cost_usd)
        latency = time.perf_counter() - started
        self.cache[cache_key] = {
            "description": caption.description,
            "ocr_text": caption.ocr_text,
            "backend": caption.backend,
            "model": caption.model,
        }
        self.path.write_text(json.dumps(self.cache), encoding="utf-8")
        self.tracer.record(
            name="caption",
            model=caption.model,
            input={"image_sha256": digest, "timestamp": timestamp},
            output={"description": caption.description, "visible_text": caption.ocr_text},
            latency_s=latency,
            cost_usd=caption.cost_usd,
            cache_hit=False,
            metadata={"backend": caption.backend},
        )
        return caption, False, digest


def caption_keyframes(frames: list[Keyframe], captioner: CachingCaptioner) -> list[Keyframe]:
    hits = 0
    cost = 0.0
    for frame in frames:
        try:
            caption, cache_hit, _digest = captioner.caption(frame.image_path, frame.time)
        except BudgetExceeded as exc:
            log.warning("%s", exc)
            break
        frame.caption = caption.description
        frame.ocr_text = caption.ocr_text
        frame.caption_backend = caption.backend
        frame.caption_model = caption.model
        frame.cache_hit = cache_hit
        frame.cost_usd = caption.cost_usd
        hits += int(cache_hit)
        cost += caption.cost_usd
    total = len(frames) or 1
    log.info("captions=%d cache_hit_rate=%.2f cost_usd=%.6f", len(frames), hits / total, cost)
    return frames
