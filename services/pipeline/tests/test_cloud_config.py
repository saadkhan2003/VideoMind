import pytest

from pipeline.budget import BudgetExceeded, UsdBudget
from pipeline.captions import CachingCaptioner, Caption, caption_keyframes
from pipeline.config import Settings
from pipeline.index import qdrant_client_kwargs
from pipeline.openrouter_models import (
    is_capable_vision,
    select_cheapest_vision_model,
    usage_cost_usd,
)
from pipeline.storage import object_storage_target
from pipeline.testing import make_settings
from pipeline.tracing import Tracer
from pipeline.types import Keyframe


def _model(model_id, description, prompt, completion, **extra):
    payload = {
        "id": model_id,
        "description": description,
        "context_length": extra.get("context_length", 128000),
        "architecture": {
            "input_modalities": extra.get("input", ["text", "image"]),
            "output_modalities": extra.get("output", ["text"]),
        },
        "pricing": {"prompt": str(prompt), "completion": str(completion), "image": "0"},
    }
    return payload


def test_cheapest_capable_model_skips_free_batch_and_coding_agents():
    models = [
        _model("openrouter/auto", "router", -1, -1),
        _model("google/gemma-4-31b-it:free", "multimodal vision-language", 0, 0),
        _model("qwen/qwen3-vl-8b-instruct:batch", "vision-language model", 1e-8, 1e-8),
        _model(
            "nex-agi/nex-n2.5-mini",
            "agentic coding within a visual feedback loop",
            1e-9,
            1e-9,
        ),
        _model("google/gemma-3-4b-it", "Gemma 3 vision-language multimodality", 5e-8, 1e-7),
        _model("qwen/qwen3.7-flash", "Qwen3.7 Flash is a vision-language model", 3e-8, 1.3e-7),
    ]
    assert is_capable_vision(models[1]) is False
    assert is_capable_vision(models[3]) is False
    chosen = select_cheapest_vision_model(models)
    assert chosen["id"] == "qwen/qwen3.7-flash"


def test_usage_cost_prefers_the_reported_openrouter_cost():
    reported = usage_cost_usd(
        {"cost": 0.0123, "prompt_tokens": 9999},
        {"prompt": 1, "completion": 1},
    )
    assert reported == 0.0123
    estimated = usage_cost_usd(
        {"prompt_tokens": 1000, "completion_tokens": 100},
        {"prompt": 0.000002, "completion": 0.000004},
    )
    assert estimated == pytest.approx(0.0024)
    with pytest.raises(RuntimeError):
        usage_cost_usd({}, None)


def test_budget_stops_further_caption_calls(tmp_path):
    settings = make_settings(tmp_path)
    budget = UsdBudget(0.15)

    class Paid:
        backend = "openrouter"
        model = "fixture"

        def __init__(self):
            self.calls = 0

        def caption(self, image_path, timestamp):
            self.calls += 1
            return Caption("slide", "TITLE", "openrouter", "fixture", 0.10)

    image = tmp_path / "frame.jpg"
    image.write_bytes(b"frame-bytes")
    inner = Paid()
    captioner = CachingCaptioner(inner, settings, Tracer(settings), budget=budget)
    frames = [
        Keyframe(time=float(i), image_path=str(image), thumb_path="", image_hash=str(i))
        for i in range(4)
    ]
    # Same bytes would cache. Use a unique file per frame so each call is a miss.
    for frame in frames:
        path = tmp_path / f"{frame.time}.jpg"
        path.write_bytes(f"frame-{frame.time}".encode())
        frame.image_path = str(path)
    caption_keyframes(frames, captioner)
    assert inner.calls == 2
    assert budget.spent == pytest.approx(0.20)
    assert frames[0].caption == "slide"
    assert frames[1].caption == "slide"
    assert frames[2].caption == ""
    with pytest.raises(BudgetExceeded):
        budget.ensure_open()


def test_r2_and_qdrant_cloud_endpoints():
    settings = Settings(
        r2_account_id="abc123",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
        qdrant_url="https://example.cloud.qdrant.io",
        qdrant_api_key="qd",
    )
    target = object_storage_target(settings)
    assert target["endpoint"] == "https://abc123.r2.cloudflarestorage.com"
    assert target["bucket"] == "videomind-media"
    assert target["access_key"] == "key"
    kwargs = qdrant_client_kwargs(settings)
    assert kwargs["port"] == 443
    assert kwargs["api_key"] == "qd"
    assert kwargs["prefer_grpc"] is False
    explicit = Settings(qdrant_url="https://example.cloud.qdrant.io:6333", qdrant_api_key="qd")
    assert "port" not in qdrant_client_kwargs(explicit)
    defaults = Settings()
    assert defaults.caption_budget_usd == 0.15
    assert defaults.openrouter_vlm_model == "auto"
    assert defaults.langfuse_host == "https://cloud.langfuse.com"
    assert defaults.r2_bucket == "videomind-media"
    assert defaults.reranker_enabled is False
