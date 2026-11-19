"""Teloxtech Services Assistant — Conversational Sales Concierge Service.

Integrates with:
1. DeepSeek AI (`deepseek-chat` / `deepseek-reasoner`) as the primary live AI provider.
2. Optional Google Gemini Flash-Lite API if a valid Gemini key is explicitly passed.
3. Smart lead qualification and conversational detail capture.
4. Managed AI service recommendations aligned with canonical catalog slugs.
5. Intelligent fallback concierge engine for offline / unkeyed environments.
"""

import os
import re
from typing import Any, Dict, List, Optional

import httpx
from app.config import settings
from app.core.logging import logger
from app.core.security import sanitize_ai_prompt
from app.integrations.ai_providers.router import route_and_execute_ai_task
from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse, ChatMessagePayload

TELOXTECH_SYSTEM_PROMPT = """You are the official "Teloxtech Services Assistant", a responsible, persuasive, and professional AI Sales Concierge for Teloxtech (https://teloxtech.stream) — a premier Done-For-You Managed AI Automation Platform.

TELOXTECH MANAGED SERVICE CATALOG:
1. Business Financial Tracking & Ledger (Slug: "business-financial-tracking", Dashboard URL: "/finance")
   - Value: Eliminates manual bookkeeping, automates rent payment reminders via WhatsApp, logs multi-currency income/expenses, and reconciles balances in real time.
   - Ideal For: Landlords, Real Estate managers, Clinics, Agencies, and SMEs.
   - Plans: Starter ($99/mo), Growth ($249/mo), Enterprise ($499/mo).

2. WhatsApp Business Concierge & Webhook Sync (Slug: "whatsapp-business-concierge", Dashboard URL: "/onboarding?service=whatsapp-business-concierge")
   - Value: 24/7 intelligent automated customer support, patient medical triage, doctor appointment booking with Google Calendar sync, property viewing coordinator.
   - Ideal For: Clinics, Dental practices, Real Estate brokers, E-Commerce brands.
   - Plans: Starter ($129/mo), Growth ($279/mo), Enterprise ($549/mo).

3. AI Marketing & Growth Automation (Slug: "ai-marketing-growth", Dashboard URL: "/marketing")
   - Value: Managed Google Maps/Places B2B lead harvesting worldwide (e.g. Dubai, Riyadh, London, Toronto), automated lead scoring (0-100%), and personalized multi-channel outreach.
   - Ideal For: B2B services, Financial advisors, High-ticket sales, Real estate agencies.
   - Plans: Starter ($149/mo), Growth ($349/mo), Enterprise ($699/mo).

4. Multi-Agent Task Orchestration Suite (Slug: "multi-agent-orchestration", Dashboard URL: "/onboarding?service=multi-agent-orchestration")
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
[[RECOMMEND: business-financial-tracking | Business Financial Tracking & Ledger | /finance]]
"""


