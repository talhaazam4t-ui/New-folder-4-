"""Daily Global Niche Lead-Finder & Gmail Draft Autopilot Service.

Zero-n8n pure Python asyncio automation service that:
1. Discovers real companies globally across rotating niches and target cities.
2. Enriches companies having an official website with public contact emails (SSRF-safe, bounded timeout).
3. Crafts tailored company-specific B2B outreach emails via the AI router (with deterministic fallback).
4. Saves drafts directly into the workspace's connected Gmail Drafts folder (with OAuth token auto-refresh)
   and stores reviewable drafts in CRM metadata — strictly Human-in-the-Loop (never auto-sends emails).
"""

import asyncio
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import uuid

import httpx
from app.automation.budget_manager import budget_manager
from app.config import settings
from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.core.logging import logger
from app.core.security import decrypt_secret, encrypt_secret
from app.database.models.automation import AuditLog, Integration
from app.database.models.marketing import Lead
from app.database.models.receptionist import ReceptionistConfig
from app.database.models.tenant import Tenant
from app.integrations.ai_providers.router import route_and_execute_ai_task
from app.integrations.email.adapter import email_adapter, is_live_google_token
from app.schemas.agent import OutreachAutopilotConfigUpdate
from app.schemas.marketing import LeadGenerationRequest
from app.services.integration_service import refresh_google_access_token
from app.services.marketing_service import marketing_service
from app.services.notification_service import notification_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

AUTOPILOT_SETTINGS_KEY = "daily_outreach_autopilot"
DEFAULT_BOOKING_URL = "https://cal.com/talha-azam-jhhqzd/30min"
DEFAULT_SERVICE_OFFER = (
    "24/7 AI Office Receptionist & Multi-Agent Automation that answers every inbound call "
    "and inquiry, qualifies prospects, and books appointments straight into your calendar starting at $199/month."
)

DEFAULT_NICHES: List[str] = [
    "Clinics / Hospitals",
    "Dental & Aesthetic Clinics",
    "Real Estate / Property",
    "Enterprise & Software Companies",
    "Law & Accounting Firms",
    "Financing & Advisory",
    "E-Commerce",
]

DEFAULT_CITIES: List[str] = [
    "Dubai",
    "London",
    "Toronto",
    "Riyadh",
    "New York",
    "Sydney",
    "Singapore",
    "Abu Dhabi",
    "Manchester",
    "Lahore",
]

NICHE_SEARCH_KEYWORDS: Dict[str, str] = {
    "clinics / hospitals": "medical clinic",
    "dental & aesthetic clinics": "dental clinic",
    "real estate / property": "real estate agency",
    "enterprise & software companies": "software company",
    "law & accounting firms": "law firm",
    "financing & advisory": "accounting firm",
    "e-commerce": "retail store",
}

_EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,12}")
_MAILTO_REGEX = re.compile(r"mailto:([^\"'?\s<>#]+)", re.IGNORECASE)
_CONTACT_HREF_REGEX = re.compile(r"href=[\"']([^\"']*contact[^\"']*)[\"']", re.IGNORECASE)

_IGNORED_EMAIL_SUBSTRINGS = (
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "example.com",
    "example.org",
    "wixpress.com",
    "sentry.io",
    "schema.org",
    "w3.org",
    "googleapis.com",
    "googleusercontent.com",
    "cloudflare",
    "domain.com",
    "email.com",
    "yoursite.",
    "u003e",
)

_IGNORED_EMAIL_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".css",
    ".js",
    ".woff",
    ".woff2",
    ".ico",
    ".pdf",
)

_PREFERRED_EMAIL_PREFIXES = (
    "info",
    "contact",
    "hello",
    "reception",
    "appointments",
    "appointment",
    "booking",
    "bookings",
    "sales",
    "office",
    "admin",
    "inquiries",
    "enquiry",
    "support",
)


def _clean_string_list(values: Optional[List[str]], fallback: List[str], max_items: int) -> List[str]:
    """Deduplicate and strip a list of labels while keeping insertion order."""
    if not values:
        return list(fallback)
    cleaned: List[str] = []
    seen = set()
    for raw in values:
        item = str(raw or "").strip()
        if item and item.lower() not in seen:
            seen.add(item.lower())
            cleaned.append(item[:120])
        if len(cleaned) >= max_items:
            break
    return cleaned or list(fallback)


