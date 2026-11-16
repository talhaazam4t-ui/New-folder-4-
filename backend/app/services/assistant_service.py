"""Teloxtech Services Assistant — Conversational Sales Concierge Service.

Integrates with:
1. Google Gemini Flash-Lite API (`gemini-2.5-flash-lite` / `gemini-2.0-flash-lite` / `gemini-1.5-flash`).
2. Smart lead qualification and conversational detail capture.
3. Managed AI service recommendations with smooth Client Service Dashboard redirect signals.
4. Intelligent fallback concierge engine for offline / unkeyed environments.
"""

import os
import re
from typing import Any, Dict, List, Optional

import httpx
from app.config import settings
from app.core.logging import logger
from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse, ChatMessagePayload

TELOXTECH_SYSTEM_PROMPT = """You are the official "Teloxtech Services Assistant", a responsible, persuasive, and professional AI Sales Concierge for Teloxtech (https://teloxtech.com) — a premier Done-For-You Managed AI Automation Platform.

TELOXTECH MANAGED SERVICE CATALOG:
1. Business Financial & Rent Tracking (Slug: "business-financial-tracking", Dashboard URL: "/finance")
   - Value: Eliminates manual bookkeeping, automates rent payment reminders via WhatsApp, logs multi-currency income/expenses, and reconciles balances in real time.
   - Ideal For: Landlords, Real Estate managers, Clinics, Agencies, and SMEs.
   - Plans: Starter ($99/mo), Growth ($249/mo), Enterprise ($499/mo).

2. WhatsApp Client Support & Patient/Buyer Conversational AI (Slug: "whatsapp-conversational-ai", Dashboard URL: "/onboarding?service=whatsapp")
   - Value: 24/7 intelligent automated customer support, patient medical triage, doctor appointment booking with Google Calendar sync, property viewing coordinator.
   - Ideal For: Clinics, Dental practices, Real Estate brokers, E-Commerce brands.
   - Plans: Starter ($149/mo), Growth ($279/mo), Enterprise ($549/mo).

3. Omnichannel Lead Generation & Growth Engine (Slug: "lead-generation-outreach", Dashboard URL: "/marketing")
   - Value: Managed Google Maps/Places B2B lead harvesting worldwide (e.g. Dubai, Riyadh, London, Toronto), automated lead scoring (0-100%), and personalized multi-channel outreach.
   - Ideal For: B2B services, Financial advisors, High-ticket sales, Real estate agencies.
   - Plans: Starter ($199/mo), Growth ($349/mo), Enterprise ($599/mo).

4. Multi-Agent Task Orchestration Suite (Slug: "multi-agent-orchestration", Dashboard URL: "/onboarding?service=orchestration")
   - Value: Complete done-for-you multi-agent operational engine coordinating research, planning, execution, and QA verification.
   - Ideal For: Enterprises wanting full-funnel hands-off automation.
   - Plans: Starter ($199/mo), Growth ($399/mo), Enterprise ($799/mo).

CONVERSATIONAL OBJECTIVES:
1. Role & Tone: Polite, proactive, confident, and business-focused.
2. Lead Qualification: Inquire naturally about their company name, industry, current bottlenecks, and goals to capture their profile.
3. Service Recommendation: Recommend the specific Teloxtech managed package that best solves their problem.
4. Closing & Dashboard Redirect: Once the visitor agrees or is ready to get started, confirm their choice with an encouraging summary and provide a dashboard navigation link.
5. Important: Do NOT repeat the phone number in your text; direct WhatsApp contact is already pinned right above the user input box.

FORMATTING RULE:
Whenever you recommend a specific service or the user is ready to explore/onboard, append a single recommendation tag at the end of your message in this exact format:
[[RECOMMEND: service_slug | Service Name | /dashboard_url]]
Example:
[[RECOMMEND: business-financial-tracking | Business Financial & Rent Tracking | /finance]]
"""


