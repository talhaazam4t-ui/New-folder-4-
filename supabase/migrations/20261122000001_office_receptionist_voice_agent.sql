-- ==============================================================================
-- TALOX TECH STREAM — Office Receptionist (AI Voice Agent: Retell AI, Twilio, Cal.com)
-- Additive migration creating:
--   1. public.platform_voice_credentials (Super Admin encrypted master API keys)
--   2. public.receptionist_configs (Per-tenant Twilio, Retell AI, Cal.com, FAQs & Forwarding Guide)
--   3. public.receptionist_call_logs (Per-tenant call logs, transcripts, bookings & transfers)
-- All tables enforce strict Row Level Security (RLS) with TO authenticated policies
-- and covering FK indexes.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.platform_voice_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider VARCHAR(40) NOT NULL UNIQUE,
    encrypted_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(30) NOT NULL DEFAULT 'unconfigured',
    updated_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT platform_voice_credentials_provider_check CHECK (provider IN ('retell', 'twilio', 'calcom')),
    CONSTRAINT platform_voice_credentials_status_check CHECK (status IN ('configured', 'unconfigured', 'error'))
);

CREATE INDEX IF NOT EXISTS idx_platform_voice_credentials_updated_by
    ON public.platform_voice_credentials(updated_by);

CREATE TABLE IF NOT EXISTS public.receptionist_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL UNIQUE REFERENCES public.tenants(id) ON DELETE CASCADE,
    business_name VARCHAR(255) NOT NULL,
    operating_hours VARCHAR(500) NOT NULL DEFAULT 'Mon-Fri 9:00 AM - 6:00 PM',
    fallback_phone_number VARCHAR(50) NOT NULL,
    greeting_message TEXT NOT NULL DEFAULT 'Hello! Thank you for calling. How may I assist you today?',
    faqs_knowledge_base TEXT NOT NULL DEFAULT '',
    calcom_booking_url VARCHAR(500),
    calcom_event_type_id VARCHAR(100),
    encrypted_calcom_api_key TEXT,
    twilio_phone_number VARCHAR(50),
    twilio_phone_sid VARCHAR(120),
    retell_agent_id VARCHAR(120),
    retell_llm_id VARCHAR(120),
    voice_id VARCHAR(100) NOT NULL DEFAULT '11labs-Adrian',
    provisioning_status VARCHAR(40) NOT NULL DEFAULT 'pending_onboarding',
    provisioning_notes TEXT,
    call_forwarding_guide JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT receptionist_configs_status_check CHECK (
        provisioning_status IN ('pending_onboarding', 'provisioning', 'active', 'sandbox_ready', 'error')
    )
);

CREATE INDEX IF NOT EXISTS idx_receptionist_configs_twilio_phone
    ON public.receptionist_configs(twilio_phone_number);
CREATE INDEX IF NOT EXISTS idx_receptionist_configs_retell_agent
    ON public.receptionist_configs(retell_agent_id);

