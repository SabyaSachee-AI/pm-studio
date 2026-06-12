"""Publish live Celery job metadata for SSE / polling consumers."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def publish_job_progress(**meta: Any) -> None:
    """Update current Celery task PROGRESS meta (no-op outside a worker task)."""
    try:
        from celery import current_task  # noqa: PLC0415

        task = current_task
        if task and getattr(task, "request", None) and task.request.id:
            task.update_state(state="PROGRESS", meta=meta)
    except Exception:
        logger.debug("Could not publish job progress", exc_info=True)
