-- ==============================================================================
-- TALOX TECH STREAM — Financial & Rent Tracking Schema Migration v1.1
-- Multi-Tenant Accounts, Transactions, Rent Schedules, and Audit Logs
-- ==============================================================================

-- 1. Helper security functions for multi-tenant and sole admin isolation
CREATE OR REPLACE FUNCTION public.is_super_admin()
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT COALESCE(
    (auth.jwt() ->> 'email') IN ('talazam40@gmail.com', 'talhazam4@gmail.com', 'talhaazam4t@gmail.com')
    OR (auth.jwt() -> 'app_metadata' ->> 'role') = 'super_admin'
    OR (auth.jwt() -> 'user_metadata' ->> 'is_super_admin') = 'true',
    FALSE
  );
$$;

CREATE OR REPLACE FUNCTION public.is_tenant_member(target_tenant_id TEXT)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT (
    COALESCE(auth.jwt() -> 'app_metadata' ->> 'tenant_id' = target_tenant_id, FALSE)
    OR EXISTS (
      SELECT 1 FROM public.tenant_members
      WHERE tenant_id = target_tenant_id
        AND user_id = auth.uid()
        AND status = 'active'
    )
  );
$$;

-- Restrict function execution to authenticated users
REVOKE EXECUTE ON FUNCTION public.is_super_admin() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.is_tenant_member(text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_super_admin() TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_tenant_member(text) TO authenticated;

-- 2. financial_accounts Table
CREATE TABLE IF NOT EXISTS public.financial_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    current_balance NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_financial_accounts_tenant ON public.financial_accounts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_financial_accounts_tenant_currency ON public.financial_accounts(tenant_id, currency);

-- 3. financial_transactions Table
CREATE TABLE IF NOT EXISTS public.financial_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    account_id UUID REFERENCES public.financial_accounts(id) ON DELETE SET NULL,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense', 'rent')),
    category TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL DEFAULT 'paid' CHECK (status IN ('paid', 'pending', 'overdue')),
    transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,
    due_date DATE,
    counterparty_name TEXT NOT NULL,
    notes TEXT,
    receipt_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_financial_transactions_tenant ON public.financial_transactions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_financial_transactions_account ON public.financial_transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_financial_transactions_status ON public.financial_transactions(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_financial_transactions_date ON public.financial_transactions(tenant_id, transaction_date DESC);

-- 4. rent_schedules Table
CREATE TABLE IF NOT EXISTS public.rent_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    property_unit TEXT NOT NULL,
    lessee_name TEXT NOT NULL,
    lessee_whatsapp TEXT NOT NULL,
    monthly_rent NUMERIC(14, 2) NOT NULL CHECK (monthly_rent > 0),
    currency TEXT NOT NULL DEFAULT 'PKR',
    billing_day INTEGER NOT NULL DEFAULT 1 CHECK (billing_day >= 1 AND billing_day <= 31),
    auto_remind_whatsapp BOOLEAN NOT NULL DEFAULT TRUE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'vacant')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rent_schedules_tenant ON public.rent_schedules(tenant_id);
CREATE INDEX IF NOT EXISTS idx_rent_schedules_status ON public.rent_schedules(tenant_id, status);

-- 5. financial_audit_logs Table (Immutable)
CREATE TABLE IF NOT EXISTS public.financial_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    diff_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_financial_audit_logs_tenant ON public.financial_audit_logs(tenant_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_financial_audit_logs_user ON public.financial_audit_logs(user_id);

-- Enable Row Level Security (RLS) on all 4 tables
ALTER TABLE public.financial_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.financial_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rent_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.financial_audit_logs ENABLE ROW LEVEL SECURITY;

-- Policies for financial_accounts
CREATE POLICY financial_accounts_select ON public.financial_accounts
    FOR SELECT TO authenticated
    USING (public.is_tenant_member(tenant_id) OR public.is_super_admin());

CREATE POLICY financial_accounts_insert ON public.financial_accounts
    FOR INSERT TO authenticated
    WITH CHECK (public.is_tenant_member(tenant_id));

CREATE POLICY financial_accounts_update ON public.financial_accounts
    FOR UPDATE TO authenticated
    USING (public.is_tenant_member(tenant_id))
    WITH CHECK (public.is_tenant_member(tenant_id));

CREATE POLICY financial_accounts_delete ON public.financial_accounts
    FOR DELETE TO authenticated
    USING (public.is_tenant_member(tenant_id));

-- Policies for financial_transactions
CREATE POLICY financial_transactions_select ON public.financial_transactions
    FOR SELECT TO authenticated
    USING (public.is_tenant_member(tenant_id) OR public.is_super_admin());

CREATE POLICY financial_transactions_insert ON public.financial_transactions
    FOR INSERT TO authenticated
    WITH CHECK (public.is_tenant_member(tenant_id));

CREATE POLICY financial_transactions_update ON public.financial_transactions
    FOR UPDATE TO authenticated
    USING (public.is_tenant_member(tenant_id))
    WITH CHECK (public.is_tenant_member(tenant_id));

CREATE POLICY financial_transactions_delete ON public.financial_transactions
    FOR DELETE TO authenticated
    USING (public.is_tenant_member(tenant_id));

-- Policies for rent_schedules
CREATE POLICY rent_schedules_select ON public.rent_schedules
    FOR SELECT TO authenticated
    USING (public.is_tenant_member(tenant_id) OR public.is_super_admin());

CREATE POLICY rent_schedules_insert ON public.rent_schedules
    FOR INSERT TO authenticated
    WITH CHECK (public.is_tenant_member(tenant_id));

CREATE POLICY rent_schedules_update ON public.rent_schedules
    FOR UPDATE TO authenticated
    USING (public.is_tenant_member(tenant_id))
    WITH CHECK (public.is_tenant_member(tenant_id));

CREATE POLICY rent_schedules_delete ON public.rent_schedules
    FOR DELETE TO authenticated
    USING (public.is_tenant_member(tenant_id));

-- Policies for financial_audit_logs (Immutable log)
CREATE POLICY financial_audit_logs_select ON public.financial_audit_logs
    FOR SELECT TO authenticated
    USING (public.is_tenant_member(tenant_id) OR public.is_super_admin());

CREATE POLICY financial_audit_logs_insert ON public.financial_audit_logs
    FOR INSERT TO authenticated
    WITH CHECK (public.is_tenant_member(tenant_id));