CREATE TABLE IF NOT EXISTS public.receptionist_call_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    config_id UUID REFERENCES public.receptionist_configs(id) ON DELETE SET NULL,
    external_call_id VARCHAR(120) NOT NULL,
    caller_phone VARCHAR(50) NOT NULL DEFAULT 'Unknown',
    caller_name VARCHAR(120),
    to_number VARCHAR(50),
    direction VARCHAR(20) NOT NULL DEFAULT 'inbound',
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(40) NOT NULL DEFAULT 'completed',
    booking_status VARCHAR(40) NOT NULL DEFAULT 'none',
    booked_appointment_at TIMESTAMPTZ,
    calcom_booking_uid VARCHAR(120),
    transferred_to_human BOOLEAN NOT NULL DEFAULT false,
    summary TEXT,
    transcript TEXT,
    recording_url VARCHAR(500),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT receptionist_call_logs_duration_check CHECK (duration_seconds >= 0),
    CONSTRAINT receptionist_call_logs_direction_check CHECK (direction IN ('inbound', 'outbound')),
    CONSTRAINT receptionist_call_logs_status_check CHECK (
        status IN ('in_progress', 'completed', 'transferred', 'missed', 'failed')
    ),
    CONSTRAINT receptionist_call_logs_booking_check CHECK (
        booking_status IN ('none', 'booked', 'rescheduled', 'canceled', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_receptionist_call_logs_tenant_created
    ON public.receptionist_call_logs(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_receptionist_call_logs_config_id
    ON public.receptionist_call_logs(config_id);
CREATE INDEX IF NOT EXISTS idx_receptionist_call_logs_external_call_id
    ON public.receptionist_call_logs(external_call_id);

-- ==============================================================================
-- Row Level Security (RLS) Policies — Strict Multi-Tenant Isolation
-- ==============================================================================

ALTER TABLE public.platform_voice_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.receptionist_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.receptionist_call_logs ENABLE ROW LEVEL SECURITY;

-- 1. platform_voice_credentials: Super Admin ONLY
DROP POLICY IF EXISTS platform_voice_credentials_admin_all ON public.platform_voice_credentials;
CREATE POLICY platform_voice_credentials_admin_all
    ON public.platform_voice_credentials
    FOR ALL
    TO authenticated
    USING (public.is_super_admin())
    WITH CHECK (public.is_super_admin());

-- 2. receptionist_configs: Tenant members read; tenant admins & super admins manage
DROP POLICY IF EXISTS receptionist_configs_select ON public.receptionist_configs;
CREATE POLICY receptionist_configs_select
    ON public.receptionist_configs
    FOR SELECT
    TO authenticated
    USING (public.is_tenant_member(tenant_id) OR public.is_super_admin());

DROP POLICY IF EXISTS receptionist_configs_insert ON public.receptionist_configs;
CREATE POLICY receptionist_configs_insert
    ON public.receptionist_configs
    FOR INSERT
    TO authenticated
    WITH CHECK (public.is_tenant_member(tenant_id) OR public.is_super_admin());

DROP POLICY IF EXISTS receptionist_configs_update ON public.receptionist_configs;
CREATE POLICY receptionist_configs_update
    ON public.receptionist_configs
    FOR UPDATE
    TO authenticated
    USING (public.is_tenant_member(tenant_id) OR public.is_super_admin())
    WITH CHECK (public.is_tenant_member(tenant_id) OR public.is_super_admin());

DROP POLICY IF EXISTS receptionist_configs_delete ON public.receptionist_configs;
CREATE POLICY receptionist_configs_delete
    ON public.receptionist_configs
    FOR DELETE
    TO authenticated
    USING (public.is_tenant_member(tenant_id) OR public.is_super_admin());

-- 3. receptionist_call_logs: Tenant members read & manage
DROP POLICY IF EXISTS receptionist_call_logs_select ON public.receptionist_call_logs;
CREATE POLICY receptionist_call_logs_select
    ON public.receptionist_call_logs
    FOR SELECT
    TO authenticated
    USING (public.is_tenant_member(tenant_id) OR public.is_super_admin());

DROP POLICY IF EXISTS receptionist_call_logs_insert ON public.receptionist_call_logs;
CREATE POLICY receptionist_call_logs_insert
    ON public.receptionist_call_logs
    FOR INSERT
    TO authenticated
    WITH CHECK (public.is_tenant_member(tenant_id) OR public.is_super_admin());

DROP POLICY IF EXISTS receptionist_call_logs_update ON public.receptionist_call_logs;
CREATE POLICY receptionist_call_logs_update
    ON public.receptionist_call_logs
    FOR UPDATE
    TO authenticated
    USING (public.is_tenant_member(tenant_id) OR public.is_super_admin())
    WITH CHECK (public.is_tenant_member(tenant_id) OR public.is_super_admin());

DROP POLICY IF EXISTS receptionist_call_logs_delete ON public.receptionist_call_logs;
CREATE POLICY receptionist_call_logs_delete
    ON public.receptionist_call_logs
    FOR DELETE
    TO authenticated
    USING (public.is_tenant_member(tenant_id) OR public.is_super_admin());
