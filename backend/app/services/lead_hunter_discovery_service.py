"""International Dual-Source Lead Finder (Google Places + Apollo Free Tier),
AI Receptionist Detector, and 0-100 Interest Scoring Service.

Strict Rules:
- ZERO fake / dummy leads generated if API keys are missing.
- Apollo enrichment runs strictly within daily free-credit caps and ONLY after
  Google Places filters out businesses that already have AI widgets.
"""

import re
import urllib.parse
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx
from app.config import settings
from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.core.logging import logger
from app.database.models.lead_hunter import HunterLead
from app.services.lead_hunter_control_service import lead_hunter_control_service
from app.services.outreach_autopilot_service import _is_safe_public_url
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

COUNTRIES: List[str] = ["USA", "UK", "Canada", "Australia", "UAE", "Singapore"]

CITIES_BY_COUNTRY: Dict[str, List[str]] = {
    "USA": ["New York", "Los Angeles", "Houston", "Miami", "Chicago"],
    "UK": ["London", "Manchester"],
    "Canada": ["Toronto"],
    "Australia": ["Sydney"],
    "UAE": ["Dubai"],
    "Singapore": ["Singapore"],
}

ALL_CITIES: List[str] = [
    "New York",
    "London",
    "Los Angeles",
    "Toronto",
    "Sydney",
    "Dubai",
    "Houston",
    "Miami",
    "Chicago",
    "Manchester",
    "Singapore",
]

CITY_TIMEZONES: Dict[str, str] = {
    "New York": "America/New_York",
    "Miami": "America/New_York",
    "Toronto": "America/Toronto",
    "Chicago": "America/Chicago",
    "Houston": "America/Chicago",
    "Los Angeles": "America/Los_Angeles",
    "London": "Europe/London",
    "Manchester": "Europe/London",
    "Sydney": "Australia/Sydney",
    "Dubai": "Asia/Dubai",
    "Singapore": "Asia/Singapore",
}

CATEGORIES: List[str] = [
    "Dental Clinic",
    "Medical Clinic",
    "Law Firm",
    "Real Estate Agency",
    "Beauty Salon",
    "Spa",
    "Restaurant",
    "Hotel",
    "Gym",
    "Auto Repair Shop",
    "Cleaning Company",
    "Plumbing Company",
]

AI_WIDGET_SIGNATURES: Dict[str, str] = {
    "intercom": "Intercom Chat Widget",
    "widget.intercom.io": "Intercom Chat Widget",
    "drift.com": "Drift AI Chat",
    "js.driftt.com": "Drift AI Chat",
    "tidio": "Tidio AI / Live Chat",
    "code.tidio.co": "Tidio AI / Live Chat",
    "crisp.chat": "Crisp Live Chat",
    "client.crisp.chat": "Crisp Live Chat",
    "zendesk": "Zendesk Chat",
    "zdassets.com": "Zendesk Chat",
    "leadconnectorhq": "GoHighLevel Chat Widget",
    "widgets.leadconnectorhq.com": "GoHighLevel Chat Widget",
    "tawk.to": "Tawk.to Live Chat",
    "livechatinc": "LiveChat Widget",
    "js-eu1.hs-scripts.com": "HubSpot Conversations",
    "hs-scripts.com": "HubSpot Chat Widget",
    "freshchat": "Freshchat Widget",
    "botpress": "Botpress AI Chatbot",
    "voiceflow": "Voiceflow AI Agent",
    "retellai": "Retell AI Voice Agent",
    "vapi.ai": "Vapi AI Receptionist",
    "podium": "Podium Messaging Widget",
    "birdeye": "Birdeye Webchat",
    "smith.ai": "Smith.ai Receptionist",
    "ruby.com": "Ruby Virtual Receptionist",
}

MISSED_CALL_PHRASES: Tuple[str, ...] = (
    "never answer",
    "never answers",
    "no one picks up",
    "nobody picks up",
    "nobody answers",
    "missed call",
    "missed calls",
    "voicemail",
    "hard to reach",
    "couldn't reach",
    "could not reach",
    "never pick up",
    "phone rings off",
    "no answer",
)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def _extract_domain(website: Optional[str]) -> Optional[str]:
    if not website:
        return None
    raw = website.strip()
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    parsed = urllib.parse.urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _is_configured_key(val: Optional[str]) -> bool:
    clean = (val or "").strip()
    return bool(clean and not clean.lower().startswith("your-") and clean.lower() not in ("mock", "none", "null"))


