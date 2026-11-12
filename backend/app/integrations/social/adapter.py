"""Social Media Campaign Publishing Adapter (`backend/app/integrations/social/`).

Enforces non-negotiable Rule #8 & #9: refuses to publish any campaign post
unless `human_approved=True` is explicitly verified.
"""

import uuid
from typing import Any, Dict

from app.core.exceptions import ApprovalRequiredError
from app.core.logging import logger
from app.integrations.base import BaseIntegrationAdapter


class SocialPublishingAdapter(BaseIntegrationAdapter):
    """Adapter for publishing approved marketing creatives to Meta, LinkedIn, and Instagram."""

    provider_name = "social"
    integration_type = "marketing"

    async def health_check(self) -> Dict[str, Any]:
        return {"provider": self.provider_name, "healthy": True}

    async def publish_campaign_post(
        self,
        tenant_id: str,
        platform: str,
        content: str,
        human_approved: bool = False,
    ) -> Dict[str, Any]:
        if not human_approved:
            raise ApprovalRequiredError(
                "Social media campaign posts cannot be published without explicit human approval."
            )

        post_id = f"social.{platform}.{uuid.uuid4().hex[:10]}"
        logger.info(
            "Published approved social campaign post",
            tenant_id=tenant_id,
            platform=platform,
            post_id=post_id,
        )
        return {
            "success": True,
            "post_id": post_id,
            "platform": platform,
            "status": "published",
        }


social_adapter = SocialPublishingAdapter()
