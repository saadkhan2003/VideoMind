from __future__ import annotations

from pathlib import Path

from pipeline.config import Settings


def make_settings(tmp_path: Path, **overrides) -> Settings:
    tmp_path.mkdir(parents=True, exist_ok=True)
    data = {
        "database_url": f"sqlite:///{tmp_path / 'videomind.db'}",
        "qdrant_url": "",
        "qdrant_path": ":memory:",
        "data_dir": str(tmp_path),
        "embedding_backend": "hash",
        "embedding_dim": 64,
        "reranker_enabled": True,
        "reranker_backend": "lexical",
        "caption_backend": "mock",
        "worker_backend": "inline",
        "eager_jobs": True,
        "retry_attempts": 2,
        "retry_base_delay_s": 0.01,
        "chunk_window_s": 4,
        "chunk_overlap_s": 1,
        "chunk_max_s": 5,
        "max_concurrent_jobs": 4,
        "max_upload_bytes": 5_000_000,
        "max_video_seconds": 600,
        "api_key": "",
        "rate_limit_per_minute": 1000,
        "signing_secret": "test-secret",
        "public_base_url": "http://test",
    }
    data.update(overrides)
    return Settings(**data)
