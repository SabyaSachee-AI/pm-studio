"""Knowledge base API endpoints."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_screen_permission
from app.core.database import get_db
from app.models.knowledge_base_item import (
    KnowledgeBaseItem,
    KnowledgeItemType,
    KnowledgeSourceType,
)
from app.models.prd import PRD
from app.models.reusable_module import ReusableModule
from app.models.srs import SRS
from app.models.task_spec import TaskSpec
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeItemCreate,
    KnowledgeItemResponse,
    ReusableModuleCreate,
    ReusableModuleResponse,
    SaveFromSourceRequest,
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


def _item_response(item: KnowledgeBaseItem) -> KnowledgeItemResponse:
    return KnowledgeItemResponse(
        id=item.id,
        project_id=item.project_id,
        item_type=item.item_type.value,
        source_type=item.source_type.value,
        source_id=item.source_id,
        title=item.title,
        description=item.description,
        content_json=item.content_json,
        tags=item.tags,
        saved_by_id=item.saved_by_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/items", response_model=list[KnowledgeItemResponse])
async def list_knowledge_items(
    project_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("knowledge_base", "view")),
) -> list[KnowledgeItemResponse]:
    """List knowledge base items, optionally filtered by project."""
    query = select(KnowledgeBaseItem).where(KnowledgeBaseItem.deleted_at.is_(None))
    if project_id:
        query = query.where(KnowledgeBaseItem.project_id == project_id)
    query = query.order_by(KnowledgeBaseItem.created_at.desc())
    result = await db.execute(query)
    return [_item_response(i) for i in result.scalars().all()]


@router.post("/items", response_model=KnowledgeItemResponse, status_code=201)
async def create_knowledge_item(
    body: KnowledgeItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("knowledge_base", "edit")),
) -> KnowledgeItemResponse:
    """Save a new knowledge base item."""
    now = datetime.now(timezone.utc)
    item = KnowledgeBaseItem(
        project_id=body.project_id,
        item_type=KnowledgeItemType(body.item_type),
        source_type=KnowledgeSourceType(body.source_type),
        source_id=body.source_id,
        title=body.title,
        description=body.description,
        content_json=body.content_json,
        tags=body.tags,
        saved_by_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _item_response(item)


@router.post("/items/save-from-source", response_model=KnowledgeItemResponse, status_code=201)
async def save_from_source(
    body: SaveFromSourceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("knowledge_base", "edit")),
) -> KnowledgeItemResponse:
    """Save an existing PRD, SRS, or spec into the knowledge base."""
    content_json: dict | None = None
    project_id: UUID | None = None
    title = body.title
    item_type = KnowledgeItemType.document

    if body.source_type == "prd":
        result = await db.execute(
            select(PRD).where(PRD.id == body.source_id, PRD.deleted_at.is_(None))
        )
        prd = result.scalar_one_or_none()
        if not prd or not prd.content_json:
            raise HTTPException(status_code=404, detail="PRD not found")
        content_json = prd.content_json
        project_id = prd.project_id
        title = title or f"PRD v{prd.version}"
        item_type = KnowledgeItemType.document
    elif body.source_type == "srs":
        result = await db.execute(
            select(SRS).where(SRS.id == body.source_id, SRS.deleted_at.is_(None))
        )
        srs = result.scalar_one_or_none()
        if not srs or not srs.content_json:
            raise HTTPException(status_code=404, detail="SRS not found")
        content_json = srs.content_json
        project_id = srs.project_id
        title = title or f"SRS v{srs.version}"
        item_type = KnowledgeItemType.document
    elif body.source_type == "spec":
        result = await db.execute(
            select(TaskSpec).where(
                TaskSpec.id == body.source_id, TaskSpec.deleted_at.is_(None)
            )
        )
        spec = result.scalar_one_or_none()
        if not spec or not spec.content_json:
            raise HTTPException(status_code=404, detail="Spec not found")
        content_json = spec.content_json
        title = title or "Technical spec"
        item_type = KnowledgeItemType.spec
    else:
        raise HTTPException(status_code=400, detail="Invalid source type")

    now = datetime.now(timezone.utc)
    item = KnowledgeBaseItem(
        project_id=project_id,
        item_type=item_type,
        source_type=KnowledgeSourceType(body.source_type),
        source_id=body.source_id,
        title=title,
        content_json=content_json,
        tags=body.tags,
        saved_by_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _item_response(item)


@router.get("/items/{item_id}", response_model=KnowledgeItemResponse)
async def get_knowledge_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("knowledge_base", "view")),
) -> KnowledgeItemResponse:
    """Return a single knowledge base item."""
    result = await db.execute(
        select(KnowledgeBaseItem).where(
            KnowledgeBaseItem.id == item_id,
            KnowledgeBaseItem.deleted_at.is_(None),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return _item_response(item)


@router.get("/modules", response_model=list[ReusableModuleResponse])
async def list_reusable_modules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("knowledge_base", "view")),
) -> list[ReusableModuleResponse]:
    """List reusable module definitions."""
    result = await db.execute(
        select(ReusableModule)
        .where(ReusableModule.deleted_at.is_(None))
        .order_by(ReusableModule.name.asc())
    )
    return [ReusableModuleResponse.model_validate(m) for m in result.scalars().all()]


@router.post("/modules", response_model=ReusableModuleResponse, status_code=201)
async def create_reusable_module(
    body: ReusableModuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_screen_permission("knowledge_base", "edit")),
) -> ReusableModuleResponse:
    """Save a reusable module pattern."""
    now = datetime.now(timezone.utc)
    module = ReusableModule(
        knowledge_base_item_id=body.knowledge_base_item_id,
        name=body.name,
        description=body.description,
        content_json=body.content_json,
        saved_by_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return ReusableModuleResponse.model_validate(module)
