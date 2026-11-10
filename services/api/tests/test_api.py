from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from pipeline.repository import InvalidTransition
from pipeline.runtime import Resources
from pipeline.testing import make_settings
from pipeline.tests.ffmpeg_util import tiny_mp4
from pipeline.types import AsrSegment, Keyframe, Transcript


def _client(tmp_path: Path, **overrides):
    settings = make_settings(tmp_path, **overrides)
    app = create_app(settings)
    app.state.hooks = {
        "transcribe": lambda wav, settings: Transcript(
            language="en",
            duration=4,
            rtf=0.01,
            segments=[AsrSegment(0, 4, "we explain backpropagation", [])],
        ),
        "keyframes": lambda path, duration, settings: [
            Keyframe(time=1.0, image_path="", thumb_path="", image_hash="a")
        ],
        "caption": lambda path, ts, settings: __import__(
            "pipeline.captions", fromlist=["Caption"]
        ).Caption("a frame", "", "mock", "mock-v1", 0),
    }
    return app, settings


def test_health_and_upload_search_flow(tmp_path):
    video = tiny_mp4(tmp_path / "clip.mp4", seconds=4)
    app, _settings = _client(tmp_path / "app")
    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        body = health.json()
        assert body["status"] == "ok"
        assert body["db"]["ok"] and body["qdrant"]["ok"] and body["storage"]["ok"]
        assert client.get("/readyz").json()["ready"] is True
        assert client.get("/metrics").status_code == 200
        uploaded = client.post(
            "/videos",
            files={"file": ("clip.mp4", video.read_bytes(), "video/mp4")},
            data={"title": "Clip", "video_id": "clip1"},
        )
        assert uploaded.status_code == 201, uploaded.text
        job = uploaded.json()["job"]
        assert job["status"] == "indexed"
        fetched = client.get(f"/jobs/{job['id']}")
        assert fetched.json()["status"] == "indexed"
        assert "asr" in fetched.json()["stages"]
        found = client.get("/search", params={"q": "backpropagation", "k": 3})
        assert found.status_code == 200
        hits = found.json()["hits"]
        assert hits
        assert hits[0]["timestamp"]
        assert "backpropagation" in hits[0]["transcript_text"]
        media = client.get("/videos/clip1/media")
        assert media.status_code == 200
        assert media.content[:3] != b""
        answer = client.post("/answer", json={"query": "backpropagation"})
        assert answer.status_code == 200
        assert answer.json()["refused"] is False
        assert answer.json()["citations"][0]["segment_id"] == hits[0]["segment_id"]
        refused = client.post("/answer", json={"query": "unrelated origami folding"})
        assert refused.json()["refused"] is True
        assert refused.json()["citations"] == []


def test_rejects_bad_types_and_oversize_and_enforces_limits(tmp_path):
    video = tiny_mp4(tmp_path / "clip.mp4", seconds=3)
    small_app, _small = _client(tmp_path / "small", max_upload_bytes=50, api_key="secret")
    with TestClient(small_app) as client:
        huge = client.post(
            "/videos",
            files={"file": ("clip.mp4", b"x" * 80, "video/mp4")},
            headers={"x-api-key": "secret"},
        )
        assert huge.status_code == 413
    app, _settings = _client(
        tmp_path / "app",
        max_video_seconds=1,
        max_concurrent_jobs=1,
        api_key="secret",
        rate_limit_per_minute=2,
    )
    with TestClient(app) as client:
        denied = client.post(
            "/videos",
            files={"file": ("clip.mp4", video.read_bytes(), "video/mp4")},
        )
        assert denied.status_code == 401
        headers = {"x-api-key": "secret"}
        bad = client.post(
            "/videos",
            files={"file": ("notes.txt", b"hello", "text/plain")},
            headers=headers,
        )
        assert bad.status_code == 400
        long = client.post(
            "/videos",
            files={"file": ("clip.mp4", video.read_bytes(), "video/mp4")},
            headers=headers,
        )
        assert long.status_code == 400
        assert "over the limit" in long.text
        # A processing job blocks the concurrency limit.
        resources = client.app.state.resources
        resources.repo.create_video(
            video_id="busy",
            title="busy",
            filename="busy.mp4",
            object_key="videos/busy/source.mp4",
            content_type="video/mp4",
        )
        job = resources.repo.create_job(job_id="busy-job", video_id="busy")
        resources.repo.transition(job["id"], "processing")
        blocked = client.post(
            "/videos",
            files={"file": ("other.mp4", video.read_bytes(), "video/mp4")},
            headers=headers,
        )
        assert blocked.status_code == 429
        failed = resources.repo.transition(job["id"], "failed", error="boom")
        assert failed["status"] == "failed"
        dead = client.get("/jobs", params={"status": "failed"}, headers=headers)
        assert dead.json()["jobs"][0]["id"] == "busy-job"
        retried = client.post(f"/jobs/{job['id']}/retry", headers=headers)
        # Retry starts the real pipeline, which fails because the object is missing,
        # and the job ends failed again. The endpoint itself must accept the retry.
        assert retried.status_code == 200
        assert retried.json()["status"] in {"queued", "processing", "failed", "indexed"}
        assert client.get("/search", params={"q": "one"}, headers=headers).status_code == 200
        assert client.get("/search", params={"q": "two"}, headers=headers).status_code == 200
        limited = client.get("/search", params={"q": "three"}, headers=headers)
        assert limited.status_code == 429


def test_illegal_job_transition(tmp_path):
    settings = make_settings(tmp_path)
    resources = Resources(settings)
    try:
        resources.repo.create_video(
            video_id="v",
            title="t",
            filename="v.mp4",
            object_key="videos/v/source.mp4",
            content_type="video/mp4",
        )
        job = resources.repo.create_job(job_id="j", video_id="v")
        with pytest_raises():
            resources.repo.transition(job["id"], "indexed")
    finally:
        resources.close()


def test_presign_round_trip(tmp_path):
    settings = make_settings(tmp_path)
    resources = Resources(settings)
    try:
        resources.store.put_bytes("videos/v/source.mp4", b"hello", "video/mp4")
        url = resources.store.presign("videos/v/source.mp4", expires_s=60)
        assert "sig=" in url
        from pipeline.storage import verify_signature

        exp = int(url.split("exp=")[1].split("&")[0])
        sig = url.split("sig=")[1]
        assert verify_signature(settings.signing_secret, "videos/v/source.mp4", exp, sig)
    finally:
        resources.close()


def pytest_raises():
    import pytest

    return pytest.raises(InvalidTransition)
