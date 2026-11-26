-- =============================================================================
-- PHASE 3: Content Repurposing Bundles & Automated Freelancing Pipeline
-- Target Project: pmmduhflikdvddzpgwsi (eu-west-1)
-- =============================================================================

-- 1. Content Repurposing Bundles (`public.repurposed_content_bundles`)
CREATE TABLE IF NOT EXISTS public.repurposed_content_bundles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    source_campaign_id UUID NULL REFERENCES public.marketing_campaigns(id) ON DELETE SET NULL,
    source_title VARCHAR(255) NOT NULL,
    core_message TEXT NOT NULL,
    linkedin_post TEXT NOT NULL,
    blog_summary TEXT NOT NULL,
    newsletter_draft TEXT NOT NULL,
    qc_report JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'pending_hitl',
    approval_id UUID NULL REFERENCES public.approvals(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_repurposed_content_bundles_tenant
    ON public.repurposed_content_bundles(tenant_id, created_at DESC);

ALTER TABLE public.repurposed_content_bundles ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'repurposed_content_bundles'
          AND policyname = 'repurposed_content_bundles_isolation'
    ) THEN
        CREATE POLICY repurposed_content_bundles_isolation
            ON public.repurposed_content_bundles
            FOR ALL
            TO authenticated
            USING ((SELECT public.is_super_admin()) OR public.is_tenant_member(tenant_id))
            WITH CHECK ((SELECT public.is_super_admin()) OR public.is_tenant_member(tenant_id));
    END IF;
END $$;

-- 2. Automated Freelancing Pipeline (`public.freelance_orders`)
CREATE TABLE IF NOT EXISTS public.freelance_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    client_name VARCHAR(200) NOT NULL,
    project_title VARCHAR(255) NOT NULL,
    category VARCHAR(64) NOT NULL DEFAULT 'seo_audit',
    budget_usd NUMERIC(12, 2) NOT NULL DEFAULT 250.00,
    requirements TEXT NOT NULL,
    assigned_workforce_agent VARCHAR(100) NOT NULL DEFAULT 'seo_auditor_agent',
    deliverable_draft TEXT NULL,
    qc_report JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(36) NOT NULL DEFAULT 'scanned',
    approval_id UUID NULL REFERENCES public.approvals(id) ON DELETE SET NULL,
    delivered_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_freelance_orders_tenant_status
    ON public.freelance_orders(tenant_id, status, created_at DESC);

ALTER TABLE public.freelance_orders ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'freelance_orders'
          AND policyname = 'freelance_orders_isolation'
    ) THEN
        CREATE POLICY freelance_orders_isolation
            ON public.freelance_orders
            FOR ALL
            TO authenticated
            USING ((SELECT public.is_super_admin()) OR public.is_tenant_member(tenant_id))
            WITH CHECK ((SELECT public.is_super_admin()) OR public.is_tenant_member(tenant_id));
    END IF;
END $$;
