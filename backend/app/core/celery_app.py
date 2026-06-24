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
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Long-running code builds go to a dedicated queue so they never block PRD/SRS/
    # architecture jobs. Run a second worker for it:
    #   celery -A app.core.celery_app worker -Q build --pool=solo -n build@%h
    # The default worker still serves everything else (the "celery" queue).
    task_routes={"build.*": {"queue": "build"}},
    task_default_queue="celery",
)

celery_app.autodiscover_tasks(["app.workers"])
