"""Background task status polling and SSE endpoints."""

import asyncio
import json

from celery.result import AsyncResult
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

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


@router.get("/{task_id}/stream")
async def stream_task_status(task_id: str) -> StreamingResponse:
    """Stream task status updates via Server-Sent Events."""

    async def event_generator():
        while True:
            result = AsyncResult(task_id, app=celery_app)
            payload = {"task_id": task_id, "status": result.status}
            if result.status == "SUCCESS":
                payload["result"] = result.result
            elif result.status == "FAILURE":
                payload["error"] = str(result.result)
            yield f"data: {json.dumps(payload)}\n\n"
            if result.ready():
                break
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
