-- Phase 2: Prepaid Credit Wallets, Usage Ledger, and Native Asyncio Scheduled Jobs

-- 1. Tenant Wallets
CREATE TABLE IF NOT EXISTS public.tenant_wallets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL UNIQUE REFERENCES public.tenants(id) ON DELETE CASCADE,
    balance_credits numeric(14,2) NOT NULL DEFAULT 0.00,
    reserved_credits numeric(14,2) NOT NULL DEFAULT 0.00,
    currency text NOT NULL DEFAULT 'USD',
    low_balance_threshold numeric(14,2) NOT NULL DEFAULT 25.00,
    auto_pause_enabled boolean NOT NULL DEFAULT false,
    is_paused boolean NOT NULL DEFAULT false,
    low_balance_notified_at timestamptz,
    lifetime_credited numeric(14,2) NOT NULL DEFAULT 0.00,
    lifetime_debited numeric(14,2) NOT NULL DEFAULT 0.00,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.tenant_wallets ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'tenant_wallets' AND policyname = 'tenant_wallets_member_or_admin_select'
    ) THEN
        CREATE POLICY tenant_wallets_member_or_admin_select
            ON public.tenant_wallets
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR public.is_tenant_member(tenant_id)
            );
    END IF;
END $$;

-- 2. Usage Ledger (idempotent credit/debit/trial/plan/refund audit trail)
CREATE TABLE IF NOT EXISTS public.usage_ledger (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    wallet_id uuid NOT NULL REFERENCES public.tenant_wallets(id) ON DELETE CASCADE,
    entry_type text NOT NULL CHECK (entry_type IN ('credit', 'debit', 'refund', 'trial_grant', 'plan_grant', 'adjustment')),
    category text NOT NULL,
    credits_delta numeric(14,2) NOT NULL,
    balance_after numeric(14,2) NOT NULL,
    unit_count numeric(12,2) NOT NULL DEFAULT 1.00,
    unit_cost numeric(12,4) NOT NULL DEFAULT 0.0000,
    reference_id text,
    description text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_usage_ledger_tenant_created
    ON public.usage_ledger (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_usage_ledger_wallet_id
    ON public.usage_ledger (wallet_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_usage_ledger_tenant_ref
    ON public.usage_ledger (tenant_id, reference_id)
    WHERE reference_id IS NOT NULL;

ALTER TABLE public.usage_ledger ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'usage_ledger' AND policyname = 'usage_ledger_member_or_admin_select'
    ) THEN
        CREATE POLICY usage_ledger_member_or_admin_select
            ON public.usage_ledger
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR public.is_tenant_member(tenant_id)
            );
    END IF;
END $$;

-- 3. Native Python Asyncio Scheduled Jobs & Retry/Dead-Letter Queue
CREATE TABLE IF NOT EXISTS public.scheduled_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE,
    job_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed', 'dead_letter', 'cancelled')),
    attempts integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL DEFAULT 3,
    run_at timestamptz NOT NULL DEFAULT now(),
    last_error text,
    idempotency_key text UNIQUE,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_due
    ON public.scheduled_jobs (status, run_at);

CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_tenant
    ON public.scheduled_jobs (tenant_id);

ALTER TABLE public.scheduled_jobs ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'scheduled_jobs' AND policyname = 'scheduled_jobs_member_or_admin_select'
    ) THEN
        CREATE POLICY scheduled_jobs_member_or_admin_select
            ON public.scheduled_jobs
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR (tenant_id IS NOT NULL AND public.is_tenant_member(tenant_id))
            );
    END IF;
END $$;