class AssistantService:
    """Manages conversational AI sales interactions (DeepSeek primary + optional Gemini) and lead capture."""

    def __init__(self):
        self.default_gemini_models = [
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
        ]

    async def chat(self, request: AssistantChatRequest) -> AssistantChatResponse:
        """Process conversational turn using DeepSeek AI (primary), optional Gemini, or smart concierge fallback."""
        captured_lead = self._extract_lead_profile(request.messages, request)

        explicit_key = (request.api_key or "").strip()
        target_model = (request.model or settings.ai_default_fast_model or "deepseek-chat").strip()
        if "gemini" in target_model.lower() and not explicit_key.startswith("AIza"):
            target_model = settings.ai_default_fast_model or "deepseek-chat"

        deepseek_key = (
            settings.deepseek_api_key
            or os.environ.get("DEEPSEEK_API_KEY")
            or (
                settings.ai_api_key
                if settings.ai_api_key
                and not settings.ai_api_key.startswith("sk-or-")
                and not settings.ai_api_key.startswith("AIza")
                else None
            )
        )
        has_live_deepseek = bool(
            deepseek_key
            and deepseek_key not in ("mock", "your-deepseek-api-key", "your-openrouter-api-key")
            and settings.ai_provider != "mock"
        )

        # 1. Explicit client-provided key routing
        if explicit_key and explicit_key not in ("mock", "your-openrouter-api-key", "your-deepseek-api-key"):
            try:
                if explicit_key.startswith("sk-or-"):
                    or_result = await self._call_openrouter(
                        api_key=explicit_key,
                        messages=request.messages,
                        model=target_model,
                    )
                    if or_result:
                        reply_text, action_url, action_label, service_slug, service_name = (
                            self._parse_recommendation(or_result)
                        )
                        return AssistantChatResponse(
                            success=True,
                            reply=reply_text,
                            model_used=f"{target_model} (OpenRouter API)",
                            action_url=action_url,
                            action_label=action_label,
                            service_slug=service_slug,
                            service_name=service_name,
                            captured_lead=captured_lead,
                        )
                elif explicit_key.startswith("AIza") or (
                    not explicit_key.startswith("sk-") and "gemini" in (request.model or "").lower()
                ):
                    gemini_model = request.model if (request.model and "gemini" in request.model.lower()) else "gemini-2.5-flash-lite"
                    gemini_result = await self._call_google_gemini_flash_lite(
                        api_key=explicit_key,
                        messages=request.messages,
                        model=gemini_model,
                    )
                    if gemini_result:
                        reply_text, action_url, action_label, service_slug, service_name = (
                            self._parse_recommendation(gemini_result)
                        )
                        return AssistantChatResponse(
                            success=True,
                            reply=reply_text,
                            model_used=f"{gemini_model} (Live Gemini API)",
                            action_url=action_url,
                            action_label=action_label,
                            service_slug=service_slug,
                            service_name=service_name,
                            captured_lead=captured_lead,
                        )
                else:
                    ds_result = await self._call_deepseek_chat(
                        api_key=explicit_key,
                        messages=request.messages,
                        model=target_model if "deepseek" in target_model else "deepseek-chat",
                    )
                    if ds_result:
                        reply_text, action_url, action_label, service_slug, service_name = (
                            self._parse_recommendation(ds_result)
                        )
                        return AssistantChatResponse(
                            success=True,
                            reply=reply_text,
                            model_used=f"{target_model} (Live DeepSeek API)",
                            action_url=action_url,
                            action_label=action_label,
                            service_slug=service_slug,
                            service_name=service_name,
                            captured_lead=captured_lead,
                        )
            except Exception as exc:
                logger.warning("Explicit AI API key call failed, continuing to server provider/fallback", error=str(exc))

        # 2. Primary Server Provider: Exclusive DeepSeek AI (via DeepSeek API / route_and_execute_ai_task)
        if has_live_deepseek and deepseek_key:
            try:
                ds_result, ds_http_error = await self._call_deepseek_chat_with_status(
                    api_key=deepseek_key,
                    messages=request.messages,
                    model=target_model if "deepseek" in target_model else "deepseek-chat",
                )
                if not ds_result and not ds_http_error:
                    # Secondary check via centralized router when no upstream HTTP error occurred
                    conversation_prompt = "\n".join(
                        f"{m.role.upper()}: {m.content}" for m in request.messages[-8:]
                    )
                    routed = await route_and_execute_ai_task(
                        task_type="simple_support",
                        prompt=conversation_prompt,
                        system_instruction=TELOXTECH_SYSTEM_PROMPT,
                        temperature=0.3,
                    )
                    if routed.success and not routed.is_mock and routed.content:
                        ds_result = routed.content

                if ds_result:
                    reply_text, action_url, action_label, service_slug, service_name = (
                        self._parse_recommendation(ds_result)
                    )
                    if not action_url:
                        _, action_url, action_label, service_slug, service_name = (
                            self._generate_concierge_response(request.messages, captured_lead)
                        )
                    return AssistantChatResponse(
                        success=True,
                        reply=reply_text,
                        model_used=f"{target_model} (Live DeepSeek API)",
                        action_url=action_url,
                        action_label=action_label,
                        service_slug=service_slug,
                        service_name=service_name,
                        captured_lead=captured_lead,
                    )
            except Exception as exc:
                logger.warning("DeepSeek assistant API call failed, falling back to local concierge", error=str(exc))

        # 3. Optional Server-Configured Gemini API Key (only if explicitly configured without DeepSeek)
        gemini_env_key = os.environ.get("GEMINI_API_KEY") or settings.gemini_api_key
        if gemini_env_key and gemini_env_key.startswith("AIza"):
            try:
                gemini_result = await self._call_google_gemini_flash_lite(
                    api_key=gemini_env_key,
                    messages=request.messages,
                    model=settings.gemini_model or "gemini-2.5-flash-lite",
                )
                if gemini_result:
                    reply_text, action_url, action_label, service_slug, service_name = (
                        self._parse_recommendation(gemini_result)
                    )
                    return AssistantChatResponse(
                        success=True,
                        reply=reply_text,
                        model_used=f"{settings.gemini_model} (Live Gemini API)",
                        action_url=action_url,
                        action_label=action_label,
                        service_slug=service_slug,
                        service_name=service_name,
                        captured_lead=captured_lead,
                    )
            except Exception as exc:
                logger.warning("Gemini assistant API call failed, falling back to local concierge", error=str(exc))

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

    async def _call_deepseek_chat(
        self,
        api_key: str,
        messages: List[ChatMessagePayload],
        model: str = "deepseek-chat",
    ) -> Optional[str]:
        """Call DeepSeek Chat Completions API with multi-turn sanitized messages."""
        content, _ = await self._call_deepseek_chat_with_status(
            api_key=api_key,
            messages=messages,
            model=model,
        )
        return content

    async def _call_deepseek_chat_with_status(
        self,
        api_key: str,
        messages: List[ChatMessagePayload],
        model: str = "deepseek-chat",
    ) -> tuple[Optional[str], bool]:
        """Call DeepSeek Chat Completions API and report whether an upstream HTTP error occurred."""
        ds_messages: List[Dict[str, str]] = [
            {"role": "system", "content": TELOXTECH_SYSTEM_PROMPT}
        ]
        for m in messages:
            role = "assistant" if m.role in ("assistant", "bot", "model") else "user"
            ds_messages.append({"role": role, "content": sanitize_ai_prompt(m.content)})

        ds_model = model if model in ("deepseek-chat", "deepseek-reasoner") else "deepseek-chat"
        payload: Dict[str, Any] = {
            "model": ds_model,
            "messages": ds_messages,
            "max_tokens": 4096 if "reasoner" in ds_model else 800,
        }
        if ds_model == "deepseek-chat":
            payload["temperature"] = 0.3

        base_url = settings.deepseek_base_url.rstrip("/")
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if res.status_code == 200:
                data = res.json()
                choices = data.get("choices") or []
                if choices:
                    content = (choices[0].get("message") or {}).get("content") or ""
                    return (content.strip() or None), False
            else:
                logger.warning(
                    "DeepSeek assistant returned non-200",
                    status=res.status_code,
                    text=res.text[:200],
                )
                return None, True
        return None, False

    async def _call_google_gemini_flash_lite(
        self,
        api_key: str,
        messages: List[ChatMessagePayload],
        model: str = "gemini-2.5-flash-lite",
    ) -> Optional[str]:
        """Call Google Generative Language REST API for Gemini Flash-Lite."""
        contents = []
        for msg in messages:
            role = "model" if msg.role in ("assistant", "model", "bot") else "user"
            contents.append({"role": role, "parts": [{"text": sanitize_ai_prompt(msg.content)}]})

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

    async def _call_openrouter(
        self,
        api_key: str,
        messages: List[ChatMessagePayload],
        model: str,
    ) -> Optional[str]:
        """Call OpenRouter gateway ONLY when explicitly provided an sk-or- key."""
        openrouter_messages = [{"role": "system", "content": TELOXTECH_SYSTEM_PROMPT}]
        for m in messages:
            r = "assistant" if m.role in ("bot", "model") else m.role
            openrouter_messages.append({"role": r, "content": sanitize_ai_prompt(m.content)})

        or_model = "deepseek/deepseek-chat" if "deepseek" in model else "google/gemini-2.0-flash-lite:free"
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
                choices = data.get("choices") or []
                if choices:
                    return (choices[0].get("message") or {}).get("content", "").strip()

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

        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", full_conversation)
        if email_match:
            lead["email"] = email_match.group(0)

        phone_match = re.search(r"(\+?[0-9]{1,4}?[-.\s]?\(?[0-9]{1,3}?\)?[-.\s]?[0-9]{3,4}[-.\s]?[0-9]{3,4})", full_conversation)
        if phone_match and len(phone_match.group(0).strip()) >= 7:
            lead["phone"] = phone_match.group(0).strip()

        lower_conv = full_conversation.lower()
        if any(w in lower_conv for w in ("real estate", "rent", "tenant", "property", "lease", "landlord", "finance", "ledger", "invoice")):
            lead["business_type"] = lead["business_type"] or "Real Estate / Property"
            lead["service_needed"] = "Business Financial Tracking & Ledger"
            lead["service_slug"] = "business-financial-tracking"
        elif any(w in lower_conv for w in ("clinic", "hospital", "patient", "dental", "doctor", "appointment", "whatsapp", "concierge")):
            lead["business_type"] = lead["business_type"] or "Clinics / Hospitals"
            lead["service_needed"] = "WhatsApp Business Concierge & Webhook Sync"
            lead["service_slug"] = "whatsapp-business-concierge"
        elif any(w in lower_conv for w in ("lead", "outreach", "maps", "b2b", "marketing", "clients", "sales", "growth")):
            lead["business_type"] = lead["business_type"] or "B2B Sales & Agency"
            lead["service_needed"] = "AI Marketing & Growth Automation"
            lead["service_slug"] = "ai-marketing-growth"
        elif any(w in lower_conv for w in ("ecommerce", "store", "retail", "orders", "shop")):
            lead["business_type"] = lead["business_type"] or "E-Commerce"
            lead["service_needed"] = "WhatsApp Business Concierge & Webhook Sync"
            lead["service_slug"] = "whatsapp-business-concierge"

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
                "**Business Financial Tracking & Ledger** module is a game changer. It automates WhatsApp rent "
                "reminders 3 days before due dates, captures payment receipts, and provides real-time cash flow statements. "
                "Would you like to review this package on your Client Service Dashboard?"
            )
            return (
                reply,
                "/finance",
                "👉 Proceed to Client Service Dashboard: Business Financial Tracking & Ledger",
                "business-financial-tracking",
                "Business Financial Tracking & Ledger",
            )

        # 2. WhatsApp Customer Support / Patient Booking
        if any(w in last_msg for w in ("whatsapp", "patient", "clinic", "doctor", "receptionist", "booking", "appointment", "chat", "concierge")):
            reply = (
                "Our **WhatsApp Business Concierge & Webhook Sync** service gives your business a 24/7 autonomous receptionist. "
                "It handles patient intake, schedules appointments directly into Google Calendar, and coordinates client viewing requests without manual intervention. "
                "Shall I direct you to the service setup dashboard?"
            )
            return (
                reply,
                "/onboarding?service=whatsapp-business-concierge",
                "👉 Proceed to Client Service Dashboard: WhatsApp Business Concierge",
                "whatsapp-business-concierge",
                "WhatsApp Business Concierge & Webhook Sync",
            )

        # 3. Lead Generation / Growth / Google Maps
        if any(w in last_msg for w in ("lead", "growth", "maps", "places", "outreach", "b2b", "sales", "client acquisition", "marketing")):
            reply = (
                "Our **AI Marketing & Growth Automation** engine harvests verified B2B leads directly from Google Maps worldwide "
                "(Dubai, Riyadh, London, etc.), scores them based on quality metrics, and executes personalized outreach campaigns. "
                "Let's open your Client Service Dashboard to configure your lead pipeline."
            )
            return (
                reply,
                "/marketing",
                "👉 Proceed to Client Service Dashboard: AI Marketing & Growth Automation",
                "ai-marketing-growth",
                "AI Marketing & Growth Automation",
            )

        # 4. Ready to proceed / Register / Onboarding
        if any(w in last_msg for w in ("ready", "proceed", "start", "sign up", "register", "onboard", "dashboard", "yes", "package")):
            service_needed = lead.get("service_needed") or "Business Financial Tracking & Ledger"
            service_slug = lead.get("service_slug") or "business-financial-tracking"
            target_url = "/onboarding"
            if service_slug == "business-financial-tracking":
                target_url = "/finance"
            elif service_slug == "whatsapp-business-concierge":
                target_url = "/onboarding?service=whatsapp-business-concierge"
            elif service_slug == "ai-marketing-growth":
                target_url = "/marketing"

            reply = (
                f"Fantastic! Based on our discussion, **{service_needed}** is the ideal solution to automate your operations. "
                "I have prepared your workspace. Click below to proceed directly to your Client Service Dashboard and finalize your onboarding."
            )
            return (
                reply,
                target_url,
                f"👉 Proceed to Client Service Dashboard: {service_needed}",
                service_slug,
                service_needed,
            )

        # 5. Pricing / Cost inquiries
        if any(w in last_msg for w in ("price", "cost", "how much", "rate", "fee", "plans")):
            reply = (
                "Our managed AI services start at just **$99/month** (Starter) for full financial tracking, and **$129–$199/month** "
                "for 24/7 WhatsApp concierge, Google Maps lead generation, or multi-agent orchestration. Every tier is done-for-you with dedicated engineering support. "
                "What specific service would you like to set up for your business?"
            )
            return (
                reply,
                "/onboarding",
                "👉 View Service Packages on Client Dashboard",
                "multi-agent-orchestration",
                "Multi-Agent Task Orchestration Suite",
            )

        # 6. Default Discovery Turn
        reply = (
            "I'd be glad to help! At Teloxtech, we eliminate manual business overhead through managed AI automations — "
            "including automated **Rent & Financial Tracking**, **24/7 WhatsApp AI Concierge**, and **Google Maps Lead Growth**. "
            "Could you share a little about your business or the biggest manual task you'd like us to take off your plate?"
        )
        return reply, None, None, None, None


assistant_service = AssistantService()
