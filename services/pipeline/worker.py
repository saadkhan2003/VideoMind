from __future__ import annotations

import logging
import time

from pipeline.config import get_settings
from pipeline.orchestrator import run_pipeline
from pipeline.ray_runner import ray_available
from pipeline.runtime import Resources

log = logging.getLogger("videomind.worker")


def serve() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    backend = settings.worker_backend
    if backend == "celery":
        from pipeline.celery_app import make_celery

        app = make_celery(settings.redis_url)
        app.worker_main(argv=["worker", "--loglevel=INFO", "-Q", "cpu,gpu"])
        return
    if backend == "ray":
        if not ray_available():
            log.warning("Ray is not installed; falling back to the poll worker")
        else:
            log.info("Ray poll: claiming jobs and submitting a DAG per video")
            _poll(settings, use_ray=True)
            return
    _poll(settings, use_ray=False)


def _poll(settings, use_ray: bool) -> None:
    resources = Resources(settings)
    log.info("polling for jobs (ray=%s)", use_ray)
    try:
        while True:
            job = resources.repo.claim_next(settings.max_concurrent_jobs)
            if job is None:
                time.sleep(1)
                continue
            video_id = job["video_id"]
            try:
                if use_ray:
                    from pipeline.ray_runner import run_blocking

                    run_blocking(video_id, settings)
                else:
                    run_pipeline(
                        video_id,
                        settings,
                        repo=resources.repo,
                        store=resources.store,
                        index=resources.index,
                        already_processing=True,
                    )
            except Exception:
                log.exception("job %s failed", job["id"])
    finally:
        resources.close()


def main() -> None:
    serve()
