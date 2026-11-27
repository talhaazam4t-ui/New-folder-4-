"""Phase 4 Verification Suite:
1. AI Financial Controller (`/api/v1/enterprise/financial-controller`) — 30/60/90-day predictive cash-flow
   forecast, rent MRR, and Zoho-compatible double-entry journal export.
2. Automated Contract Compliance Agent (`/api/v1/enterprise/contracts/audit`) — flags SLA/liability/milestone
   breaches and routes high-risk contracts to the HITL Approval Queue.
3. Zero-Touch Client Onboarding Specialist (`/api/v1/enterprise/onboarding/kyc`) — verifies B2B KYC and
   auto-provisions requested services.
4. Omnichannel Reputation Manager (`/api/v1/enterprise/reputation/route`) — routes 5★ publicly and escalates
   1-3★ feedback immediately to human support + HITL.
5. Content Compliance & Continuous Security Auditors (`/api/v1/enterprise/compliance/screen-content` &
   `/api/v1/enterprise/security/audit`).
6. Modular Vertical Packs Toggle Enforcement (Super Admin disabling a vertical pack blocks module execution).
"""

import uuid
from datetime import date

import pytest
from app.config import settings
from app.main import app
from httpx import ASGITransport, AsyncClient


async def _register_workspace(client: AsyncClient, email: str, slug: str, name: str):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"{name} Exec"},
    )
    assert reg.status_code == 201
    tok = reg.json()["access_token"]
    auth_h = {"Authorization": f"Bearer {tok}"}
    t_res = await client.post(
        "/api/v1/tenants",
        json={"name": name, "slug": slug, "industry": "Real Estate / Property"},
        headers=auth_h,
    )
    assert t_res.status_code in (200, 201)
    tid = t_res.json()["id"]
    return uuid.UUID(tid), {**auth_h, "X-Tenant-ID": str(tid)}


