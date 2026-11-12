"""Central API Router mounting all Version 1 Domain Endpoints.
"""

from app.api.v1.admin import router as admin_router
from app.api.v1.agents import router as agents_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.auth import router as auth_router
from app.api.v1.business import router as business_router
from app.api.v1.payments import router as payments_router
from app.api.v1.services import router as services_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.tenants import router as tenants_router
from fastapi import APIRouter

api_v1_router = APIRouter(prefix="/api/v1")

# Mount Version 1 subrouters
api_v1_router.include_router(auth_router)
api_v1_router.include_router(tenants_router)
api_v1_router.include_router(services_router)
api_v1_router.include_router(payments_router)
api_v1_router.include_router(business_router)
api_v1_router.include_router(tasks_router)
api_v1_router.include_router(approvals_router)
api_v1_router.include_router(agents_router)
api_v1_router.include_router(admin_router)
