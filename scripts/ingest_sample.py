"""Generate the synthetic lecture and index it as video id `sample-lecture`.

Uses the same settings as the API (environment / .env). Close this process
before starting the API if Qdrant is the embedded on-disk store: only one
process can open that directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "services")]

from pipeline.config import get_settings  # noqa: E402
from pipeline.orchestrator import run_pipeline  # noqa: E402
from pipeline.runtime import Resources  # noqa: E402
from pipeline.sample_clip import generate_lecture  # noqa: E402


def main() -> None:
    settings = get_settings()
    # The sample is 32 seconds. The production window is ~45s, which would
    # collapse the clip into one segment and the player would start at 0.
    if settings.chunk_window_s >= 30:
        settings.chunk_window_s = 8
        settings.chunk_overlap_s = 1
        settings.chunk_max_s = 12
    if settings.caption_backend == "mock":
        settings.caption_backend = "tesseract"
    data = Path(settings.data_dir)
    data.mkdir(parents=True, exist_ok=True)
    video_path = data / "sample-lecture.mp4"
    if not video_path.exists():
        print("generating synthetic lecture")
        generate_lecture(video_path, work=data / "sample_build")
    resources = Resources(settings)
    video_id = "sample-lecture"
    key = f"videos/{video_id}/source.mp4"
    try:
        if resources.repo.get_video(video_id) is None:
            resources.store.put_file(key, video_path, "video/mp4")
            resources.repo.create_video(
                video_id=video_id,
                title="Neural networks (synthetic sample)",
                filename="lecture.mp4",
                object_key=key,
                content_type="video/mp4",
                license_name="CC0-synthetic",
            )
            resources.repo.create_job(job_id="sample-job", video_id=video_id)
        job = resources.repo.latest_job(video_id)
        if job and job["status"] == "indexed":
            print("already indexed")
        else:
            if job and job["status"] == "failed":
                resources.repo.transition(job["id"], "queued")
            elif job is None:
                resources.repo.create_job(job_id="sample-job", video_id=video_id)
            job = run_pipeline(
                video_id,
                settings,
                repo=resources.repo,
                store=resources.store,
                index=resources.index,
                already_processing=False,
            )
            print("job", job["status"])
        for query in ("backpropagation", "architecture diagram", "mean squared error"):
            hits, timings = resources.retriever.search(query, k=3, video_id=video_id)
            print(f"{query!r} {timings['total'] * 1000:.0f} ms hits={len(hits)}")
            for hit in hits:
                text = (hit.transcript_text or hit.visual_caption or hit.ocr_text)[:80]
                print(f"  {hit.start_s:.1f}-{hit.end_s:.1f} {text!r}")
    finally:
        resources.close()


if __name__ == "__main__":
    main()
