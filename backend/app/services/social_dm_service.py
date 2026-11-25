"""Native Meta (Instagram & Facebook) Comment-to-DM Webhook & Keyword Automation Service.

Replaces external tools like ManyChat natively in FastAPI + Python asyncio:
1. Enforces `X-Hub-Signature-256` HMAC-SHA256 verification on Meta webhook callbacks.
2. Evaluates tenant-isolated keyword rules (`instagram`, `facebook`, or `both`, optional `post_id`).
3. Generates RAG-grounded DM replies embedding Cal.com booking URLs via `route_and_execute_ai_task`.
4. Creates/links CRM `Lead` records and logs DMs into the Unified CRM Inbox (`OmnichannelSession`).
"""

import hashlib
import hmac
import uuid
from typing import Any, Dict, List, Optional

import httpx
from app.config import settings
from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.core.logging import logger
from app.core.security import decrypt_secret
from app.database.models.automation import AuditLog, Integration
from app.database.models.marketing import Lead
from app.database.models.receptionist import ReceptionistConfig
from app.database.models.upsells import SocialCommentRule, SocialDmLog
from app.integrations.ai_providers.router import route_and_execute_ai_task
from app.services.inbox_service import inbox_service
from app.services.rag_service import rag_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class SocialDmService:
    """In-house IG & FB Comment-to-DM rule engine and Meta Graph API webhook handler."""

    def __init__(self) -> None:
        self.graph_api_url = "https://graph.facebook.com/v21.0"

    def verify_webhook_challenge(
        self,
        hub_mode: Optional[str],
        hub_verify_token: Optional[str],
        hub_challenge: Optional[str],
    ) -> str:
        if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
            return hub_challenge or ""
        raise TaloxException(
            message="Meta webhook verify token mismatch",
            code="META_VERIFY_TOKEN_MISMATCH",
            status_code=403,
        )

    def verify_meta_signature(
        self,
        payload_bytes: bytes,
        signature_header: Optional[str],
    ) -> bool:
        app_secret = (settings.meta_app_secret or settings.whatsapp_app_secret or "").strip()
        if not app_secret:
            return settings.app_env in ("development", "test")
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = hmac.new(app_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_header[7:].strip().lower())

    @staticmethod
    def _serialize_rule(rule: SocialCommentRule) -> Dict[str, Any]:
        return {
            "id": str(rule.id),
            "tenant_id": str(rule.tenant_id),
            "platform": rule.platform,
            "keyword": rule.keyword,
            "post_id": rule.post_id,
            "dm_template": rule.dm_template,
            "reply_comment_template": rule.reply_comment_template,
            "booking_url": rule.booking_url,
            "is_active": bool(rule.is_active),
            "trigger_count": int(rule.trigger_count or 0),
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
        }

    @staticmethod
    def _serialize_log(row: SocialDmLog) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "rule_id": str(row.rule_id) if row.rule_id else None,
            "lead_id": str(row.lead_id) if row.lead_id else None,
            "platform": row.platform,
            "post_id": row.post_id,
            "external_comment_id": row.external_comment_id,
            "commenter_id": row.commenter_id,
            "commenter_name": row.commenter_name,
            "comment_text": row.comment_text,
            "matched_keyword": row.matched_keyword,
            "dm_text": row.dm_text,
            "booking_link": row.booking_link,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def list_rules(self, session: AsyncSession, tenant_id: uuid.UUID) -> List[Dict[str, Any]]:
        res = await session.execute(
            select(SocialCommentRule)
            .where(SocialCommentRule.tenant_id == tenant_id)
            .order_by(SocialCommentRule.created_at.desc())
        )
        return [self._serialize_rule(r) for r in res.scalars().all()]

    async def create_rule(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        platform: str,
        keyword: str,
        dm_template: str,
        reply_comment_template: Optional[str] = None,
        post_id: Optional[str] = None,
        booking_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        clean_plat = platform.strip().lower()
        if clean_plat not in ("instagram", "facebook", "both"):
            raise TaloxException(message="Platform must be instagram, facebook, or both", code="INVALID_PLATFORM", status_code=400)
        rule = SocialCommentRule(
            tenant_id=tenant_id,
            platform=clean_plat,
            keyword=keyword.strip(),
            post_id=post_id.strip() if post_id else None,
            dm_template=dm_template.strip(),
            reply_comment_template=reply_comment_template.strip() if reply_comment_template else None,
            booking_url=booking_url.strip() if booking_url else None,
            is_active=True,
        )
        session.add(rule)
        await session.flush()
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=user_id,
                actor_type="user",
                action="growth.comment_dm_rule.created",
                resource_type="social_comment_rule",
                resource_id=rule.id,
                metadata_={"platform": clean_plat, "keyword": rule.keyword},
            )
        )
        await session.commit()
        await session.refresh(rule)
        return self._serialize_rule(rule)

    async def update_rule(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        rule_id: uuid.UUID,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        res = await session.execute(
            select(SocialCommentRule).where(
                SocialCommentRule.id == rule_id,
                SocialCommentRule.tenant_id == tenant_id,
            )
        )
        rule = res.scalar_one_or_none()
        if not rule:
            raise ResourceNotFoundError("SocialCommentRule", str(rule_id))
        for field in ("platform", "keyword", "post_id", "dm_template", "reply_comment_template", "booking_url", "is_active"):
            if field in updates and updates[field] is not None:
                setattr(rule, field, updates[field])
        await session.commit()
        await session.refresh(rule)
        return self._serialize_rule(rule)

    async def delete_rule(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        rule_id: uuid.UUID,
    ) -> None:
        res = await session.execute(
            select(SocialCommentRule).where(
                SocialCommentRule.id == rule_id,
                SocialCommentRule.tenant_id == tenant_id,
            )
        )
        rule = res.scalar_one_or_none()
        if not rule:
            raise ResourceNotFoundError("SocialCommentRule", str(rule_id))
        await session.delete(rule)
        await session.commit()

    async def list_dm_logs(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        res = await session.execute(
            select(SocialDmLog)
            .where(SocialDmLog.tenant_id == tenant_id)
            .order_by(SocialDmLog.created_at.desc())
            .limit(limit)
        )
        return [self._serialize_log(r) for r in res.scalars().all()]

    async def _resolve_meta_credentials(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Dict[str, Optional[str]]:
        res = await session.execute(
            select(Integration).where(
                Integration.tenant_id == tenant_id,
                Integration.provider == "meta_social",
                Integration.status == "connected",
            ).limit(1)
        )
        integ = res.scalar_one_or_none()
        if not integ:
            return {"access_token": None, "page_id": None, "ig_account_id": None}
        cfg = dict(integ.configuration or {})
        raw_tok = cfg.get("access_token") or cfg.get("api_key") or ""
        return {
            "access_token": decrypt_secret(str(raw_tok)) if raw_tok else None,
            "page_id": str(cfg.get("page_id") or integ.external_account_id or "").strip() or None,
            "ig_account_id": str(cfg.get("ig_account_id") or "").strip() or None,
        }

    async def process_comment_event(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        platform: str,
        comment_text: str,
        commenter_name: str = "Social Commenter",
        commenter_id: Optional[str] = None,
        comment_id: Optional[str] = None,
        post_id: Optional[str] = None,
        dispatch_live: bool = False,
    ) -> Dict[str, Any]:
        clean_plat = platform.strip().lower()
        clean_text = (comment_text or "").strip()
        if not clean_text:
            return {"processed": False, "reason": "empty_comment"}

        if comment_id:
            dup_res = await session.execute(
                select(SocialDmLog).where(
                    SocialDmLog.tenant_id == tenant_id,
                    SocialDmLog.external_comment_id == str(comment_id),
                ).limit(1)
            )
            existing_log = dup_res.scalar_one_or_none()
            if existing_log:
                return {"processed": True, "idempotent": True, "log": self._serialize_log(existing_log)}

        rules_res = await session.execute(
            select(SocialCommentRule)
            .where(SocialCommentRule.tenant_id == tenant_id, SocialCommentRule.is_active.is_(True))
            .order_by(SocialCommentRule.created_at.asc())
        )
        rules = rules_res.scalars().all()
        lower_text = clean_text.lower()

        matched_rule: Optional[SocialCommentRule] = None
        wildcard_rule: Optional[SocialCommentRule] = None
        for r in rules:
            if r.platform not in (clean_plat, "both"):
                continue
            if r.post_id and post_id and r.post_id != post_id:
                continue
            kw = r.keyword.strip().lower()
            if kw == "*":
                if wildcard_rule is None:
                    wildcard_rule = r
            elif kw and kw in lower_text:
                matched_rule = r
                break

        chosen_rule = matched_rule or wildcard_rule
        if not chosen_rule:
            return {"processed": False, "reason": "no_matching_keyword_rule"}

        # Resolve booking URL: rule -> tenant receptionist Cal.com -> platform default
        cfg_res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id).limit(1)
        )
        recep_cfg = cfg_res.scalar_one_or_none()
        booking_link = (
            chosen_rule.booking_url
            or (recep_cfg.calcom_booking_url if recep_cfg else None)
            or settings.calcom_default_booking_url
        )

        rag_matches = await rag_service.search_knowledge(session, tenant_id, clean_text, top_k=2)
        rag_note = f"\nVerified business facts:\n{rag_matches[0]['content'][:260]}" if rag_matches else ""

        prompt = (
            f"Write a friendly, concise {clean_plat} DM reply to {commenter_name} who commented: '{clean_text}'.\n"
            f"Rule template: {chosen_rule.dm_template}\n"
            f"Cal.com booking link: {booking_link or 'Ask them for their preferred time'}{rag_note}"
        )
        ai_res = await route_and_execute_ai_task(
            task_type="social_dm_reply",
            prompt=prompt,
            tenant_id=str(tenant_id),
        )
        if ai_res.success and ai_res.content and "[Mock AI]" not in ai_res.content:
            dm_text = ai_res.content.strip()
        else:
            dm_text = chosen_rule.dm_template.replace("{{name}}", commenter_name).replace("{{booking_url}}", booking_link or "")
        if booking_link and booking_link not in dm_text:
            dm_text = f"{dm_text}\nBook directly here: {booking_link}"

        dm_status = "sandbox_sent"
        if dispatch_live and settings.app_env != "test":
            meta_creds = await self._resolve_meta_credentials(session, tenant_id)
            token = meta_creds.get("access_token")
            page_id = meta_creds.get("page_id")
            if token and page_id and not token.startswith("meta_mock_"):
                try:
                    async with httpx.AsyncClient(timeout=12.0) as client:
                        if clean_plat == "instagram" and comment_id:
                            recipient = {"comment_id": str(comment_id)}
                        elif commenter_id:
                            recipient = {"id": str(commenter_id)}
                        elif comment_id:
                            recipient = {"comment_id": str(comment_id)}
                        else:
                            recipient = None
                        if recipient:
                            resp = await client.post(
                                f"{self.graph_api_url}/{page_id}/messages",
                                headers={"Authorization": f"Bearer {token}"},
                                json={"recipient": recipient, "message": {"text": dm_text[:950]}},
                            )
                            if resp.status_code in (200, 201):
                                dm_status = "sent_live"
                            else:
                                logger.warning("Meta DM Graph API non-200", status_code=resp.status_code)
                except Exception as exc:
                    logger.warning("Meta Graph DM send failed; kept fallback log", error=str(exc))

        # Upsert CRM Lead + log inside Unified CRM Inbox
        ext_user = commenter_id or f"social:{clean_plat}:{commenter_name}"
        l_res = await session.execute(
            select(Lead).where(Lead.tenant_id == tenant_id, Lead.name == commenter_name, Lead.source == f"{clean_plat}_comment").limit(1)
        )
        lead = l_res.scalar_one_or_none()
        if not lead:
            lead = Lead(
                tenant_id=tenant_id,
                name=commenter_name or f"{clean_plat.title()} User",
                source=f"{clean_plat}_comment",
                status="qualified",
                qualification_score=78,
                metadata_={
                    "platform": clean_plat,
                    "comment_text": clean_text,
                    "matched_keyword": chosen_rule.keyword,
                    "commenter_id": commenter_id,
                    "booking_link": booking_link,
                },
            )
            session.add(lead)
            await session.flush()

        chat_sess = await inbox_service.get_or_create_session(
            session=session,
            tenant_id=tenant_id,
            channel=clean_plat,
            external_user_id=str(ext_user),
            contact_name=commenter_name,
            lead_id=lead.id,
        )
        await inbox_service.record_message(
            session=session,
            tenant_id=tenant_id,
            chat_session=chat_sess,
            direction="inbound",
            sender_id=str(ext_user),
            content=f"[Comment] {clean_text}",
            message_id=comment_id,
        )
        await inbox_service.record_message(
            session=session,
            tenant_id=tenant_id,
            chat_session=chat_sess,
            direction="outbound",
            sender_id="ai_social_dm",
            content=dm_text,
        )

        chosen_rule.trigger_count = int(chosen_rule.trigger_count or 0) + 1
        dm_log = SocialDmLog(
            tenant_id=tenant_id,
            rule_id=chosen_rule.id,
            lead_id=lead.id,
            platform=clean_plat,
            post_id=post_id,
            external_comment_id=str(comment_id) if comment_id else None,
            commenter_id=str(commenter_id) if commenter_id else None,
            commenter_name=commenter_name,
            comment_text=clean_text,
            matched_keyword=chosen_rule.keyword,
            dm_text=dm_text,
            booking_link=booking_link,
            status=dm_status,
        )
        session.add(dm_log)
        await session.flush()

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_type="system",
                action="growth.comment_dm.sent",
                resource_type="social_dm_log",
                resource_id=dm_log.id,
                metadata_={"platform": clean_plat, "keyword": chosen_rule.keyword, "status": dm_status},
            )
        )
        await session.commit()
        await session.refresh(dm_log)
        return {"processed": True, "idempotent": False, "log": self._serialize_log(dm_log)}

    async def handle_meta_webhook_payload(
        self,
        session: AsyncSession,
        payload: Dict[str, Any],
        fallback_tenant_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        obj_type = str(payload.get("object") or "").lower()
        entries = payload.get("entry") or []
        results: List[Dict[str, Any]] = []

        # Preload connected meta_social integrations once for entry routing
        integ_rows = (
            await session.execute(
                select(Integration).where(
                    Integration.provider == "meta_social",
                    Integration.status == "connected",
                )
            )
        ).scalars().all()

        for entry in entries:
            entry_id = str(entry.get("id") or "").strip()
            matched_tenant: Optional[uuid.UUID] = None
            for row in integ_rows:
                cfg = dict(row.configuration or {})
                candidates = {
                    str(row.external_account_id or "").strip(),
                    str(cfg.get("page_id") or "").strip(),
                    str(cfg.get("ig_account_id") or "").strip(),
                }
                if entry_id and entry_id in candidates:
                    matched_tenant = row.tenant_id
                    break
            if not matched_tenant and fallback_tenant_id and settings.app_env in ("development", "test"):
                matched_tenant = fallback_tenant_id
            if not matched_tenant:
                logger.warning("Meta comment webhook skipped: unmatched page/ig entry ID", entry_id=entry_id)
                continue

            for ch in entry.get("changes") or []:
                field = str(ch.get("field") or "").lower()
                val = ch.get("value") or {}

                # Instagram Comment webhook (`object=instagram`, `field=comments`)
                if obj_type == "instagram" or field == "comments":
                    from_obj = val.get("from") or {}
                    c_id = str(val.get("id") or "")
                    c_text = str(val.get("text") or "")
                    c_user_id = str(from_obj.get("id") or "") or None
                    c_name = str(from_obj.get("username") or from_obj.get("name") or "Instagram User")
                    m_id = str((val.get("media") or {}).get("id") or val.get("media_id") or "") or None
                    res = await self.process_comment_event(
                        session=session,
                        tenant_id=matched_tenant,
                        platform="instagram",
                        comment_text=c_text,
                        commenter_name=c_name,
                        commenter_id=c_user_id,
                        comment_id=c_id or None,
                        post_id=m_id,
                        dispatch_live=True,
                    )
                    results.append(res)
                # Facebook Page Feed Comment webhook (`object=page`, `field=feed`, `item=comment`)
                elif (obj_type == "page" or field == "feed") and str(val.get("item") or "").lower() == "comment":
                    verb = str(val.get("verb") or "add").lower()
                    if verb not in ("add", "edited"):
                        continue
                    from_obj = val.get("from") or {}
                    c_id = str(val.get("comment_id") or "")
                    c_text = str(val.get("message") or "")
                    c_user_id = str(from_obj.get("id") or "") or None
                    c_name = str(from_obj.get("name") or "Facebook User")
                    p_id = str(val.get("post_id") or "") or None
                    res = await self.process_comment_event(
                        session=session,
                        tenant_id=matched_tenant,
                        platform="facebook",
                        comment_text=c_text,
                        commenter_name=c_name,
                        commenter_id=c_user_id,
                        comment_id=c_id or None,
                        post_id=p_id,
                        dispatch_live=True,
                    )
                    results.append(res)

        return {"processed": len(results), "results": results}


social_dm_service = SocialDmService()
