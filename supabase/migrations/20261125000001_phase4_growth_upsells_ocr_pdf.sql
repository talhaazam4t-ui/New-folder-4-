-- Phase 4: Native Meta IG/FB Comment-to-DM, Smart Google Review Booster & WhatsApp Vision OCR

-- 1. Meta Comment-to-DM Keyword Rules
CREATE TABLE IF NOT EXISTS public.social_comment_rules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    platform text NOT NULL DEFAULT 'both' CHECK (platform IN ('instagram', 'facebook', 'both')),
    keyword text NOT NULL,
    post_id text,
    dm_template text NOT NULL,
    reply_comment_template text,
    booking_url text,
    is_active boolean NOT NULL DEFAULT true,
    trigger_count integer NOT NULL DEFAULT 0,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_social_comment_rules_tenant_active
    ON public.social_comment_rules (tenant_id, is_active);

ALTER TABLE public.social_comment_rules ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'social_comment_rules' AND policyname = 'social_comment_rules_member_or_admin_select'
    ) THEN
        CREATE POLICY social_comment_rules_member_or_admin_select
            ON public.social_comment_rules
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR public.is_tenant_member(tenant_id)
            );
    END IF;
END $$;

-- 2. Meta Auto-DM Execution Logs (with comment idempotency)
CREATE TABLE IF NOT EXISTS public.social_dm_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    rule_id uuid REFERENCES public.social_comment_rules(id) ON DELETE SET NULL,
    lead_id uuid REFERENCES public.leads(id) ON DELETE SET NULL,
    platform text NOT NULL,
    post_id text,
    external_comment_id text,
    commenter_id text,
    commenter_name text,
    comment_text text NOT NULL,
    matched_keyword text,
    dm_text text NOT NULL,
    booking_link text,
    status text NOT NULL DEFAULT 'sandbox_sent',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_social_dm_logs_tenant_created
    ON public.social_dm_logs (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_dm_logs_rule
    ON public.social_dm_logs (rule_id);
CREATE INDEX IF NOT EXISTS idx_social_dm_logs_lead
    ON public.social_dm_logs (lead_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_social_dm_logs_tenant_comment
    ON public.social_dm_logs (tenant_id, external_comment_id)
    WHERE external_comment_id IS NOT NULL;

ALTER TABLE public.social_dm_logs ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'social_dm_logs' AND policyname = 'social_dm_logs_member_or_admin_select'
    ) THEN
        CREATE POLICY social_dm_logs_member_or_admin_select
            ON public.social_dm_logs
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR public.is_tenant_member(tenant_id)
            );
    END IF;
END $$;

-- 3. Smart Google Review Booster Requests (1-5 Star Routing)
CREATE TABLE IF NOT EXISTS public.review_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    call_log_id uuid REFERENCES public.receptionist_call_logs(id) ON DELETE SET NULL,
    lead_id uuid REFERENCES public.leads(id) ON DELETE SET NULL,
    customer_name text,
    customer_phone text NOT NULL,
    rating integer CHECK (rating BETWEEN 1 AND 5),
    status text NOT NULL DEFAULT 'sent',
    routing_target text,
    google_review_url text,
    private_feedback text,
    feedback_token text NOT NULL,
    sent_at timestamptz NOT NULL DEFAULT now(),
    responded_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_review_requests_tenant_created
    ON public.review_requests (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_requests_call_log
    ON public.review_requests (call_log_id);
CREATE INDEX IF NOT EXISTS idx_review_requests_lead
    ON public.review_requests (lead_id);
CREATE INDEX IF NOT EXISTS idx_review_requests_tenant_phone
    ON public.review_requests (tenant_id, customer_phone);
CREATE UNIQUE INDEX IF NOT EXISTS uq_review_requests_feedback_token
    ON public.review_requests (feedback_token);

ALTER TABLE public.review_requests ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'review_requests' AND policyname = 'review_requests_member_or_admin_select'
    ) THEN
        CREATE POLICY review_requests_member_or_admin_select
            ON public.review_requests
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR public.is_tenant_member(tenant_id)
            );
    END IF;
END $$;

-- 4. WhatsApp & Dashboard Vision OCR Document Extractions
CREATE TABLE IF NOT EXISTS public.document_extractions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    lead_id uuid REFERENCES public.leads(id) ON DELETE SET NULL,
    session_id uuid REFERENCES public.omnichannel_sessions(id) ON DELETE SET NULL,
    approval_id uuid REFERENCES public.approvals(id) ON DELETE SET NULL,
    source_channel text NOT NULL DEFAULT 'whatsapp',
    document_type text NOT NULL DEFAULT 'unknown',
    mime_type text NOT NULL DEFAULT 'image/jpeg',
    sender_phone text,
    sender_name text,
    media_id text,
    extracted_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_summary text,
    confidence numeric(4, 2) NOT NULL DEFAULT 0.85,
    status text NOT NULL DEFAULT 'extracted',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_extractions_tenant_created
    ON public.document_extractions (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_document_extractions_lead
    ON public.document_extractions (lead_id);
CREATE INDEX IF NOT EXISTS idx_document_extractions_session
    ON public.document_extractions (session_id);
CREATE INDEX IF NOT EXISTS idx_document_extractions_approval
    ON public.document_extractions (approval_id);

ALTER TABLE public.document_extractions ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'document_extractions' AND policyname = 'document_extractions_member_or_admin_select'
    ) THEN
        CREATE POLICY document_extractions_member_or_admin_select
            ON public.document_extractions
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR public.is_tenant_member(tenant_id)
            );
    END IF;
END $$;
