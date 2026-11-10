from __future__ import annotations

import json
import threading
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from pipeline.db import Job, SegmentRow, Video, utcnow
from pipeline.metrics import refresh_job_gauges

_lock = threading.Lock()

ALLOWED = {
    "queued": {"processing", "failed"},
    "processing": {"indexed", "failed"},
    "failed": {"queued"},
    "indexed": {"queued"},
}

STAGE_WEIGHTS = {
    "extract_audio": 0.05,
    "asr": 0.35,
    "scenes": 0.15,
    "captions": 0.20,
    "chunk": 0.05,
    "embed": 0.15,
    "upsert": 0.05,
}


class InvalidTransition(Exception):
    pass


def _job_dict(job: Job) -> dict[str, Any]:
    try:
        stages = json.loads(job.stages_json or "{}")
    except json.JSONDecodeError:
        stages = {}
    return {
        "id": job.id,
        "video_id": job.video_id,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "stages": stages,
        "error": job.error,
        "attempts": job.attempts,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def _video_dict(video: Video) -> dict[str, Any]:
    return {
        "id": video.id,
        "title": video.title,
        "filename": video.filename,
        "object_key": video.object_key,
        "content_type": video.content_type,
        "duration_s": video.duration_s,
        "status": video.status,
        "language": video.language,
        "source_url": video.source_url,
        "license": video.license,
        "error": video.error,
        "created_at": video.created_at.isoformat() if video.created_at else None,
    }


class Repository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def _counts(self, session) -> dict[str, int]:
        rows = session.execute(select(Job.status, func.count()).group_by(Job.status)).all()
        return {status: count for status, count in rows}

    def create_video(
        self,
        *,
        video_id: str,
        title: str,
        filename: str,
        object_key: str,
        content_type: str,
        source_url: str = "",
        license_name: str = "",
    ) -> dict[str, Any]:
        with _lock:
            session = self._sf()
            try:
                video = Video(
                    id=video_id,
                    title=title,
                    filename=filename,
                    object_key=object_key,
                    content_type=content_type,
                    source_url=source_url,
                    license=license_name,
                    status="uploaded",
                )
                session.add(video)
                session.commit()
                return _video_dict(video)
            finally:
                session.close()

    def create_job(self, *, job_id: str, video_id: str) -> dict[str, Any]:
        with _lock:
            session = self._sf()
            try:
                job = Job(id=job_id, video_id=video_id, status="queued", stage="queued")
                session.add(job)
                session.commit()
                refresh_job_gauges(self._counts(session))
                return _job_dict(job)
            finally:
                session.close()

    def get_video(self, video_id: str) -> dict[str, Any] | None:
        session = self._sf()
        try:
            video = session.get(Video, video_id)
            return _video_dict(video) if video else None
        finally:
            session.close()

    def list_videos(self) -> list[dict[str, Any]]:
        session = self._sf()
        try:
            rows = session.execute(select(Video).order_by(Video.created_at.desc())).scalars().all()
            return [_video_dict(v) for v in rows]
        finally:
            session.close()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        session = self._sf()
        try:
            job = session.get(Job, job_id)
            return _job_dict(job) if job else None
        finally:
            session.close()

    def latest_job(self, video_id: str) -> dict[str, Any] | None:
        session = self._sf()
        try:
            job = session.execute(
                select(Job).where(Job.video_id == video_id).order_by(Job.created_at.desc())
            ).scalars().first()
            return _job_dict(job) if job else None
        finally:
            session.close()

    def list_jobs(self, status: str | None = None) -> list[dict[str, Any]]:
        session = self._sf()
        try:
            stmt = select(Job).order_by(Job.created_at.desc())
            if status:
                stmt = stmt.where(Job.status == status)
            rows = session.execute(stmt).scalars().all()
            return [_job_dict(j) for j in rows]
        finally:
            session.close()

    def count_active(self) -> int:
        session = self._sf()
        try:
            stmt = select(func.count()).select_from(Job).where(
                Job.status.in_(("queued", "processing"))
            )
            return int(session.execute(stmt).scalar_one())
        finally:
            session.close()

    def transition(self, job_id: str, new_status: str, error: str = "") -> dict[str, Any]:
        with _lock:
            session = self._sf()
            try:
                job = session.get(Job, job_id)
                if job is None:
                    raise KeyError(job_id)
                if new_status not in ALLOWED.get(job.status, set()):
                    raise InvalidTransition(f"{job.status} -> {new_status}")
                job.status = new_status
                job.error = error
                job.updated_at = utcnow()
                if new_status == "processing":
                    job.stage = "processing"
                if new_status == "indexed":
                    job.progress = 1.0
                    job.stage = "indexed"
                    job.error = ""
                if new_status == "queued":
                    job.attempts = (job.attempts or 0) + 1
                    job.stage = "queued"
                    job.progress = 0.0
                    job.error = ""
                video = session.get(Video, job.video_id)
                if video is not None:
                    video.status = {
                        "queued": "uploaded",
                        "processing": "processing",
                        "indexed": "indexed",
                        "failed": "failed",
                    }[new_status]
                    video.error = error
                    video.updated_at = utcnow()
                session.commit()
                refresh_job_gauges(self._counts(session))
                return _job_dict(job)
            finally:
                session.close()

    def update_stage(
        self,
        job_id: str,
        stage: str,
        status: str,
        detail: str = "",
    ) -> None:
        with _lock:
            session = self._sf()
            try:
                job = session.get(Job, job_id)
                if job is None:
                    return
                try:
                    stages = json.loads(job.stages_json or "{}")
                except json.JSONDecodeError:
                    stages = {}
                entry = stages.get(stage, {})
                now = utcnow().isoformat()
                if status == "running" and "started_at" not in entry:
                    entry["started_at"] = now
                entry["status"] = status
                entry["detail"] = detail
                entry["updated_at"] = now
                if status in {"succeeded", "failed"}:
                    entry["finished_at"] = now
                stages[stage] = entry
                job.stages_json = json.dumps(stages)
                job.stage = stage
                done = sum(
                    STAGE_WEIGHTS[name]
                    for name, payload in stages.items()
                    if payload.get("status") == "succeeded" and name in STAGE_WEIGHTS
                )
                job.progress = min(0.99, done)
                job.updated_at = utcnow()
                session.commit()
            finally:
                session.close()

    def update_video(self, video_id: str, **fields: Any) -> None:
        with _lock:
            session = self._sf()
            try:
                video = session.get(Video, video_id)
                if video is None:
                    return
                for key, value in fields.items():
                    setattr(video, key, value)
                video.updated_at = utcnow()
                session.commit()
            finally:
                session.close()

    def replace_segments(self, video_id: str, rows: list[dict[str, Any]]) -> None:
        with _lock:
            session = self._sf()
            try:
                existing = session.execute(
                    select(SegmentRow).where(SegmentRow.video_id == video_id)
                ).scalars().all()
                for row in existing:
                    session.delete(row)
                for row in rows:
                    session.add(SegmentRow(**row))
                session.commit()
            finally:
                session.close()

    def get_segment(self, segment_id: str) -> dict[str, Any] | None:
        session = self._sf()
        try:
            row = session.get(SegmentRow, segment_id)
            if row is None:
                return None
            return {
                "id": row.id,
                "video_id": row.video_id,
                "start_s": row.start_s,
                "end_s": row.end_s,
                "transcript_text": row.transcript_text,
                "visual_caption": row.visual_caption,
                "ocr_text": row.ocr_text,
                "keyframe_key": row.keyframe_key,
                "lang": row.lang,
                "point_id": row.point_id,
            }
        finally:
            session.close()

    def claim_next(self, max_concurrent: int) -> dict[str, Any] | None:
        with _lock:
            session = self._sf()
            try:
                processing = session.execute(
                    select(func.count()).select_from(Job).where(Job.status == "processing")
                ).scalar_one()
                if int(processing) >= max_concurrent:
                    return None
                job = session.execute(
                    select(Job).where(Job.status == "queued").order_by(Job.created_at.asc())
                ).scalars().first()
                if job is None:
                    return None
                job.status = "processing"
                job.stage = "processing"
                job.updated_at = utcnow()
                video = session.get(Video, job.video_id)
                if video is not None:
                    video.status = "processing"
                    video.updated_at = utcnow()
                session.commit()
                refresh_job_gauges(self._counts(session))
                return _job_dict(job)
            finally:
                session.close()
