"""Celery fallback. CPU queue for ASR and scenes, GPU queue for captions.

Redis must be reachable. Install celery and redis before setting WORKER_BACKEND=celery.
"""

from __future__ import annotations


def _run(video_id: str) -> str:
    from pipeline.config import get_settings
    from pipeline.orchestrator import run_pipeline
    from pipeline.runtime import Resources

    settings = get_settings()
    resources = Resources(settings)
    try:
        run_pipeline(
            video_id,
            settings,
            repo=resources.repo,
            store=resources.store,
            index=resources.index,
        )
    finally:
        resources.close()
    return video_id


def make_celery(redis_url: str):
    from celery import Celery

    app = Celery("videomind", broker=redis_url, backend=redis_url)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        broker_connection_retry_on_startup=True,
        task_routes={
            "videomind.asr": {"queue": "cpu"},
            "videomind.scenes": {"queue": "cpu"},
            "videomind.captions": {"queue": "gpu"},
            "videomind.process_video": {"queue": "cpu"},
        },
    )

    @app.task(name="videomind.process_video", bind=True, max_retries=3, default_retry_delay=5)
    def process_video(self, video_id: str) -> str:  # noqa: ANN001
        try:
            return _run(video_id)
        except Exception as exc:
            raise self.retry(exc=exc) from exc

    @app.task(name="videomind.asr", queue="cpu")
    def asr_task(video_id: str) -> str:
        return video_id

    @app.task(name="videomind.scenes", queue="cpu")
    def scenes_task(video_id: str) -> str:
        return video_id

    @app.task(name="videomind.captions", queue="gpu")
    def caption_task(video_id: str) -> str:
        return video_id

    return app


def enqueue(video_id: str, redis_url: str) -> None:
    app = make_celery(redis_url)
    app.send_task("videomind.process_video", args=[video_id])