@pytest.mark.asyncio
async def test_phase4_enterprise_financial_controller_contracts_kyc_reputation_and_auditors(monkeypatch):
    """Verify all 6 Phase 4 High-Ticket Enterprise & Vertical Modules + modular toggle enforcement."""
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "allow_super_admin_bootstrap", True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, admin_h = await _register_workspace(
            client, "talhaazam4t@gmail.com", "talox-p4-admin", "Talox P4 Admin"
        )
        t1_id, h1 = await _register_workspace(client, "p4_ent1@test.ai", "p4-ent-1", "Emirates Property Group")
        _, h2 = await _register_workspace(client, "p4_ent2@test.ai", "p4-ent-2", "Other Enterprise")

        # ----------------------------------------------------------------------
        # 1. ZERO-TOUCH CLIENT KYC ONBOARDING -> AUTO-PROVISIONS SERVICES
        # ----------------------------------------------------------------------
        kyc_res = await client.post(
            "/api/v1/enterprise/onboarding/kyc",
            json={
                "company_legal_name": "Emirates Property Holdings LLC",
                "registration_number": "DED-992817",
                "tax_id": "TRN-100492817200003",
                "jurisdiction": "UAE (Dubai)",
                "contact_email": "cfo@emiratesproperty.ae",
                "requested_services": [
                    "business-financial-tracking",
                    "executive-analytics-compliance",
                    "ai-marketing-growth",
                ],
            },
            headers=h1,
        )
        assert kyc_res.status_code == 201
        kyc_data = kyc_res.json()["data"]
        assert kyc_data["kyc"]["kyc_status"] == "verified_provisioned"
        assert "business-financial-tracking" in kyc_data["provisioned_services"]

        # ----------------------------------------------------------------------
        # 2. AI FINANCIAL CONTROLLER (Rent MRR + Zoho Ledger + 30/60/90d Forecast)
        # ----------------------------------------------------------------------
        acc_res = await client.post(
            "/api/v1/finance/accounts",
            json={"name": "Emirates NBD Corporate", "currency": "USD", "current_balance": 25000.0},
            headers=h1,
        )
        assert acc_res.status_code == 201
        acc_id = acc_res.json()["id"]

        tx_res = await client.post(
            "/api/v1/finance/transactions",
            json={
                "account_id": acc_id,
                "type": "rent",
                "status": "paid",
                "amount": 6000.0,
                "category": "Commercial Lease",
                "counterparty_name": "Marina Tower Lessee LLC",
                "notes": "Marina Tower Unit 402 Monthly Rent",
                "transaction_date": str(date.today()),
            },
            headers=h1,
        )
        assert tx_res.status_code == 201

        fc_res = await client.get("/api/v1/enterprise/financial-controller", headers=h1)
        assert fc_res.status_code == 200
        fc = fc_res.json()["data"]
        assert fc["total_cash_balance"] == 31000.0
        assert len(fc["zoho_compatible_ledger"]) == 1
        assert fc["zoho_compatible_ledger"][0]["journal_number"] == "ZOHO-JRN-0001"
        assert fc["forecast"]["projected_net_90d"] >= 31000.0

        # ----------------------------------------------------------------------
        # 3. AUTOMATED CONTRACT COMPLIANCE AGENT (SLA Breach -> HITL Queue)
        # ----------------------------------------------------------------------
        contract_res = await client.post(
            "/api/v1/enterprise/contracts/audit",
            json={
                "contract_title": "Master AI Managed Services MSA 2026",
                "counterparty": "Apex Global Logistics",
                "contract_text": (
                    "Vendor agrees to unlimited liability for any downtime and this agreement is non-cancellable "
                    "for 36 months."
                ),
                "sla_terms": {"promised_uptime_pct": 99.9, "observed_uptime_pct": 98.4},
                "milestone_status": "delayed",
            },
            headers=h1,
        )
        assert contract_res.status_code == 201
        ca = contract_res.json()["data"]
        assert ca["risk_level"] == "high"
        assert len(ca["breach_flags"]) >= 3
        assert ca["approval_id"] is not None

        # Tenant 2 sees zero contract audits (strict isolation)
        assert (await client.get("/api/v1/enterprise/contracts/audits", headers=h2)).json()["data"] == []

        # ----------------------------------------------------------------------
        # 4. OMNICHANNEL REPUTATION MANAGER (5★ Public vs 2★ Human Escalation)
        # ----------------------------------------------------------------------
        rep_pos = await client.post(
            "/api/v1/enterprise/reputation/route",
            json={
                "customer_name": "Tariq Al-Mansoor",
                "customer_phone": "+971501234567",
                "rating": 5,
                "comment_text": "Outstanding 24/7 AI Receptionist service!",
            },
            headers=h1,
        )
        assert rep_pos.status_code == 200
        assert rep_pos.json()["data"]["routing"] == "public_google_redirect"
        assert rep_pos.json()["data"]["escalated_to_human"] is False

        rep_neg = await client.post(
            "/api/v1/enterprise/reputation/route",
            json={
                "customer_name": "David Sterling",
                "customer_phone": "+971509876543",
                "rating": 2,
                "comment_text": "Invoice arrived late and callback took two hours.",
            },
            headers=h1,
        )
        assert rep_neg.status_code == 200
        assert rep_neg.json()["data"]["routing"] == "private_human_support_escalation"
        assert rep_neg.json()["data"]["escalated_to_human"] is True
        assert rep_neg.json()["data"]["approval_id"] is not None

        # ----------------------------------------------------------------------
        # 5. CONTENT COMPLIANCE & CONTINUOUS SECURITY AUDITORS
        # ----------------------------------------------------------------------
        comp_res = await client.post(
            "/api/v1/enterprise/compliance/screen-content",
            json={
                "copy_text": "100% guaranteed medical miracle!! Double your money with BUY NOW!!!",
                "industry": "Clinics / Hospitals",
                "max_words": 60,
            },
            headers=h1,
        )
        assert comp_res.status_code == 200
        cdata = comp_res.json()["data"]
        assert cdata["compliant_initially"] is False
        assert len(cdata["legal_flags"]) >= 2
        assert "100% guaranteed" not in cdata["safe_revised_copy"].lower()

        sec_res = await client.get("/api/v1/enterprise/security/audit", headers=h1)
        assert sec_res.status_code == 200
        sdata = sec_res.json()["data"]
        assert sdata["rls_tenant_isolation_enforced"] is True
        assert sdata["audit_log_immutability_enforced"] is True
        assert sdata["total_logs_scanned"] >= 3

        # ----------------------------------------------------------------------
        # 6. MODULAR VERTICAL PACK TOGGLE (Super Admin Disabling Blocks Module)
        # ----------------------------------------------------------------------
        await client.post(
            f"/api/v1/agents/admin/tenants/{t1_id}/services/toggle",
            json={"service_slug": "business-financial-tracking", "enabled": False},
            headers=admin_h,
        )
        blocked_fc = await client.get("/api/v1/enterprise/financial-controller", headers=h1)
        assert blocked_fc.status_code == 403
