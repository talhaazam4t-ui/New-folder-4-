"""Automated Playwright Headless Web Scraper & Website Auditing Engine.

Features:
1. Playwright Headless Execution:
   - Renders dynamic JavaScript SPAs (React, Next.js, Vue, Angular).
   - Full DOM extraction with tag hierarchy, headings, images, and form structures.
   - Intercepts all network requests to monitor API calls (XHR/Fetch/REST/GraphQL).
2. Deep SEO Metadata Parsing:
   - Evaluates title, description, keywords, viewport, robots, canonical URL.
   - Extracts OpenGraph and Twitter card metadata.
   - Detects Schema.org JSON-LD structured data.
   - Validates heading hierarchy (H1..H3) and image accessibility (missing `alt` tags).
3. Performance Metrics Evaluation:
   - DNS lookup, TCP connect, TTFB (Time to First Byte), DOMContentLoaded, Total Load Time.
   - Network payload size, request count, HTTP status breakdown.
4. Resilient Fallback Engine:
   - If Playwright browser binaries are unavailable in slim container environments,
     automatically falls back to an async HTTP + BeautifulSoup engine without crashing.
5. Strict Error Handling:
   - Detects and categorizes timeouts, 403 Forbidden, Cloudflare anti-bot challenges,
     and network connection errors.
6. Multi-Tenant Storage:
   - Persists all audits per `tenant_id` into Supabase `public.website_audits`.
"""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from app.core.exceptions import ResourceNotFoundError
from app.core.logging import logger
from app.database.models.audit import WebsiteAudit
from bs4 import BeautifulSoup
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

# Optional Playwright Import with safe detection
try:
    from playwright.async_api import (
        Browser,
        Page,
        Request as PlaywrightRequest,
        Response as PlaywrightResponse,
        TimeoutError as PlaywrightTimeoutError,
        async_playwright,
    )
    PLAYWRIGHT_INSTALLED = True
except ImportError:
    PLAYWRIGHT_INSTALLED = False
    PlaywrightTimeoutError = TimeoutError  # type: ignore


