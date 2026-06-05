"""Example Celery tasks for health and infrastructure testing."""

import time

from app.core.celery_app import celery_app


@celery_app.task(name="health.test_task")
def test_task(seconds: int) -> dict:
    """
    Simple background task for testing Celery.
    Sleeps for N seconds then returns confirmation.
    """
    time.sleep(seconds)
    return {"status": "completed", "slept": seconds}
