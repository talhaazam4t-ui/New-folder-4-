-- ==============================================================================
-- TALOX TECH STREAM — ORM / UUID Reconciliation & Advisor-Clean RLS Migration
-- Idempotent migration reconciling live Supabase TEXT/legacy drift with ORM
-- GUID()/UUID models, missing tables, CHECK constraints, and RLS advisors.
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ------------------------------------------------------------------------------
-- 1. Drop existing RLS policies on public schema so column types can be altered
--    and duplicate/initplan-heavy policies are replaced cleanly.
-- ------------------------------------------------------------------------------
DO $$
DECLARE
    pol RECORD;
BEGIN
    FOR pol IN
        SELECT schemaname, tablename, policyname
        FROM pg_policies
        WHERE schemaname = 'public'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', pol.policyname, pol.schemaname, pol.tablename);
    END LOOP;
END $$;

-- Drop legacy text signature if present before type alignment
DROP FUNCTION IF EXISTS public.is_tenant_member(TEXT) CASCADE;

-- ------------------------------------------------------------------------------
-- 2. Create missing ORM tables (business_records, business_metrics, agent_permissions)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.business_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    record_type TEXT NOT NULL CHECK (record_type IN ('income', 'expense', 'rent', 'payment_received', 'outstanding', 'adjustment')),
    title TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    description TEXT,
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'whatsapp', 'integration', 'agent')),
    reference_id TEXT,
    recorded_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_business_records_tenant ON public.business_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_business_records_type ON public.business_records(record_type);
CREATE INDEX IF NOT EXISTS idx_business_records_recorded_at ON public.business_records(recorded_at);
CREATE INDEX IF NOT EXISTS idx_business_records_recorded_by ON public.business_records(recorded_by);

CREATE TABLE IF NOT EXISTS public.business_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value NUMERIC NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_business_metrics_tenant ON public.business_metrics(tenant_id);

CREATE TABLE IF NOT EXISTS public.agent_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES public.agent_registry(id) ON DELETE CASCADE,
    permission_name TEXT NOT NULL,
    allowed BOOLEAN NOT NULL DEFAULT FALSE,
    scope JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(agent_id, permission_name)
);

CREATE INDEX IF NOT EXISTS idx_agent_permissions_agent ON public.agent_permissions(agent_id);

-- ------------------------------------------------------------------------------
-- 3. Reconcile TEXT -> UUID types on tenants(id) and all tenant_id/UUID columns
-- ------------------------------------------------------------------------------
DO $$
DECLARE
    fk RECORD;
    tbl TEXT;
    col_type TEXT;
    tenant_tables TEXT[] := ARRAY[
        'tenant_members',
        'service_subscriptions',
        'payments',
        'invoices',
        'business_records',
        'business_metrics',
        'leads',
        'marketing_campaigns',
        'marketing_metrics',
        'tenant_agents',
        'agent_tasks',
        'agent_executions',
        'approvals',
        'integrations',
        'notifications',
        'audit_logs',
        'usage_records',
        'financial_accounts',
        'financial_transactions',
        'rent_schedules',
        'financial_audit_logs',
        'appointments',
        'consent_records',
        'customers',
        'human_tasks',
        'tool_executions',
        'workflow_executions'
    ];
