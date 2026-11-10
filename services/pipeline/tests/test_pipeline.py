
from pipeline.captions import CachingCaptioner, Caption, MockCaptioner
from pipeline.orchestrator import run_pipeline
from pipeline.runtime import Resources
from pipeline.scenes import extract_keyframes
from pipeline.testing import make_settings
from pipeline.tests.ffmpeg_util import tiny_mp4
from pipeline.tracing import Tracer
from pipeline.types import AsrSegment, Keyframe, Transcript, Word


def _transcript() -> Transcript:
    return Transcript(
        language="en",
        duration=8,
        rtf=0.01,
        segments=[
            AsrSegment(
                0,
                3,
                "we explain backpropagation today",
                [Word("backpropagation", 1.0, 1.6)],
            ),
            AsrSegment(3, 8, "moving on to the next topic", []),
        ],
    )


def test_ingest_indexes_a_clip_and_is_idempotent(tmp_path):
    video = tiny_mp4(tmp_path / "clip.mp4", seconds=8)
    settings = make_settings(tmp_path / "app")
    resources = Resources(settings)
    calls = {"n": 0}

    def transcribe(wav, _settings):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient asr failure")
        return _transcript()

    def keyframes(_path, duration, _settings):
        return [
            Keyframe(time=1.0, image_path="", thumb_path="", image_hash="a"),
            Keyframe(time=5.0, image_path="", thumb_path="", image_hash="b"),
        ]

    def caption(_path, ts, _settings):
        if ts < 3:
            return Caption("gradient slide", "", "mock", "mock-v1", 0)
        return Caption(
            "architecture diagram of the network",
            "Architecture Diagram",
            "mock",
            "mock-v1",
            0,
        )

    key = "videos/lecture/source.mp4"
    resources.store.put_file(key, video, "video/mp4")
    resources.repo.create_video(
        video_id="lecture",
        title="Lecture",
        filename="clip.mp4",
        object_key=key,
        content_type="video/mp4",
    )
    resources.repo.create_job(job_id="job1", video_id="lecture")
    hooks = {"transcribe": transcribe, "keyframes": keyframes, "caption": caption}
    try:
        job = run_pipeline(
            "lecture",
            settings,
            repo=resources.repo,
            store=resources.store,
            index=resources.index,
            hooks=hooks,
        )
        assert job["status"] == "indexed"
        assert calls["n"] == 2
        assert resources.index.count() == len(resources.repo.list_videos()) or resources.index.count() >= 1
        count = resources.index.count()
        run_pipeline(
            "lecture",
            settings,
            repo=resources.repo,
            store=resources.store,
            index=resources.index,
            hooks=hooks,
        )
        assert resources.index.count() == count
        hits, _ = resources.retriever.search("backpropagation", k=3, video_id="lecture")
        assert hits
        assert "backpropagation" in hits[0].transcript_text
        visual, _ = resources.retriever.search("architecture diagram", k=3, video_id="lecture")
        assert "architecture" in (
            visual[0].visual_caption + visual[0].ocr_text
        ).lower()
        stored = resources.store.get_bytes("videos/lecture/transcript.json")
        assert b"backpropagation" in stored
    finally:
        resources.close()


def test_static_video_does_not_keep_identical_consecutive_frames(tmp_path):
    video = tiny_mp4(tmp_path / "static.mp4", seconds=4)
    frames = extract_keyframes(
        video,
        duration=4,
        work_dir=tmp_path / "frames",
        every=1.0,
        phash_threshold=4,
        video_id="static",
    )
    assert len(frames) == 1


def test_caption_cache_skips_the_second_call(tmp_path):
    settings = make_settings(tmp_path)
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"not really a jpeg but the hash is stable")

    class Counting:
        backend = "mock"
        model = "mock-v1"

        def __init__(self):
            self.calls = 0

        def caption(self, image_path, timestamp):
            self.calls += 1
            return Caption("a slide", "TITLE", "mock", "mock-v1", 0.0)

    inner = Counting()
    captioner = CachingCaptioner(inner, settings, Tracer(settings))
    first, hit1, digest1 = captioner.caption(str(image), 1.0)
    second, hit2, digest2 = captioner.caption(str(image), 1.0)
    assert inner.calls == 1
    assert hit1 is False and hit2 is True
    assert digest1 == digest2
    assert first.description == second.description == "a slide"
    traces = (tmp_path / "traces.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(traces) == 2
    assert '"cache_hit": true' in traces[1]
    # Constructing the default mock still works.
    assert MockCaptioner().caption(str(image), 0).backend == "mock"
