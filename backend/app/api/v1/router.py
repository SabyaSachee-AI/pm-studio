"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.auth.router import router as auth_router
from app.api.v1.clients.router import router as clients_router
from app.api.v1.projects.router import router as projects_router
from app.api.v1.tasks.router import router as tasks_router

api_router = APIRouter(prefix="")

# Register domain routers here as they are built
api_router.include_router(auth_router)
api_router.include_router(clients_router)
api_router.include_router(projects_router)
api_router.include_router(tasks_router)
