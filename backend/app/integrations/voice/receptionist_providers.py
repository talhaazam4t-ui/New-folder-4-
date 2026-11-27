"""Voice AI Provider Adapters for Office Receptionist:
1. TelnyxVoiceAdapter: Automatic phone number provisioning/assignment, TeXML Voice Application
   configuration, live call transfer TeXML, and personalized Call Forwarding guide generation.
2. RetellAIAdapter: Dedicated Retell LLM + Voice Agent creation/updates with Cal.com custom tools
   and live human/emergency call transfer routing, plus Telnyx phone linking.
3. CalComAdapter: Live Cal.com availability checks and real-time appointment booking during calls.
"""

import hashlib
import hmac
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set
from xml.sax.saxutils import escape as xml_escape

import httpx
from app.config import settings
from app.core.logging import logger


def normalize_e164(phone: str) -> str:
    """Normalize a phone string into compact E.164-like format."""
    cleaned = re.sub(r"[^\d+]", "", (phone or "").strip())
    if cleaned and not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"
    return cleaned


def generate_call_forwarding_guide(
    fallback_phone: str,
    assigned_telnyx_number: str,
    business_name: str,
) -> Dict[str, Any]:
    """Generate a simple, carrier-friendly Call Forwarding setup guide for the client."""
    ai_num = normalize_e164(assigned_telnyx_number)
    digits_only = ai_num.lstrip("+")
    return {
        "business_name": business_name,
        "assigned_ai_number": ai_num,
        "fallback_human_number": normalize_e164(fallback_phone),
        "quick_dial_codes": {
            "forward_all_calls_gsm": f"*21*{ai_num}#",
            "forward_when_unanswered_gsm": f"*61*{ai_num}#",
            "forward_when_busy_gsm": f"*67*{ai_num}#",
            "disable_forwarding_gsm": "#21#",
            "us_att_tmobile_forward_all": f"**21*{ai_num}#",
            "us_verizon_forward_all": f"*72{digits_only}",
            "us_verizon_disable": "*73",
        },
        "steps": [
            f"1. Open your phone keypad on your business line ({fallback_phone or 'your current office phone'}).",
            f"2. To forward ALL calls 24/7 to your AI Receptionist, dial *21*{ai_num}# (or *72{digits_only} on Verizon) and press Call.",
            f"3. To forward ONLY missed/unanswered calls (after 4 rings), dial *61*{ai_num}# and press Call.",
            f"4. Place a test call from another phone to verify your AI Receptionist answers for {business_name}.",
            f"5. If a caller asks for a human or reports an emergency, your AI Receptionist automatically transfers the call live to {fallback_phone}.",
            "6. To turn off call forwarding anytime, dial #21# (or *73 on Verizon).",
        ],
        "ios_android_menu_tip": (
            "iPhone: Settings -> Phone -> Call Forwarding -> Toggle On -> enter "
            f"{ai_num}. Android: Phone App -> Settings -> Calling Accounts -> Call Forwarding -> Always Forward -> {ai_num}."
        ),
    }


