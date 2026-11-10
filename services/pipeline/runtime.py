from __future__ import annotations

from pipeline.config import Settings
from pipeline.db import make_session_factory
from pipeline.embed import build_embedder
from pipeline.index import SegmentIndex, build_qdrant
from pipeline.repository import Repository
from pipeline.rerank import build_reranker
from pipeline.retrieve import Retriever
from pipeline.storage import build_store
from pipeline.tracing import Tracer


class Resources:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine, factory = make_session_factory(settings.database_url)
        self.repo = Repository(factory)
        self.store = build_store(settings)
        self.qdrant = build_qdrant(settings)
        self.index = SegmentIndex(self.qdrant, settings)
        self.embedder = build_embedder(
            settings.embedding_backend, settings.embedding_model, settings.embedding_dim
        )
        reranker = None
        if settings.reranker_enabled:
            reranker = build_reranker(settings.reranker_backend, settings.reranker_model)
        self.retriever = Retriever(self.index, settings, self.embedder, reranker)
        self.tracer = Tracer(settings)

    def close(self) -> None:
        self.engine.dispose()
        close = getattr(self.qdrant, "close", None)
        if close:
            close()

    def ping_db(self) -> bool:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
