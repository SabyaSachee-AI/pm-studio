"""One-off DB state check."""
from sqlalchemy import inspect, text

from app.core.database import SyncSessionLocal

db = SyncSessionLocal()
insp = inspect(db.bind)
cols = [c["name"] for c in insp.get_columns("organizations")]
print("org cols:", cols)
perms = db.execute(
    text(
        "SELECT role, screen_key, can_view, can_edit FROM screen_permissions "
        "WHERE screen_key IN ('architecture','admin_ai_config') AND deleted_at IS NULL"
    )
).fetchall()
print("perms:", perms)
ver = db.execute(text("SELECT version_num FROM alembic_version")).fetchone()
print("alembic:", ver)
db.close()
