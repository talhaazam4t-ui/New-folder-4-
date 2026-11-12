"""Integration Management Service (WhatsApp Cloud API, Meta Embedded Signup, and Webhook Processor).
"""

import uuid
from typing import Any, Dict, List, Optional

from app.automation.approval_manager import approval_manager
from app.core.exceptions import ResourceNotFoundError
from app.database.models.automation import AuditLog, Integration
from app.integrations.ai_providers.router import route_and_execute_ai_task
from app.integrations.whatsapp.client import whatsapp_client
from app.integrations.whatsapp.onboarding import whatsapp_onboarding_adapter
from app.schemas.approval import ApprovalCreateRequest
from app.schemas.business import BusinessRecordCreateRequest
from app.schemas.marketing import LeadCreateRequest
from app.services.business_service import business_service
from app.services.marketing_service import marketing_service
from app.services.notification_service import notification_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class IntegrationService:
    """Manages tenant integrations, Meta Embedded Signup, and inbound WhatsApp event routing."""

    def _to_dict(self, row: Integration) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "provider": row.provider,
            "integration_type": row.integration_type,
            "status": row.status,
            "external_account_id": row.external_account_id,
            "configuration": row.configuration or {},
            "created_at": row.created_at.isoformat(),
        }

    async def connect_whatsapp(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        oauth_code: str,
    ) -> Dict[str, Any]:
        """Connect WhatsApp Business via Meta Embedded Signup OAuth code exchange."""
        onboarding = await whatsapp_onboarding_adapter.exchange_code_and_register_waba(
            tenant_id=str(tenant_id),
            oauth_code=oauth_code,
        )

        res = await session.execute(
            select(Integration).where(
                Integration.tenant_id == tenant_id,
                Integration.provider == "whatsapp",
            )
        )
        integ = res.scalar_one_or_none()
        config_payload = {
            "waba_id": onboarding.waba_id,
            "phone_number_id": onboarding.phone_number_id,
            "display_phone_number": onboarding.display_phone_number,
            "is_mock": onboarding.is_mock,
            "details": onboarding.details or {},
        }

        if integ:
            integ.status = "connected"
            integ.external_account_id = onboarding.waba_id
            integ.configuration = config_payload
        else:
            integ = Integration(
                tenant_id=tenant_id,
                provider="whatsapp",
                integration_type="messaging",
                status="connected",
                external_account_id=onboarding.waba_id,
                configuration=config_payload,
            )
            session.add(integ)

        await session.flush()

        audit = AuditLog(
            tenant_id=tenant_id,
            actor_id=user_id,
            actor_type="user",
            action="integration.whatsapp.connected",
            resource_type="integration",
            resource_id=integ.id,
            metadata_={"waba_id": onboarding.waba_id, "phone": onboarding.display_phone_number},
        )
        session.add(audit)
        await session.commit()
        await session.refresh(integ)
        return self._to_dict(integ)

    async def list_integrations(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        """List all integrations configured for the tenant."""
        res = await session.execute(
            select(Integration).where(Integration.tenant_id == tenant_id)
        )
        return [self._to_dict(row) for row in res.scalars().all()]

    async def disconnect_integration(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        integration_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Disconnect an active integration for the tenant."""
        res = await session.execute(
            select(Integration).where(
                Integration.id == integration_id,
                Integration.tenant_id == tenant_id,
            )
        )
        integ = res.scalar_one_or_none()
        if not integ:
            raise ResourceNotFoundError("Integration", str(integration_id))

        integ.status = "disconnected"
        audit = AuditLog(
            tenant_id=tenant_id,
            actor_id=user_id,
            actor_type="user",
            action="integration.disconnected",
            resource_type="integration",
            resource_id=integ.id,
            metadata_={"provider": integ.provider},
        )
        session.add(audit)
        await session.commit()
        await session.refresh(integ)
        return self._to_dict(integ)

    async def process_inbound_whatsapp_message(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        sender_phone: str,
        sender_name: str,
        message_text: str,
        message_id: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Process an inbound WhatsApp message with financial ambiguity guardrails.

        1. Unambiguous financial message -> records `BusinessRecord` (`source='whatsapp'`).
        2. Ambiguous financial message -> queues `Approval` (`confirm_ambiguous_whatsapp_transaction`)
           and sends notification WITHOUT altering the ledger.
        3. Customer inquiry -> captures `Lead` (`source='whatsapp'`) and drafts fast-tier AI reply.
        """
        parsed = whatsapp_client.parse_and_classify_inbound_message(message_text)
        msg_ref = message_id or f"wamid.{uuid.uuid4().hex[:10]}"

        if parsed.intent_type == "financial_confirmed" and parsed.amount and parsed.record_type:
            record = await business_service.create_record(
                session=session,
                tenant_id=tenant_id,
                user_id=user_id or tenant_id,
                request=BusinessRecordCreateRequest(
                    record_type=parsed.record_type,  # type: ignore[arg-type]
                    title=parsed.summary_title,
                    amount=parsed.amount,
                    currency=parsed.currency,
                    description=f"WhatsApp sender: {sender_name} ({sender_phone})",
                    source="whatsapp",
                    reference_id=msg_ref,
                ),
            )
            await notification_service.send_notification(
                session=session,
                tenant_id=tenant_id,
                title="WhatsApp Financial Transaction Recorded",
                message=f"Recorded {parsed.record_type} of ${parsed.amount:.2f} from {sender_name}.",
                channel="whatsapp",
            )
            return {
                "classification": "financial_confirmed",
                "requires_confirmation": False,
                "business_record_id": str(record.id),
                "amount": parsed.amount,
                "record_type": parsed.record_type,
            }

        if parsed.intent_type == "financial_ambiguous":
            approval = await approval_manager.request_approval(
                session=session,
                tenant_id=tenant_id,
                request=ApprovalCreateRequest(
                    action_type="confirm_ambiguous_whatsapp_transaction",
                    proposed_action={
                        "sender_phone": sender_phone,
                        "sender_name": sender_name,
                        "raw_text": message_text,
                        "detected_amount": parsed.amount,
                        "detected_type": parsed.record_type,
                        "message_id": msg_ref,
                    },
                    requested_by="whatsapp_webhook_processor",
                ),
            )
            await notification_service.send_notification(
                session=session,
                tenant_id=tenant_id,
                title="Ambiguous WhatsApp Payment Needs Confirmation",
                message=f"Message from {sender_name} ('{message_text}') requires human confirmation before ledger entry.",
                channel="in_app",
            )
            return {
                "classification": "financial_ambiguous",
                "requires_confirmation": True,
                "approval_id": str(approval.id),
                "business_record_id": None,
            }

        # General customer lead / inquiry
        lead = await marketing_service.create_lead(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id or tenant_id,
            request=LeadCreateRequest(
                name=sender_name,
                phone=sender_phone,
                source="whatsapp",
                notes=message_text,
            ),
        )
        ai_reply = await route_and_execute_ai_task(
            task_type="whatsapp_reply",
            prompt=f"Customer {sender_name} wrote via WhatsApp: '{message_text}'. Write a helpful reply.",
            tenant_id=str(tenant_id),
        )
        return {
            "classification": "lead_inquiry",
            "requires_confirmation": False,
            "lead_id": str(lead.id),
            "auto_reply": ai_reply.content,
            "model_used": ai_reply.model,
        }


integration_service = IntegrationService()
