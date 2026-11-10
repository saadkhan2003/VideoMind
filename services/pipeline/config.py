from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every secret comes from the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/videomind.db"
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_path: str = "./data/qdrant"
    qdrant_collection: str = "segments"

    s3_endpoint: str = ""
    s3_bucket: str = "videomind"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "auto"
    s3_use_ssl: bool = False
    # Cloudflare R2. When all three credentials are set, they win over S3_*.
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "videomind-media"
    data_dir: str = "./data"

    whisper_model: str = "tiny"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    caption_backend: str = "mock"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # "auto" asks OpenRouter's public model list for the cheapest capable vision model.
    openrouter_vlm_model: str = "auto"
    caption_budget_usd: float = 0.15
    openrouter_answer_model: str = "openai/gpt-4o-mini"
    vllm_base_url: str = "http://127.0.0.1:8001/v1"
    vllm_model: str = "Qwen/Qwen2.5-VL-3B-Instruct"
    vllm_api_key: str = ""

    embedding_backend: str = "hash"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 384

    # Off by default. On the 10 Nov 2026 short-clip BGE run the cross-encoder
    # lowered hybrid Recall@1 and about doubled CPU latency. Turn it on for a
    # longer corpus after you measure it.
    reranker_enabled: bool = False
    reranker_backend: str = "lexical"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_candidates: int = 50

    use_text_dense: bool = True
    use_visual_dense: bool = True
    use_sparse: bool = True
    fusion: str = "qdrant"
    rrf_k: int = 60

    chunk_window_s: float = 45.0
    chunk_overlap_s: float = 10.0
    chunk_max_s: float = 60.0
    keyframe_every_s: float = 30.0
    phash_threshold: int = 6

    max_video_seconds: float = 4 * 3600
    max_upload_bytes: int = 2 * 1024**3
    max_concurrent_jobs: int = 2
    retry_attempts: int = 3
    retry_base_delay_s: float = 0.2

    worker_backend: str = "inline"
    redis_url: str = "redis://localhost:6379/0"
    eager_jobs: bool = False

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    api_key: str = ""
    signing_secret: str = "dev-only-change-me"
    presign_ttl_s: int = 3600
    public_base_url: str = "http://127.0.0.1:43124"
    rate_limit_per_minute: int = 120
    answer_min_score: float = 0.05


@lru_cache
def get_settings() -> Settings:
    return Settings()
