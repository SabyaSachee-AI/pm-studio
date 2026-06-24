"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.admin.ai_config.router import router as admin_ai_config_router
from app.api.v1.admin.screen_permissions.router import router as admin_screen_perms_router
from app.api.v1.dashboard.router import router as dashboard_router
from app.api.v1.ai_models.router import router as ai_models_router
from app.api.v1.architecture.router import router as architecture_router
from app.api.v1.auth.router import router as auth_router
from app.api.v1.build.router import router as build_router
from app.api.v1.clients.router import router as clients_router
from app.api.v1.decisions.router import router as decisions_router
from app.api.v1.documents.router import router as documents_router
from app.api.v1.jobs.router import router as jobs_router
from app.api.v1.knowledge.router import router as knowledge_router
from app.api.v1.notifications.router import router as notifications_router
from app.api.v1.prds.router import router as prds_router
from app.api.v1.projects.router import router as projects_router
from app.api.v1.requirements.router import router as requirements_router
from app.api.v1.specs.router import router as specs_router
from app.api.v1.srs.router import router as srs_router
from app.api.v1.tasks.router import router as celery_tasks_router
from app.api.v1.tasks_domain.router import router as tasks_domain_router
from app.api.v1.users.router import router as users_router

api_router = APIRouter(prefix="")

# Register domain routers here as they are built
api_router.include_router(dashboard_router)
api_router.include_router(auth_router)
api_router.include_router(clients_router)
api_router.include_router(projects_router)
api_router.include_router(prds_router)
api_router.include_router(requirements_router)
api_router.include_router(srs_router)
api_router.include_router(architecture_router)
api_router.include_router(build_router)
api_router.include_router(specs_router)
api_router.include_router(tasks_domain_router)
api_router.include_router(jobs_router)
api_router.include_router(celery_tasks_router)
api_router.include_router(knowledge_router)
api_router.include_router(decisions_router)
api_router.include_router(notifications_router)
api_router.include_router(users_router)
api_router.include_router(admin_ai_config_router)
api_router.include_router(admin_screen_perms_router)
api_router.include_router(ai_models_router)
api_router.include_router(documents_router)
