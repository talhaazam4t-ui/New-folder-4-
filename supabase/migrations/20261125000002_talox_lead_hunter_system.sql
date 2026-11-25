-- TALOX International AI Receptionist Lead Hunting + Demo + Follow-up System

-- 1. International Hunter Leads (Dual Source: Google Places + Apollo Free Tier)
CREATE TABLE IF NOT EXISTS public.hunter_leads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    google_place_id text,
    business_name text NOT NULL,
    owner_name text,
    owner_title text,
    linkedin_url text,
    country text NOT NULL,
    city text NOT NULL,
    category text NOT NULL,
    address text,
    phone text,
    email text,
    email_verified boolean NOT NULL DEFAULT false,
    website text,
    favicon_url text,
    services text,
    working_hours text,
    pricing_info text,
    rating numeric(3, 2) NOT NULL DEFAULT 0.0,
    total_reviews integer NOT NULL DEFAULT 0,
    has_ai boolean NOT NULL DEFAULT false,
    ai_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    pain_points jsonb NOT NULL DEFAULT '[]'::jsonb,
    interest_score integer NOT NULL DEFAULT 50 CHECK (interest_score BETWEEN 0 AND 100),
    lead_source text NOT NULL DEFAULT 'google_places' CHECK (lead_source IN ('google_places', 'apollo', 'hybrid')),
    status text NOT NULL DEFAULT 'new',
    pipeline_stage text NOT NULL DEFAULT 'new_lead',
    timezone text NOT NULL DEFAULT 'America/New_York',
    deal_value_usd numeric(12, 2) NOT NULL DEFAULT 0.00,
    human_needed boolean NOT NULL DEFAULT false,
    do_not_disturb boolean NOT NULL DEFAULT false,
    last_contact_at timestamptz,
    next_followup_at timestamptz,
    call_result text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hunter_leads_tenant_score
    ON public.hunter_leads (tenant_id, interest_score DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hunter_leads_tenant_stage
    ON public.hunter_leads (tenant_id, pipeline_stage);
CREATE UNIQUE INDEX IF NOT EXISTS uq_hunter_leads_tenant_place
    ON public.hunter_leads (tenant_id, google_place_id)
    WHERE google_place_id IS NOT NULL;

ALTER TABLE public.hunter_leads ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'hunter_leads' AND policyname = 'hunter_leads_member_or_admin_select'
    ) THEN
        CREATE POLICY hunter_leads_member_or_admin_select
            ON public.hunter_leads
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR public.is_tenant_member(tenant_id)
            );
    END IF;
END $$;

-- 2. Personalized English Demos (Draft / Approved / Sent HITL Gate)
CREATE TABLE IF NOT EXISTS public.hunter_demos (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    lead_id uuid NOT NULL REFERENCES public.hunter_leads(id) ON DELETE CASCADE,
    email_subject text NOT NULL,
    email_copy text NOT NULL,
    whatsapp_copy text NOT NULL,
    voice_script text NOT NULL,
    chat_prompt text NOT NULL,
    business_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'sent', 'rejected')),
    approved_at timestamptz,
    sent_at timestamptz,
    sent_channels jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hunter_demos_tenant_status
    ON public.hunter_demos (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hunter_demos_lead
    ON public.hunter_demos (lead_id);

ALTER TABLE public.hunter_demos ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'hunter_demos' AND policyname = 'hunter_demos_member_or_admin_select'
    ) THEN
        CREATE POLICY hunter_demos_member_or_admin_select
            ON public.hunter_demos
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR public.is_tenant_member(tenant_id)
            );
    END IF;
END $$;

-- 3. Auto Follow-up Engine Queue (24h / 48h / 72h with Human Handover & DND Stop)
CREATE TABLE IF NOT EXISTS public.hunter_followups (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    lead_id uuid NOT NULL REFERENCES public.hunter_leads(id) ON DELETE CASCADE,
    demo_id uuid REFERENCES public.hunter_demos(id) ON DELETE SET NULL,
    followup_number integer NOT NULL CHECK (followup_number BETWEEN 1 AND 3),
    subject text,
    message text NOT NULL,
    channel text NOT NULL DEFAULT 'email' CHECK (channel IN ('email', 'linkedin', 'whatsapp')),
    scheduled_at timestamptz NOT NULL,
    sent_at timestamptz,
    status text NOT NULL DEFAULT 'scheduled' CHECK (
        status IN ('scheduled', 'sent', 'cancelled_human_handover', 'cancelled_dnd', 'skipped_limit', 'failed')
    ),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hunter_followups_tenant_due
    ON public.hunter_followups (tenant_id, status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_hunter_followups_lead
    ON public.hunter_followups (lead_id);
CREATE INDEX IF NOT EXISTS idx_hunter_followups_demo
    ON public.hunter_followups (demo_id);

ALTER TABLE public.hunter_followups ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'hunter_followups' AND policyname = 'hunter_followups_member_or_admin_select'
    ) THEN
        CREATE POLICY hunter_followups_member_or_admin_select
            ON public.hunter_followups
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR public.is_tenant_member(tenant_id)
            );
    END IF;
END $$;

-- 4. Lead Hunter Omnichannel Conversation Log
CREATE TABLE IF NOT EXISTS public.hunter_conversations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    lead_id uuid NOT NULL REFERENCES public.hunter_leads(id) ON DELETE CASCADE,
    message text NOT NULL,
    direction text NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    channel text NOT NULL DEFAULT 'email',
    intent_detected text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hunter_conversations_tenant_created
    ON public.hunter_conversations (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hunter_conversations_lead
    ON public.hunter_conversations (lead_id, created_at ASC);

ALTER TABLE public.hunter_conversations ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'hunter_conversations' AND policyname = 'hunter_conversations_member_or_admin_select'
    ) THEN
        CREATE POLICY hunter_conversations_member_or_admin_select
            ON public.hunter_conversations
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR public.is_tenant_member(tenant_id)
            );
    END IF;
END $$;

-- 5. Master Control Panel Settings & Daily Anti-Ban / Free-Tier Quotas (All OFF by Default except direct_call_mode)
CREATE TABLE IF NOT EXISTS public.hunter_settings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    module_name text NOT NULL,
    is_on boolean NOT NULL DEFAULT false,
    budget_mode text NOT NULL DEFAULT 'custom',
    daily_limit integer NOT NULL DEFAULT 10,
    used_today integer NOT NULL DEFAULT 0,
    usage_date text NOT NULL DEFAULT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD'),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_hunter_settings_tenant_module UNIQUE (tenant_id, module_name)
);

CREATE INDEX IF NOT EXISTS idx_hunter_settings_tenant
    ON public.hunter_settings (tenant_id);

ALTER TABLE public.hunter_settings ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'hunter_settings' AND policyname = 'hunter_settings_member_or_admin_select'
    ) THEN
        CREATE POLICY hunter_settings_member_or_admin_select
            ON public.hunter_settings
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR public.is_tenant_member(tenant_id)
            );
    END IF;
END $$;