def _is_safe_public_url(raw_url: str) -> Optional[str]:
    """Validate URL scheme and guard against SSRF toward local/private network addresses."""
    candidate = (raw_url or "").strip()
    if not candidate or "openstreetmap.org" in candidate.lower():
        return None
    if not candidate.lower().startswith(("http://", "https://")):
        candidate = f"https://{candidate}"
    try:
        parsed = urllib.parse.urlsplit(candidate)
    except Exception:
        return None

    host = (parsed.hostname or "").strip().lower()
    if not host or parsed.scheme not in ("http", "https"):
        return None
    if host in ("localhost", "ip6-localhost") or host.endswith((".local", ".internal", ".localhost")):
        return None
    try:
        ip_obj = ipaddress.ip_address(host)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
            return None
    except ValueError:
        if "." not in host:
            return None
    return candidate


def _extract_best_email_from_html(html: str, site_host: str) -> Optional[str]:
    """Extract and rank public business contact emails from HTML content."""
    if not html:
        return None
    raw_matches: List[str] = []
    for m in _MAILTO_REGEX.findall(html):
        raw_matches.append(urllib.parse.unquote(m).strip())
    raw_matches.extend(_EMAIL_REGEX.findall(html))

    normalized_host = site_host.lower().lstrip("www.")
    scored: List[Tuple[int, str]] = []
    seen = set()
    for raw in raw_matches:
        email = raw.strip().strip(".,;:<>\"'()").lower()
        if not email or "@" not in email or email in seen:
            continue
        if not _EMAIL_REGEX.fullmatch(email):
            continue
        if any(bad in email for bad in _IGNORED_EMAIL_SUBSTRINGS):
            continue
        if email.endswith(_IGNORED_EMAIL_EXTENSIONS):
            continue
        seen.add(email)
        local_part, domain_part = email.split("@", 1)
        score = 0
        if normalized_host and (domain_part == normalized_host or domain_part.endswith(f".{normalized_host}")):
            score += 50
        if local_part in _PREFERRED_EMAIL_PREFIXES:
            score += 30
        elif any(local_part.startswith(p) for p in _PREFERRED_EMAIL_PREFIXES):
            score += 15
        scored.append((score, email))

    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]


async def discover_public_website_email(website_url: str) -> Optional[str]:
    """Politely fetch a company's public homepage (and contact page) to find a listed contact email."""
    if settings.app_env == "test" or os.environ.get("PYTEST_CURRENT_TEST"):
        return None

    safe_url = _is_safe_public_url(website_url)
    if not safe_url:
        return None

    parsed = urllib.parse.urlsplit(safe_url)
    site_host = (parsed.hostname or "").lower()
    headers = {
        "User-Agent": "TaloxTech-LeadFinder/1.0 (+https://teloxtech.stream)",
        "Accept": "text/html,application/xhtml+xml",
    }

    try:
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
            resp = await client.get(safe_url, headers=headers)
            if resp.status_code != 200:
                return None
            html = (resp.text or "")[:200_000]
            found = _extract_best_email_from_html(html, site_host)
            if found:
                return found

            contact_links = _CONTACT_HREF_REGEX.findall(html)
            contact_target = (
                urllib.parse.urljoin(str(resp.url), contact_links[0])
                if contact_links
                else f"{parsed.scheme}://{parsed.netloc}/contact"
            )
            safe_contact = _is_safe_public_url(contact_target)
            if not safe_contact:
                return None
            contact_resp = await client.get(safe_contact, headers=headers)
            if contact_resp.status_code == 200:
                contact_html = (contact_resp.text or "")[:200_000]
                return _extract_best_email_from_html(contact_html, site_host)
    except Exception as exc:
        logger.debug("Public website email lookup skipped", url=safe_url, error=str(exc))
    return None


def _build_default_config(tenant: Tenant, booking_url_hint: Optional[str] = None) -> Dict[str, Any]:
    """Merge persisted daily autopilot settings with sensible workspace defaults."""
    stored = dict((tenant.settings or {}).get(AUTOPILOT_SETTINGS_KEY) or {})
    niches = _clean_string_list(stored.get("niches"), DEFAULT_NICHES, 20)
    cities = _clean_string_list(stored.get("cities"), DEFAULT_CITIES, 40)
    try:
        daily_limit = min(max(int(stored.get("daily_draft_limit") or 5), 1), 15)
    except (TypeError, ValueError):
        daily_limit = 5
    try:
        run_hour_utc = min(max(int(stored.get("run_hour_utc") if stored.get("run_hour_utc") is not None else 6), 0), 23)
    except (TypeError, ValueError):
        run_hour_utc = 6
    try:
        rotation_index = max(int(stored.get("rotation_index") or 0), 0)
    except (TypeError, ValueError):
        rotation_index = 0

    return {
        "enabled": bool(stored.get("enabled", False)),
        "niches": niches,
        "cities": cities,
        "daily_draft_limit": daily_limit,
        "service_offer": str(stored.get("service_offer") or DEFAULT_SERVICE_OFFER).strip() or DEFAULT_SERVICE_OFFER,
        "sender_name": str(stored.get("sender_name") or tenant.name or "Teloxtech AI Automation").strip(),
        "booking_url": str(stored.get("booking_url") or booking_url_hint or DEFAULT_BOOKING_URL).strip(),
        "run_hour_utc": run_hour_utc,
        "rotation_index": rotation_index,
        "last_run_at": stored.get("last_run_at"),
        "last_run_summary": stored.get("last_run_summary") or None,
    }


