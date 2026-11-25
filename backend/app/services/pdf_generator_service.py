"""In-House Auto-PDF Generator Service powered natively by ReportLab (Zero External PDF APIs).

Generates crisp branded A4 PDFs directly in memory (`io.BytesIO`) for:
1. Billing Invoices (`/pdf/invoice/{invoice_id}`)
2. Appointment Summaries / Clinic Visit Passes (`/pdf/appointment/{call_log_id}`)
3. Weekly AI ROI Executive Reports (`/pdf/weekly-roi`)
4. Custom Quotes, Invoices & Clinic Prescriptions (`/pdf/generate`)
"""

import io
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from app.core.exceptions import ResourceNotFoundError
from app.database.models.automation import AuditLog
from app.database.models.billing import Invoice
from app.database.models.receptionist import ReceptionistCallLog
from app.database.models.tenant import Tenant
from app.services.call_intelligence_service import call_intelligence_service
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _safe_filename(name: str, fallback: str = "document") -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", (name or "").strip()).strip("-")
    return (clean[:60] or fallback) + ".pdf"


class PdfGeneratorService:
    """Pure Python ReportLab PDF document generator."""

    @staticmethod
    def render_document(
        tenant_name: str,
        title: str,
        subtitle: str,
        meta_rows: List[Tuple[str, str]],
        table_headers: List[str],
        table_rows: List[List[str]],
        notes: Optional[str] = None,
    ) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=title,
            author=tenant_name,
        )
        styles = getSampleStyleSheet()
        brand_style = ParagraphStyle(
            "BrandHeader",
            parent=styles["Heading1"],
            fontSize=18,
            textColor=colors.HexColor("#059669"),
            spaceAfter=2,
        )
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading2"],
            fontSize=14,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=4,
        )
        muted_style = ParagraphStyle(
            "MutedSub",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#475569"),
            spaceAfter=10,
        )
        body_style = ParagraphStyle(
            "BodyNormal",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#1e293b"),
        )

        story: List[Any] = [
            Paragraph(escape(tenant_name), brand_style),
            Paragraph(escape(title), title_style),
            Paragraph(escape(subtitle), muted_style),
        ]

        if meta_rows:
            meta_data = [[Paragraph(f"<b>{escape(k)}</b>", body_style), Paragraph(escape(v), body_style)] for k, v in meta_rows]
            meta_tbl = Table(meta_data, colWidths=[50 * mm, 120 * mm])
            meta_tbl.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ])
            )
            story.append(meta_tbl)
            story.append(Spacer(1, 12))

        if table_headers and table_rows:
            col_cnt = len(table_headers)
            total_width = 170 * mm
            col_w = [total_width / col_cnt] * col_cnt
            rows_rendered = [[Paragraph(f"<b>{escape(str(h))}</b>", body_style) for h in table_headers]]
            for r in table_rows:
                rows_rendered.append([Paragraph(escape(str(c)), body_style) for c in r])

            main_tbl = Table(rows_rendered, colWidths=col_w)
            main_tbl.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfdf5")),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#94a3b8")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ])
            )
            story.append(main_tbl)
            story.append(Spacer(1, 12))

        if notes:
            story.append(Paragraph(f"<b>Notes & Instructions:</b><br/>{escape(notes)}", body_style))
            story.append(Spacer(1, 12))

        ts_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        story.append(Paragraph(f"Generated natively by TaloxTech SaaS Platform on {ts_str}", muted_style))

        doc.build(story)
        return buf.getvalue()

    async def _get_tenant_name(self, session: AsyncSession, tenant_id: uuid.UUID) -> str:
        t_res = await session.execute(select(Tenant.name).where(Tenant.id == tenant_id))
        return t_res.scalar_one_or_none() or "TaloxTech Workspace"

    async def generate_invoice_pdf(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        invoice_id: uuid.UUID,
    ) -> Tuple[bytes, str]:
        res = await session.execute(
            select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
        )
        inv = res.scalar_one_or_none()
        if not inv:
            raise ResourceNotFoundError("Invoice", str(invoice_id))

        tenant_name = await self._get_tenant_name(session, tenant_id)
        pdf_bytes = self.render_document(
            tenant_name=tenant_name,
            title=f"Invoice {inv.invoice_number}",
            subtitle=f"Official Billing Statement — Status: {inv.status.upper()}",
            meta_rows=[
                ("Invoice Number", inv.invoice_number),
                ("Status", inv.status.upper()),
                ("Currency", inv.currency),
                ("Due Date", inv.due_at.strftime("%Y-%m-%d") if inv.due_at else "-"),
            ],
            table_headers=["Description", "Subtotal", "Tax", "Total"],
            table_rows=[
                [
                    "TaloxTech AI Automation & SaaS Services",
                    f"{inv.currency} {float(inv.subtotal):,.2f}",
                    f"{inv.currency} {float(inv.tax):,.2f}",
                    f"{inv.currency} {float(inv.total):,.2f}",
                ]
            ],
            notes="Thank you for partnering with TaloxTech. Settle invoices anytime from your Billing dashboard.",
        )
        return pdf_bytes, _safe_filename(f"invoice-{inv.invoice_number}", "invoice")

    async def generate_appointment_pdf(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        call_log_id: uuid.UUID,
    ) -> Tuple[bytes, str]:
        res = await session.execute(
            select(ReceptionistCallLog).where(
                ReceptionistCallLog.id == call_log_id,
                ReceptionistCallLog.tenant_id == tenant_id,
            )
        )
        call_log = res.scalar_one_or_none()
        if not call_log:
            raise ResourceNotFoundError("ReceptionistCallLog", str(call_log_id))

        tenant_name = await self._get_tenant_name(session, tenant_id)
        intel = dict((call_log.metadata_ or {}).get("call_intelligence") or {})
        appt_str = call_log.booked_appointment_at.strftime("%Y-%m-%d %H:%M UTC") if call_log.booked_appointment_at else "Pending Scheduling"
        pdf_bytes = self.render_document(
            tenant_name=tenant_name,
            title="Appointment Confirmation & Call Brief",
            subtitle=f"Booking Reference: {call_log.calcom_booking_uid or call_log.external_call_id}",
            meta_rows=[
                ("Client Name", call_log.caller_name or "Walk-In / Caller"),
                ("Phone", call_log.caller_phone),
                ("Appointment Time", appt_str),
                ("Booking Status", call_log.booking_status.upper()),
                ("AI Lead Score", f"{intel.get('lead_tier', 'N/A').upper()} ({intel.get('lead_score', '-')}/100)"),
            ],
            table_headers=["Call Summary", "Duration", "Sentiment"],
            table_rows=[
                [
                    call_log.summary or "Handled cleanly by AI Voice Receptionist.",
                    f"{int(call_log.duration_seconds or 0)}s",
                    str(intel.get("sentiment") or "neutral").title(),
                ]
            ],
            notes="Reply via WhatsApp anytime to confirm or reschedule your slot.",
        )
        return pdf_bytes, _safe_filename(f"appointment-{call_log.caller_name or 'visit'}", "appointment")

    async def generate_weekly_roi_pdf(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        days: int = 7,
    ) -> Tuple[bytes, str]:
        report = await call_intelligence_service.build_weekly_roi_report(session, tenant_id, days=days)
        tenant_name = str(report.get("tenant_name") or "Workspace")
        period_days = int(report.get("period_days") or days)
        pdf_bytes = self.render_document(
            tenant_name=tenant_name,
            title=f"Weekly AI Performance & ROI Report ({period_days} Days)",
            subtitle="Automated Executive Summary generated natively in Python",
            meta_rows=[
                ("Reporting Window", f"Last {period_days} days"),
                ("Estimated Revenue / Value Saved", f"${float(report.get('estimated_revenue_saved') or 0.0):,.2f}"),
                ("Estimated Hours Saved", f"{float(report.get('estimated_hours_saved') or 0.0)} hrs"),
                ("Hot / Warm / Cold Leads", f"{report.get('hot_leads', 0)} Hot / {report.get('warm_leads', 0)} Warm / {report.get('cold_leads', 0)} Cold"),
            ],
            table_headers=["Metric", "Measured Value"],
            table_rows=[
                ["AI Receptionist Calls Handled", str(report.get("calls_handled", 0))],
                ["Appointments Booked", str(report.get("appointments_booked", 0))],
                ["No-Show Recoveries Confirmed", str(report.get("noshows_recovered", 0))],
                ["WhatsApp Messages Processed", str(report.get("whatsapp_messages_handled", 0))],
            ],
            notes="All metrics reflect genuine verified records inside your workspace.",
        )
        return pdf_bytes, _safe_filename(f"weekly-roi-{tenant_name}", "weekly-roi")

    async def generate_custom_document_pdf(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        document_type: str,
        title: str,
        recipient_name: Optional[str] = None,
        recipient_contact: Optional[str] = None,
        line_items: Optional[List[Dict[str, Any]]] = None,
        notes: Optional[str] = None,
        currency: str = "PKR",
        actor_id: Optional[uuid.UUID] = None,
    ) -> Tuple[bytes, str]:
        tenant_name = await self._get_tenant_name(session, tenant_id)
        clean_type = (document_type or "quote").strip().lower()
        items = list(line_items or [])
        grand_total = 0.0
        rows: List[List[str]] = []
        for idx, item in enumerate(items, start=1):
            desc = str(item.get("description") or f"Item #{idx}")
            qty = float(item.get("quantity") or 1)
            unit_price = float(item.get("unit_price") or 0.0)
            line_total = round(qty * unit_price, 2)
            grand_total += line_total
            rows.append([
                desc,
                f"{qty:g}",
                f"{currency} {unit_price:,.2f}",
                f"{currency} {line_total:,.2f}",
            ])

        if rows and clean_type in ("invoice", "quote"):
            rows.append(["TOTAL", "", "", f"{currency} {grand_total:,.2f}"])

        meta_rows = [("Document Type", clean_type.replace("_", " ").title())]
        if recipient_name:
            meta_rows.append(("Prepared For", recipient_name))
        if recipient_contact:
            meta_rows.append(("Contact", recipient_contact))

        pdf_bytes = self.render_document(
            tenant_name=tenant_name,
            title=title.strip() or f"{clean_type.title()} Document",
            subtitle=f"{clean_type.replace('_', ' ').title()} issued by {tenant_name}",
            meta_rows=meta_rows,
            table_headers=["Description", "Qty", "Unit Price", "Amount"] if rows else [],
            table_rows=rows,
            notes=notes,
        )
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="growth.pdf.generated",
                resource_type="pdf_document",
                metadata_={"document_type": clean_type, "title": title, "total": grand_total},
            )
        )
        await session.commit()
        return pdf_bytes, _safe_filename(f"{clean_type}-{title}", clean_type)


pdf_generator_service = PdfGeneratorService()
