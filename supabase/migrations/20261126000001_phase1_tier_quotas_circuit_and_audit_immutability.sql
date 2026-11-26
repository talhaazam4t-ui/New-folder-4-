-- =============================================================================
-- PHASE 1: Multi-Tenant Tier Quotas (80% Alert / 100% Hard-Lock) & Immutable Audit Logs
-- Target Project: pmmduhflikdvddzpgwsi (eu-west-1)
-- =============================================================================

-- 1. Tiered Usage & Token Metering Table (`public.tenant_tier_quotas`)
CREATE TABLE IF NOT EXISTS public.tenant_tier_quotas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL UNIQUE REFERENCES public.tenants(id) ON DELETE CASCADE,
    tier VARCHAR(32) NOT NULL DEFAULT 'starter',
    period_month VARCHAR(16) NOT NULL DEFAULT to_char( now() AT TIME ZONE 'utc', 'YYYY-MM' ),
    tokens_limit INTEGER NOT NULL DEFAULT 100000,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    api_calls_limit INTEGER NOT NULL DEFAULT 2500,
    api_calls_used INTEGER NOT NULL DEFAULT 0,
    voice_minutes_limit NUMERIC(10, 2) NOT NULL DEFAULT 60.00,
    voice_minutes_used NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    alert_80_triggered BOOLEAN NOT NULL DEFAULT FALSE,
    alert_80_notified_at TIMESTAMPTZ NULL,
    hard_locked_100 BOOLEAN NOT NULL DEFAULT FALSE,
    hard_locked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_tier_quotas_tenant_id
    ON public.tenant_tier_quotas(tenant_id);

CREATE INDEX IF NOT EXISTS idx_tenant_tier_quotas_tier_locked
    ON public.tenant_tier_quotas(tier, hard_locked_100);

ALTER TABLE public.tenant_tier_quotas ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'tenant_tier_quotas'
          AND policyname = 'tenant_tier_quotas_tenant_isolation'
    ) THEN
        CREATE POLICY tenant_tier_quotas_tenant_isolation
            ON public.tenant_tier_quotas
            FOR ALL
            TO authenticated
            USING ((SELECT public.is_super_admin()) OR public.is_tenant_member(tenant_id))
            WITH CHECK ((SELECT public.is_super_admin()) OR public.is_tenant_member(tenant_id));
    END IF;
END $$;

-- 2. Immutable Audit Logs Trigger (`public.prevent_audit_log_mutation`)
CREATE OR REPLACE FUNCTION public.prevent_audit_log_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'IMMUTABLE_AUDIT_LOG: Audit logs are append-only and cannot be modified.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        -- Allow ON DELETE CASCADE only when parent tenant workspace itself is being purged
        IF OLD.tenant_id IS NULL OR EXISTS (SELECT 1 FROM public.tenants WHERE id = OLD.tenant_id) THEN
            RAISE EXCEPTION 'IMMUTABLE_AUDIT_LOG: Audit logs are append-only and cannot be deleted.';
        END IF;
    END IF;
    RETURN OLD;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_audit_logs_immutable'
    ) THEN
        CREATE TRIGGER trg_audit_logs_immutable
        BEFORE UPDATE OR DELETE ON public.audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION public.prevent_audit_log_mutation();
    END IF;
END $$;
