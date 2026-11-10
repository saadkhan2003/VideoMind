import json

import pytest

from pipeline.orchestrator import run_pipeline
from pipeline.runtime import Resources
from pipeline.sample_clip import SLIDE_SECONDS, generate_lecture
from pipeline.testing import make_settings


@pytest.mark.e2e
def test_synthetic_lecture_round_trip(tmp_path):
    video = generate_lecture(tmp_path / "lecture.mp4", work=tmp_path / "build")
    settings = make_settings(
        tmp_path / "app",
        caption_backend="tesseract",
        whisper_model="tiny",
        whisper_device="cpu",
        whisper_compute_type="int8",
        chunk_window_s=8,
        chunk_overlap_s=1,
        chunk_max_s=10,
        retry_attempts=1,
        reranker_enabled=True,
        reranker_backend="lexical",
    )
    resources = Resources(settings)
    key = "videos/sample-lecture/source.mp4"
    resources.store.put_file(key, video, "video/mp4")
    resources.repo.create_video(
        video_id="sample-lecture",
        title="Neural networks (synthetic sample)",
        filename="lecture.mp4",
        object_key=key,
        content_type="video/mp4",
        license_name="CC0-synthetic",
    )
    resources.repo.create_job(job_id="sample-job", video_id="sample-lecture")
    try:
        job = run_pipeline(
            "sample-lecture",
            settings,
            repo=resources.repo,
            store=resources.store,
            index=resources.index,
        )
        assert job["status"] == "indexed", job
        transcript = json.loads(
            resources.store.get_bytes("videos/sample-lecture/transcript.json")
        )
        words = [
            word
            for segment in transcript["segments"]
            for word in segment["words"]
        ]
        assert words, transcript
        for word in words:
            assert word["end"] >= word["start"]
        # Search for a word the ASR actually emitted, and require the hit to
        # cover that word's timestamp. This checks the full loop without
        # assuming a particular hearing of the synthetic voice.
        chosen = next(word for word in words if len(word["word"].strip()) >= 5)
        query = chosen["word"].strip()
        hits, timings = resources.retriever.search(query, k=5, video_id="sample-lecture")
        assert hits, query
        assert any(hit.start_s - 1 <= chosen["start"] <= hit.end_s + 1 for hit in hits), (
            query,
            chosen,
            [(hit.start_s, hit.end_s, hit.transcript_text) for hit in hits],
        )
        assert timings["total"] >= 0
        assert resources.index.count() >= 1
        assert SLIDE_SECONDS == 8
    finally:
        resources.close()
