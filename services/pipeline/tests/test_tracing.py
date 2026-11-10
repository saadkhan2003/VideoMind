import json
import logging
from importlib.metadata import version

from pipeline.config import Settings
from pipeline.tracing import Tracer


def _settings(tmp_path) -> Settings:
    return Settings(
        data_dir=str(tmp_path),
        langfuse_public_key="",
        langfuse_secret_key="",
    )


def test_pinned_langfuse_exposes_start_observation():
    from langfuse import Langfuse

    assert version("langfuse") == "5.2.0"
    assert hasattr(Langfuse, "start_observation")
    assert not hasattr(Langfuse, "start_generation")


def test_record_exports_a_generation_observation(tmp_path):
    class Observation:
        def __init__(self):
            self.ended = False

        def end(self):
            self.ended = True

    class Client:
        def __init__(self):
            self.calls = []
            self.observation = Observation()
            self.flushed = False

        def start_observation(self, **kwargs):
            self.calls.append(kwargs)
            return self.observation

        def start_generation(self, **kwargs):
            raise AssertionError("start_generation is not part of langfuse 5.2")

        def flush(self):
            self.flushed = True

    tracer = Tracer(_settings(tmp_path))
    client = Client()
    tracer._langfuse = client
    record = tracer.record(
        name="caption",
        model="qwen/qwen3.7-flash",
        input={"image": "sha"},
        output="a banner",
        latency_s=0.2,
        cost_usd=0.000044,
        metadata={"video_id": "hufsky-data-retention"},
    )

    assert record["output"] == "a banner"
    assert client.flushed is True
    assert client.observation.ended is True
    call = client.calls[0]
    assert call["as_type"] == "generation"
    assert call["name"] == "caption"
    assert call["model"] == "qwen/qwen3.7-flash"
    assert call["cost_details"] == {"total": 0.000044}
    saved = json.loads(tracer.path.read_text(encoding="utf-8").strip())
    assert saved["name"] == "caption"


def test_langfuse_failure_is_a_warning_and_keeps_the_local_trace(tmp_path, caplog):
    class Client:
        def start_observation(self, **kwargs):
            raise AttributeError("start_generation is gone; use start_observation")

    tracer = Tracer(_settings(tmp_path))
    tracer._langfuse = Client()
    with caplog.at_level(logging.WARNING, logger="videomind.trace"):
        record = tracer.record(
            name="caption",
            model="qwen/qwen3.7-flash",
            input="img",
            output="text",
            latency_s=0.1,
        )

    assert record["output"] == "text"
    assert "Langfuse export failed for caption" in caplog.text
    assert "start_generation is gone" in caplog.text
    assert "local trace was still written" in caplog.text
    assert '"name": "caption"' in tracer.path.read_text(encoding="utf-8")
