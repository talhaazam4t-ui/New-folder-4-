"""WhatsApp Business Cloud API Client & Inbound Financial Message Parser (Section 11).

Enforces the Section 8.3 & 11.2 safety rule:
- Unambiguous financial messages (single clear amount + clear confirmed intent) can be extracted.
- Ambiguous financial messages (multiple conflicting amounts, tentative language like 'maybe', 'around',
  'not sure', 'later', or '?') are flagged `is_ambiguous=True` and routed to Human Approval
  instead of silently writing to the financial ledger.
"""

import re
import uuid
from typing import Any, Dict, Optional

import httpx
from app.config import settings
from app.core.exceptions import PermissionDeniedError
from app.core.logging import logger
from app.integrations.base import BaseIntegrationAdapter
from pydantic import BaseModel

AMBIGUOUS_REGEX = re.compile(
    r"(?:\b(?:maybe|around|approx|not\s+sure|later|tomorrow|think|or|estimate)\b|\?)",
    re.IGNORECASE,
)


class ParsedWhatsAppIntent(BaseModel):
    intent_type: str  # "financial_confirmed", "financial_ambiguous", "lead_inquiry"
    record_type: Optional[str] = None  # "rent", "payment_received", "expense", "income"
    amount: Optional[float] = None
    currency: str = "USD"
    is_ambiguous: bool = False
    summary_title: str = ""
    raw_text: str = ""


class WhatsAppCloudClient(BaseIntegrationAdapter):
    """Handles WhatsApp Cloud API webhook verification, outbound messages, and inbound parsing."""

    provider_name = "whatsapp"
    integration_type = "messaging"

    def __init__(self):
        self.graph_api_url = "https://graph.facebook.com/v21.0"

    async def health_check(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "mode": settings.whatsapp_provider,
            "healthy": True,
        }

    def verify_webhook_challenge(
        self,
        hub_mode: Optional[str],
        hub_verify_token: Optional[str],
        hub_challenge: Optional[str],
    ) -> str:
        """Verify Meta WhatsApp webhook subscription challenge."""
        if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
            return hub_challenge or ""
        raise PermissionDeniedError("WhatsApp webhook verify token mismatch")

    async def send_text_message(
        self,
        tenant_id: str,
        to_phone: str,
        message_body: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an outbound WhatsApp message via Meta Cloud API or sandbox mock."""
        if settings.whatsapp_provider == "mock" or not settings.whatsapp_access_token:
            msg_id = f"wamid.mock.{uuid.uuid4().hex[:12]}"
            logger.info(
                "Sent WhatsApp message (sandbox mock)",
                tenant_id=tenant_id,
                to_phone=to_phone,
                message_id=msg_id,
            )
            return {
                "success": True,
                "message_id": msg_id,
                "to": to_phone,
                "status": "sent",
                "is_mock": True,
            }

        target_phone_id = phone_number_id or settings.whatsapp_phone_number_id
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{self.graph_api_url}/{target_phone_id}/messages",
                headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to_phone,
                    "type": "text",
                    "text": {"body": message_body},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "success": True,
                "message_id": data.get("messages", [{}])[0].get("id", "wamid.live"),
                "to": to_phone,
                "status": "sent",
                "is_mock": False,
            }

    def parse_and_classify_inbound_message(self, message_text: str) -> ParsedWhatsAppIntent:
        """Classify inbound WhatsApp text into confirmed financial, ambiguous financial, or lead inquiry."""
        lower = message_text.lower().strip()
        # Filter out unit numbers when preceded by 'unit' or '#'
        cleaned_text = re.sub(r"(?:unit|apt|#)\s*\d+", "", lower)
        currency_amounts = re.findall(r"(?:\$|usd|pkr|eur|rs\.?\s*)\s*(\d+(?:\.\d{1,2})?)", cleaned_text)
        if not currency_amounts:
            currency_amounts = re.findall(r"\b(\d{2,7}(?:\.\d{1,2})?)\b", cleaned_text)

        financial_keywords = {"paid", "rent", "payment", "received", "expense", "invoice", "transfer", "sent"}
        has_financial_keyword = any(kw in lower for kw in financial_keywords)

        if not has_financial_keyword or not currency_amounts:
            return ParsedWhatsAppIntent(
                intent_type="lead_inquiry",
                is_ambiguous=False,
                summary_title="Customer WhatsApp Inquiry",
                raw_text=message_text,
            )

        # Check for ambiguity: multiple distinct amounts or uncertain/tentative language
        has_ambiguous_word = bool(AMBIGUOUS_REGEX.search(lower))
        multiple_amounts = len(currency_amounts) > 1

        parsed_amount = float(currency_amounts[0])
        if "rent" in lower:
            rec_type = "rent"
            title = "WhatsApp Rent Payment"
        elif "expense" in lower or "invoice" in lower:
            rec_type = "expense"
            title = "WhatsApp Reported Expense"
        else:
            rec_type = "payment_received"
            title = "WhatsApp Payment Received"

        if has_ambiguous_word or multiple_amounts:
            return ParsedWhatsAppIntent(
                intent_type="financial_ambiguous",
                record_type=rec_type,
                amount=parsed_amount,
                is_ambiguous=True,
                summary_title=f"Ambiguous {title}: {message_text[:60]}",
                raw_text=message_text,
            )

        return ParsedWhatsAppIntent(
            intent_type="financial_confirmed",
            record_type=rec_type,
            amount=parsed_amount,
            is_ambiguous=False,
            summary_title=f"{title}: {message_text[:60]}",
            raw_text=message_text,
        )


whatsapp_client = WhatsAppCloudClient()
