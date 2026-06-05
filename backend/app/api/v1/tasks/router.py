"""Background task status polling endpoints."""

from celery.result import AsyncResult
from fastapi import APIRouter

from app.core.celery_app import celery_app

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("/{task_id}")
async def get_task_status(task_id: str) -> dict:
    """
    Poll the status of any background Celery task.

    Returns:
    - status: PENDING | STARTED | SUCCESS | FAILURE | RETRY
    - result: the task return value (only when SUCCESS)
    - error: error message (only when FAILURE)
    """
    result = AsyncResult(task_id, app=celery_app)

    response: dict = {"task_id": task_id, "status": result.status}

    if result.status == "SUCCESS":
        response["result"] = result.result
    elif result.status == "FAILURE":
        response["error"] = str(result.result)

    return response
