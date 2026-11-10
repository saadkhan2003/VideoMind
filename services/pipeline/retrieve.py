from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from qdrant_client import models

from pipeline.config import Settings
from pipeline.embed import build_embedder
from pipeline.index import SegmentIndex
from pipeline.metrics import SEARCH_STAGE
from pipeline.rerank import build_reranker
from pipeline.rrf import reciprocal_rank_fusion
from pipeline.sparse import sparse_vector
from pipeline.types import format_ts

log = logging.getLogger("videomind.search")


@dataclass
class Hit:
    segment_id: str
    video_id: str
    title: str
    start_s: float
    end_s: float
    score: float
    transcript_text: str
    visual_caption: str
    ocr_text: str
    keyframe_url: str
    lang: str

    def as_dict(self) -> dict:
        snippet_source = self.transcript_text or self.visual_caption or self.ocr_text
        return {
            "segment_id": self.segment_id,
            "video_id": self.video_id,
            "title": self.title,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "timestamp": format_ts(self.start_s),
            "end_timestamp": format_ts(self.end_s),
            "score": self.score,
            "snippet": snippet_source[:240],
            "transcript_text": self.transcript_text,
            "visual_caption": self.visual_caption,
            "ocr_text": self.ocr_text,
            "thumbnail_url": self.keyframe_url,
            "lang": self.lang,
        }


def _hit_from_payload(payload: dict, score: float) -> Hit:
    return Hit(
        segment_id=str(payload.get("segment_id", "")),
        video_id=str(payload.get("video_id", "")),
        title=str(payload.get("title", "")),
        start_s=float(payload.get("start_s", 0.0)),
        end_s=float(payload.get("end_s", 0.0)),
        score=float(score),
        transcript_text=str(payload.get("transcript_text", "")),
        visual_caption=str(payload.get("visual_caption", "")),
        ocr_text=str(payload.get("ocr_text", "")),
        keyframe_url=str(payload.get("keyframe_url", "")),
        lang=str(payload.get("lang", "")),
    )


def _document_text(hit: Hit) -> str:
    return " ".join(
        part for part in (hit.transcript_text, hit.visual_caption, hit.ocr_text) if part
    )


class Retriever:
    def __init__(self, index: SegmentIndex, settings: Settings, embedder=None, reranker=None):
        self.index = index
        self.settings = settings
        self.embedder = embedder or build_embedder(
            settings.embedding_backend, settings.embedding_model, settings.embedding_dim
        )
        self.reranker = reranker
        if self.reranker is None and settings.reranker_enabled:
            self.reranker = build_reranker(settings.reranker_backend, settings.reranker_model)

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        video_id: str | None = None,
        use_text_dense: bool | None = None,
        use_visual_dense: bool | None = None,
        use_sparse: bool | None = None,
        rerank: bool | None = None,
    ) -> tuple[list[Hit], dict[str, float]]:
        settings = self.settings
        use_text = settings.use_text_dense if use_text_dense is None else use_text_dense
        use_visual = settings.use_visual_dense if use_visual_dense is None else use_visual_dense
        use_sparse_flag = settings.use_sparse if use_sparse is None else use_sparse
        do_rerank = settings.reranker_enabled if rerank is None else rerank
        if not any((use_text, use_visual, use_sparse_flag)):
            raise ValueError("at least one retrieval source must be enabled")

        timings: dict[str, float] = {}
        started = time.perf_counter()
        vector = self.embedder.embed([query])[0]
        indices, values = sparse_vector(query)
        embed_done = time.perf_counter()
        timings["embed"] = embed_done - started

        limit = settings.rerank_candidates if do_rerank else k
        limit = max(limit, k)
        hits = self._retrieve(
            vector=vector,
            sparse_indices=indices,
            sparse_values=values,
            limit=limit,
            video_id=video_id,
            use_text=use_text,
            use_visual=use_visual,
            use_sparse=use_sparse_flag,
        )
        retrieve_done = time.perf_counter()
        timings["retrieve"] = retrieve_done - embed_done

        if do_rerank and self.reranker is not None and hits:
            docs = [_document_text(hit) for hit in hits]
            scores = self.reranker.score(query, docs)
            order = sorted(range(len(hits)), key=lambda i: scores[i], reverse=True)
            hits = [hits[i] for i in order]
            for hit, score in zip(hits, (scores[i] for i in order), strict=True):
                hit.score = float(score)
        timings["rerank"] = time.perf_counter() - retrieve_done
        timings["total"] = time.perf_counter() - started
        for stage, value in timings.items():
            SEARCH_STAGE.labels(stage=stage).observe(value)
        log.info(
            "search q=%r k=%d hits=%d retrieve_ms=%.1f rerank_ms=%.1f",
            query[:80],
            k,
            len(hits),
            timings["retrieve"] * 1000,
            timings["rerank"] * 1000,
        )
        return hits[:k], timings

    def _retrieve(
        self,
        *,
        vector: list[float],
        sparse_indices: list[int],
        sparse_values: list[float],
        limit: int,
        video_id: str | None,
        use_text: bool,
        use_visual: bool,
        use_sparse: bool,
    ) -> list[Hit]:
        sparse = models.SparseVector(indices=sparse_indices, values=sparse_values)
        prefetches = []
        if use_text:
            prefetches.append(models.Prefetch(query=vector, using="text_dense", limit=limit))
        if use_visual:
            prefetches.append(models.Prefetch(query=vector, using="visual_dense", limit=limit))
        if use_sparse:
            prefetches.append(models.Prefetch(query=sparse, using="sparse", limit=limit))

        if self.settings.fusion == "qdrant":
            try:
                points = self.index.query_fusion(prefetches, limit=limit, video_id=video_id)
                return [_hit_from_payload(p.payload or {}, p.score) for p in points]
            except Exception:
                log.exception("qdrant fusion failed; falling back to client RRF")

        rankings: list[list[str]] = []
        by_id: dict[str, Hit] = {}
        sources = []
        if use_text:
            sources.append(("text_dense", vector))
        if use_visual:
            sources.append(("visual_dense", vector))
        if use_sparse:
            sources.append(("sparse", sparse))
        for using, query in sources:
            points = self.index.query_named(
                using=using, query=query, limit=limit, video_id=video_id
            )
            ranking = []
            for point in points:
                hit = _hit_from_payload(point.payload or {}, point.score)
                by_id[hit.segment_id] = hit
                ranking.append(hit.segment_id)
            rankings.append(ranking)
        fused = reciprocal_rank_fusion(rankings, k=self.settings.rrf_k)
        hits = []
        for seg_id, score in fused:
            hit = by_id[seg_id]
            hit.score = score
            hits.append(hit)
        return hits[:limit]
