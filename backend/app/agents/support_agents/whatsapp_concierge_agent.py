"""Specialized Support Agent — WhatsApp Concierge & Lead Triage Assistant.
"""

from app.agents.base_agent import BaseAgent


class WhatsAppConciergeAgent(BaseAgent):
    name = "whatsapp_concierge_agent"
    role = "WhatsApp Customer Concierge"
    category = "support"
    support_phone = "03238300330"
    description = (
        "Handles inbound customer WhatsApp inquiries, drafts polite auto-replies, "
        "routes service inquiries to WhatsApp 03238300330, and flags ambiguous "
        "payment confirmations for human verification."
    )
    default_task_type = "whatsapp_reply"
    allowed_tools = {"read_context", "draft_whatsapp_reply", "qualify_lead"}
    max_steps = 3
    timeout_seconds = 20


whatsapp_concierge_agent = WhatsAppConciergeAgent()
