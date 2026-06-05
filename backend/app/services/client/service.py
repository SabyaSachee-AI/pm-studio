"""Client business logic and database operations."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.schemas.client import ClientCreate, ClientUpdate


async def get_clients(db: AsyncSession) -> list[Client]:
    """Return all non-deleted clients ordered by newest first."""
    result = await db.execute(
        select(Client)
        .where(Client.deleted_at.is_(None))
        .order_by(Client.created_at.desc())
    )
    return list(result.scalars().all())


async def get_client_by_id(db: AsyncSession, client_id: UUID) -> Client | None:
    """Return a non-deleted client by id, or None."""
    result = await db.execute(
        select(Client).where(
            Client.id == client_id,
            Client.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def create_client(
    db: AsyncSession,
    data: ClientCreate,
    created_by_id: UUID,
) -> Client:
    """Create and persist a new client."""
    client = Client(
        name=data.name,
        company_name=data.company_name,
        email=str(data.email) if data.email is not None else None,
        phone=data.phone,
        notes=data.notes,
        created_by_id=created_by_id,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return client


async def update_client(
    db: AsyncSession,
    client: Client,
    data: ClientUpdate,
) -> Client:
    """Update only fields provided in the PATCH payload."""
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "email" and value is not None:
            value = str(value)
        setattr(client, field, value)

    await db.commit()
    await db.refresh(client)
    return client


async def delete_client(db: AsyncSession, client: Client) -> None:
    """Soft-delete a client by setting deleted_at."""
    client.deleted_at = datetime.now(timezone.utc)
    await db.commit()
