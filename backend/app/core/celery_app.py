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
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

celery_app.autodiscover_tasks(["app.workers"])
