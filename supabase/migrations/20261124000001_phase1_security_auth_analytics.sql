-- Phase 1: DB Security Hardening, Email Verification / Reset Tokens, and Privacy-Friendly Analytics

-- 1. Restrict SECURITY DEFINER helper functions from unauthenticated anon RPC access
REVOKE EXECUTE ON FUNCTION public.get_tenant_subscription_tier(uuid) FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.get_user_tenant_ids() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.is_tenant_admin(uuid) FROM PUBLIC, anon;

GRANT EXECUTE ON FUNCTION public.get_tenant_subscription_tier(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_user_tenant_ids() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.is_tenant_admin(uuid) TO authenticated, service_role;

-- 2. Add email verification flag to profiles
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS email_verified boolean NOT NULL DEFAULT false;

-- 3. Secure server-only verification and password reset tokens table
CREATE TABLE IF NOT EXISTS public.auth_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    token_type text NOT NULL CHECK (token_type IN ('email_verify', 'password_reset')),
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_type
    ON public.auth_tokens (user_id, token_type);

ALTER TABLE public.auth_tokens ENABLE ROW LEVEL SECURITY;

-- Service-role only (no open anon/authenticated policies so token hashes are never exposed via PostgREST)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'auth_tokens' AND policyname = 'auth_tokens_service_role_only'
    ) THEN
        CREATE POLICY auth_tokens_service_role_only
            ON public.auth_tokens
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;

-- 4. Privacy-friendly lightweight analytics events table
CREATE TABLE IF NOT EXISTS public.analytics_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE,
    event_name text NOT NULL,
    page_path text NOT NULL,
    referrer text,
    session_key text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_analytics_events_name_created
    ON public.analytics_events (event_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_analytics_events_tenant_created
    ON public.analytics_events (tenant_id, created_at DESC);

ALTER TABLE public.analytics_events ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'analytics_events' AND policyname = 'analytics_events_tenant_or_admin_select'
    ) THEN
        CREATE POLICY analytics_events_tenant_or_admin_select
            ON public.analytics_events
            FOR SELECT
            TO authenticated
            USING (
                public.is_super_admin()
                OR (tenant_id IS NOT NULL AND public.is_tenant_member(tenant_id))
            );
    END IF;
END $$;
