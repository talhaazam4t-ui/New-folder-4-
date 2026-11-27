-- Phase 5: Multi-Tenant White-Label Engine & Metered API-as-a-Service
-- Strictly additive, idempotent DDL with Row-Level Security (RLS)

CREATE TABLE IF NOT EXISTS public.tenant_whitelabel_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL UNIQUE REFERENCES public.tenants(id) ON DELETE CASCADE,
    brand_name VARCHAR(255) NOT NULL DEFAULT 'Talox Tech Stream',
    logo_url VARCHAR(500),
    favicon_url VARCHAR(500),
    primary_color VARCHAR(32) NOT NULL DEFAULT '#2563EB',
    accent_color VARCHAR(32) NOT NULL DEFAULT '#10B981',
    custom_domain VARCHAR(255) UNIQUE,
    support_email VARCHAR(255),
    hide_powered_by BOOLEAN NOT NULL DEFAULT FALSE,
    agency_reseller_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_whitelabel_configs_tenant_id
    ON public.tenant_whitelabel_configs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_whitelabel_configs_custom_domain
    ON public.tenant_whitelabel_configs(custom_domain);

ALTER TABLE public.tenant_whitelabel_configs ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'tenant_whitelabel_configs'
          AND policyname = 'tenant_whitelabel_configs_isolation_policy'
    ) THEN
        CREATE POLICY tenant_whitelabel_configs_isolation_policy
            ON public.tenant_whitelabel_configs
            FOR ALL
            TO authenticated
            USING (public.is_tenant_member(tenant_id) OR public.is_super_admin())
            WITH CHECK (public.is_tenant_member(tenant_id) OR public.is_super_admin());
    END IF;
END $$;


CREATE TABLE IF NOT EXISTS public.tenant_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    name VARCHAR(160) NOT NULL,
    key_prefix VARCHAR(32) NOT NULL,
    key_hash VARCHAR(128) NOT NULL UNIQUE,
    scopes JSONB NOT NULL DEFAULT '["agents:invoke","leads:read","finance:read","compliance:audit"]'::jsonb,
    rate_limit_per_minute INTEGER NOT NULL DEFAULT 60,
    total_calls INTEGER NOT NULL DEFAULT 0,
    total_tokens_metered INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_api_keys_tenant_id
    ON public.tenant_api_keys(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_api_keys_key_hash
    ON public.tenant_api_keys(key_hash);

ALTER TABLE public.tenant_api_keys ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'tenant_api_keys'
          AND policyname = 'tenant_api_keys_isolation_policy'
    ) THEN
        CREATE POLICY tenant_api_keys_isolation_policy
            ON public.tenant_api_keys
            FOR ALL
            TO authenticated
            USING (public.is_tenant_member(tenant_id) OR public.is_super_admin())
            WITH CHECK (public.is_tenant_member(tenant_id) OR public.is_super_admin());
    END IF;
END $$;
