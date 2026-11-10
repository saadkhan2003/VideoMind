from __future__ import annotations

import hmac
import logging
import re
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.limiter import RateLimiter
from app.schemas import AnswerRequest, AnswerResponse, SearchResponse
from pipeline.config import Settings, get_settings
from pipeline.media import MediaError, probe_duration
from pipeline.metrics import HTTP_LATENCY, SEARCH_STAGE
from pipeline.orchestrator import run_pipeline
from pipeline.runtime import Resources
from pipeline.storage import verify_signature
from pipeline.validate import UploadRejected, assert_upload_allowed

log = logging.getLogger("videomind.api")
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
}


def require_api_key(request: Request) -> None:
    expected = request.app.state.settings.api_key
    if not expected:
        return
    got = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(got, expected):
        raise HTTPException(status_code=401, detail="missing or invalid API key")


def _client_key(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "local")


def _limit(request: Request) -> None:
    limiter: RateLimiter = request.app.state.limiter
    if not limiter.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="rate limit exceeded")


def dispatch(resources: Resources, video_id: str, hooks: dict) -> None:
    settings = resources.settings

    def _run() -> None:
        run_pipeline(
            video_id,
            settings,
            repo=resources.repo,
            store=resources.store,
            index=resources.index,
            hooks=hooks,
        )

    if settings.eager_jobs:
        _run()
        return
    backend = settings.worker_backend
    if backend == "poll":
        return
    if backend == "celery":
        from pipeline.celery_app import enqueue

        enqueue(video_id, settings.redis_url)
        return
    if backend == "ray":
        from pipeline.ray_runner import submit

        submit(video_id, settings)
        return
    threading.Thread(target=_run, name=f"ingest-{video_id}", daemon=True).start()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    if getattr(app.state, "resources", None) is None:
        app.state.resources = Resources(app.state.settings)
    app.state.limiter = RateLimiter(app.state.settings.rate_limit_per_minute)
    try:
        yield
    finally:
        app.state.resources.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="VideoMind", version="0.1.0", lifespan=_lifespan)
    app.state.settings = settings
    app.state.hooks = {}
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def observe(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        HTTP_LATENCY.labels(request.method, path).observe(time.perf_counter() - started)
        return response

    @app.get("/")
    def root():
        return {"service": "videomind", "health": "/healthz", "docs": "/docs"}

    @app.get("/healthz")
    def healthz(request: Request):
        resources: Resources = request.app.state.resources
        db_ok = True
        db_error = ""
        try:
            resources.ping_db()
        except Exception as exc:  # noqa: BLE001
            db_ok = False
            db_error = str(exc)
        qdrant = resources.index.health()
        storage = resources.store.health()
        ok = db_ok and qdrant.get("ok") and storage.get("ok")
        body = {
            "status": "ok" if ok else "degraded",
            "db": {"ok": db_ok, "error": db_error},
            "qdrant": qdrant,
            "storage": storage,
        }
        return JSONResponse(body, status_code=200 if ok else 503)

    @app.get("/readyz")
    def readyz(request: Request):
        try:
            request.app.state.resources.ping_db()
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"ready": False, "error": str(exc)}, status_code=503)
        return {"ready": True}

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/videos", dependencies=[Depends(require_api_key)])
    def list_videos(request: Request):
        return {"videos": request.app.state.resources.repo.list_videos()}

    @app.get("/videos/{video_id}", dependencies=[Depends(require_api_key)])
    def get_video(video_id: str, request: Request):
        video = request.app.state.resources.repo.get_video(video_id)
        if video is None:
            raise HTTPException(404, "video not found")
        return video

    @app.get("/videos/{video_id}/media")
    def media(video_id: str, request: Request):
        resources: Resources = request.app.state.resources
        video = resources.repo.get_video(video_id)
        if video is None:
            raise HTTPException(404, "video not found")
        if resources.store.backend == "s3":
            return RedirectResponse(resources.store.presign(video["object_key"]))
        path = resources.store.path_for(video["object_key"])
        if not path.is_file():
            raise HTTPException(404, "media missing")
        return FileResponse(path, media_type=video["content_type"] or "video/mp4")

    @app.get("/keyframes/{segment_id}")
    def keyframe(segment_id: str, request: Request):
        resources: Resources = request.app.state.resources
        segment = resources.repo.get_segment(segment_id)
        if segment is None or not segment["keyframe_key"]:
            raise HTTPException(404, "keyframe not found")
        if not resources.store.exists(segment["keyframe_key"]):
            raise HTTPException(404, "keyframe not found")
        data = resources.store.get_bytes(segment["keyframe_key"])
        return Response(content=data, media_type="image/jpeg")

    @app.get("/objects/{key:path}")
    def signed_object(key: str, exp: int, sig: str, request: Request):
        resources: Resources = request.app.state.resources
        settings = request.app.state.settings
        if resources.store.backend != "local":
            raise HTTPException(404, "local signing is not used for this store")
        if not verify_signature(settings.signing_secret, key, exp, sig):
            raise HTTPException(403, "expired or invalid signature")
        path = resources.store.path_for(key)
        if not path.is_file():
            raise HTTPException(404, "object not found")
        return FileResponse(path)

    @app.post("/videos", dependencies=[Depends(require_api_key)])
    async def upload_video(
        request: Request,
        file: UploadFile = File(...),
        title: str = Form(""),
        video_id: str = Form(""),
        source_url: str = Form(""),
        license_name: str = Form(""),
    ):
        resources: Resources = request.app.state.resources
        settings: Settings = request.app.state.settings
        filename = file.filename or "upload.mp4"
        if resources.repo.count_active() >= settings.max_concurrent_jobs:
            raise HTTPException(429, "too many jobs in progress")
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > settings.max_upload_bytes + 1_048_576:
            raise HTTPException(413, "file too large")
        try:
            assert_upload_allowed(
                filename=filename,
                size=0,
                max_bytes=settings.max_upload_bytes,
            )
        except UploadRejected as exc:
            raise HTTPException(exc.status, exc.message) from exc

        chosen = video_id.strip() or uuid.uuid4().hex
        if not _VIDEO_ID.fullmatch(chosen):
            raise HTTPException(400, "video_id must be 1-64 characters of letters, numbers, _ or -")
        if resources.repo.get_video(chosen):
            raise HTTPException(409, "video id already exists")

        work = Path(settings.data_dir) / "uploads"
        work.mkdir(parents=True, exist_ok=True)
        dest = work / f"{chosen}{Path(filename).suffix.lower()}"
        size = 0
        try:
            with dest.open("wb") as handle:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_upload_bytes:
                        raise UploadRejected(
                            "too_large",
                            f"File is over the limit of {settings.max_upload_bytes} bytes.",
                            status=413,
                        )
                    handle.write(chunk)
            try:
                duration = probe_duration(dest)
            except MediaError as exc:
                raise UploadRejected("bad_type", str(exc)) from exc
            assert_upload_allowed(
                filename=filename,
                size=size,
                max_bytes=settings.max_upload_bytes,
                duration=duration,
                max_seconds=settings.max_video_seconds,
            )
        except UploadRejected as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(exc.status, exc.message) from exc

        ext = Path(filename).suffix.lower()
        key = f"videos/{chosen}/source{ext}"
        resources.store.put_file(key, dest, _CONTENT_TYPES.get(ext, "application/octet-stream"))
        dest.unlink(missing_ok=True)
        resources.repo.create_video(
            video_id=chosen,
            title=title.strip() or Path(filename).stem,
            filename=Path(filename).name,
            object_key=key,
            content_type=_CONTENT_TYPES.get(ext, "video/mp4"),
            source_url=source_url,
            license_name=license_name,
        )
        job = resources.repo.create_job(job_id=uuid.uuid4().hex, video_id=chosen)
        try:
            dispatch(resources, chosen, dict(request.app.state.hooks))
        except Exception:
            log.exception("failed to start pipeline for %s", chosen)
        latest = resources.repo.latest_job(chosen) or job
        return JSONResponse({"video_id": chosen, "job": latest}, status_code=201)

    @app.get("/jobs/{job_id}", dependencies=[Depends(require_api_key)])
    def get_job(job_id: str, request: Request):
        job = request.app.state.resources.repo.get_job(job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        return job

    @app.get("/jobs", dependencies=[Depends(require_api_key)])
    def list_jobs(request: Request, status: str | None = None):
        return {"jobs": request.app.state.resources.repo.list_jobs(status=status)}

    @app.post("/jobs/{job_id}/retry", dependencies=[Depends(require_api_key)])
    def retry_job(job_id: str, request: Request):
        resources: Resources = request.app.state.resources
        job = resources.repo.get_job(job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        if job["status"] != "failed":
            raise HTTPException(409, "only failed jobs can be retried")
        if resources.repo.count_active() >= request.app.state.settings.max_concurrent_jobs:
            raise HTTPException(429, "too many jobs in progress")
        updated = resources.repo.transition(job_id, "queued")
        try:
            dispatch(resources, job["video_id"], dict(request.app.state.hooks))
        except Exception:
            log.exception("retry dispatch failed")
        return resources.repo.get_job(job_id) or updated

    @app.get("/search", response_model=SearchResponse, dependencies=[Depends(require_api_key)])
    def search(
        request: Request,
        q: str,
        k: int = 5,
        video_id: str | None = None,
    ):
        _limit(request)
        if not q.strip():
            raise HTTPException(400, "q is required")
        k = max(1, min(k, 50))
        started = time.perf_counter()
        hits, timings = request.app.state.resources.retriever.search(
            q.strip(), k=k, video_id=video_id or None
        )
        took = (time.perf_counter() - started) * 1000
        SEARCH_STAGE.labels(stage="request").observe(took / 1000)
        return {
            "query": q,
            "k": k,
            "took_ms": round(timings.get("total", took / 1000) * 1000, 2),
            "hits": [hit.as_dict() for hit in hits],
        }

    @app.post("/answer", response_model=AnswerResponse, dependencies=[Depends(require_api_key)])
    def answer(body: AnswerRequest, request: Request):
        _limit(request)
        from pipeline.answer import answer_question

        resources: Resources = request.app.state.resources
        started = time.perf_counter()
        hits, _timings = resources.retriever.search(
            body.query, k=max(1, min(body.k, 10)), video_id=body.video_id
        )
        result = answer_question(body.query, hits, resources.settings, resources.tracer)
        SEARCH_STAGE.labels(stage="answer").observe(time.perf_counter() - started)
        return result

    return app


app = create_app()
