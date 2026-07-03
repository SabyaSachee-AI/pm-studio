"""Background job status polling and SSE (Celery)."""

import asyncio
import json

from celery.result import AsyncResult
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.celery_app import celery_app
from app.services.ai.job_progress import read_sync_progress

router = APIRouter(prefix="/jobs", tags=["Background Jobs"])


@router.get("/progress/{progress_id}")
async def get_sync_job_progress(progress_id: str) -> dict:
    """Poll live model/progress meta for synchronous API AI calls (e.g. feedback synthesis)."""
    meta = await read_sync_progress(progress_id)
    return {
        "progress_id": progress_id,
        "status": "PROGRESS" if meta else "PENDING",
        "meta": meta or {},
    }


@router.get("/{task_id}")
async def get_job_status(task_id: str) -> dict:
    """Poll the status of a Celery background job."""
    result = AsyncResult(task_id, app=celery_app)
    response: dict = {"task_id": task_id, "status": result.status}
    if isinstance(result.info, dict) and result.info:
        response["meta"] = result.info
    elif result.status == "STARTED":
        response["meta"] = {"phase": "starting", "message": "Worker picked up the job…"}
    if result.status == "SUCCESS":
        response["result"] = result.result
    elif result.status == "FAILURE":
        response["error"] = str(result.result)
    return response


@router.get("/{task_id}/stream")
async def stream_job_status(task_id: str) -> StreamingResponse:
    """Stream Celery job status via Server-Sent Events."""

    async def event_generator():
        while True:
            result = AsyncResult(task_id, app=celery_app)
            payload = {"task_id": task_id, "status": result.status}
            if result.status == "SUCCESS":
                payload["result"] = result.result
            elif result.status == "FAILURE":
                payload["error"] = str(result.result)
            elif result.status == "PROGRESS":
                payload["meta"] = result.info or {}
            yield f"data: {json.dumps(payload)}\n\n"
            if result.ready():
                break
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
