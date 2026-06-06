"""Notification creation helpers."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def create_notification(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    message: str,
    link: str | None = None,
) -> Notification:
    """Create an in-app notification for a user."""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        link=link,
        is_read=False,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    return notification