class TelnyxVoiceAdapter:
    """Handles Telnyx number provisioning/assignment, TeXML Voice App wiring, and live transfer TeXML."""

    base_url = "https://api.telnyx.com/v2"

    async def _ensure_texml_connection(
        self,
        client: httpx.AsyncClient,
        headers: Dict[str, str],
        voice_webhook_url: str,
        status_callback_url: str,
        connection_id: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve an existing Telnyx Connection / TeXML Application ID or create one for Voice webhooks."""
        if connection_id and connection_id.strip():
            return connection_id.strip()

        # Check existing TeXML applications for a Talox Receptionist app
        try:
            apps_resp = await client.get(
                f"{self.base_url}/texml_applications",
                headers=headers,
                params={"page[size]": 25},
            )
            if apps_resp.status_code == 200:
                apps = apps_resp.json().get("data") or []
                existing = next(
                    (
                        a
                        for a in apps
                        if a.get("voice_url") == voice_webhook_url
                        or str(a.get("friendly_name") or "").startswith("Talox Receptionist")
                    ),
                    None,
                )
                if existing and existing.get("id"):
                    app_id = str(existing["id"])
                    if existing.get("voice_url") != voice_webhook_url:
                        await client.patch(
                            f"{self.base_url}/texml_applications/{app_id}",
                            headers=headers,
                            json={
                                "friendly_name": existing.get("friendly_name") or "Talox Receptionist Voice",
                                "voice_url": voice_webhook_url,
                                "voice_method": "post",
                                "status_callback": status_callback_url,
                                "status_callback_method": "post",
                                "active": True,
                            },
                        )
                    return app_id

            # Create a fresh TeXML Application wired to our Voice Webhook
            create_resp = await client.post(
                f"{self.base_url}/texml_applications",
                headers=headers,
                json={
                    "friendly_name": "Talox Receptionist Voice",
                    "voice_url": voice_webhook_url,
                    "voice_method": "post",
                    "status_callback": status_callback_url,
                    "status_callback_method": "post",
                    "active": True,
                },
            )
            if create_resp.status_code in (200, 201):
                created = create_resp.json().get("data") or {}
                if created.get("id"):
                    return str(created["id"])
        except Exception as exc:
            logger.warning("Telnyx TeXML application lookup/creation skipped", error=str(exc))

        return None

    async def provision_or_assign_number(
        self,
        tenant_id: str,
        api_key: Optional[str],
        voice_webhook_url: str,
        status_callback_url: str,
        connection_id: Optional[str] = None,
        default_number: Optional[str] = None,
        country_code: str = "US",
        existing_phone: Optional[str] = None,
        existing_phone_id: Optional[str] = None,
        assigned_phones: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Provision or assign a dedicated Telnyx phone number and attach the TeXML Voice Application."""
        key = (api_key or "").strip()
        blocked = {normalize_e164(p) for p in (assigned_phones or set()) if p}

        def _pick_sandbox_number() -> str:
            if existing_phone:
                return normalize_e164(existing_phone)
            norm_def = normalize_e164(default_number or "")
            if norm_def and norm_def not in blocked:
                return norm_def
            try:
                candidate = f"+1555{uuid.UUID(tenant_id).int % 10000000:07d}"
            except Exception:
                candidate = f"+1555{abs(hash(tenant_id)) % 10000000:07d}"
            while candidate in blocked:
                candidate = f"+1555{uuid.uuid4().int % 10000000:07d}"
            return candidate

        if not key or key.startswith("your-"):
            sandbox_num = _pick_sandbox_number()
            return {
                "success": True,
                "phone_number": sandbox_num,
                "phone_id": existing_phone_id or f"TN_SANDBOX_{tenant_id[:8]}",
                "is_live": False,
                "note": "Telnyx master API key not configured yet; assigned sandbox AI number.",
            }

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                active_conn_id = await self._ensure_texml_connection(
                    client=client,
                    headers=headers,
                    voice_webhook_url=voice_webhook_url,
                    status_callback_url=status_callback_url,
                    connection_id=connection_id,
                )

                # 1. Sync existing assigned Telnyx number if already provisioned for this tenant
                if existing_phone_id and not existing_phone_id.startswith(("TN_SANDBOX_", "PN_SANDBOX_")):
                    patch_body: Dict[str, Any] = {}
                    if active_conn_id:
                        patch_body["connection_id"] = active_conn_id
                    if patch_body:
                        upd = await client.patch(
                            f"{self.base_url}/phone_numbers/{existing_phone_id}",
                            headers=headers,
                            json=patch_body,
                        )
                        if upd.status_code in (200, 201):
                            data = upd.json().get("data") or {}
                            return {
                                "success": True,
                                "phone_number": data.get("phone_number") or existing_phone,
                                "phone_id": str(data.get("id") or existing_phone_id),
                                "is_live": True,
                                "note": "Existing Telnyx phone number TeXML voice routing synced.",
                            }

                # 2. Check existing unassigned owned Telnyx phone numbers (never steal another tenant's number)
                list_resp = await client.get(
                    f"{self.base_url}/phone_numbers",
                    headers=headers,
                    params={"page[size]": 25},
                )
                if list_resp.status_code == 200:
                    owned = list_resp.json().get("data") or []
                    available_owned = [
                        n
                        for n in owned
                        if normalize_e164(n.get("phone_number", "")) not in blocked
                    ]
                    chosen = None
                    if default_number:
                        norm_def = normalize_e164(default_number)
                        chosen = next(
                            (
                                n
                                for n in available_owned
                                if normalize_e164(n.get("phone_number", "")) == norm_def
                            ),
                            None,
                        )
                    if not chosen and available_owned:
                        chosen = next(
                            (n for n in available_owned if not n.get("connection_id")),
                            None,
                        )
                    if chosen:
                        chosen_id = str(chosen["id"])
                        if active_conn_id:
                            upd = await client.patch(
                                f"{self.base_url}/phone_numbers/{chosen_id}",
                                headers=headers,
                                json={"connection_id": active_conn_id},
                            )
                            upd.raise_for_status()
                        return {
                            "success": True,
                            "phone_number": chosen["phone_number"],
                            "phone_id": chosen_id,
                            "is_live": True,
                            "note": "Assigned owned Telnyx number and attached TeXML Voice Application.",
                        }

                # 3. Search & order a fresh Telnyx voice-enabled phone number automatically
                avail_resp = await client.get(
                    f"{self.base_url}/available_phone_numbers",
                    headers=headers,
                    params={
                        "filter[country_code]": country_code.upper(),
                        "filter[features][]": "voice",
                        "filter[limit]": 5,
                    },
                )
                avail_resp.raise_for_status()
                available = avail_resp.json().get("data") or []
                if not available:
                    raise RuntimeError(f"No available Telnyx voice numbers found in country '{country_code}'")

                target_num = available[0]["phone_number"]
                order_payload: Dict[str, Any] = {
                    "phone_numbers": [{"phone_number": target_num}],
                    "customer_reference": f"talox-receptionist-{tenant_id[:8]}",
                }
                if active_conn_id:
                    order_payload["connection_id"] = active_conn_id

                buy_resp = await client.post(
                    f"{self.base_url}/number_orders",
                    headers=headers,
                    json=order_payload,
                )
                buy_resp.raise_for_status()
                order_data = buy_resp.json().get("data") or {}
                ordered_nums = order_data.get("phone_numbers") or []
                ordered_id = (
                    str(ordered_nums[0].get("id"))
                    if ordered_nums and ordered_nums[0].get("id")
                    else str(order_data.get("id") or f"TN_ORDER_{tenant_id[:8]}")
                )
                return {
                    "success": True,
                    "phone_number": normalize_e164(target_num),
                    "phone_id": ordered_id,
                    "is_live": True,
                    "note": "Provisioned new Telnyx voice number and linked TeXML Voice Application.",
                }

        except Exception as exc:
            logger.warning("Telnyx live provisioning failed; keeping sandbox assignment", error=str(exc))
            sandbox_num = _pick_sandbox_number()
            return {
                "success": False,
                "phone_number": sandbox_num,
                "phone_id": existing_phone_id or f"TN_SANDBOX_{tenant_id[:8]}",
                "is_live": False,
                "note": f"Telnyx live call failed ({str(exc)[:140]}); sandbox number retained.",
            }

    def build_live_transfer_texml(
        self,
        fallback_phone: str,
        announcement: str = "Connecting you directly to a human representative now. Please hold.",
    ) -> str:
        """Build Telnyx TeXML XML for immediate live call transfer to the client's personal/fallback phone."""
        safe_msg = xml_escape(announcement)
        safe_num = xml_escape(normalize_e164(fallback_phone))
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f'<Say voice="Polly.Joanna">{safe_msg}</Say>'
            f'<Dial timeout="25">{safe_num}</Dial>'
            "<Say>We were unable to reach a representative right now. Please leave a message after the beep.</Say>"
            '<Record maxLength="120" playBeep="true" />'
            "</Response>"
        )

    def build_retell_sip_or_greeting_texml(
        self,
        business_name: str,
        greeting: str,
        fallback_phone: str,
        retell_agent_id: Optional[str] = None,
        telnyx_phone_number: Optional[str] = None,
    ) -> str:
        """Build Telnyx inbound voice TeXML routing to Retell SIP or fallback live transfer."""
        if retell_agent_id and not retell_agent_id.startswith("agent_sandbox_"):
            norm_phone = normalize_e164(telnyx_phone_number or "")
            if norm_phone and not norm_phone.startswith("+1555"):
                sip_target = f"sip:{norm_phone}@sip.retellai.com;transport=tcp"
            else:
                sip_target = f"sip:{retell_agent_id}@5t4n6j0wnrl.sip.livekit.cloud"
            safe_sip = xml_escape(sip_target)
            return (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<Response>"
                "<Dial>"
                f"<Sip>{safe_sip}</Sip>"
                "</Dial>"
                "</Response>"
            )
        safe_greeting = xml_escape(greeting or f"Welcome to {business_name}. Connecting you now.")
        return self.build_live_transfer_texml(fallback_phone, announcement=safe_greeting)