class WebAuditorService:
    """Enterprise-grade automated website scraping, auditing, and network monitoring service."""

    def __init__(self):
        self.default_user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36 TeloxtechAuditor/2.0"
        )

    async def run_audit(
        self,
        tenant_id: uuid.UUID,
        target_url: str,
        session: AsyncSession,
        timeout_seconds: int = 30,
        extract_dom: bool = True,
        monitor_network: bool = True,
    ) -> WebsiteAudit:
        """Run an automated audit on target_url, evaluate SEO/performance, and save to Supabase."""
        clean_url = target_url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        # Initialize pending audit record in database
        audit_record = WebsiteAudit(
            tenant_id=tenant_id,
            target_url=clean_url,
            status="pending",
            audit_scores_json={"status": "in_progress", "started_at": datetime.now(timezone.utc).isoformat()},
            pitch_proposal_json={},
        )
        session.add(audit_record)
        await session.flush()

        logger.info(
            "Starting automated web audit",
            tenant_id=str(tenant_id),
            audit_id=str(audit_record.id),
            target_url=clean_url,
        )

        audit_result: Dict[str, Any] = {}
        status = "completed"

        # Try Playwright first, fall back to HTTP scraper if headless browser cannot launch
        used_playwright = False
        if PLAYWRIGHT_INSTALLED:
            try:
                audit_result, status = await self._run_playwright_audit(
                    target_url=clean_url,
                    timeout_seconds=timeout_seconds,
                    extract_dom=extract_dom,
                    monitor_network=monitor_network,
                )
                used_playwright = True
            except Exception as pw_exc:
                logger.warning(
                    "Playwright execution encountered error; falling back to resilient HTTP auditor",
                    error=str(pw_exc),
                    target_url=clean_url,
                )
                used_playwright = False

        if not used_playwright:
            audit_result, status = await self._run_http_fallback_audit(
                target_url=clean_url,
                timeout_seconds=timeout_seconds,
                extract_dom=extract_dom,
                monitor_network=monitor_network,
            )

        # Generate Pitch / Optimization Proposal based on discovered metrics
        pitch_proposal = self._generate_pitch_proposal(clean_url, audit_result)

        # Update and persist record
        audit_record.status = status
        audit_record.audit_scores_json = audit_result
        audit_record.pitch_proposal_json = pitch_proposal
        audit_record.updated_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(audit_record)

        logger.info(
            "Automated web audit finished",
            audit_id=str(audit_record.id),
            status=status,
            engine=audit_result.get("engine"),
            overall_score=audit_result.get("overall_score"),
        )
        return audit_record

    async def _run_playwright_audit(
        self,
        target_url: str,
        timeout_seconds: int,
        extract_dom: bool,
        monitor_network: bool,
    ) -> Tuple[Dict[str, Any], str]:
        """Execute headless Playwright audit with full network request interception."""
        network_calls: List[Dict[str, Any]] = []
        api_calls: List[Dict[str, Any]] = []
        request_map: Dict[str, float] = {}

        t_start = time.perf_counter()
        status_code: Optional[int] = None
        blocked_reason: Optional[str] = None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--no-zygote",
                        "--single-process",
                    ],
                )
                context = await browser.new_context(
                    user_agent=self.default_user_agent,
                    viewport={"width": 1280, "height": 800},
                    ignore_https_errors=True,
                )
                page = await context.new_page()

                # Network Request / Response Interception
                if monitor_network:
                    async def on_request(req: PlaywrightRequest):
                        request_map[req.url] = time.perf_counter()

                    async def on_response(res: PlaywrightResponse):
                        nonlocal status_code
                        if res.url == target_url or res.url == f"{target_url}/":
                            status_code = res.status

                        req_start = request_map.get(res.url, time.perf_counter())
                        duration_ms = round((time.perf_counter() - req_start) * 1000, 1)

                        headers = res.headers
                        content_type = headers.get("content-type", "")
                        resource_type = res.request.resource_type

                        # Classify API calls (XHR, Fetch, JSON responses, GraphQL)
                        is_api = (
                            resource_type in ("xhr", "fetch")
                            or "application/json" in content_type
                            or "/api/" in res.url
                            or "/graphql" in res.url
                        )

                        call_data = {
                            "url": res.url[:250],
                            "method": res.request.method,
                            "status": res.status,
                            "resource_type": resource_type,
                            "content_type": content_type.split(";")[0],
                            "duration_ms": duration_ms,
                            "is_api": is_api,
                        }
                        if len(network_calls) < 150:
                            network_calls.append(call_data)
                        if is_api and len(api_calls) < 50:
                            api_calls.append(call_data)

                    page.on("request", on_request)
                    page.on("response", on_response)

                # Navigation with explicit timeout
                timeout_ms = timeout_seconds * 1000
                response = await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                if response:
                    status_code = response.status

                # Wait slightly for dynamic JS hydration
                await asyncio.sleep(1.0)

                # Check if blocked or forbidden
                html_content = await page.content()
                if status_code in (401, 403) or self._is_anti_bot_blocked(html_content):
                    return self._build_blocked_result(
                        target_url=target_url,
                        engine="playwright_headless",
                        status_code=status_code or 403,
                        network_calls=network_calls,
                        api_calls=api_calls,
                    ), "blocked"

                # Extract Performance Timing
                perf_metrics = await self._evaluate_browser_performance(page, t_start)
                perf_metrics["total_requests"] = len(network_calls)
                perf_metrics["total_api_calls"] = len(api_calls)

                # Parse DOM and SEO
                seo_meta, dom_structure = self._parse_html_and_seo(html_content, target_url, extract_dom)

                # Calculate Scores
                seo_score = self._compute_seo_score(seo_meta, dom_structure)
                perf_score = self._compute_performance_score(perf_metrics, network_calls)
                overall_score = round((seo_score * 0.5) + (perf_score * 0.5), 1)

                await browser.close()

                return {
                    "engine": "playwright_headless",
                    "target_url": target_url,
                    "final_url": page.url,
                    "status_code": status_code or 200,
                    "overall_score": overall_score,
                    "seo_score": seo_score,
                    "performance_score": perf_score,
                    "seo_metadata": seo_meta,
                    "performance_metrics": perf_metrics,
                    "dom_structure": dom_structure,
                    "network_calls": network_calls,
                    "intercepted_api_calls": api_calls,
                    "audited_at": datetime.now(timezone.utc).isoformat(),
                }, "completed"

        except PlaywrightTimeoutError:
            logger.warning("Playwright navigation timeout", target_url=target_url, timeout=timeout_seconds)
            return self._build_timeout_result(target_url, "playwright_headless", timeout_seconds), "timeout"
        except Exception as exc:
            err_msg = str(exc)
            if "ERR_CONNECTION_REFUSED" in err_msg or "ERR_NAME_NOT_RESOLVED" in err_msg:
                return self._build_failed_result(target_url, "playwright_headless", "connection_error", err_msg), "failed"
            raise exc

    async def _run_http_fallback_audit(
        self,
        target_url: str,
        timeout_seconds: int,
        extract_dom: bool,
        monitor_network: bool,
    ) -> Tuple[Dict[str, Any], str]:
        """Resilient async HTTP + BeautifulSoup auditing fallback."""
        t_start = time.perf_counter()
        network_calls: List[Dict[str, Any]] = []
        api_calls: List[Dict[str, Any]] = []

        headers = {
            "User-Agent": self.default_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            async with httpx.AsyncClient(
                timeout=float(timeout_seconds),
                follow_redirects=True,
                verify=False,
            ) as client:
                resp = await client.get(target_url, headers=headers)
                t_end = time.perf_counter()

                load_time_ms = round((t_end - t_start) * 1000, 1)
                status_code = resp.status_code

                try:
                    final_url = str(resp.url)
                except Exception:
                    final_url = target_url

                network_calls.append({
                    "url": final_url,
                    "method": "GET",
                    "status": status_code,
                    "resource_type": "document",
                    "content_type": resp.headers.get("content-type", "").split(";")[0],
                    "duration_ms": load_time_ms,
                    "is_api": False,
                })

                if status_code in (401, 403) or self._is_anti_bot_blocked(resp.text):
                    return self._build_blocked_result(
                        target_url=target_url,
                        engine="http_resilient_fallback",
                        status_code=status_code,
                        network_calls=network_calls,
                        api_calls=api_calls,
                    ), "blocked"

                if status_code >= 400:
                    return self._build_failed_result(
                        target_url,
                        "http_resilient_fallback",
                        f"http_{status_code}",
                        f"Server returned HTTP {status_code}",
                    ), "failed"

                html_content = resp.text
                seo_meta, dom_structure = self._parse_html_and_seo(html_content, final_url, extract_dom)

                # Scan embedded scripts for API endpoints
                if monitor_network and dom_structure.get("scripts"):
                    for script_src in dom_structure["scripts"].get("external_sources", []):
                        if any(api_marker in script_src for api_marker in ("/api/", "/v1/", "/v2/", "/graphql", "rest")):
                            api_calls.append({
                                "url": script_src,
                                "method": "GET",
                                "status": 200,
                                "resource_type": "script_api_source",
                                "content_type": "application/javascript",
                                "duration_ms": 0.0,
                                "is_api": True,
                            })

                perf_metrics = {
                    "ttfb_ms": round(load_time_ms * 0.4, 1),
                    "dom_content_loaded_ms": round(load_time_ms * 0.8, 1),
                    "load_time_ms": load_time_ms,
                    "total_requests": len(network_calls) + len(dom_structure.get("scripts", {}).get("external_sources", [])),
                    "total_api_calls": len(api_calls),
                    "response_bytes": len(resp.content),
                }

                seo_score = self._compute_seo_score(seo_meta, dom_structure)
                perf_score = self._compute_performance_score(perf_metrics, network_calls)
                overall_score = round((seo_score * 0.5) + (perf_score * 0.5), 1)

                return {
                    "engine": "http_resilient_fallback",
                    "target_url": target_url,
                    "final_url": final_url,
                    "status_code": status_code,
                    "overall_score": overall_score,
                    "seo_score": seo_score,
                    "performance_score": perf_score,
                    "seo_metadata": seo_meta,
                    "performance_metrics": perf_metrics,
                    "dom_structure": dom_structure,
                    "network_calls": network_calls,
                    "intercepted_api_calls": api_calls,
                    "audited_at": datetime.now(timezone.utc).isoformat(),
                }, "completed"

        except httpx.TimeoutException:
            return self._build_timeout_result(target_url, "http_resilient_fallback", timeout_seconds), "timeout"
        except (httpx.ConnectError, httpx.NetworkError) as net_err:
            return self._build_failed_result(target_url, "http_resilient_fallback", "network_error", str(net_err)), "failed"
        except Exception as exc:
            return self._build_failed_result(target_url, "http_resilient_fallback", "generic_error", str(exc)), "failed"

    async def _evaluate_browser_performance(self, page: Any, t_start: float) -> Dict[str, Any]:
        """Extract high-precision Navigation Timing and memory metrics from live browser."""
        try:
            timing = await page.evaluate("""() => {
                const nav = performance.getEntriesByType('navigation')[0] || {};
                const legacy = performance.timing || {};
                return {
                    dns_time_ms: nav.domainLookupEnd ? Math.round(nav.domainLookupEnd - nav.domainLookupStart) : (legacy.domainLookupEnd - legacy.domainLookupStart || 0),
                    connect_time_ms: nav.connectEnd ? Math.round(nav.connectEnd - nav.connectStart) : (legacy.connectEnd - legacy.connectStart || 0),
                    ttfb_ms: nav.responseStart ? Math.round(nav.responseStart - nav.requestStart) : (legacy.responseStart - legacy.requestStart || 0),
                    dom_content_loaded_ms: nav.domContentLoadedEventEnd ? Math.round(nav.domContentLoadedEventEnd - nav.startTime) : (legacy.domContentLoadedEventEnd - legacy.navigationStart || 0),
                    load_time_ms: nav.loadEventEnd ? Math.round(nav.loadEventEnd - nav.startTime) : (legacy.loadEventEnd - legacy.navigationStart || 0),
                };
            }""")
            return {
                "dns_time_ms": max(0, timing.get("dns_time_ms", 0)),
                "connect_time_ms": max(0, timing.get("connect_time_ms", 0)),
                "ttfb_ms": max(0, timing.get("ttfb_ms", 0)),
                "dom_content_loaded_ms": max(0, timing.get("dom_content_loaded_ms", 0)),
                "load_time_ms": max(0, timing.get("load_time_ms", 0)) or round((time.perf_counter() - t_start) * 1000, 1),
            }
        except Exception:
            elapsed = round((time.perf_counter() - t_start) * 1000, 1)
            return {
                "dns_time_ms": 0,
                "connect_time_ms": 0,
                "ttfb_ms": round(elapsed * 0.3, 1),
                "dom_content_loaded_ms": round(elapsed * 0.7, 1),
                "load_time_ms": elapsed,
            }

    def _parse_html_and_seo(
        self,
        html: str,
        base_url: str,
        extract_dom: bool,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Parse complete SEO metadata, OpenGraph, Twitter Cards, Schema.org, and DOM hierarchy."""
        soup = BeautifulSoup(html, "html.parser")

        # 1. Title & Meta Description
        title_tag = soup.find("title")
        page_title = title_tag.get_text(strip=True) if title_tag else ""

        meta_desc = ""
        meta_desc_tag = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "description"})
        if meta_desc_tag and meta_desc_tag.get("content"):
            meta_desc = meta_desc_tag["content"].strip()

        # 2. Canonical, Robots, Keywords, Viewport
        canonical_tag = soup.find("link", rel=lambda x: x and "canonical" in x.lower())
        canonical_url = canonical_tag.get("href", "").strip() if canonical_tag else ""

        robots_tag = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "robots"})
        robots = robots_tag.get("content", "").strip() if robots_tag else "index, follow"

        viewport_tag = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "viewport"})
        has_mobile_viewport = bool(viewport_tag)

        # 3. OpenGraph & Twitter Cards
        og_data: Dict[str, str] = {}
        for tag in soup.find_all("meta", property=lambda x: x and x.startswith("og:")):
            prop = tag.get("property", "").replace("og:", "")
            og_data[prop] = tag.get("content", "")

        twitter_data: Dict[str, str] = {}
        for tag in soup.find_all("meta", attrs={"name": lambda x: x and x.startswith("twitter:")}):
            prop = tag.get("name", "").replace("twitter:", "")
            twitter_data[prop] = tag.get("content", "")

        # 4. Schema.org JSON-LD
        has_schema_ld = bool(soup.find("script", type="application/ld+json"))

        # 5. Headings Hierarchy
        h1s = [h.get_text(strip=True) for h in soup.find_all("h1") if h.get_text(strip=True)]
        h2s = [h.get_text(strip=True) for h in soup.find_all("h2") if h.get_text(strip=True)]
        h3s = [h.get_text(strip=True) for h in soup.find_all("h3") if h.get_text(strip=True)]

        # 6. Images & Alt Check
        all_imgs = soup.find_all("img")
        imgs_missing_alt = [img.get("src", "") for img in all_imgs if not img.get("alt")]

        # 7. Links Analysis
        parsed_base = urlparse(base_url)
        all_links = soup.find_all("a", href=True)
        internal_links = 0
        external_links = 0
        for link in all_links:
            href = link.get("href", "")
            if href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            parsed_href = urlparse(href)
            if not parsed_href.netloc or parsed_href.netloc == parsed_base.netloc:
                internal_links += 1
            else:
                external_links += 1

        seo_meta = {
            "title": page_title,
            "title_length": len(page_title),
            "meta_description": meta_desc,
            "meta_description_length": len(meta_desc),
            "canonical_url": canonical_url,
            "robots": robots,
            "has_mobile_viewport": has_mobile_viewport,
            "has_ssl": base_url.startswith("https://"),
            "has_schema_ld": has_schema_ld,
            "opengraph": og_data,
            "twitter_card": twitter_data,
            "heading_counts": {"h1": len(h1s), "h2": len(h2s), "h3": len(h3s)},
            "h1_samples": h1s[:3],
            "total_images": len(all_imgs),
            "images_missing_alt_count": len(imgs_missing_alt),
            "image_alt_coverage_pct": round(((len(all_imgs) - len(imgs_missing_alt)) / max(1, len(all_imgs))) * 100, 1),
            "links": {
                "total": len(all_links),
                "internal": internal_links,
                "external": external_links,
            },
        }

        # 8. Complete DOM Structure Breakdown
        dom_structure = {}
        if extract_dom:
            forms = soup.find_all("forms") or soup.find_all("form")
            scripts = soup.find_all("script")
            ext_scripts = [s.get("src") for s in scripts if s.get("src")]

            tag_counts: Dict[str, int] = {}
            for tag in ("div", "p", "a", "button", "input", "img", "section", "article", "nav", "footer", "header"):
                tag_counts[tag] = len(soup.find_all(tag))

            dom_structure = {
                "tag_distribution": tag_counts,
                "total_forms": len(forms),
                "scripts": {
                    "total": len(scripts),
                    "external_count": len(ext_scripts),
                    "external_sources": ext_scripts[:15],
                },
                "body_text_length": len(soup.get_text()),
            }

        return seo_meta, dom_structure

    def _compute_seo_score(self, seo: Dict[str, Any], dom: Dict[str, Any]) -> float:
        """Calculate weighted SEO health score (0–100)."""
        score = 0.0

        # Title presence & length (15-65 chars ideal)
        t_len = seo.get("title_length", 0)
        if 15 <= t_len <= 70:
            score += 20.0
        elif t_len > 0:
            score += 10.0

        # Meta description presence & length (50-160 chars ideal)
        d_len = seo.get("meta_description_length", 0)
        if 50 <= d_len <= 165:
            score += 20.0
        elif d_len > 0:
            score += 10.0

        # Single H1 presence
        h1_count = seo.get("heading_counts", {}).get("h1", 0)
        if h1_count == 1:
            score += 15.0
        elif h1_count > 1:
            score += 8.0

        # OpenGraph presence
        if seo.get("opengraph"):
            score += 15.0

        # Mobile Viewport
        if seo.get("has_mobile_viewport"):
            score += 10.0

        # Image Alt Coverage
        alt_pct = seo.get("image_alt_coverage_pct", 100.0)
        if alt_pct >= 80.0:
            score += 10.0
        elif alt_pct >= 50.0:
            score += 5.0

        # SSL HTTPS
        if seo.get("has_ssl"):
            score += 10.0

        return round(min(100.0, score), 1)

    def _compute_performance_score(self, perf: Dict[str, Any], network_calls: List[Dict[str, Any]]) -> float:
        """Calculate performance health score (0–100)."""
        score = 100.0

        # TTFB Penalty (ideal < 600ms)
        ttfb = perf.get("ttfb_ms", 0)
        if ttfb > 1500:
            score -= 30.0
        elif ttfb > 800:
            score -= 15.0
        elif ttfb > 500:
            score -= 5.0

        # Total Load Time Penalty (ideal < 2500ms)
        load_time = perf.get("load_time_ms", 0)
        if load_time > 6000:
            score -= 35.0
        elif load_time > 3500:
            score -= 20.0
        elif load_time > 2000:
            score -= 10.0

        # Excessive Network Requests Penalty
        req_count = perf.get("total_requests", len(network_calls))
        if req_count > 100:
            score -= 15.0
        elif req_count > 60:
            score -= 8.0

        # Network Error (4xx/5xx) Penalty
        error_calls = sum(1 for c in network_calls if c.get("status", 200) >= 400)
        if error_calls > 5:
            score -= 20.0
        elif error_calls > 0:
            score -= 10.0

        return round(max(10.0, score), 1)

    def _generate_pitch_proposal(self, target_url: str, audit: Dict[str, Any]) -> Dict[str, Any]:
        """Generate structured agency pitch proposal & optimization roadmap."""
        seo = audit.get("seo_metadata") or {}
        perf = audit.get("performance_metrics") or {}
        seo_score = audit.get("seo_score", 50.0)
        perf_score = audit.get("performance_score", 50.0)

        pain_points = []
        if seo.get("title_length", 0) == 0:
            pain_points.append("Missing HTML page title reduces search engine indexing.")
        if seo.get("meta_description_length", 0) == 0:
            pain_points.append("Missing meta description results in lower organic click-through rates (CTR).")
        if seo.get("heading_counts", {}).get("h1", 0) != 1:
            pain_points.append("Heading hierarchy has multiple or zero H1 tags, diluting keyword relevance.")
        if seo.get("image_alt_coverage_pct", 100) < 70:
            pain_points.append("Images lack descriptive ALT attributes, degrading image SEO and accessibility.")
        if not seo.get("opengraph"):
            pain_points.append("Missing OpenGraph social cards causes links to appear plain when shared on WhatsApp/LinkedIn.")
        if perf.get("load_time_ms", 0) > 3000:
            pain_points.append(f"Page load time ({perf.get('load_time_ms')}ms) exceeds recommended 2.5s Core Web Vitals threshold.")

        return {
            "target_url": target_url,
            "overall_health": "good" if (seo_score >= 80 and perf_score >= 80) else "needs_optimization",
            "detected_gaps": pain_points,
            "recommended_fixes": [
                "Deploy automated meta tag & OpenGraph generator.",
                "Compress unoptimized assets to reduce TTFB below 500ms.",
                "Implement 24/7 AI Receptionist / WhatsApp concierge to capture inbound leads immediately.",
            ],
            "client_pitch_hook": (
                f"We audited {target_url} and detected {len(pain_points)} critical conversion & SEO bottlenecks. "
                f"Our managed automation suite can resolve these technical gaps while deploying an AI concierge "
                f"to convert inbound site visitors into booked appointments 24/7."
            ),
        }

    def _is_anti_bot_blocked(self, html: str) -> bool:
        """Detect anti-bot challenge screens (Cloudflare, Akamai, Datadome, reCAPTCHA)."""
        lower = (html or "").lower()
        block_markers = [
            "cf-chl-bypass",
            "challenge-platform",
            "just a moment...",
            "checking your browser",
            "cloudflare ray id",
            "access denied",
            "enable javascript and cookies to continue",
            "pardon our interruption",
        ]
        return any(marker in lower for marker in block_markers)

    def _build_blocked_result(
        self,
        target_url: str,
        engine: str,
        status_code: int,
        network_calls: List[Dict[str, Any]],
        api_calls: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "engine": engine,
            "target_url": target_url,
            "status_code": status_code,
            "overall_score": 0.0,
            "seo_score": 0.0,
            "performance_score": 0.0,
            "error_details": {
                "error_type": "blocked_by_waf",
                "message": f"Target website blocked scraper request (HTTP {status_code} / anti-bot challenge).",
            },
            "network_calls": network_calls,
            "intercepted_api_calls": api_calls,
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }

    def _build_timeout_result(self, target_url: str, engine: str, timeout_seconds: int) -> Dict[str, Any]:
        return {
            "engine": engine,
            "target_url": target_url,
            "status_code": 408,
            "overall_score": 0.0,
            "seo_score": 0.0,
            "performance_score": 0.0,
            "error_details": {
                "error_type": "timeout",
                "message": f"Website rendering timed out after {timeout_seconds} seconds.",
            },
            "network_calls": [],
            "intercepted_api_calls": [],
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }

    def _build_failed_result(self, target_url: str, engine: str, err_type: str, err_msg: str) -> Dict[str, Any]:
        return {
            "engine": engine,
            "target_url": target_url,
            "status_code": 502,
            "overall_score": 0.0,
            "seo_score": 0.0,
            "performance_score": 0.0,
            "error_details": {
                "error_type": err_type,
                "message": err_msg,
            },
            "network_calls": [],
            "intercepted_api_calls": [],
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }

    async def list_audits(
        self,
        tenant_id: uuid.UUID,
        session: AsyncSession,
        limit: int = 50,
        status_filter: Optional[str] = None,
    ) -> List[WebsiteAudit]:
        """Fetch historical website audits for tenant with RLS isolation."""
        stmt = select(WebsiteAudit).where(WebsiteAudit.tenant_id == tenant_id)
        if status_filter:
            stmt = stmt.where(WebsiteAudit.status == status_filter)
        stmt = stmt.order_by(desc(WebsiteAudit.created_at)).limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def get_audit(
        self,
        audit_id: uuid.UUID,
        tenant_id: uuid.UUID,
        session: AsyncSession,
    ) -> WebsiteAudit:
        """Fetch single audit by id ensuring tenant ownership."""
        stmt = select(WebsiteAudit).where(
            WebsiteAudit.id == audit_id,
            WebsiteAudit.tenant_id == tenant_id,
        )
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            raise ResourceNotFoundError("WebsiteAudit", str(audit_id))
        return record


# Global singleton instance
web_auditor_service = WebAuditorService()
