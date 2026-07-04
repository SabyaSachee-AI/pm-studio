"""Celery application instance for background task processing."""

from dotenv import load_dotenv
from pathlib import Path

_env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "pm_studio",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.health_tasks",
        "app.workers.requirement_tasks",
        "app.workers.prd_tasks",
        "app.workers.srs_tasks",
        "app.workers.pdf_tasks",
        "app.workers.spec_tasks",
        "app.workers.module_tasks",
        "app.workers.architecture_tasks",
        "app.workers.orchestration_tasks",
        "app.workers.build_tasks",
        "app.workers.gap_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Report STARTED as soon as a worker picks up a task (Build UI no longer stuck on QUEUED).
    task_track_started=True,
    result_extended=True,
    # Long-running code builds go to a dedicated queue so they never block PRD/SRS/
    # architecture jobs. Run a second worker for it:
    #   celery -A app.core.celery_app worker -Q build --pool=solo -n build@%h
    # Run exactly ONE build worker locally — a second terminal with the same -n causes 422 push races.
    # The default worker still serves everything else (the "celery" queue).
    task_routes={"build.*": {"queue": "build"}},
    task_default_queue="celery",
    # Each worker process takes ONE task at a time (fair scheduling across projects —
    # no process hoards the queue while others sit idle).
    worker_prefetch_multiplier=1,
    # A stuck task (e.g. endless provider rate-limits) can't hog a worker forever.
    # Soft limit raises a catchable error first (long codegen auto-resumes); the
    # hard limit is a last-resort backstop. Normal tasks finish well under these.
    task_soft_time_limit=1800,   # 30 min
    task_time_limit=2400,        # 40 min
)

celery_app.autodiscover_tasks(["app.workers"])


@celery_app.on_after_configure.connect
def _register_worker_hooks(**kwargs: object) -> None:
    from celery.signals import worker_ready  # noqa: PLC0415

    @worker_ready.connect
    def _resume_auto_ci_on_build_worker_start(sender=None, **kw: object) -> None:
        """Resume orphaned auto-CI watchers when the build queue worker starts."""
        try:
            queues = {q.name for q in sender.consumer.task_queues}  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            return
        if "build" not in queues:
            return
        from app.workers.build_tasks import (  # noqa: PLC0415
            resume_orphaned_auto_ci,
            resume_orphaned_build_jobs,
        )

        n_ci = resume_orphaned_auto_ci()
        n_build = resume_orphaned_build_jobs()
        if n_ci or n_build:
            import logging  # noqa: PLC0415

            logging.getLogger(__name__).info(
                "Resumed %s orphaned auto-CI watcher(s), %s build job(s)",
                n_ci,
                n_build,
            )