class RetellAIAdapter:
    """Handles Retell AI LLM + Voice Agent provisioning, Cal.com tools, live transfer, and Telnyx linking."""

    def _build_receptionist_prompt(
        self,
        business_name: str,
        operating_hours: str,
        greeting_message: str,
        faqs: str,
        fallback_phone: str,
        calcom_booking_url: Optional[str],
    ) -> str:
        faq_block = faqs.strip() or "Answer caller questions politely and offer to book an appointment."
        cal_hint = (
            f"Booking link reference: {calcom_booking_url}. Always use check_calcom_availability before calling book_calcom_appointment."
            if calcom_booking_url
            else "Always use check_calcom_availability before calling book_calcom_appointment."
        )
        return (
            f"You are the professional 24/7 AI Office Receptionist for {business_name}.\n"
            f"Operating Hours: {operating_hours}\n"
            f"Opening Greeting: {greeting_message}\n\n"
            f"Business FAQs & Knowledge Base:\n{faq_block}\n\n"
            f"Appointment Booking Instructions:\n{cal_hint}\n"
            "Collect caller name, email or phone, and preferred date/time before booking.\n\n"
            "LIVE HUMAN / EMERGENCY TRANSFER RULE (CRITICAL):\n"
            "If the caller asks to speak to a human, owner, manager, doctor, or real person, OR mentions an emergency/urgent issue, "
            f"politely let them know you are transferring them immediately and invoke the transfer_call tool to {normalize_e164(fallback_phone)}."
        )

    def _build_retell_tools(
        self,
        backend_base_url: str,
        tenant_id: str,
        fallback_phone: str,
    ) -> List[Dict[str, Any]]:
        base = backend_base_url.rstrip("/")
        return [
            {
                "type": "custom",
                "name": "check_calcom_availability",
                "description": "Check available appointment time slots in the client's Cal.com calendar for a given date.",
                "url": f"{base}/api/v1/receptionist/tools/{tenant_id}/calcom/availability",
                "speak_during_execution": True,
                "execution_message_description": "Let me check our calendar availability for you.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "Target date in YYYY-MM-DD format",
                        }
                    },
                    "required": ["date"],
                },
            },
            {
                "type": "custom",
                "name": "book_calcom_appointment",
                "description": "Book an appointment directly into the client's Cal.com calendar after confirming slot availability.",
                "url": f"{base}/api/v1/receptionist/tools/{tenant_id}/calcom/book",
                "speak_during_execution": True,
                "execution_message_description": "Booking your appointment right now.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_iso": {"type": "string", "description": "Selected ISO-8601 start datetime"},
                        "attendee_name": {"type": "string", "description": "Caller's full name"},
                        "attendee_email": {"type": "string", "description": "Caller's email address"},
                        "attendee_phone": {"type": "string", "description": "Caller's phone number"},
                        "notes": {"type": "string", "description": "Reason for the appointment"},
                    },
                    "required": ["start_iso", "attendee_name"],
                },
            },
            {
                "type": "transfer_call",
                "name": "transfer_call",
                "description": "Transfer the live phone call immediately to the business owner/human fallback line when caller asks for a human or has an emergency.",
                "transfer_destination": {
                    "type": "predefined",
                    "number": normalize_e164(fallback_phone),
                },
                "transfer_option": {
                    "type": "cold_transfer",
                },
            },
            {
                "type": "custom",
                "name": "search_business_knowledge",
                "description": "Search the business knowledge base (website services, pricing PDFs, clinic procedures) for exact answers.",
                "url": f"{base}/api/v1/receptionist/tools/{tenant_id}/knowledge/search",
                "speak_during_execution": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Caller question or topic to look up"},
                    },
                    "required": ["query"],
                },
            },
        ]

    async def create_or_update_agent(
        self,
        api_key: Optional[str],
        tenant_id: str,
        business_name: str,
        operating_hours: str,
        greeting_message: str,
        faqs: str,
        fallback_phone: str,
        backend_base_url: str,
        telnyx_phone_number: Optional[str] = None,
        calcom_booking_url: Optional[str] = None,
        voice_id: str = "11labs-Adrian",
        existing_llm_id: Optional[str] = None,
        existing_agent_id: Optional[str] = None,
        base_url: Optional[str] = None,
        telnyx_sip_username: Optional[str] = None,
        telnyx_sip_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Provision or update a dedicated Retell AI LLM + Voice Agent and bind it to the Telnyx number."""
        key = (api_key or "").strip()
        retell_base = (base_url or settings.retell_base_url).rstrip("/")

        if not key or key.startswith("your-"):
            return {
                "success": True,
                "retell_llm_id": existing_llm_id or f"llm_sandbox_{tenant_id[:8]}",
                "retell_agent_id": existing_agent_id or f"agent_sandbox_{tenant_id[:8]}",
                "is_live": False,
                "note": "Retell AI master key not configured yet; agent specification vaulted in sandbox-ready mode.",
            }

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        general_prompt = self._build_receptionist_prompt(
            business_name=business_name,
            operating_hours=operating_hours,
            greeting_message=greeting_message,
            faqs=faqs,
            fallback_phone=fallback_phone,
            calcom_booking_url=calcom_booking_url,
        )
        tools = self._build_retell_tools(backend_base_url, tenant_id, fallback_phone)
        llm_payload = {
            "general_prompt": general_prompt,
            "begin_message": greeting_message,
            "general_tools": tools,
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                # 1. Create or update Retell LLM (with schema fallback if custom tool format is rejected)
                if existing_llm_id and not existing_llm_id.startswith("llm_sandbox_"):
                    llm_resp = await client.patch(
                        f"{retell_base}/update-retell-llm/{existing_llm_id}",
                        headers=headers,
                        json=llm_payload,
                    )
                    if llm_resp.status_code not in (200, 201):
                        llm_resp = await client.patch(
                            f"{retell_base}/update-retell-llm/{existing_llm_id}",
                            headers=headers,
                            json={"general_prompt": general_prompt, "begin_message": greeting_message},
                        )
                    llm_resp.raise_for_status()
                    llm_id = existing_llm_id
                else:
                    llm_resp = await client.post(
                        f"{retell_base}/create-retell-llm",
                        headers=headers,
                        json=llm_payload,
                    )
                    if llm_resp.status_code not in (200, 201):
                        llm_resp = await client.post(
                            f"{retell_base}/create-retell-llm",
                            headers=headers,
                            json={"general_prompt": general_prompt, "begin_message": greeting_message},
                        )
                    llm_resp.raise_for_status()
                    llm_id = llm_resp.json().get("llm_id")

                # 2. Create or update Retell Voice Agent
                webhook_url = f"{backend_base_url.rstrip('/')}/api/v1/receptionist/webhooks/retell"
                agent_payload = {
                    "agent_name": f"{business_name} - Office Receptionist",
                    "voice_id": voice_id or "11labs-Adrian",
                    "response_engine": {
                        "type": "retell-llm",
                        "llm_id": llm_id,
                    },
                    "webhook_url": webhook_url,
                }
                if existing_agent_id and not existing_agent_id.startswith("agent_sandbox_"):
                    ag_resp = await client.patch(
                        f"{retell_base}/update-agent/{existing_agent_id}",
                        headers=headers,
                        json=agent_payload,
                    )
                    ag_resp.raise_for_status()
                    agent_id = existing_agent_id
                else:
                    ag_resp = await client.post(
                        f"{retell_base}/create-agent",
                        headers=headers,
                        json=agent_payload,
                    )
                    ag_resp.raise_for_status()
                    agent_id = ag_resp.json().get("agent_id")

                # 3. Link Telnyx phone number to Retell AI Agent if live E.164 number is present
                if telnyx_phone_number and not telnyx_phone_number.startswith("+1555"):
                    norm_phone = normalize_e164(telnyx_phone_number)
                    try:
                        upd_resp = await client.patch(
                            f"{retell_base}/update-phone-number/{norm_phone}",
                            headers=headers,
                            json={"inbound_agent_id": agent_id},
                        )
                        if upd_resp.status_code not in (200, 201):
                            import_payload: Dict[str, Any] = {
                                "phone_number": norm_phone,
                                "termination_uri": "sip.telnyx.com",
                                "inbound_agent_id": agent_id,
                                "nickname": f"{business_name} AI Line",
                            }
                            if telnyx_sip_username and telnyx_sip_password:
                                import_payload["sip_trunk_auth_username"] = telnyx_sip_username
                                import_payload["sip_trunk_auth_password"] = telnyx_sip_password
                            imp_resp = await client.post(
                                f"{retell_base}/import-phone-number",
                                headers=headers,
                                json=import_payload,
                            )
                            if imp_resp.status_code not in (200, 201):
                                logger.warning(
                                    "Retell import-phone-number returned non-2xx",
                                    status_code=imp_resp.status_code,
                                    body=imp_resp.text[:200],
                                )
                    except Exception as link_exc:
                        logger.warning("Retell phone number link skipped", error=str(link_exc))

                return {
                    "success": True,
                    "retell_llm_id": llm_id,
                    "retell_agent_id": agent_id,
                    "is_live": True,
                    "note": "Dedicated Retell AI voice agent provisioned and synced with Cal.com tools & live transfer.",
                }
        except Exception as exc:
            logger.warning("Retell AI live provisioning failed; keeping sandbox state", error=str(exc))
            return {
                "success": False,
                "retell_llm_id": existing_llm_id or f"llm_sandbox_{tenant_id[:8]}",
                "retell_agent_id": existing_agent_id or f"agent_sandbox_{tenant_id[:8]}",
                "is_live": False,
                "note": f"Retell AI live call failed ({str(exc)[:140]}); sandbox agent retained.",
            }

    def verify_webhook_signature(
        self,
        body_bytes: bytes,
        signature_header: Optional[str],
        webhook_secret: Optional[str],
        fallback_api_key: Optional[str] = None,
    ) -> bool:
        keys = [k.strip() for k in (webhook_secret, fallback_api_key) if k and k.strip()]
        if not keys:
            return True
        if not signature_header:
            return False
        sig_str = signature_header.strip()

        # Official Retell AI signature format: "v=<timestamp>,d=<hmac_sha256(raw_body + timestamp)>"
        if "v=" in sig_str and "d=" in sig_str:
            parts: Dict[str, str] = {}
            for segment in sig_str.split(","):
                if "=" in segment:
                    k, v = segment.split("=", 1)
                    parts[k.strip()] = v.strip()
            ts = parts.get("v", "")
            digest = parts.get("d", "")
            if ts and digest:
                signed_payload = body_bytes + ts.encode("utf-8")
                for key in keys:
                    expected = hmac.new(key.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
                    if hmac.compare_digest(expected, digest):
                        return True
                return False

        # Backward-compatible raw hex / "sha256=<hex>" format over body_bytes
        sig_clean = sig_str.split("=")[-1].strip()
        for key in keys:
            expected = hmac.new(key.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected, sig_clean):
                return True
        return False


class CalComAdapter:
    """Handles Cal.com availability checks and live appointment booking for Retell AI voice calls."""

    async def check_availability(
        self,
        api_key: Optional[str],
        event_type_id: Optional[str],
        date_str: str,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query open appointment slots on Cal.com for the requested date."""
        key = (api_key or "").strip()
        cal_base = (base_url or settings.calcom_base_url).rstrip("/")

        # Default target date fallback
        try:
            target_dt = datetime.fromisoformat(date_str[:10]).replace(tzinfo=timezone.utc)
        except Exception:
            target_dt = datetime.now(timezone.utc) + timedelta(days=1)
        start_day = target_dt.strftime("%Y-%m-%dT00:00:00Z")
        end_day = target_dt.strftime("%Y-%m-%dT23:59:59Z")

        if key and event_type_id and not key.startswith("your-"):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(
                        f"{cal_base}/slots/available",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "cal-api-version": "2024-08-13",
                        },
                        params={
                            "eventTypeId": str(event_type_id),
                            "startTime": start_day,
                            "endTime": end_day,
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json().get("data") or {}
                        slots_map = data.get("slots") or {}
                        flat_slots: List[str] = []
                        for day_slots in slots_map.values():
                            for item in day_slots:
                                slot_t = item.get("time") if isinstance(item, dict) else str(item)
                                if slot_t:
                                    flat_slots.append(slot_t)
                        return {
                            "available": len(flat_slots) > 0,
                            "date": target_dt.strftime("%Y-%m-%d"),
                            "slots": flat_slots[:8],
                            "is_live": True,
                            "calcom_connected": True,
                        }
            except Exception as exc:
                logger.warning("Cal.com availability check failed; returning default business slots", error=str(exc))

        day_prefix = target_dt.strftime("%Y-%m-%d")
        return {
            "available": True,
            "date": day_prefix,
            "slots": [
                f"{day_prefix}T10:00:00Z",
                f"{day_prefix}T11:30:00Z",
                f"{day_prefix}T14:00:00Z",
                f"{day_prefix}T16:00:00Z",
            ],
            "is_live": False,
            "calcom_connected": False,
        }

    async def create_booking(
        self,
        api_key: Optional[str],
        event_type_id: Optional[str],
        start_iso: str,
        attendee_name: str,
        attendee_email: Optional[str] = None,
        attendee_phone: Optional[str] = None,
        notes: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a real isolated Cal.com booking (or log a tenant-isolated in-app request)."""
        key = (api_key or "").strip()
        cal_base = (base_url or settings.calcom_base_url).rstrip("/")
        safe_email = (attendee_email or "").strip() or "caller@teloxtech.stream"

        if key and event_type_id and not key.startswith("your-"):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    payload: Dict[str, Any] = {
                        "start": start_iso,
                        "eventTypeId": int(event_type_id) if str(event_type_id).isdigit() else event_type_id,
                        "attendee": {
                            "name": attendee_name,
                            "email": safe_email,
                            "timeZone": "UTC",
                        },
                        "metadata": {
                            "source": "talox_office_receptionist",
                            "phone": attendee_phone or "",
                            "notes": notes or "",
                        },
                    }
                    resp = await client.post(
                        f"{cal_base}/bookings",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "cal-api-version": "2024-08-13",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    if resp.status_code in (200, 201):
                        b_data = resp.json().get("data") or resp.json()
                        return {
                            "success": True,
                            "booking_uid": str(b_data.get("uid") or b_data.get("id") or f"cal_{uuid.uuid4().hex[:10]}"),
                            "start_iso": start_iso,
                            "status": "booked",
                            "is_live": True,
                            "calcom_connected": True,
                        }
            except Exception as exc:
                logger.warning("Cal.com live booking failed; recording fallback confirmation", error=str(exc))

        return {
            "success": True,
            "booking_uid": f"local_req_{uuid.uuid4().hex[:10]}",
            "start_iso": start_iso,
            "status": "booked",
            "is_live": False,
            "calcom_connected": False,
            "note": (
                "Appointment request logged inside your Teloxtech dashboard. "
                "Connect your personal Cal.com API Key and Event Type ID to sync directly to your Cal.com calendar."
            ),
        }


telnyx_voice_adapter = TelnyxVoiceAdapter()
retell_ai_adapter = RetellAIAdapter()
calcom_adapter = CalComAdapter()