class LeadHunterDiscoveryService:
    """Real Google Places + Apollo Free Tier discovery, AI detection, and 0-100 scoring."""

    @staticmethod
    def serialize_lead(row: HunterLead) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "google_place_id": row.google_place_id,
            "business_name": row.business_name,
            "owner_name": row.owner_name,
            "owner_title": row.owner_title,
            "linkedin_url": row.linkedin_url,
            "country": row.country,
            "city": row.city,
            "category": row.category,
            "address": row.address,
            "phone": row.phone,
            "email": row.email,
            "email_verified": bool(row.email_verified),
            "website": row.website,
            "favicon_url": row.favicon_url,
            "services": row.services,
            "working_hours": row.working_hours,
            "pricing_info": row.pricing_info,
            "rating": float(row.rating or 0.0),
            "total_reviews": int(row.total_reviews or 0),
            "has_ai": bool(row.has_ai),
            "ai_evidence": row.ai_evidence or {},
            "pain_points": row.pain_points or [],
            "interest_score": int(row.interest_score or 0),
            "lead_source": row.lead_source,
            "status": row.status,
            "pipeline_stage": row.pipeline_stage,
            "timezone": row.timezone,
            "deal_value_usd": float(row.deal_value_usd or 0.0),
            "human_needed": bool(row.human_needed),
            "do_not_disturb": bool(row.do_not_disturb),
            "last_contact_at": row.last_contact_at.isoformat() if row.last_contact_at else None,
            "next_followup_at": row.next_followup_at.isoformat() if row.next_followup_at else None,
            "call_result": row.call_result,
            "metadata": row.metadata_ or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def inspect_website_and_ai(
        self,
        website_url: Optional[str],
        reviews: Optional[List[Dict[str, Any]]] = None,
        gbp_messaging_enabled: bool = False,
    ) -> Dict[str, Any]:
        """Inspect website HTML for chatbot scripts + scan reviews for missed-call pain points."""
        detected_widgets: List[str] = []
        extracted_email: Optional[str] = None
        services_hint: Optional[str] = None
        html_checked = False
        safe_url = _is_safe_public_url(website_url) if website_url else None
        domain = _extract_domain(safe_url or website_url)
        favicon_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=64" if domain else None

        if safe_url:
            try:
                async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                    resp = await client.get(
                        safe_url,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; TaloxLeadAuditor/1.0)"},
                    )
                    if resp.status_code == 200 and resp.text:
                        html_checked = True
                        raw_html = resp.text[:300000]
                        lower_html = raw_html.lower()
                        for sig, label in AI_WIDGET_SIGNATURES.items():
                            if sig in lower_html and label not in detected_widgets:
                                detected_widgets.append(label)

                        soup = BeautifulSoup(raw_html, "html.parser")
                        emails_found = [
                            m for m in EMAIL_REGEX.findall(soup.get_text(" ", strip=True) + " " + raw_html)
                            if not any(bad in m.lower() for bad in ("example.com", "sentry.io", "wixpress.com", ".png", ".jpg"))
                        ]
                        if emails_found:
                            # Prefer non-generic or matching domain email first
                            extracted_email = emails_found[0]

                        meta_desc = soup.find("meta", attrs={"name": "description"})
                        title_txt = soup.title.string.strip() if soup.title and soup.title.string else ""
                        desc_txt = meta_desc.get("content", "").strip() if meta_desc else ""
                        combined_hint = " — ".join(p for p in (title_txt, desc_txt) if p)
                        if combined_hint:
                            services_hint = combined_hint[:280]
            except Exception as exc:
                logger.debug("Website AI inspection skipped", website=website_url, error=str(exc))

        if gbp_messaging_enabled and "Google Business Chat" not in detected_widgets:
            detected_widgets.append("Google Business Chat")

        pain_points: List[str] = []
        missed_call_count = 0
        for rev in (reviews or []):
            rev_text = str(rev.get("text") or "").strip()
            rev_lower = rev_text.lower()
            if any(phrase in rev_lower for phrase in MISSED_CALL_PHRASES):
                missed_call_count += 1
                if len(pain_points) < 3:
                    pain_points.append(rev_text[:180])

        has_ai = len(detected_widgets) > 0
        return {
            "has_ai": has_ai,
            "detected_widgets": detected_widgets,
            "html_checked": html_checked,
            "gbp_messaging_enabled": gbp_messaging_enabled,
            "missed_call_mentions": missed_call_count,
            "pain_points": pain_points,
            "scraped_email": extracted_email,
            "services_hint": services_hint,
            "favicon_url": favicon_url,
        }

    @staticmethod
    def compute_interest_score(
        *,
        has_ai: bool,
        missed_call_mentions: int,
        rating: float,
        total_reviews: int,
        website: Optional[str],
        email: Optional[str],
        email_verified: bool,
        owner_name: Optional[str],
        linkedin_url: Optional[str],
    ) -> int:
        """Score lead 0-100 matching High (80-100), Medium (50-79), Low (0-49) rubric."""
        if has_ai:
            score = 32
            if missed_call_mentions > 0:
                score += 10
            return min(49, max(10, score))

        score = 58
        if missed_call_mentions > 0:
            score += min(22, 14 + missed_call_mentions * 4)
        if rating > 0 and rating < 4.2 and total_reviews >= 15:
            score += 12
        elif total_reviews >= 25:
            score += 6
        if website:
            score += 8
        if email and not email.lower().startswith(("info@", "contact@", "hello@", "support@")):
            score += 6
        if email_verified and owner_name and linkedin_url:
            score += 10
        elif owner_name or linkedin_url:
            score += 5
        return min(100, max(50, score))

    async def _fetch_google_places(
        self,
        category: str,
        city: str,
        country: str,
        max_results: int = 8,
    ) -> List[Dict[str, Any]]:
        api_key = (settings.google_places_api_key or "").strip()
        if not _is_configured_key(api_key):
            raise TaloxException(
                message="Please add Google Places API Key in .env",
                code="MISSING_GOOGLE_PLACES_API_KEY",
                status_code=400,
            )

        query = f"{category} in {city}, {country}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            search_resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={"query": query, "key": api_key},
            )
            if search_resp.status_code != 200:
                raise TaloxException(
                    message=f"Google Places API error (HTTP {search_resp.status_code})",
                    code="GOOGLE_PLACES_ERROR",
                    status_code=502,
                )
            search_json = search_resp.json()
            status_txt = str(search_json.get("status") or "")
            if status_txt in ("REQUEST_DENIED", "INVALID_REQUEST", "OVER_QUERY_LIMIT"):
                raise TaloxException(
                    message=search_json.get("error_message") or f"Google Places API returned {status_txt}",
                    code="GOOGLE_PLACES_REJECTED",
                    status_code=400,
                )

            results = (search_json.get("results") or [])[:max_results]
            detailed: List[Dict[str, Any]] = []
            for place in results:
                pid = place.get("place_id")
                det: Dict[str, Any] = dict(place)
                if pid:
                    det_resp = await client.get(
                        "https://maps.googleapis.com/maps/api/place/details/json",
                        params={
                            "place_id": pid,
                            "fields": (
                                "name,formatted_address,formatted_phone_number,"
                                "international_phone_number,website,rating,"
                                "user_ratings_total,reviews,opening_hours,url"
                            ),
                            "key": api_key,
                        },
                    )
                    if det_resp.status_code == 200:
                        det_json = det_resp.json()
                        if det_json.get("result"):
                            det.update(det_json["result"])
                detailed.append(det)
            return detailed

    async def _search_apollo_people(
        self,
        category: str,
        city: str,
        country: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        api_key = (settings.apollo_api_key or "").strip()
        if not _is_configured_key(api_key):
            raise TaloxException(
                message="Please add Apollo API Key in .env",
                code="MISSING_APOLLO_API_KEY",
                status_code=400,
            )

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.apollo.io/api/v1/mixed_people/search",
                headers={
                    "X-Api-Key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "q_keywords": category,
                    "person_titles": ["Owner", "Founder", "Managing Partner", "CEO", "Director", "Principal", "Dentist"],
                    "person_locations": [f"{city}, {country}"],
                    "page": 1,
                    "per_page": min(max_results, 15),
                },
            )
            if resp.status_code in (402, 429):
                raise TaloxException(
                    message="Apollo free-tier quota exhausted or rate-limited. Hard-stopped to avoid overages.",
                    code="APOLLO_QUOTA_EXHAUSTED",
                    status_code=429,
                )
            if resp.status_code in (401, 403):
                raise TaloxException(
                    message="Apollo API Key rejected. Check APOLLO_API_KEY in .env.",
                    code="INVALID_APOLLO_API_KEY",
                    status_code=401,
                )
            if resp.status_code != 200:
                raise TaloxException(
                    message=f"Apollo API returned HTTP {resp.status_code}",
                    code="APOLLO_API_ERROR",
                    status_code=502,
                )
            data = resp.json()
            return list(data.get("people") or data.get("contacts") or [])

    async def _enrich_domain_via_apollo(
        self,
        business_name: str,
        website: Optional[str],
        city: str,
        country: str,
    ) -> Optional[Dict[str, Any]]:
        api_key = (settings.apollo_api_key or "").strip()
        if not _is_configured_key(api_key):
            raise TaloxException(
                message="Please add Apollo API Key in .env",
                code="MISSING_APOLLO_API_KEY",
                status_code=400,
            )

        domain = _extract_domain(website)
        payload: Dict[str, Any] = {
            "person_titles": ["Owner", "Founder", "Managing Partner", "CEO", "Director", "Practice Manager"],
            "page": 1,
            "per_page": 3,
        }
        if domain:
            payload["q_organization_domains"] = domain
        else:
            payload["q_keywords"] = f"{business_name} {city}"
            payload["person_locations"] = [f"{city}, {country}"]

        async with httpx.AsyncClient(timeout=18.0) as client:
            resp = await client.post(
                "https://api.apollo.io/api/v1/mixed_people/search",
                headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code in (402, 429):
                raise TaloxException(
                    message="Apollo free-tier credits reached 0 / rate limit hit. Hard-stopped.",
                    code="APOLLO_QUOTA_EXHAUSTED",
                    status_code=429,
                )
            if resp.status_code != 200:
                return None
            people = list((resp.json() or {}).get("people") or [])
            if not people:
                return None

            # Pick person with verified email or top owner title first
            best = next((p for p in people if p.get("email") and p.get("email_status") == "verified"), people[0])
            org = best.get("organization") or {}
            phones = best.get("phone_numbers") or []
            direct_phone = phones[0].get("sanitized_number") if phones and isinstance(phones[0], dict) else org.get("phone")
            return {
                "owner_name": best.get("name") or f"{best.get('first_name', '')} {best.get('last_name', '')}".strip() or None,
                "owner_title": best.get("title"),
                "email": best.get("email"),
                "email_verified": best.get("email_status") == "verified" or bool(best.get("email")),
                "linkedin_url": best.get("linkedin_url"),
                "direct_phone": direct_phone,
                "organization_name": org.get("name"),
                "website": org.get("website_url"),
            }

    async def search_and_ingest_leads(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        country: str,
        city: str,
        category: str,
        source_mode: str = "google_places",
        max_results: int = 8,
    ) -> Dict[str, Any]:
        """Search real leads from Google Places, Apollo Free Tier, or Hybrid (enriching No-AI leads only)."""
        mode = source_mode.strip().lower()
        if mode not in ("google_places", "apollo", "hybrid"):
            raise TaloxException(
                message="source_mode must be 'google_places', 'apollo', or 'hybrid'",
                code="INVALID_SOURCE_MODE",
                status_code=400,
            )

        if mode in ("google_places", "hybrid"):
            await lead_hunter_control_service.assert_module_enabled_and_quota(
                session, tenant_id, "google_places_finder", units=1, require_switch_on=True
            )
            if not _is_configured_key(settings.google_places_api_key):
                raise TaloxException(
                    message="Please add Google Places API Key in .env",
                    code="MISSING_GOOGLE_PLACES_API_KEY",
                    status_code=400,
                )

        if mode in ("apollo", "hybrid"):
            await lead_hunter_control_service.assert_module_enabled_and_quota(
                session, tenant_id, "apollo_enrichment", units=1, require_switch_on=True
            )
            if not _is_configured_key(settings.apollo_api_key):
                raise TaloxException(
                    message="Please add Apollo API Key in .env",
                    code="MISSING_APOLLO_API_KEY",
                    status_code=400,
                )

        tz = CITY_TIMEZONES.get(city.strip(), "America/New_York")
        ingested: List[HunterLead] = []
        skipped_ai_apollo = 0
        apollo_used = 0

        if mode in ("google_places", "hybrid"):
            places = await self._fetch_google_places(category, city, country, max_results=max_results)
            await lead_hunter_control_service.increment_usage(session, tenant_id, "google_places_finder", units=1)

            apollo_row = await lead_hunter_control_service.get_module_row(session, tenant_id, "apollo_enrichment")
            apollo_remaining = max(0, int(apollo_row.daily_limit) - int(apollo_row.used_today))

            for place in places:
                place_id = str(place.get("place_id") or "").strip() or None
                biz_name = str(place.get("name") or "").strip()
                if not biz_name:
                    continue

                website = place.get("website")
                reviews = list(place.get("reviews") or [])
                audit = await self.inspect_website_and_ai(website_url=website, reviews=reviews)
                has_ai = audit["has_ai"]
                rating = float(place.get("rating") or 0.0)
                total_reviews = int(place.get("user_ratings_total") or 0)
                phone = place.get("international_phone_number") or place.get("formatted_phone_number")
                hours_list = (place.get("opening_hours") or {}).get("weekday_text") or []
                working_hours = "; ".join(hours_list[:3]) if hours_list else None

                owner_name: Optional[str] = None
                owner_title: Optional[str] = None
                linkedin_url: Optional[str] = None
                email: Optional[str] = audit["scraped_email"]
                email_verified = False
                actual_source = "google_places"

                # Smart Guardrail: In Hybrid mode, ONLY spend free Apollo credits on businesses with NO AI!
                if mode == "hybrid":
                    if has_ai:
                        skipped_ai_apollo += 1
                    elif apollo_remaining > 0:
                        enriched = await self._enrich_domain_via_apollo(biz_name, website, city, country)
                        apollo_remaining -= 1
                        apollo_used += 1
                        if enriched:
                            owner_name = enriched.get("owner_name")
                            owner_title = enriched.get("owner_title")
                            linkedin_url = enriched.get("linkedin_url")
                            email = enriched.get("email") or email
                            email_verified = bool(enriched.get("email_verified"))
                            phone = phone or enriched.get("direct_phone")
                            actual_source = "hybrid"

                score = self.compute_interest_score(
                    has_ai=has_ai,
                    missed_call_mentions=audit["missed_call_mentions"],
                    rating=rating,
                    total_reviews=total_reviews,
                    website=website,
                    email=email,
                    email_verified=email_verified,
                    owner_name=owner_name,
                    linkedin_url=linkedin_url,
                )

                existing: Optional[HunterLead] = None
                if place_id:
                    existing = (
                        await session.execute(
                            select(HunterLead).where(
                                HunterLead.tenant_id == tenant_id,
                                HunterLead.google_place_id == place_id,
                            ).limit(1)
                        )
                    ).scalar_one_or_none()

                if existing:
                    existing.business_name = biz_name
                    existing.address = place.get("formatted_address") or existing.address
                    existing.phone = phone or existing.phone
                    existing.website = website or existing.website
                    existing.email = email or existing.email
                    existing.email_verified = existing.email_verified or email_verified
                    existing.owner_name = owner_name or existing.owner_name
                    existing.owner_title = owner_title or existing.owner_title
                    existing.linkedin_url = linkedin_url or existing.linkedin_url
                    existing.has_ai = has_ai
                    existing.ai_evidence = audit
                    existing.pain_points = audit["pain_points"]
                    existing.interest_score = score
                    existing.lead_source = actual_source if existing.lead_source == "google_places" else existing.lead_source
                    if actual_source == "hybrid" and existing.pipeline_stage == "new_lead":
                        existing.pipeline_stage = "apollo_enriched"
                    row_obj = existing
                else:
                    row_obj = HunterLead(
                        tenant_id=tenant_id,
                        google_place_id=place_id,
                        business_name=biz_name,
                        owner_name=owner_name,
                        owner_title=owner_title,
                        linkedin_url=linkedin_url,
                        country=country,
                        city=city,
                        category=category,
                        address=place.get("formatted_address"),
                        phone=phone,
                        email=email,
                        email_verified=email_verified,
                        website=website,
                        favicon_url=audit["favicon_url"],
                        services=audit["services_hint"] or f"{category} services",
                        working_hours=working_hours or "Mon-Fri 9:00 AM - 6:00 PM",
                        rating=rating,
                        total_reviews=total_reviews,
                        has_ai=has_ai,
                        ai_evidence=audit,
                        pain_points=audit["pain_points"],
                        interest_score=score,
                        lead_source=actual_source,
                        status="enriched" if actual_source == "hybrid" else "new",
                        pipeline_stage="apollo_enriched" if actual_source == "hybrid" else "new_lead",
                        timezone=tz,
                    )
                    session.add(row_obj)
                ingested.append(row_obj)

            if apollo_used > 0:
                await lead_hunter_control_service.increment_usage(session, tenant_id, "apollo_enrichment", units=apollo_used)

        elif mode == "apollo":
            people = await self._search_apollo_people(category, city, country, max_results=max_results)
            await lead_hunter_control_service.increment_usage(session, tenant_id, "apollo_enrichment", units=1)
            apollo_used = 1

            for p in people:
                org = p.get("organization") or {}
                biz_name = str(org.get("name") or p.get("organization_name") or "").strip()
                if not biz_name:
                    continue
                website = org.get("website_url")
                audit = await self.inspect_website_and_ai(website_url=website, reviews=[])
                email = p.get("email") or audit["scraped_email"]
                verified = bool(p.get("email_status") == "verified" or p.get("email"))
                owner_name = p.get("name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or None
                linkedin_url = p.get("linkedin_url")
                phones = p.get("phone_numbers") or []
                phone = phones[0].get("sanitized_number") if phones and isinstance(phones[0], dict) else org.get("phone")

                score = self.compute_interest_score(
                    has_ai=audit["has_ai"],
                    missed_call_mentions=0,
                    rating=0.0,
                    total_reviews=0,
                    website=website,
                    email=email,
                    email_verified=verified,
                    owner_name=owner_name,
                    linkedin_url=linkedin_url,
                )
                row_obj = HunterLead(
                    tenant_id=tenant_id,
                    business_name=biz_name,
                    owner_name=owner_name,
                    owner_title=p.get("title"),
                    linkedin_url=linkedin_url,
                    country=country,
                    city=city,
                    category=category,
                    address=f"{city}, {country}",
                    phone=phone,
                    email=email,
                    email_verified=verified,
                    website=website,
                    favicon_url=audit["favicon_url"],
                    services=audit["services_hint"] or f"{category} services",
                    working_hours="Mon-Fri 9:00 AM - 6:00 PM",
                    has_ai=audit["has_ai"],
                    ai_evidence=audit,
                    pain_points=[],
                    interest_score=score,
                    lead_source="apollo",
                    status="enriched",
                    pipeline_stage="apollo_enriched",
                    timezone=tz,
                )
                session.add(row_obj)
                ingested.append(row_obj)

        await session.commit()
        for obj in ingested:
            await session.refresh(obj)

        return {
            "leads": [self.serialize_lead(l) for l in ingested],
            "count": len(ingested),
            "apollo_credits_used": apollo_used,
            "skipped_has_ai_apollo": skipped_ai_apollo,
        }

    async def enrich_lead_via_apollo(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        lead_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Enrich one specific lead with Apollo Decision Maker data (enforces daily free-tier cap)."""
        lead = (
            await session.execute(
                select(HunterLead).where(HunterLead.id == lead_id, HunterLead.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if not lead:
            raise ResourceNotFoundError("HunterLead", str(lead_id))

        await lead_hunter_control_service.assert_module_enabled_and_quota(
            session, tenant_id, "apollo_enrichment", units=1, require_switch_on=True
        )
        enriched = await self._enrich_domain_via_apollo(lead.business_name, lead.website, lead.city, lead.country)
        await lead_hunter_control_service.increment_usage(session, tenant_id, "apollo_enrichment", units=1)

        if enriched:
            lead.owner_name = enriched.get("owner_name") or lead.owner_name
            lead.owner_title = enriched.get("owner_title") or lead.owner_title
            lead.linkedin_url = enriched.get("linkedin_url") or lead.linkedin_url
            lead.email = enriched.get("email") or lead.email
            lead.email_verified = bool(enriched.get("email_verified") or lead.email_verified)
            lead.phone = lead.phone or enriched.get("direct_phone")
            lead.lead_source = "hybrid" if lead.lead_source == "google_places" else lead.lead_source
            if lead.pipeline_stage == "new_lead":
                lead.pipeline_stage = "apollo_enriched"
            lead.status = "enriched"
            lead.interest_score = self.compute_interest_score(
                has_ai=bool(lead.has_ai),
                missed_call_mentions=int((lead.ai_evidence or {}).get("missed_call_mentions") or len(lead.pain_points or [])),
                rating=float(lead.rating or 0.0),
                total_reviews=int(lead.total_reviews or 0),
                website=lead.website,
                email=lead.email,
                email_verified=bool(lead.email_verified),
                owner_name=lead.owner_name,
                linkedin_url=lead.linkedin_url,
            )
            await session.commit()
            await session.refresh(lead)

        return self.serialize_lead(lead)


lead_hunter_discovery_service = LeadHunterDiscoveryService()
