-- Operations Console Database Enhancements & Full RLS Hardening
-- Adds/ensures tables for Subscriptions, Payments, Marketing Campaigns, Tenant Agents,
-- Agent Executions, Approvals, Integrations, Notifications, and Usage Records.

-- 1. Tenants default status
ALTER TABLE IF EXISTS public.tenants
    ALTER COLUMN status SET DEFAULT 'pending_approval';

-- 2. Service Subscriptions
CREATE TABLE IF NOT EXISTS public.service_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    service_id UUID NOT NULL REFERENCES public.services(id) ON DELETE RESTRICT,
    plan_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'trialing', 'past_due', 'canceled', 'suspended', 'pending_approval')),
    price NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    billing_interval TEXT NOT NULL CHECK (billing_interval IN ('monthly', 'annual', 'one_time')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Payments
CREATE TABLE IF NOT EXISTS public.payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES public.service_subscriptions(id) ON DELETE SET NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    currency TEXT NOT NULL DEFAULT 'USD',
    payment_method TEXT NOT NULL,
    provider_reference TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Marketing Campaigns & Metrics
CREATE TABLE IF NOT EXISTS public.marketing_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    platform TEXT NOT NULL,
    objective TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'pending_approval', 'active', 'paused', 'completed')),
    budget NUMERIC NOT NULL DEFAULT 0,
    start_date DATE,
    end_date DATE,
    configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.marketing_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    campaign_id UUID NOT NULL REFERENCES public.marketing_campaigns(id) ON DELETE CASCADE,
    impressions BIGINT NOT NULL DEFAULT 0,
    clicks BIGINT NOT NULL DEFAULT 0,
    leads BIGINT NOT NULL DEFAULT 0,
    conversions BIGINT NOT NULL DEFAULT 0,
    spend NUMERIC NOT NULL DEFAULT 0,
    revenue NUMERIC NOT NULL DEFAULT 0,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Tenant Agents & Executions
CREATE TABLE IF NOT EXISTS public.tenant_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES public.agent_registry(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
    execution_limit INTEGER NOT NULL DEFAULT 1000,
    budget_limit NUMERIC NOT NULL DEFAULT 50.00,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, agent_id)
);

CREATE TABLE IF NOT EXISTS public.agent_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    task_id UUID NOT NULL REFERENCES public.agent_tasks(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES public.agent_registry(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'timeout')),
    tokens_used BIGINT NOT NULL DEFAULT 0,
    estimated_cost NUMERIC(10, 6) NOT NULL DEFAULT 0,
    duration_ms BIGINT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. Approvals Gate
CREATE TABLE IF NOT EXISTS public.approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    proposed_action JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    requested_by TEXT NOT NULL,
    reviewed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    rejection_reason TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. Integrations (OAuth & Credential Governance)
CREATE TABLE IF NOT EXISTS public.integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    integration_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'disconnected' CHECK (status IN ('connected', 'disconnected', 'pending_approval', 'error')),
    external_account_id TEXT,
    configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 8. Notifications & Usage Records
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
    channel TEXT NOT NULL CHECK (channel IN ('in_app', 'email', 'whatsapp')),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unread' CHECK (status IN ('unread', 'read', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    estimated_cost NUMERIC(10, 6) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant ON public.service_subscriptions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_payments_tenant ON public.payments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_tenant ON public.marketing_campaigns(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_agents_tenant ON public.tenant_agents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agent_executions_tenant ON public.agent_executions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_approvals_tenant ON public.approvals(tenant_id);
CREATE INDEX IF NOT EXISTS idx_integrations_tenant ON public.integrations(tenant_id);
CREATE INDEX IF NOT EXISTS idx_usage_records_tenant ON public.usage_records(tenant_id);

-- Enable RLS
ALTER TABLE public.service_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.marketing_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.marketing_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_records ENABLE ROW LEVEL SECURITY;

-- Policies for Authenticated & Sole Administrator
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'service_subscriptions' AND policyname = 'service_subscriptions_select') THEN
        CREATE POLICY service_subscriptions_select ON public.service_subscriptions FOR SELECT TO authenticated USING (is_tenant_member(tenant_id) OR is_super_admin());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'service_subscriptions' AND policyname = 'service_subscriptions_mod') THEN
        CREATE POLICY service_subscriptions_mod ON public.service_subscriptions FOR ALL TO authenticated USING (is_tenant_member(tenant_id) OR is_super_admin()) WITH CHECK (is_tenant_member(tenant_id) OR is_super_admin());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'payments' AND policyname = 'payments_select') THEN
        CREATE POLICY payments_select ON public.payments FOR SELECT TO authenticated USING (is_tenant_member(tenant_id) OR is_super_admin());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'payments' AND policyname = 'payments_mod') THEN
        CREATE POLICY payments_mod ON public.payments FOR ALL TO authenticated USING (is_tenant_member(tenant_id) OR is_super_admin()) WITH CHECK (is_tenant_member(tenant_id) OR is_super_admin());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'marketing_campaigns' AND policyname = 'marketing_campaigns_select') THEN
        CREATE POLICY marketing_campaigns_select ON public.marketing_campaigns FOR SELECT TO authenticated USING (is_tenant_member(tenant_id) OR is_super_admin());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'marketing_campaigns' AND policyname = 'marketing_campaigns_mod') THEN
        CREATE POLICY marketing_campaigns_mod ON public.marketing_campaigns FOR ALL TO authenticated USING (is_tenant_member(tenant_id) OR is_super_admin()) WITH CHECK (is_tenant_member(tenant_id) OR is_super_admin());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'approvals' AND policyname = 'approvals_select') THEN
        CREATE POLICY approvals_select ON public.approvals FOR SELECT TO authenticated USING (is_tenant_member(tenant_id) OR is_super_admin());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'approvals' AND policyname = 'approvals_mod') THEN
        CREATE POLICY approvals_mod ON public.approvals FOR ALL TO authenticated USING (is_tenant_member(tenant_id) OR is_super_admin()) WITH CHECK (is_tenant_member(tenant_id) OR is_super_admin());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'integrations' AND policyname = 'integrations_select') THEN
        CREATE POLICY integrations_select ON public.integrations FOR SELECT TO authenticated USING (is_tenant_member(tenant_id) OR is_super_admin());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'integrations' AND policyname = 'integrations_mod') THEN
        CREATE POLICY integrations_mod ON public.integrations FOR ALL TO authenticated USING (is_tenant_member(tenant_id) OR is_super_admin()) WITH CHECK (is_tenant_member(tenant_id) OR is_super_admin());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'agent_executions' AND policyname = 'agent_executions_select') THEN
        CREATE POLICY agent_executions_select ON public.agent_executions FOR SELECT TO authenticated USING (is_tenant_member(tenant_id) OR is_super_admin());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'usage_records' AND policyname = 'usage_records_select') THEN
        CREATE POLICY usage_records_select ON public.usage_records FOR SELECT TO authenticated USING (is_tenant_member(tenant_id) OR is_super_admin());
    END IF;
END $$;
