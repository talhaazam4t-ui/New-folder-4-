"""Central API Router mounting all Version 1 Domain Endpoints.
"""

from app.api.v1.admin import router as admin_router
from app.api.v1.agents import router as agents_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.assistant import router as assistant_router
from app.api.v1.auth import router as auth_router
from app.api.v1.business import router as business_router
from app.api.v1.finance import router as finance_router
from app.api.v1.growth_upsells import router as growth_upsells_router
from app.api.v1.inbox import router as inbox_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.internal import router as internal_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.lead_hunter import router as lead_hunter_router
from app.api.v1.marketing import router as marketing_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.payments import router as payments_router
from app.api.v1.receptionist import router as receptionist_router
from app.api.v1.services import router as services_router
from app.api.v1.subscriptions import router as subscriptions_router
from app.api.v1.support import router as support_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.tenants import router as tenants_router
from app.api.v1.users import router as users_router
from fastapi import APIRouter

api_v1_router = APIRouter(prefix="/api/v1")

# Mount Version 1 subrouters
api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(tenants_router)
api_v1_router.include_router(services_router)
api_v1_router.include_router(subscriptions_router)
api_v1_router.include_router(payments_router)
api_v1_router.include_router(business_router)
api_v1_router.include_router(finance_router)
api_v1_router.include_router(marketing_router)
api_v1_router.include_router(tasks_router)
api_v1_router.include_router(approvals_router)
api_v1_router.include_router(agents_router)
api_v1_router.include_router(integrations_router)
api_v1_router.include_router(inbox_router)
api_v1_router.include_router(notifications_router)
api_v1_router.include_router(analytics_router)
api_v1_router.include_router(assistant_router)
api_v1_router.include_router(support_router)
api_v1_router.include_router(receptionist_router)
api_v1_router.include_router(knowledge_router)
api_v1_router.include_router(growth_upsells_router)
api_v1_router.include_router(lead_hunter_router)
api_v1_router.include_router(internal_router)
api_v1_router.include_router(admin_router)
