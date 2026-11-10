"""Index a few short CC / public-domain clips against the cloud services in the environment.

Reads OPENROUTER_API_KEY, QDRANT_URL, QDRANT_API_KEY, R2_ACCOUNT_ID,
R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET (default videomind-media),
LANGFUSE_PUBLIC_KEY, and LANGFUSE_SECRET_KEY. Does not print secret values.

    python scripts/cloud_ingest.py --dry-run
    python scripts/cloud_ingest.py --max-usd 0.15
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "services")]

from pipeline.budget import UsdBudget  # noqa: E402
from pipeline.config import get_settings  # noqa: E402
from pipeline.openrouter_models import estimated_caption_usd, resolve_vlm_model  # noqa: E402
from pipeline.orchestrator import run_pipeline  # noqa: E402
from pipeline.runtime import Resources  # noqa: E402

CLIPS = [
    {
        "video_id": "edison-1920s",
        "title": "Edison speech, 1920s",
        "url": "https://upload.wikimedia.org/wikipedia/commons/3/3c/Edison_speech%2C_1920s.ogv",
        "page": "https://commons.wikimedia.org/wiki/File:Edison_speech,_1920s.ogv",
        "license": "Public domain",
        "filename": "edison-1920s.ogv",
    },
    {
        "video_id": "hufsky-data-retention",
        "title": "Demonstration data retention speech, Hufsky 1 (2007)",
        "url": "https://upload.wikimedia.org/wikipedia/commons/8/82/Demonstration_data_retention_at_BMVIT_speech_Hufsky_1_2007-06-07.ogv",
        "page": "https://commons.wikimedia.org/wiki/File:Demonstration_data_retention_at_BMVIT_speech_Hufsky_1_2007-06-07.ogv",
        "license": "CC BY-SA 3.0",
        "filename": "hufsky-data-retention.ogv",
    },
    {
        "video_id": "talking-tree-2011",
        "title": "Talking tree 2011",
        "url": "https://upload.wikimedia.org/wikipedia/commons/b/b7/Talking_tree_2011.webm",
        "page": "https://commons.wikimedia.org/wiki/File:Talking_tree_2011.webm",
        "license": "CC BY 2.0",
        "filename": "talking-tree-2011.webm",
    },
]

REQUIRED = (
    "OPENROUTER_API_KEY",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
)


def missing_env(settings) -> list[str]:
    present = {
        "OPENROUTER_API_KEY": settings.openrouter_api_key,
        "QDRANT_URL": settings.qdrant_url,
        "QDRANT_API_KEY": settings.qdrant_api_key,
        "R2_ACCOUNT_ID": settings.r2_account_id,
        "R2_ACCESS_KEY_ID": settings.r2_access_key_id,
        "R2_SECRET_ACCESS_KEY": settings.r2_secret_access_key,
        "LANGFUSE_PUBLIC_KEY": settings.langfuse_public_key,
        "LANGFUSE_SECRET_KEY": settings.langfuse_secret_key,
    }
    return [name for name in REQUIRED if not str(present[name]).strip()]


def download(url: str, dest: Path) -> None:
    import httpx

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"already downloaded {dest.name}")
        return
    print(f"downloading {dest.name}")
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        with dest.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cloud ingest for the three short CC clips")
    parser.add_argument(
        "--max-usd",
        type=float,
        default=0.15,
        help="Stop OpenRouter caption calls once reported usage reaches this many USD (default 0.15)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check env vars and print the vision model selected from live prices. No captions are requested.",
    )
    args = parser.parse_args()
    if args.max_usd <= 0:
        raise SystemExit("--max-usd must be greater than 0")
    # Validate the number the same way the pipeline will.
    UsdBudget(args.max_usd)

    settings = get_settings()
    settings.caption_backend = "openrouter"
    settings.caption_budget_usd = args.max_usd
    settings.openrouter_vlm_model = settings.openrouter_vlm_model or "auto"
    # These clips are one to two minutes. A 45s window still leaves a few segments.
    settings.chunk_window_s = 20
    settings.chunk_overlap_s = 5
    settings.chunk_max_s = 30
    settings.whisper_device = "cpu"
    if not settings.whisper_model:
        settings.whisper_model = "tiny"

    absent = missing_env(settings)
    if absent:
        print("Missing environment variables (values are not printed):")
        for name in absent:
            print(f"  {name}")
        raise SystemExit(2)

    model, pricing = resolve_vlm_model(settings.openrouter_base_url, settings.openrouter_vlm_model)
    settings.openrouter_vlm_model = model
    if pricing:
        print(
            f"vision model {model} catalog estimate ${estimated_caption_usd(pricing):.6f} per caption; "
            f"budget ${args.max_usd:.2f} uses the cost field OpenRouter returns"
        )
    else:
        print(f"vision model {model} (explicit); budget ${args.max_usd:.2f}")
    print(f"qdrant {settings.qdrant_url}")
    print(f"r2 bucket {settings.r2_bucket} account set")
    print(f"langfuse host {settings.langfuse_host}")
    if args.dry_run:
        print("dry run only; no video was downloaded and no caption was requested")
        return

    data = Path(settings.data_dir)
    clip_dir = data / "clips"
    resources = Resources(settings)
    try:
        for clip in CLIPS:
            path = clip_dir / clip["filename"]
            download(clip["url"], path)
            video_id = clip["video_id"]
            suffix = Path(clip["filename"]).suffix.lower()
            key = f"videos/{video_id}/source{suffix}"
            content_type = {".webm": "video/webm", ".ogv": "video/ogg", ".mp4": "video/mp4"}.get(
                suffix, "application/octet-stream"
            )
            if resources.repo.get_video(video_id) is None:
                resources.store.put_file(key, path, content_type)
                resources.repo.create_video(
                    video_id=video_id,
                    title=clip["title"],
                    filename=clip["filename"],
                    object_key=key,
                    content_type=content_type,
                    source_url=clip["page"],
                    license_name=clip["license"],
                )
                resources.repo.create_job(job_id=uuid.uuid4().hex, video_id=video_id)
            job = resources.repo.latest_job(video_id)
            if job and job["status"] == "indexed":
                print(f"{video_id} already indexed")
                continue
            if job and job["status"] == "failed":
                resources.repo.transition(job["id"], "queued")
            elif job is None:
                resources.repo.create_job(job_id=uuid.uuid4().hex, video_id=video_id)
            finished = run_pipeline(
                video_id,
                settings,
                repo=resources.repo,
                store=resources.store,
                index=resources.index,
            )
            print(f"{video_id} {finished['status']}")
    finally:
        resources.close()


if __name__ == "__main__":
    main()