def _compute_rotation_target(niches: List[str], cities: List[str], rotation_index: int) -> Tuple[str, str]:
    """Return deterministic (niche, city) pair for the current rotation index."""
    safe_niches = niches or DEFAULT_NICHES
    safe_cities = cities or DEFAULT_CITIES
    total_pairs = len(safe_niches) * len(safe_cities)
    idx = rotation_index % max(total_pairs, 1)
    niche = safe_niches[idx % len(safe_niches)]
    city = safe_cities[(idx // len(safe_niches)) % len(safe_cities)]
    return niche, city


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp safely into a UTC-aware datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _parse_ai_email_json(raw_content: str) -> Optional[Tuple[str, str]]:
    """Extract (subject, body) JSON object from AI output, tolerating markdown code fences."""
    text = (raw_content or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except Exception:
        return None
    subject = str(data.get("subject") or "").strip()
    body = str(data.get("body") or "").strip()
    if not subject or not body:
        return None
    return subject[:140], body


async def _generate_company_email(
    tenant_id: uuid.UUID,
    company_name: str,
    niche: str,
    city: str,
    website: Optional[str],
    address: Optional[str],
    sender_name: str,
    service_offer: str,
    booking_url: str,
) -> Tuple[str, str]:
    """Generate a tailored outreach subject and email body specifically for one company."""
    context_parts = [f"Company Name: {company_name}", f"Industry/Niche: {niche}", f"City: {city}"]
    if website and "openstreetmap.org" not in website.lower():
        context_parts.append(f"Website: {website}")
    if address:
        context_parts.append(f"Location/Address: {address[:140]}")

    prompt = (
        "Write one personalized cold B2B outreach email as strict JSON with keys \"subject\" and \"body\".\n"
        f"{chr(10).join(context_parts)}\n"
        f"Sender Name / Agency: {sender_name}\n"
        f"Core Offer: {service_offer}\n"
        f"Booking Link: {booking_url}\n\n"
        "Rules:\n"
        "1. Subject must be short (<= 60 chars), natural, no spammy punctuation, mentioning the company or city.\n"
        "2. Open with 1 specific line referencing the company name, city, or website.\n"
        "3. Keep body 85-135 words, plain text (no markdown bold/links), clear value for missed calls & lead follow-up.\n"
        "4. Include the booking link on its own line and sign off cleanly with the sender name.\n"
        "5. End with a brief 1-line polite opt-out sentence.\n"
        "Return ONLY valid JSON: {\"subject\": \"...\", \"body\": \"...\"}"
    )

    try:
        budget_manager.check_execution_eligibility(str(tenant_id), estimated_tokens=450)
        ai_res = await route_and_execute_ai_task(
            task_type="outreach_email_draft",
            prompt=prompt,
            system_instruction=(
                "You are a senior B2B growth copywriter who writes brief, specific, respectful "
                "cold emails that sound human and avoid spam triggers. Output strict JSON only."
            ),
            tenant_id=str(tenant_id),
            temperature=0.35,
            max_tokens=500,
        )
        if ai_res.success and ai_res.total_tokens:
            budget_manager.record_success(str(tenant_id), ai_res.total_tokens, ai_res.estimated_cost)
        if ai_res.success and not ai_res.is_mock:
            parsed = _parse_ai_email_json(ai_res.content)
            if parsed:
                return parsed
    except Exception as exc:
        logger.warning(
            "AI outreach draft generation fell back to deterministic template",
            tenant_id=str(tenant_id),
            company_name=company_name,
            error=str(exc),
        )

    short_niche = niche.split("/")[0].strip()
    website_note = (
        f" and saw your online presence ({website})"
        if website and "openstreetmap.org" not in website.lower()
        else ""
    )
    subject = f"Quick question for {company_name} ({city})"
    booking_line = (
        f"\n\nIf you'd like to hear how a 2-minute live AI receptionist demo sounds, you can pick a slot here:\n{booking_url}"
        if booking_url
        else ""
    )
    body = (
        f"Hi {company_name} team,\n\n"
        f"I came across {company_name} while researching leading {short_niche.lower()} businesses in {city}{website_note}.\n\n"
        f"Many busy {short_niche.lower()} teams lose high-intent callers when front-desk lines are busy or inquiries arrive after hours. "
        f"We help businesses deploy a {service_offer}"
        f"{booking_line}\n\n"
        f"Best regards,\n{sender_name}\n\n"
        "P.S. If this isn't a priority right now, simply reply 'no' and I won't follow up."
    )
    return subject, body


class OutreachAutopilotService:
    """Manages daily global niche lead discovery and Gmail Draft creation per workspace."""

    async def _inspect_gmail_integration(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Tuple[Optional[Integration], Dict[str, Any]]:
        """Inspect workspace Gmail integration row and OAuth compose capability."""
        res = await session.execute(
            select(Integration).where(
                Integration.tenant_id == tenant_id,
                Integration.provider == "gmail",
            )
        )
        integ = res.scalar_one_or_none()
        if not integ:
            return None, {
                "connected": False,
                "account": None,
                "oauth_ready": False,
                "has_refresh_token": False,
                "has_compose_scope": False,
                "can_create_live_drafts": False,
                "needs_oauth_authorize": True,
            }

        cfg = dict(integ.configuration or {})
        raw_access = decrypt_secret(str(cfg.get("access_token") or ""))
        raw_refresh = decrypt_secret(str(cfg.get("refresh_token") or ""))
        scopes_raw = cfg.get("scopes_granted") or []
        if isinstance(scopes_raw, str):
            scopes = [s.strip() for s in scopes_raw.replace(",", " ").split() if s.strip()]
        else:
            scopes = [str(s).strip() for s in scopes_raw if str(s).strip()]

        has_compose_scope = any("gmail.compose" in s or "mail.google.com" in s for s in scopes)
        oauth_ready = bool(
            integ.status == "connected"
            and is_live_google_token(raw_access)
            and not cfg.get("is_mock", False)
        )
        can_draft = bool(oauth_ready and (has_compose_scope or bool(raw_refresh)))
        # Strictly require gmail.compose scope when Google reported scopes_granted
        if scopes and not has_compose_scope:
            can_draft = False

        return integ, {
            "connected": integ.status == "connected",
            "account": integ.external_account_id or cfg.get("account_identifier"),
            "oauth_ready": oauth_ready,
            "has_refresh_token": bool(raw_refresh),
            "has_compose_scope": has_compose_scope,
            "can_create_live_drafts": can_draft,
            "needs_oauth_authorize": not can_draft,
        }

    async def _ensure_fresh_gmail_token(
        self,
        session: AsyncSession,
        integ: Optional[Integration],
        force_refresh: bool = False,
    ) -> Optional[str]:
        """Return a fresh Gmail OAuth access_token, refreshing and persisting if expired."""
        if not integ or integ.status != "connected":
            return None
        cfg = dict(integ.configuration or {})
        access_token = decrypt_secret(str(cfg.get("access_token") or ""))
        refresh_token = decrypt_secret(str(cfg.get("refresh_token") or ""))

        expires_dt = _parse_iso_datetime(cfg.get("expires_at"))
        needs_refresh = force_refresh or not access_token
        if not needs_refresh and expires_dt is not None:
            if expires_dt <= datetime.now(timezone.utc) + timedelta(minutes=5):
                needs_refresh = True

        if needs_refresh and refresh_token:
            refreshed = await refresh_google_access_token(refresh_token)
            if refreshed and refreshed.get("access_token"):
                new_token = str(refreshed["access_token"])
                new_cfg = dict(cfg)
                new_cfg["access_token"] = encrypt_secret(new_token)
                if refreshed.get("expires_at"):
                    new_cfg["expires_at"] = refreshed["expires_at"]
                integ.configuration = new_cfg
                await session.flush()
                return new_token

        return access_token or None

    async def get_autopilot_state(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Return autopilot configuration, Gmail OAuth status, next target, and saved company drafts."""
        t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_res.scalar_one_or_none()
        if not tenant:
            raise ResourceNotFoundError("Tenant", str(tenant_id))

        rc_res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id).limit(1)
        )
        recep_cfg = rc_res.scalar_one_or_none()
        booking_hint = recep_cfg.calcom_booking_url if recep_cfg and recep_cfg.calcom_booking_url else DEFAULT_BOOKING_URL

        config = _build_default_config(tenant, booking_url_hint=booking_hint)
        next_niche, next_city = _compute_rotation_target(
            config["niches"], config["cities"], config["rotation_index"]
        )
        _, gmail_status = await self._inspect_gmail_integration(session, tenant_id)

        leads_res = await session.execute(
            select(Lead)
            .where(Lead.tenant_id == tenant_id)
            .order_by(Lead.created_at.desc())
            .limit(80)
        )
        leads = leads_res.scalars().all()

        drafted_leads: List[Dict[str, Any]] = []
        saved_in_gmail_count = 0
        pending_oauth_sync_count = 0
        contact_only_count = 0

        for row in leads:
            meta = dict(row.metadata_ or {})
            if not (meta.get("gmail_draft_body") or meta.get("autopilot_discovered")):
                continue
            d_status = str(meta.get("gmail_draft_status") or "saved_in_crm_oauth_required")
            if d_status == "saved_in_gmail":
                saved_in_gmail_count += 1
            elif d_status == "contact_only_no_email":
                contact_only_count += 1
            else:
                pending_oauth_sync_count += 1

            drafted_leads.append({
                "lead_id": str(row.id),
                "company_name": row.name,
                "email": row.email,
                "phone": row.phone,
                "website": meta.get("website"),
                "niche": meta.get("autopilot_niche") or meta.get("industry"),
                "city": meta.get("autopilot_city") or meta.get("location"),
                "subject": meta.get("gmail_draft_subject"),
                "body": meta.get("gmail_draft_body"),
                "draft_id": meta.get("gmail_draft_id"),
                "draft_status": d_status,
                "drafted_at": meta.get("gmail_drafted_at") or row.created_at.isoformat(),
                "email_source": meta.get("email_source"),
                "gmail_error": meta.get("gmail_error"),
            })

        return {
            "config": config,
            "gmail_status": gmail_status,
            "next_target": {"niche": next_niche, "city": next_city},
            "stats": {
                "total_drafted": len(drafted_leads),
                "saved_in_gmail_count": saved_in_gmail_count,
                "pending_oauth_sync_count": pending_oauth_sync_count,
                "contact_only_count": contact_only_count,
            },
            "drafted_leads": drafted_leads[:40],
        }

    async def update_autopilot_config(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: OutreachAutopilotConfigUpdate,
    ) -> Dict[str, Any]:
        """Validate and persist daily outreach autopilot settings onto tenant.settings."""
        t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_res.scalar_one_or_none()
        if not tenant:
            raise ResourceNotFoundError("Tenant", str(tenant_id))

        current_cfg = _build_default_config(tenant)
        if payload.enabled is not None:
            current_cfg["enabled"] = payload.enabled
        if payload.niches is not None:
            current_cfg["niches"] = _clean_string_list(payload.niches, DEFAULT_NICHES, 20)
        if payload.cities is not None:
            current_cfg["cities"] = _clean_string_list(payload.cities, DEFAULT_CITIES, 40)
        if payload.daily_draft_limit is not None:
            current_cfg["daily_draft_limit"] = payload.daily_draft_limit
        if payload.service_offer is not None and payload.service_offer.strip():
            current_cfg["service_offer"] = payload.service_offer.strip()
        if payload.sender_name is not None and payload.sender_name.strip():
            current_cfg["sender_name"] = payload.sender_name.strip()
        if payload.booking_url is not None:
            current_cfg["booking_url"] = payload.booking_url.strip()
        if payload.run_hour_utc is not None:
            current_cfg["run_hour_utc"] = payload.run_hour_utc

        new_settings = dict(tenant.settings or {})
        new_settings[AUTOPILOT_SETTINGS_KEY] = current_cfg
        tenant.settings = new_settings

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=user_id,
                actor_type="user",
                action="outreach_autopilot.config.updated",
                resource_type="tenant",
                resource_id=tenant_id,
                metadata_={
                    "enabled": current_cfg["enabled"],
                    "niches_count": len(current_cfg["niches"]),
                    "cities_count": len(current_cfg["cities"]),
                    "daily_draft_limit": current_cfg["daily_draft_limit"],
                    "run_hour_utc": current_cfg["run_hour_utc"],
                },
            )
        )
        await session.commit()
        return await self.get_autopilot_state(session, tenant_id)

    async def sync_pending_crm_drafts(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Push previously generated CRM drafts into the workspace's live Gmail Drafts folder."""
        integ, gmail_status = await self._inspect_gmail_integration(session, tenant_id)
        if not gmail_status["can_create_live_drafts"]:
            raise TaloxException(
                message="Please authorize Gmail with Compose permission first before pushing drafts to Gmail.",
                code="GMAIL_OAUTH_REQUIRED",
                status_code=400,
            )

        access_token = await self._ensure_fresh_gmail_token(session, integ)
        from_email = gmail_status.get("account")

        leads_res = await session.execute(
            select(Lead)
            .where(Lead.tenant_id == tenant_id)
            .order_by(Lead.created_at.desc())
            .limit(100)
        )
        synced_count = 0
        failed_count = 0

        for row in leads_res.scalars().all():
            if synced_count >= 20:
                break
            meta = dict(row.metadata_ or {})
            if not row.email or not meta.get("gmail_draft_body"):
                continue
            if meta.get("gmail_draft_status") not in ("saved_in_crm_oauth_required", "gmail_api_error"):
                continue

            subject = str(meta.get("gmail_draft_subject") or f"Quick question for {row.name}")
            body = str(meta.get("gmail_draft_body"))
            draft_res = await email_adapter.create_gmail_draft(
                tenant_id=str(tenant_id),
                to_email=row.email,
                subject=subject,
                body=body,
                access_token=access_token,
                from_email=from_email,
            )
            if not draft_res.get("success") and draft_res.get("status_code") == 401:
                refreshed = await self._ensure_fresh_gmail_token(session, integ, force_refresh=True)
                if refreshed:
                    access_token = refreshed
                    draft_res = await email_adapter.create_gmail_draft(
                        tenant_id=str(tenant_id),
                        to_email=row.email,
                        subject=subject,
                        body=body,
                        access_token=access_token,
                        from_email=from_email,
                    )

            updated_meta = dict(meta)
            if draft_res.get("success") and draft_res.get("is_live"):
                updated_meta["gmail_draft_status"] = "saved_in_gmail"
                updated_meta["gmail_draft_id"] = draft_res.get("draft_id")
                updated_meta["gmail_synced_at"] = datetime.now(timezone.utc).isoformat()
                updated_meta.pop("gmail_error", None)
                synced_count += 1
            else:
                updated_meta["gmail_draft_status"] = "gmail_api_error"
                updated_meta["gmail_error"] = draft_res.get("error") or "Gmail API draft creation failed"
                failed_count += 1
            row.metadata_ = updated_meta

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="outreach_autopilot.sync_drafts.executed",
                resource_type="integration",
                resource_id=integ.id if integ else None,
                metadata_={"synced_count": synced_count, "failed_count": failed_count},
            )
        )
        await session.commit()
        state = await self.get_autopilot_state(session, tenant_id)
        return {
            "synced_count": synced_count,
            "failed_count": failed_count,
            "state": state,
        }

    async def run_autopilot_cycle(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
        niche_override: Optional[str] = None,
        city_override: Optional[str] = None,
        limit_override: Optional[int] = None,
        sync_pending_crm_drafts: bool = False,
    ) -> Dict[str, Any]:
        """Discover global businesses for one niche & city, craft company-specific pitches, and save Gmail drafts.

        Strictly Human-in-the-Loop: NEVER auto-sends any email.
        """
        t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_res.scalar_one_or_none()
        if not tenant:
            raise ResourceNotFoundError("Tenant", str(tenant_id))

        rc_res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id).limit(1)
        )
        recep_cfg = rc_res.scalar_one_or_none()
        booking_hint = recep_cfg.calcom_booking_url if recep_cfg and recep_cfg.calcom_booking_url else DEFAULT_BOOKING_URL

        config = _build_default_config(tenant, booking_url_hint=booking_hint)
        integ, gmail_status = await self._inspect_gmail_integration(session, tenant_id)

        synced_pending = 0
        if sync_pending_crm_drafts and gmail_status["can_create_live_drafts"]:
            sync_res = await self.sync_pending_crm_drafts(session, tenant_id, actor_id=actor_id)
            synced_pending = sync_res.get("synced_count", 0)

        rot_niche, rot_city = _compute_rotation_target(
            config["niches"], config["cities"], config["rotation_index"]
        )
        target_niche = (niche_override or "").strip() or rot_niche
        target_city = (city_override or "").strip() or rot_city
        target_limit = min(max(limit_override or config["daily_draft_limit"], 1), 15)
        search_keyword = NICHE_SEARCH_KEYWORDS.get(target_niche.lower(), target_niche)

        gen_result = await marketing_service.generate_leads_from_google_maps(
            session=session,
            tenant_id=tenant_id,
            user_id=actor_id or tenant_id,
            request=LeadGenerationRequest(
                industry=target_niche[:100],
                location=target_city[:120],
                keywords=search_keyword[:200],
                limit=min(max(target_limit * 3, 10), 20),
            ),
        )
        created_ids = [item["id"] for item in gen_result.get("leads", []) if item.get("id")]
        created_id_set = set(created_ids)

        # Load recent tenant leads, prioritizing newly discovered rows first
        leads_res = await session.execute(
            select(Lead)
            .where(Lead.tenant_id == tenant_id)
            .order_by(Lead.created_at.desc())
            .limit(80)
        )
        all_leads = leads_res.scalars().all()

        undrafted_candidates: List[Lead] = []
        for row in all_leads:
            meta = dict(row.metadata_ or {})
            if meta.get("opted_out") is True:
                continue
            if meta.get("outreach_drafted") is True or meta.get("gmail_draft_status") == "saved_in_gmail":
                continue
            undrafted_candidates.append(row)

        undrafted_candidates.sort(
            key=lambda r: (
                0 if str(r.id) in created_id_set else 1,
                0 if r.email else 1,
            )
        )

        # Step A: Enrich leads missing an email by checking their real website (strictly concurrent, no DB)
        enrich_targets: List[Tuple[Lead, str]] = []
        for row in undrafted_candidates:
            if row.email:
                continue
            website = (row.metadata_ or {}).get("website")
            if website and "openstreetmap.org" not in str(website).lower():
                enrich_targets.append((row, str(website)))
            if len(enrich_targets) >= min(target_limit * 2, 10):
                break

        emails_enriched = 0
        if enrich_targets:
            sem = asyncio.Semaphore(4)

            async def _lookup(url: str) -> Optional[str]:
                async with sem:
                    return await discover_public_website_email(url)

            found_emails = await asyncio.gather(*[_lookup(url) for _, url in enrich_targets])
            for (row, _), found_email in zip(enrich_targets, found_emails):
                if found_email:
                    row.email = found_email
                    new_meta = dict(row.metadata_ or {})
                    new_meta["email_source"] = "public_website"
                    row.metadata_ = new_meta
                    emails_enriched += 1

        email_ready_leads = [row for row in undrafted_candidates if row.email][:target_limit]
        contact_only_leads = [
            row
            for row in undrafted_candidates
            if not row.email and str(row.id) in created_id_set
        ][:target_limit]

        # Step B: Generate company-specific AI emails concurrently (no DB calls inside gather)
        pitch_targets = [*email_ready_leads, *contact_only_leads]
        generated_pitches: Dict[str, Tuple[str, str]] = {}
        if pitch_targets:
            ai_sem = asyncio.Semaphore(3)

            async def _build_pitch(row: Lead) -> Tuple[str, Tuple[str, str]]:
                meta = dict(row.metadata_ or {})
                row_niche = str(meta.get("industry") or target_niche)
                row_city = str(meta.get("location") or target_city)
                async with ai_sem:
                    subj_body = await _generate_company_email(
                        tenant_id=tenant_id,
                        company_name=row.name,
                        niche=row_niche,
                        city=row_city,
                        website=meta.get("website"),
                        address=meta.get("address"),
                        sender_name=config["sender_name"],
                        service_offer=config["service_offer"],
                        booking_url=config["booking_url"],
                    )
                return str(row.id), subj_body

            pitch_results = await asyncio.gather(*[_build_pitch(row) for row in pitch_targets])
            generated_pitches = dict(pitch_results)

        # Step C: Save Gmail drafts sequentially (DB-safe + OAuth token refresh on 401; NEVER auto-send!)
        access_token: Optional[str] = None
        if gmail_status["can_create_live_drafts"]:
            access_token = await self._ensure_fresh_gmail_token(session, integ)

        saved_in_gmail = 0
        saved_in_crm = 0
        draft_errors = 0
        created_drafts: List[Dict[str, Any]] = []
        now_iso = datetime.now(timezone.utc).isoformat()
        from_email = gmail_status.get("account")

        for row in email_ready_leads:
            subject, body = generated_pitches[str(row.id)]
            meta = dict(row.metadata_ or {})

            if gmail_status["can_create_live_drafts"]:
                draft_res = await email_adapter.create_gmail_draft(
                    tenant_id=str(tenant_id),
                    to_email=row.email or "",
                    subject=subject,
                    body=body,
                    access_token=access_token,
                    from_email=from_email,
                )
                if not draft_res.get("success") and draft_res.get("status_code") == 401:
                    refreshed = await self._ensure_fresh_gmail_token(session, integ, force_refresh=True)
                    if refreshed:
                        access_token = refreshed
                        draft_res = await email_adapter.create_gmail_draft(
                            tenant_id=str(tenant_id),
                            to_email=row.email or "",
                            subject=subject,
                            body=body,
                            access_token=access_token,
                            from_email=from_email,
                        )
            else:
                draft_res = await email_adapter.create_gmail_draft(
                    tenant_id=str(tenant_id),
                    to_email=row.email or "",
                    subject=subject,
                    body=body,
                    access_token=None,
                    from_email=from_email,
                )

            if draft_res.get("success") and draft_res.get("is_live"):
                d_status = "saved_in_gmail"
                saved_in_gmail += 1
                err_note = None
            elif draft_res.get("success"):
                d_status = "saved_in_crm_oauth_required"
                saved_in_crm += 1
                err_note = None
            else:
                d_status = "gmail_api_error"
                draft_errors += 1
                err_note = str(draft_res.get("error") or "Gmail API draft creation failed")

            new_meta = dict(meta)
            new_meta.update({
                "autopilot_discovered": True,
                "autopilot_niche": str(meta.get("industry") or target_niche),
                "autopilot_city": str(meta.get("location") or target_city),
                "outreach_drafted": True,
                "gmail_draft_id": draft_res.get("draft_id"),
                "gmail_draft_subject": subject,
                "gmail_draft_body": body,
                "gmail_draft_status": d_status,
                "gmail_drafted_at": now_iso,
            })
            if err_note:
                new_meta["gmail_error"] = err_note
            else:
                new_meta.pop("gmail_error", None)
            row.metadata_ = new_meta

            created_drafts.append({
                "lead_id": str(row.id),
                "company_name": row.name,
                "email": row.email,
                "phone": row.phone,
                "niche": new_meta["autopilot_niche"],
                "city": new_meta["autopilot_city"],
                "subject": subject,
                "draft_id": draft_res.get("draft_id"),
                "draft_status": d_status,
            })

        for row in contact_only_leads:
            subject, body = generated_pitches[str(row.id)]
            new_meta = dict(row.metadata_ or {})
            new_meta.update({
                "autopilot_discovered": True,
                "autopilot_niche": str(new_meta.get("industry") or target_niche),
                "autopilot_city": str(new_meta.get("location") or target_city),
                "gmail_draft_subject": subject,
                "gmail_draft_body": body,
                "gmail_draft_status": "contact_only_no_email",
                "gmail_drafted_at": now_iso,
            })
            row.metadata_ = new_meta

        # Step D: Persist updated rotation & run telemetry on tenant.settings
        if not niche_override and not city_override:
            config["rotation_index"] = config["rotation_index"] + 1
        config["last_run_at"] = now_iso
        run_summary = {
            "niche": target_niche,
            "city": target_city,
            "data_source": gen_result.get("data_source"),
            "leads_discovered": gen_result.get("created_count", 0),
            "emails_enriched_from_websites": emails_enriched,
            "drafts_saved_in_gmail": saved_in_gmail,
            "drafts_saved_in_crm": saved_in_crm,
            "draft_errors": draft_errors,
            "contact_only_found": len(contact_only_leads),
            "synced_pending_drafts": synced_pending,
            "ran_at": now_iso,
        }
        config["last_run_summary"] = run_summary

        new_settings = dict(tenant.settings or {})
        new_settings[AUTOPILOT_SETTINGS_KEY] = config
        tenant.settings = new_settings

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="outreach_autopilot.cycle.executed",
                resource_type="lead",
                metadata_=run_summary,
            )
        )
        await session.commit()

        await notification_service.send_notification(
            session=session,
            tenant_id=tenant_id,
            title=f"Daily Global Outreach: {saved_in_gmail + saved_in_crm} Drafts Ready",
            message=(
                f"Searched {target_niche} in {target_city}: discovered {run_summary['leads_discovered']} new leads, "
                f"saved {saved_in_gmail} live Gmail drafts and {saved_in_crm} CRM drafts for review."
            ),
            channel="in_app",
        )

        state = await self.get_autopilot_state(session, tenant_id)
        return {
            "run_summary": run_summary,
            "created_drafts": created_drafts,
            "state": state,
        }

    async def run_scheduled_autopilot_tick(
        self,
        session: AsyncSession,
    ) -> Dict[str, Any]:
        """Background scheduler entrypoint: runs once daily per active tenant with Daily Autopilot enabled."""
        t_res = await session.execute(select(Tenant).where(Tenant.status == "active"))
        tenants = t_res.scalars().all()
        now_utc = datetime.now(timezone.utc)

        checked = 0
        executed = 0
        errors = 0

        for tenant in tenants:
            ap_cfg = (tenant.settings or {}).get(AUTOPILOT_SETTINGS_KEY) or {}
            if not ap_cfg.get("enabled"):
                continue
            checked += 1

            try:
                run_hour = min(max(int(ap_cfg.get("run_hour_utc") if ap_cfg.get("run_hour_utc") is not None else 6), 0), 23)
            except (TypeError, ValueError):
                run_hour = 6

            last_dt = _parse_iso_datetime(ap_cfg.get("last_run_at"))
            should_run = False
            if last_dt is None:
                should_run = True
            else:
                elapsed = now_utc - last_dt
                if elapsed >= timedelta(hours=24):
                    should_run = True
                elif (
                    elapsed >= timedelta(hours=20)
                    and now_utc.date() > last_dt.date()
                    and now_utc.hour >= run_hour
                ):
                    should_run = True

            if not should_run:
                continue

            try:
                await self.run_autopilot_cycle(
                    session=session,
                    tenant_id=tenant.id,
                    actor_id=None,
                )
                executed += 1
            except Exception as exc:
                errors += 1
                await session.rollback()
                logger.error(
                    "Daily global outreach autopilot tenant cycle failed",
                    tenant_id=str(tenant.id),
                    error=str(exc),
                )

        return {"checked": checked, "executed": executed, "errors": errors}


outreach_autopilot_service = OutreachAutopilotService()
