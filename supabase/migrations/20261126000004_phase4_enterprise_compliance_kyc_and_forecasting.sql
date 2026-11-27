-- =============================================================================
-- PHASE 4: High-Ticket Enterprise & Vertical Modules (Contract SLA & Zero-Touch KYC)
-- Target Project: pmmduhflikdvddzpgwsi (eu-west-1)
-- =============================================================================

-- 1. Automated Contract Compliance Audits (`public.contract_compliance_audits`)
CREATE TABLE IF NOT EXISTS public.contract_compliance_audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    contract_title VARCHAR(255) NOT NULL,
    counterparty VARCHAR(200) NOT NULL,
    contract_text TEXT NOT NULL,
    sla_terms JSONB NOT NULL DEFAULT '{}'::jsonb,
    breach_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_level VARCHAR(24) NOT NULL DEFAULT 'low',
    milestone_status VARCHAR(48) NOT NULL DEFAULT 'on_track',
    ai_summary TEXT NOT NULL,
    approval_id UUID NULL REFERENCES public.approvals(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_contract_compliance_audits_tenant
    ON public.contract_compliance_audits(tenant_id, risk_level, created_at DESC);

ALTER TABLE public.contract_compliance_audits ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'contract_compliance_audits'
          AND policyname = 'contract_compliance_audits_isolation'
    ) THEN
        CREATE POLICY contract_compliance_audits_isolation
            ON public.contract_compliance_audits
            FOR ALL
            TO authenticated
            USING ((SELECT public.is_super_admin()) OR public.is_tenant_member(tenant_id))
            WITH CHECK ((SELECT public.is_super_admin()) OR public.is_tenant_member(tenant_id));
    END IF;
END $$;

-- 2. Zero-Touch Client KYC Onboardings (`public.client_kyc_onboardings`)
CREATE TABLE IF NOT EXISTS public.client_kyc_onboardings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    company_legal_name VARCHAR(255) NOT NULL,
    registration_number VARCHAR(120) NOT NULL,
    tax_id VARCHAR(120) NOT NULL,
    jurisdiction VARCHAR(120) NOT NULL,
    contact_email VARCHAR(255) NOT NULL,
    requested_services JSONB NOT NULL DEFAULT '[]'::jsonb,
    kyc_status VARCHAR(36) NOT NULL DEFAULT 'verified_provisioned',
    provisioned_at TIMESTAMPTZ NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_client_kyc_onboardings_tenant
    ON public.client_kyc_onboardings(tenant_id, kyc_status, created_at DESC);

ALTER TABLE public.client_kyc_onboardings ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'client_kyc_onboardings'
          AND policyname = 'client_kyc_onboardings_isolation'
    ) THEN
        CREATE POLICY client_kyc_onboardings_isolation
            ON public.client_kyc_onboardings
            FOR ALL
            TO authenticated
            USING ((SELECT public.is_super_admin()) OR public.is_tenant_member(tenant_id))
            WITH CHECK ((SELECT public.is_super_admin()) OR public.is_tenant_member(tenant_id));
    END IF;
END $$;
