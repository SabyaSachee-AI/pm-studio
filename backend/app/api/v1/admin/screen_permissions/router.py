"""Admin screen-permission matrix endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_screen_permission
from app.core.database import get_db
from app.models.screen_permission import ScreenKey, ScreenPermission
from app.models.user import User, UserRole

router = APIRouter(prefix="/admin/screen-permissions", tags=["admin-screen-permissions"])

# Admin roles always have full access — never stored in the table, never editable
ADMIN_ROLES = frozenset({UserRole.studio_owner, UserRole.studio_admin})
# Editable roles (non-admin)
EDITABLE_ROLES = [r for r in UserRole if r not in ADMIN_ROLES]
ALL_SCREENS = [s.value for s in ScreenKey]


class PermissionCell(BaseModel):
    role: str
    screen_key: str
    can_view: bool
    can_edit: bool


class PermissionUpdate(BaseModel):
    can_view: bool
    can_edit: bool


class MatrixResponse(BaseModel):
    roles: list[str]
    admin_roles: list[str]
    screens: list[str]
    permissions: list[PermissionCell]


@router.get("", response_model=MatrixResponse)
async def get_permission_matrix(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_screen_permission("admin_users", "view")),
) -> MatrixResponse:
    """Return the full role × screen permission matrix."""
    rows = (
        await db.execute(
            select(ScreenPermission).where(ScreenPermission.deleted_at.is_(None))
        )
    ).scalars().all()

    # Build lookup: (role_value, screen_key) → (can_view, can_edit)
    stored: dict[tuple[str, str], tuple[bool, bool]] = {}
    for row in rows:
        role_val = row.role.value if hasattr(row.role, "value") else str(row.role)
        stored[(role_val, row.screen_key)] = (row.can_view, row.can_edit)

    # Build full matrix (filling missing combos with False/False)
    cells: list[PermissionCell] = []
    for role in EDITABLE_ROLES:
        for screen in ALL_SCREENS:
            cv, ce = stored.get((role.value, screen), (False, False))
            cells.append(PermissionCell(role=role.value, screen_key=screen, can_view=cv, can_edit=ce))

    return MatrixResponse(
        roles=[r.value for r in EDITABLE_ROLES],
        admin_roles=[r.value for r in ADMIN_ROLES],
        screens=ALL_SCREENS,
        permissions=cells,
    )


@router.patch("/{role}/{screen_key}", response_model=PermissionCell)
async def update_permission(
    role: str,
    screen_key: str,
    body: PermissionUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_screen_permission("admin_users", "edit")),
) -> PermissionCell:
    """Upsert can_view / can_edit for a role + screen combination."""
    # Validate role
    try:
        role_enum = UserRole(role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown role: {role}")

    if role_enum in ADMIN_ROLES:
        raise HTTPException(status_code=400, detail="Admin roles cannot be modified")

    # Validate screen
    if screen_key not in ALL_SCREENS:
        raise HTTPException(status_code=400, detail=f"Unknown screen: {screen_key}")

    # Upsert
    result = await db.execute(
        select(ScreenPermission).where(
            ScreenPermission.role == role_enum,
            ScreenPermission.screen_key == screen_key,
            ScreenPermission.deleted_at.is_(None),
        )
    )
    perm = result.scalar_one_or_none()

    if perm is None:
        perm = ScreenPermission(
            role=role_enum,
            screen_key=screen_key,
            can_view=body.can_view,
            can_edit=body.can_edit,
        )
        db.add(perm)
    else:
        perm.can_view = body.can_view
        perm.can_edit = body.can_edit

    # If edit is granted, view must also be true
    if perm.can_edit:
        perm.can_view = True

    await db.commit()
    await db.refresh(perm)

    return PermissionCell(
        role=role,
        screen_key=screen_key,
        can_view=perm.can_view,
        can_edit=perm.can_edit,
    )
