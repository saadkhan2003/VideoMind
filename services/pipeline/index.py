from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from qdrant_client import QdrantClient, models

from pipeline.config import Settings

log = logging.getLogger("videomind.index")
_lock = threading.Lock()


def build_qdrant(settings: Settings) -> QdrantClient:
    if settings.qdrant_url:
        return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    if settings.qdrant_path == ":memory:":
        return QdrantClient(":memory:")
    from pathlib import Path

    path = Path(settings.qdrant_path)
    path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(path))


def point_id(video_id: str, start_s: float) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"videomind:{video_id}:{start_s:.3f}"))


class SegmentIndex:
    def __init__(self, client: QdrantClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.collection = settings.qdrant_collection
        self.dim = settings.embedding_dim
        self._ensure()

    def _ensure(self) -> None:
        if self.client.collection_exists(self.collection):
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config={
                "text_dense": models.VectorParams(size=self.dim, distance=models.Distance.COSINE),
                "visual_dense": models.VectorParams(
                    size=self.dim, distance=models.Distance.COSINE
                ),
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(modifier=models.Modifier.IDF),
            },
        )
        if self.settings.qdrant_url:
            self.client.create_payload_index(
                collection_name=self.collection,
                field_name="video_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

    def delete_video(self, video_id: str) -> None:
        with _lock:
            self.client.delete(
                collection_name=self.collection,
                points_selector=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="video_id", match=models.MatchValue(value=video_id)
                        )
                    ]
                ),
            )

    def upsert(self, points: list[dict[str, Any]]) -> None:
        if not points:
            return
        structs = []
        for point in points:
            structs.append(
                models.PointStruct(
                    id=point["id"],
                    vector={
                        "text_dense": point["text_dense"],
                        "visual_dense": point["visual_dense"],
                        "sparse": models.SparseVector(
                            indices=point["sparse_indices"],
                            values=point["sparse_values"],
                        ),
                    },
                    payload=point["payload"],
                )
            )
        with _lock:
            self.client.upsert(collection_name=self.collection, points=structs)

    def count(self) -> int:
        return int(self.client.count(self.collection, exact=True).count)

    def query_named(
        self,
        *,
        using: str,
        query,
        limit: int,
        video_id: str | None = None,
    ) -> list[models.ScoredPoint]:
        return self.client.query_points(
            collection_name=self.collection,
            query=query,
            using=using,
            limit=limit,
            query_filter=_video_filter(video_id),
            with_payload=True,
        ).points

    def query_fusion(
        self,
        prefetches: list[models.Prefetch],
        limit: int,
        video_id: str | None = None,
    ) -> list[models.ScoredPoint]:
        return self.client.query_points(
            collection_name=self.collection,
            prefetch=prefetches,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            query_filter=_video_filter(video_id),
            with_payload=True,
        ).points

    def health(self) -> dict:
        try:
            self.client.get_collections()
            return {"ok": True, "collection": self.collection}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}


def _video_filter(video_id: str | None):
    if not video_id:
        return None
    return models.Filter(
        must=[models.FieldCondition(key="video_id", match=models.MatchValue(value=video_id))]
    )