BEGIN
    -- Drop all foreign key constraints pointing to tenants or on tenant_id columns
    FOR fk IN
        SELECT conname, conrelid::regclass::text AS table_name
        FROM pg_constraint
        WHERE contype = 'f'
          AND connamespace = 'public'::regnamespace
          AND (
              confrelid = 'public.tenants'::regclass
              OR pg_get_constraintdef(oid) LIKE '%(tenant_id)%'
          )
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT IF EXISTS %I', fk.table_name, fk.conname);
    END LOOP;

    -- Convert tenants.id to UUID if currently text/varchar
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'tenants' AND column_name = 'id';

    IF col_type IS NOT NULL AND col_type <> 'uuid' THEN
        ALTER TABLE public.tenants
            ALTER COLUMN id DROP DEFAULT,
            ALTER COLUMN id TYPE UUID USING TRIM(id)::uuid,
            ALTER COLUMN id SET DEFAULT gen_random_uuid();
    END IF;

    -- Convert tenant_id columns on all ORM tables to UUID if currently text/varchar
    FOREACH tbl IN ARRAY tenant_tables LOOP
        SELECT data_type INTO col_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = tbl AND column_name = 'tenant_id';

        IF col_type IS NOT NULL AND col_type <> 'uuid' THEN
            EXECUTE format(
                'ALTER TABLE public.%I ALTER COLUMN tenant_id DROP DEFAULT, ALTER COLUMN tenant_id TYPE UUID USING NULLIF(TRIM(tenant_id), '''')::uuid',
                tbl
            );
        END IF;

        -- Re-create CASCADE FK to public.tenants(id) for every table except audit_logs (nullable audit preservation)
        IF col_type IS NOT NULL AND tbl <> 'audit_logs' THEN
            EXECUTE format(
                'ALTER TABLE public.%I ADD CONSTRAINT %I FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE',
                tbl,
                tbl || '_tenant_id_fkey'
            );
        END IF;
    END LOOP;
END $$;

-- ------------------------------------------------------------------------------
-- 4. Reconcile columns & legacy drift across core ORM tables
-- ------------------------------------------------------------------------------

-- 4.1 profiles: password_hash & updated_at
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS password_hash TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- 4.2 tenants: default status & drop NOT NULL on legacy optional columns
ALTER TABLE public.tenants
    ALTER COLUMN status SET DEFAULT 'pending_approval';

DO $$
DECLARE
    legacy_col TEXT;
BEGIN
    FOREACH legacy_col IN ARRAY ARRAY['contact_email', 'system_id', 'country', 'city'] LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'tenants' AND column_name = legacy_col AND is_nullable = 'NO'
        ) THEN
            EXECUTE format('ALTER TABLE public.tenants ALTER COLUMN %I DROP NOT NULL', legacy_col);
        END IF;
    END LOOP;
END $$;

-- 4.3 invoices: ORM expects subtotal, tax, total, due_at, updated_at
ALTER TABLE public.invoices
    ADD COLUMN IF NOT EXISTS subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS tax NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS total NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS due_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 days'),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'invoices' AND column_name = 'amount_cents'
    ) THEN
        EXECUTE '
            UPDATE public.invoices
            SET total = COALESCE(NULLIF(total, 0), ROUND((amount_cents::numeric / 100.0), 2)),
                subtotal = COALESCE(NULLIF(subtotal, 0), ROUND((amount_cents::numeric / 100.0), 2))
            WHERE amount_cents IS NOT NULL
        ';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'invoices' AND column_name = 'due_date'
    ) THEN
        EXECUTE '
            UPDATE public.invoices
            SET due_at = due_date::timestamptz
            WHERE due_date IS NOT NULL
        ';
    END IF;
    -- Ensure legacy non-null constraints do not block ORM inserts
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'invoices' AND column_name = 'amount_cents' AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE public.invoices ALTER COLUMN amount_cents DROP NOT NULL;
    END IF;
END $$;

-- 4.4 leads: ORM expects name, email, phone, source, assigned_agent, metadata
ALTER TABLE public.leads
    ADD COLUMN IF NOT EXISTS name TEXT,
    ADD COLUMN IF NOT EXISTS email TEXT,
    ADD COLUMN IF NOT EXISTS phone TEXT,
    ADD COLUMN IF NOT EXISTS source TEXT,
    ADD COLUMN IF NOT EXISTS qualification_score NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS assigned_agent TEXT,
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
DECLARE
    legacy_col TEXT;
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'leads' AND column_name = 'full_name'
    ) THEN
        EXECUTE 'UPDATE public.leads SET name = COALESCE(name, full_name) WHERE full_name IS NOT NULL';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'leads' AND column_name = 'channel'
    ) THEN
        EXECUTE 'UPDATE public.leads SET source = COALESCE(source, channel, ''manual'')';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'leads' AND column_name = 'contact_detail'
    ) THEN
        EXECUTE '
            UPDATE public.leads
            SET email = COALESCE(email, CASE WHEN contact_detail LIKE ''%@%'' THEN contact_detail ELSE NULL END),
                phone = COALESCE(phone, CASE WHEN contact_detail NOT LIKE ''%@%'' THEN contact_detail ELSE NULL END)
            WHERE contact_detail IS NOT NULL
        ';
    END IF;

    UPDATE public.leads SET name = COALESCE(name, 'Unnamed Lead'), source = COALESCE(source, 'manual');
    ALTER TABLE public.leads ALTER COLUMN name SET NOT NULL;
    ALTER TABLE public.leads ALTER COLUMN source SET NOT NULL;

    -- Drop NOT NULL from legacy columns so ORM inserts succeed
    FOREACH legacy_col IN ARRAY ARRAY['full_name', 'contact_detail', 'channel', 'service_requested', 'urgency', 'consent_granted', 'notes'] LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'leads' AND column_name = legacy_col AND is_nullable = 'NO'
        ) THEN
            EXECUTE format('ALTER TABLE public.leads ALTER COLUMN %I DROP NOT NULL', legacy_col);
        END IF;
    END LOOP;
END $$;

-- 4.5 audit_logs: ORM expects actor_id, actor_type, resource_type, resource_id, metadata, created_at
ALTER TABLE public.audit_logs
    ADD COLUMN IF NOT EXISTS actor_id UUID,
    ADD COLUMN IF NOT EXISTS actor_type TEXT DEFAULT 'system',
    ADD COLUMN IF NOT EXISTS resource_type TEXT DEFAULT 'system',
    ADD COLUMN IF NOT EXISTS resource_id UUID,
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
DECLARE
    col_type TEXT;
    legacy_col TEXT;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'audit_logs' AND column_name = 'actor_id';
    IF col_type IS NOT NULL AND col_type <> 'uuid' THEN
        ALTER TABLE public.audit_logs
            ALTER COLUMN actor_id TYPE UUID USING NULLIF(actor_id::text, '')::uuid;
    END IF;

    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'audit_logs' AND column_name = 'resource_id';
    IF col_type IS NOT NULL AND col_type <> 'uuid' THEN
        ALTER TABLE public.audit_logs
            ALTER COLUMN resource_id TYPE UUID USING NULLIF(resource_id::text, '')::uuid;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'audit_logs' AND column_name = 'details'
    ) THEN
        EXECUTE 'UPDATE public.audit_logs SET metadata = COALESCE(metadata, details, ''{}''::jsonb)';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'audit_logs' AND column_name = 'timestamp'
    ) THEN
        EXECUTE 'UPDATE public.audit_logs SET created_at = COALESCE(created_at, timestamp, NOW())';
    END IF;

    UPDATE public.audit_logs
    SET actor_type = COALESCE(actor_type, 'system'),
        resource_type = COALESCE(resource_type, 'system');

    ALTER TABLE public.audit_logs ALTER COLUMN tenant_id DROP NOT NULL;
    ALTER TABLE public.audit_logs ALTER COLUMN actor_type SET NOT NULL;
    ALTER TABLE public.audit_logs ALTER COLUMN resource_type SET NOT NULL;

    FOREACH legacy_col IN ARRAY ARRAY['details', 'severity', 'timestamp'] LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'audit_logs' AND column_name = legacy_col AND is_nullable = 'NO'
        ) THEN
            EXECUTE format('ALTER TABLE public.audit_logs ALTER COLUMN %I DROP NOT NULL', legacy_col);
        END IF;
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant ON public.audit_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON public.audit_logs(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON public.audit_logs(created_at);

-- 4.6 agent_tasks: ORM expects agent_id, task_type, input, output, priority, attempts, scheduled_at, started_at, completed_at, updated_at
ALTER TABLE public.agent_tasks
    ADD COLUMN IF NOT EXISTS agent_id UUID REFERENCES public.agent_registry(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS task_type TEXT,
    ADD COLUMN IF NOT EXISTS input JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS output JSONB,
    ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
DECLARE
    legacy_col TEXT;
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'agent_tasks' AND column_name = 'goal'
    ) THEN
        EXECUTE 'UPDATE public.agent_tasks SET task_type = COALESCE(task_type, goal, ''general_task'')';
    ELSE
        UPDATE public.agent_tasks SET task_type = COALESCE(task_type, 'general_task');
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'agent_tasks' AND column_name = 'input_context'
    ) THEN
        EXECUTE 'UPDATE public.agent_tasks SET input = COALESCE(input, input_context, ''{}''::jsonb)';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'agent_tasks' AND column_name = 'output_result'
    ) THEN
        EXECUTE 'UPDATE public.agent_tasks SET output = COALESCE(output, output_result)';
    END IF;

    ALTER TABLE public.agent_tasks ALTER COLUMN task_type SET NOT NULL;

    FOREACH legacy_col IN ARRAY ARRAY['agent_name', 'session_id', 'goal', 'input_context', 'output_result', 'model_used', 'tokens_used'] LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'agent_tasks' AND column_name = legacy_col AND is_nullable = 'NO'
        ) THEN
            EXECUTE format('ALTER TABLE public.agent_tasks ALTER COLUMN %I DROP NOT NULL', legacy_col);
        END IF;
    END LOOP;
END $$;

-- 4.7 approvals: ensure task_id & reviewed_by & rejection_reason columns align with ORM + migrations
ALTER TABLE public.approvals
    ADD COLUMN IF NOT EXISTS task_id UUID REFERENCES public.agent_tasks(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS reviewed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- 4.8 Other missing updated_at columns expected by TimestampMixin
ALTER TABLE public.tenants ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.tenant_members ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.services ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.service_subscriptions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.payments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.marketing_campaigns ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.agent_registry ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.integrations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- ------------------------------------------------------------------------------
-- 5. Reconcile CHECK constraints to match Python runtime values
-- ------------------------------------------------------------------------------
DO $$
DECLARE
    c RECORD;
    target_pair RECORD;
BEGIN
    -- Drop existing column-scoped check constraints cleanly before re-creating canonical ones
    FOR target_pair IN
        SELECT * FROM (VALUES
            ('tenants', 'status'),
            ('service_subscriptions', 'status'),
            ('payments', 'status'),
            ('invoices', 'status'),
            ('agent_tasks', 'status'),
            ('agent_executions', 'status'),
            ('approvals', 'status'),
            ('integrations', 'status'),
            ('audit_logs', 'actor_type')
        ) AS t(tbl_name, col_name)
    LOOP
        FOR c IN
            SELECT con.conname
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = ANY(con.conkey)
            WHERE nsp.nspname = 'public'
              AND rel.relname = target_pair.tbl_name
              AND att.attname = target_pair.col_name
              AND con.contype = 'c'
        LOOP
            EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT IF EXISTS %I', target_pair.tbl_name, c.conname);
        END LOOP;
    END LOOP;
END $$;

ALTER TABLE public.tenants
    ADD CONSTRAINT tenants_status_check
    CHECK (status IN ('pending_approval', 'active', 'suspended', 'pending_deletion', 'deleted', 'unpaid'));

ALTER TABLE public.service_subscriptions
    ADD CONSTRAINT service_subscriptions_status_check
    CHECK (status IN ('active', 'trialing', 'past_due', 'canceled', 'cancelled', 'suspended', 'pending_approval'));

ALTER TABLE public.payments
    ADD CONSTRAINT payments_status_check
    CHECK (status IN ('pending', 'pending_confirmation', 'completed', 'failed', 'refunded'));

ALTER TABLE public.invoices
    ADD CONSTRAINT invoices_status_check
    CHECK (status IN ('draft', 'issued', 'payment_pending', 'paid', 'overdue', 'void'));

ALTER TABLE public.agent_tasks
    ADD CONSTRAINT agent_tasks_status_check
    CHECK (status IN ('pending', 'queued', 'running', 'completed', 'failed', 'approval_required', 'awaiting_approval', 'canceled', 'cancelled'));

ALTER TABLE public.agent_executions
    ADD CONSTRAINT agent_executions_status_check
    CHECK (status IN ('running', 'success', 'completed', 'failed', 'timeout'));

ALTER TABLE public.approvals
    ADD CONSTRAINT approvals_status_check
    CHECK (status IN ('pending', 'approved', 'rejected', 'expired'));

ALTER TABLE public.integrations
    ADD CONSTRAINT integrations_status_check
    CHECK (status IN ('connected', 'disconnected', 'pending_approval', 'error'));

ALTER TABLE public.audit_logs
    ADD CONSTRAINT audit_logs_actor_type_check
    CHECK (actor_type IN ('user', 'agent', 'system', 'admin'));

-- ------------------------------------------------------------------------------
-- 6. Covering FK Indexes for Performance Advisor
-- ------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_service_subscriptions_service_id ON public.service_subscriptions(service_id);
CREATE INDEX IF NOT EXISTS idx_payments_subscription_id ON public.payments(subscription_id);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_agent_id ON public.agent_tasks(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_executions_agent_id ON public.agent_executions(agent_id);
CREATE INDEX IF NOT EXISTS idx_approvals_task_id ON public.approvals(task_id);
CREATE INDEX IF NOT EXISTS idx_approvals_reviewed_by ON public.approvals(reviewed_by);
CREATE INDEX IF NOT EXISTS idx_financial_transactions_account_id ON public.financial_transactions(account_id);

-- ------------------------------------------------------------------------------
-- 7. Security Helper Functions (Pinned search_path = public, UUID Signature)
-- ------------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.proname = 'handle_updated_at'
    ) THEN
        ALTER FUNCTION public.handle_updated_at() SET search_path = public;
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.is_super_admin()
RETURNS BOOLEAN
LANGUAGE sql
SECURITY INVOKER
SET search_path = public
STABLE
AS $$
  SELECT COALESCE(
    lower(COALESCE((SELECT auth.jwt()) ->> 'email', '')) IN (
      'talhazam4@gmail.com',
      'talhaazam4t@gmail.com',
      'talazam40@gmail.com'
    )
    OR ((SELECT auth.jwt()) -> 'app_metadata' ->> 'role') = 'super_admin',
    FALSE
  );
$$;

CREATE OR REPLACE FUNCTION public.is_tenant_member(target_tenant_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT (
    COALESCE(((SELECT auth.jwt()) -> 'app_metadata' ->> 'tenant_id') = target_tenant_id::text, FALSE)
    OR EXISTS (
      SELECT 1 FROM public.tenant_members
      WHERE tenant_id = target_tenant_id
        AND user_id = (SELECT auth.uid())
        AND status = 'active'
    )
  );
$$;

REVOKE EXECUTE ON FUNCTION public.is_super_admin() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.is_tenant_member(UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_super_admin() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.is_tenant_member(UUID) TO authenticated, service_role;

-- ------------------------------------------------------------------------------
-- 8. Enable RLS on all public tables & Create Advisor-Clean Policies
--    (Wrapped SELECT subqueries prevent auth_rls_initplan; single policy per
--     command prevents multiple_permissive_policies warnings.)
-- ------------------------------------------------------------------------------
ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.services ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.service_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.business_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.business_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.marketing_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.marketing_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.financial_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.financial_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rent_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.financial_audit_logs ENABLE ROW LEVEL SECURITY;

-- tenants
CREATE POLICY tenants_select ON public.tenants
    FOR SELECT TO authenticated
    USING ((SELECT public.is_tenant_member(id)) OR (SELECT public.is_super_admin()));

CREATE POLICY tenants_insert ON public.tenants
    FOR INSERT TO authenticated
    WITH CHECK ((SELECT auth.uid()) IS NOT NULL);

CREATE POLICY tenants_update ON public.tenants
    FOR UPDATE TO authenticated
    USING ((SELECT public.is_tenant_member(id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(id)) OR (SELECT public.is_super_admin()));

CREATE POLICY tenants_delete ON public.tenants
    FOR DELETE TO authenticated
    USING ((SELECT public.is_tenant_member(id)) OR (SELECT public.is_super_admin()));

-- profiles
CREATE POLICY profiles_select ON public.profiles
    FOR SELECT TO authenticated
    USING (id = (SELECT auth.uid()) OR (SELECT public.is_super_admin()));

CREATE POLICY profiles_insert ON public.profiles
    FOR INSERT TO authenticated
    WITH CHECK (id = (SELECT auth.uid()) OR (SELECT public.is_super_admin()));

CREATE POLICY profiles_update ON public.profiles
    FOR UPDATE TO authenticated
    USING (id = (SELECT auth.uid()) OR (SELECT public.is_super_admin()))
    WITH CHECK (id = (SELECT auth.uid()) OR (SELECT public.is_super_admin()));

-- services (publicly readable catalog for authenticated users; admin-only writes)
CREATE POLICY services_select ON public.services
    FOR SELECT TO authenticated
    USING (active = TRUE OR (SELECT public.is_super_admin()));

CREATE POLICY services_insert ON public.services
    FOR INSERT TO authenticated
    WITH CHECK ((SELECT public.is_super_admin()));

CREATE POLICY services_update ON public.services
    FOR UPDATE TO authenticated
    USING ((SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_super_admin()));

CREATE POLICY services_delete ON public.services
    FOR DELETE TO authenticated
    USING ((SELECT public.is_super_admin()));

-- agent_registry & agent_permissions
CREATE POLICY agent_registry_select ON public.agent_registry
    FOR SELECT TO authenticated
    USING (TRUE);

CREATE POLICY agent_registry_insert ON public.agent_registry
    FOR INSERT TO authenticated
    WITH CHECK ((SELECT public.is_super_admin()));

CREATE POLICY agent_registry_update ON public.agent_registry
    FOR UPDATE TO authenticated
    USING ((SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_super_admin()));

CREATE POLICY agent_permissions_select ON public.agent_permissions
    FOR SELECT TO authenticated
    USING (TRUE);

CREATE POLICY agent_permissions_insert ON public.agent_permissions
    FOR INSERT TO authenticated
    WITH CHECK ((SELECT public.is_super_admin()));

CREATE POLICY agent_permissions_update ON public.agent_permissions
    FOR UPDATE TO authenticated
    USING ((SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_super_admin()));

-- Tenant-scoped tables (single ALL policy per table, initplan-safe)
CREATE POLICY tenant_members_isolation ON public.tenant_members
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR user_id = (SELECT auth.uid()) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR user_id = (SELECT auth.uid()) OR (SELECT public.is_super_admin()));

CREATE POLICY service_subscriptions_isolation ON public.service_subscriptions
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY payments_isolation ON public.payments
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY invoices_isolation ON public.invoices
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY business_records_isolation ON public.business_records
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY business_metrics_isolation ON public.business_metrics
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY leads_isolation ON public.leads
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY marketing_campaigns_isolation ON public.marketing_campaigns
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY marketing_metrics_isolation ON public.marketing_metrics
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY tenant_agents_isolation ON public.tenant_agents
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY agent_tasks_isolation ON public.agent_tasks
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY agent_executions_isolation ON public.agent_executions
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY approvals_isolation ON public.approvals
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY integrations_isolation ON public.integrations
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY notifications_isolation ON public.notifications
    FOR ALL TO authenticated
    USING (((SELECT public.is_tenant_member(tenant_id)) AND (user_id IS NULL OR user_id = (SELECT auth.uid()))) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY audit_logs_select ON public.audit_logs
    FOR SELECT TO authenticated
    USING ((tenant_id IS NOT NULL AND (SELECT public.is_tenant_member(tenant_id))) OR (SELECT public.is_super_admin()));

CREATE POLICY audit_logs_insert ON public.audit_logs
    FOR INSERT TO authenticated
    WITH CHECK ((tenant_id IS NOT NULL AND (SELECT public.is_tenant_member(tenant_id))) OR (SELECT public.is_super_admin()));

CREATE POLICY usage_records_isolation ON public.usage_records
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY financial_accounts_isolation ON public.financial_accounts
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY financial_transactions_isolation ON public.financial_transactions
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY rent_schedules_isolation ON public.rent_schedules
    FOR ALL TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY financial_audit_logs_select ON public.financial_audit_logs
    FOR SELECT TO authenticated
    USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

CREATE POLICY financial_audit_logs_insert ON public.financial_audit_logs
    FOR INSERT TO authenticated
    WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

-- Legacy / auxiliary tables in public schema
ALTER TABLE IF EXISTS public.appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.consent_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.human_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.tool_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.workflow_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.outreach_leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.approval_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.client_playbooks ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF to_regclass('public.appointments') IS NOT NULL THEN
        EXECUTE 'CREATE POLICY appointments_isolation ON public.appointments FOR ALL TO authenticated USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin())) WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))';
    END IF;
    IF to_regclass('public.consent_records') IS NOT NULL THEN
        EXECUTE 'CREATE POLICY consent_records_isolation ON public.consent_records FOR ALL TO authenticated USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin())) WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))';
    END IF;
    IF to_regclass('public.customers') IS NOT NULL THEN
        EXECUTE 'CREATE POLICY customers_isolation ON public.customers FOR ALL TO authenticated USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin())) WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))';
    END IF;
    IF to_regclass('public.human_tasks') IS NOT NULL THEN
        EXECUTE 'CREATE POLICY human_tasks_isolation ON public.human_tasks FOR ALL TO authenticated USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin())) WITH CHECK ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))';
    END IF;
    IF to_regclass('public.tool_executions') IS NOT NULL THEN
        EXECUTE 'CREATE POLICY tool_executions_select ON public.tool_executions FOR SELECT TO authenticated USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))';
    END IF;
    IF to_regclass('public.workflow_executions') IS NOT NULL THEN
        EXECUTE 'CREATE POLICY workflow_executions_select ON public.workflow_executions FOR SELECT TO authenticated USING ((SELECT public.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()))';
    END IF;
    IF to_regclass('public.outreach_leads') IS NOT NULL THEN
        EXECUTE 'CREATE POLICY outreach_leads_isolation ON public.outreach_leads FOR ALL TO authenticated USING ((tenant_id = (SELECT auth.jwt() ->> ''tenant_id'')) OR (tenant_id = (SELECT COALESCE(current_setting(''app.current_tenant_id'', true), ''''))) OR (tenant_id = ''teloxtech_internal'') OR (SELECT public.is_super_admin())) WITH CHECK ((tenant_id = (SELECT auth.jwt() ->> ''tenant_id'')) OR (tenant_id = (SELECT COALESCE(current_setting(''app.current_tenant_id'', true), ''''))) OR (tenant_id = ''teloxtech_internal'') OR (SELECT public.is_super_admin()))';
    END IF;
    IF to_regclass('public.approval_tasks') IS NOT NULL THEN
        EXECUTE 'CREATE POLICY approval_tasks_admin ON public.approval_tasks FOR ALL TO authenticated USING ((SELECT public.is_super_admin())) WITH CHECK ((SELECT public.is_super_admin()))';
    END IF;
    IF to_regclass('public.client_playbooks') IS NOT NULL THEN
        EXECUTE 'CREATE POLICY client_playbooks_admin ON public.client_playbooks FOR ALL TO authenticated USING ((SELECT public.is_super_admin())) WITH CHECK ((SELECT public.is_super_admin()))';
    END IF;
END $$;