class AssistantService:
    """Manages conversational AI sales interactions, Gemini Flash-Lite calling, and lead capture."""

    def __init__(self):
        self.default_gemini_models = [
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
        ]

    async def chat(self, request: AssistantChatRequest) -> AssistantChatResponse:
        """Process conversational turn using Gemini Flash-Lite or smart fallback concierge."""
        # 1. Resolve API Key priority: Client payload -> Environment -> Config
        api_key = (
            request.api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or settings.gemini_api_key
            or settings.ai_api_key
        )

        target_model = request.model or settings.gemini_model or "gemini-2.5-flash-lite"

        # 2. Extract any lead qualification details from conversation
        captured_lead = self._extract_lead_profile(request.messages, request)

        # 3. Attempt Gemini API execution if an API key is present
        if api_key and api_key != "your-openrouter-api-key" and api_key != "mock":
            try:
                # Check whether key is a Google Gemini key or OpenRouter key
                if api_key.startswith("sk-or-") or "openrouter" in settings.ai_provider:
                    gemini_result = await self._call_openrouter_gemini(
                        api_key=api_key,
                        messages=request.messages,
                        model=target_model,
                    )
                else:
                    gemini_result = await self._call_google_gemini_flash_lite(
                        api_key=api_key,
                        messages=request.messages,
                        model=target_model,
                    )

                if gemini_result:
                    reply_text, action_url, action_label, service_slug, service_name = (
                        self._parse_recommendation(gemini_result)
                    )
                    return AssistantChatResponse(
                        success=True,
                        reply=reply_text,
                        model_used=f"{target_model} (Live API)",
                        action_url=action_url,
                        action_label=action_label,
                        service_slug=service_slug,
                        service_name=service_name,
                        captured_lead=captured_lead,
                    )
            except Exception as exc:
                logger.warning("Gemini Flash-Lite API call failed, falling back to local concierge", error=str(exc))

        # 4. Smart Local Sales Concierge Fallback (Guaranteed fast, intelligent response)
        fallback_reply, action_url, action_label, service_slug, service_name = (
            self._generate_concierge_response(request.messages, captured_lead)
        )

        return AssistantChatResponse(
            success=True,
            reply=fallback_reply,
            model_used=f"{target_model} (Fast Concierge Engine)",
            action_url=action_url,
            action_label=action_label,
            service_slug=service_slug,
            service_name=service_name,
            captured_lead=captured_lead,
        )

    async def _call_google_gemini_flash_lite(
        self,
        api_key: str,
        messages: List[ChatMessagePayload],
        model: str = "gemini-2.5-flash-lite",
    ) -> Optional[str]:
        """Call Google Generative Language REST API for Gemini Flash-Lite."""
        # Convert messages to Gemini contents structure
        contents = []
        for msg in messages:
            role = "model" if msg.role in ("assistant", "model", "bot") else "user"
            contents.append({"role": role, "parts": [{"text": msg.content}]})

        payload = {
            "system_instruction": {
                "parts": [{"text": TELOXTECH_SYSTEM_PROMPT}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 600,
            },
        }

        # Try specified model, with automatic fallback across Flash-Lite versions
        models_to_try = [model] + [m for m in self.default_gemini_models if m != model]
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=20.0) as client:
            for m in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
                try:
                    res = await client.post(url, headers=headers, json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return parts[0].get("text", "").strip()
                    elif res.status_code in (404, 400):
                        logger.info("Model not available, trying next Gemini variant", model=m, status=res.status_code)
                        continue
                    else:
                        logger.warning("Gemini request returned non-200", status=res.status_code, text=res.text[:200])
                except Exception as exc:
                    logger.debug("Attempt failed for Gemini model", model=m, error=str(exc))
                    continue

        return None

    async def _call_openrouter_gemini(
        self,
        api_key: str,
        messages: List[ChatMessagePayload],
        model: str,
    ) -> Optional[str]:
        """Call OpenRouter gateway using Gemini Flash-Lite."""
        openrouter_messages = [{"role": "system", "content": TELOXTECH_SYSTEM_PROMPT}]
        for m in messages:
            r = "assistant" if m.role in ("bot", "model") else m.role
            openrouter_messages.append({"role": r, "content": m.content})

        # Map to OpenRouter model identifier
        or_model = "google/gemini-2.0-flash-lite:free" if "lite" in model else "google/gemini-flash-1.5"
        payload = {
            "model": or_model,
            "messages": openrouter_messages,
            "temperature": 0.3,
            "max_tokens": 600,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": settings.backend_url,
            "X-Title": "Teloxtech Assistant",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=25.0) as client:
            res = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            if res.status_code == 200:
                data = res.json()
                choice = data.get("choices", [{}])[0]
                return choice.get("message", {}).get("content", "").strip()

        return None

    def _parse_recommendation(
        self, text: str
    ) -> tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
        """Parse structured recommendation tags from AI response."""
        pattern = r"\[\[RECOMMEND:\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^\]]+)\]\]"
        match = re.search(pattern, text)
        if match:
            service_slug = match.group(1).strip()
            service_name = match.group(2).strip()
            action_url = match.group(3).strip()
            action_label = f"👉 Proceed to Client Service Dashboard: {service_name}"
            # Clean response text
            clean_reply = re.sub(pattern, "", text).strip()
            return clean_reply, action_url, action_label, service_slug, service_name

        return text, None, None, None, None

    def _extract_lead_profile(
        self, messages: List[ChatMessagePayload], req: AssistantChatRequest
    ) -> Dict[str, Any]:
        """Extract lead qualification data from user conversation turns."""
        full_conversation = " ".join([m.content for m in messages if m.role == "user"])
        lead: Dict[str, Any] = {
            "name": req.visitor_name,
            "business_type": req.business_type,
            "contact_info": req.contact_info,
            "service_needed": None,
        }

        # Check for email
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", full_conversation)
        if email_match:
            lead["email"] = email_match.group(0)

        # Check for phone
        phone_match = re.search(r"(\+?[0-9]{1,4}?[-.\s]?\(?[0-9]{1,3}?\)?[-.\s]?[0-9]{3,4}[-.\s]?[0-9]{3,4})", full_conversation)
        if phone_match and len(phone_match.group(0).strip()) >= 7:
            lead["phone"] = phone_match.group(0).strip()

        # Infer business vertical
        lower_conv = full_conversation.lower()
        if any(w in lower_conv for w in ("real estate", "rent", "tenant", "property", "lease", "landlord")):
            lead["business_type"] = lead["business_type"] or "Real Estate / Property"
            lead["service_needed"] = "Business Financial & Rent Tracking"
        elif any(w in lower_conv for w in ("clinic", "hospital", "patient", "dental", "doctor", "appointment")):
            lead["business_type"] = lead["business_type"] or "Clinics / Healthcare"
            lead["service_needed"] = "WhatsApp Client Support & Patient Triage"
        elif any(w in lower_conv for w in ("lead", "outreach", "maps", "b2b", "marketing", "clients", "sales")):
            lead["business_type"] = lead["business_type"] or "B2B Sales & Agency"
            lead["service_needed"] = "Omnichannel Lead Generation & Growth Engine"
        elif any(w in lower_conv for w in ("ecommerce", "store", "retail", "orders", "shop")):
            lead["business_type"] = lead["business_type"] or "E-Commerce / Retail"
            lead["service_needed"] = "WhatsApp Commerce & Support"

        return lead

    def _generate_concierge_response(
        self, messages: List[ChatMessagePayload], lead: Dict[str, Any]
    ) -> tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
        """Intelligent, conversational sales concierge rules engine."""
        last_msg = messages[-1].content.lower() if messages else ""

        # 1. Rent Tracking / Financial Management
        if any(w in last_msg for w in ("rent", "finance", "ledger", "landlord", "tenant", "bookkeeping", "invoice")):
            reply = (
                "For property managers, landlords, and businesses tracking recurring revenue, our "
                "**Business Financial & Rent Tracking** module is a game changer. It automates WhatsApp rent "
                "reminders 3 days before due dates, captures payment receipts, and provides real-time cash flow statements. "
                "Would you like to review this package on your Client Service Dashboard?"
            )
            return (
                reply,
                "/finance",
                "👉 Proceed to Client Service Dashboard: Business Financial & Rent Tracking",
                "business-financial-tracking",
                "Business Financial & Rent Tracking",
            )

        # 2. WhatsApp Customer Support / Patient Booking
        if any(w in last_msg for w in ("whatsapp", "patient", "clinic", "doctor", "receptionist", "booking", "appointment", "chat")):
            reply = (
                "Our **WhatsApp Conversational AI & Client Support** service gives your business a 24/7 autonomous receptionist. "
                "It handles patient intake, schedules appointments directly into Google Calendar, and coordinates client viewing requests without manual intervention. "
                "Shall I direct you to the service setup dashboard?"
            )
            return (
                reply,
                "/onboarding?service=whatsapp",
                "👉 Proceed to Client Service Dashboard: WhatsApp Conversational AI",
                "whatsapp-conversational-ai",
                "WhatsApp Client Support & Conversational AI",
            )

        # 3. Lead Generation / Growth / Google Maps
        if any(w in last_msg for w in ("lead", "growth", "maps", "places", "outreach", "b2b", "sales", "client acquisition")):
            reply = (
                "Our **Omnichannel Lead Generation & Growth Engine** harvests verified B2B leads directly from Google Maps worldwide "
                "(Dubai, Riyadh, London, etc.), scores them based on quality metrics, and executes personalized outreach campaigns. "
                "Let's open your Client Service Dashboard to configure your lead pipeline."
            )
            return (
                reply,
                "/marketing",
                "👉 Proceed to Client Service Dashboard: Lead Generation & Growth Engine",
                "lead-generation-outreach",
                "Omnichannel Lead Generation & Growth Engine",
            )

        # 4. Ready to proceed / Register / Onboarding
        if any(w in last_msg for w in ("ready", "proceed", "start", "sign up", "register", "onboard", "dashboard", "yes", "package")):
            service_needed = lead.get("service_needed") or "Business Financial & Rent Tracking"
            target_url = "/onboarding"
            if "Rent" in service_needed or "Finance" in service_needed:
                target_url = "/finance"
            elif "WhatsApp" in service_needed:
                target_url = "/onboarding?service=whatsapp"
            elif "Lead" in service_needed:
                target_url = "/marketing"

            reply = (
                f"Fantastic! Based on our discussion, **{service_needed}** is the ideal solution to automate your operations. "
                "I have prepared your workspace. Click below to proceed directly to your Client Service Dashboard and finalize your onboarding."
            )
            return (
                reply,
                target_url,
                f"👉 Proceed to Client Service Dashboard: {service_needed}",
                "business-financial-tracking",
                service_needed,
            )

        # 5. Pricing / Cost inquiries
        if any(w in last_msg for w in ("price", "cost", "how much", "rate", "fee", "plans")):
            reply = (
                "Our managed AI services start at just **$99/month** (Starter) for full financial tracking, and **$149–$199/month** "
                "for 24/7 WhatsApp concierge or global Google Maps lead generation. Every tier is done-for-you with dedicated engineering support. "
                "What specific service would you like to set up for your business?"
            )
            return (
                reply,
                "/onboarding",
                "👉 View Service Packages on Client Dashboard",
                "multi-agent-orchestration",
                "Managed AI Service Catalog",
            )

        # 6. Default Discovery Turn
        reply = (
            "I'd be glad to help! At Teloxtech, we eliminate manual business overhead through managed AI automations — "
            "including automated **Rent & Financial Tracking**, **24/7 WhatsApp AI Support**, and **Google Maps Lead Growth**. "
            "Could you share a little about your business or the biggest manual task you'd like us to take off your plate?"
        )
        return reply, None, None, None, None


assistant_service = AssistantService()
