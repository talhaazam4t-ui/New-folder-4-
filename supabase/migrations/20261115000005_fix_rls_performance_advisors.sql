-- ==============================================================================
-- TALOX TECH STREAM — Database Performance Remediation Migration v1.5
-- Fixes auth_rls_initplan warnings by subquery wrapping and eliminates duplicate permissive policies
-- ==============================================================================

-- 1. Remove duplicate permissive SELECT policies (covered by corresponding *_mod ALL policies)
DROP POLICY IF EXISTS approvals_select ON public.approvals;
DROP POLICY IF EXISTS integrations_select ON public.integrations;
DROP POLICY IF EXISTS marketing_campaigns_select ON public.marketing_campaigns;
DROP POLICY IF EXISTS payments_select ON public.payments;
DROP POLICY IF EXISTS service_subscriptions_select ON public.service_subscriptions;

-- 2. Optimize RLS evaluation plans by wrapping auth.jwt() and current_setting() in subqueries (SELECT ...)

-- 2.1 tenants
DROP POLICY IF EXISTS "Tenant isolation for tenants" ON public.tenants;
CREATE POLICY "Tenant isolation for tenants" ON public.tenants
FOR SELECT TO authenticated
USING (
    (id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
);

-- 2.2 customers
DROP POLICY IF EXISTS "Tenant isolation for customers" ON public.customers;
CREATE POLICY "Tenant isolation for customers" ON public.customers
FOR ALL TO authenticated
USING (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
)
WITH CHECK (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
);

-- 2.3 leads
DROP POLICY IF EXISTS "Tenant isolation for leads" ON public.leads;
CREATE POLICY "Tenant isolation for leads" ON public.leads
FOR ALL TO authenticated
USING (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
)
WITH CHECK (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
);

-- 2.4 appointments
DROP POLICY IF EXISTS "Tenant isolation for appointments" ON public.appointments;
CREATE POLICY "Tenant isolation for appointments" ON public.appointments
FOR ALL TO authenticated
USING (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
)
WITH CHECK (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
);

-- 2.5 invoices
DROP POLICY IF EXISTS "Tenant isolation for invoices" ON public.invoices;
CREATE POLICY "Tenant isolation for invoices" ON public.invoices
FOR ALL TO authenticated
USING (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
)
WITH CHECK (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
);

-- 2.6 consent_records
DROP POLICY IF EXISTS "Tenant isolation for consent_records" ON public.consent_records;
CREATE POLICY "Tenant isolation for consent_records" ON public.consent_records
FOR ALL TO authenticated
USING (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
)
WITH CHECK (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
);

-- 2.7 workflow_executions
DROP POLICY IF EXISTS "Tenant isolation for workflow_executions" ON public.workflow_executions;
CREATE POLICY "Tenant isolation for workflow_executions" ON public.workflow_executions
FOR SELECT TO authenticated
USING (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
);

-- 2.8 audit_logs
DROP POLICY IF EXISTS "Tenant isolation for audit_logs" ON public.audit_logs;
CREATE POLICY "Tenant isolation for audit_logs" ON public.audit_logs
FOR SELECT TO authenticated
USING (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
);

-- 2.9 agent_tasks
DROP POLICY IF EXISTS "Tenant isolation for agent_tasks" ON public.agent_tasks;
CREATE POLICY "Tenant isolation for agent_tasks" ON public.agent_tasks
FOR ALL TO authenticated
USING (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
)
WITH CHECK (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
);

-- 2.10 human_tasks
DROP POLICY IF EXISTS "Tenant isolation for human_tasks" ON public.human_tasks;
CREATE POLICY "Tenant isolation for human_tasks" ON public.human_tasks
FOR ALL TO authenticated
USING (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
)
WITH CHECK (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
);

-- 2.11 tool_executions
DROP POLICY IF EXISTS "Tenant isolation for tool_executions" ON public.tool_executions;
CREATE POLICY "Tenant isolation for tool_executions" ON public.tool_executions
FOR SELECT TO authenticated
USING (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
);

-- 2.12 outreach_leads
DROP POLICY IF EXISTS "Tenant isolation for outreach_leads" ON public.outreach_leads;
CREATE POLICY "Tenant isolation for outreach_leads" ON public.outreach_leads
FOR ALL TO authenticated
USING (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
    OR (tenant_id = 'teloxtech_internal')
)
WITH CHECK (
    (tenant_id = (SELECT auth.jwt() ->> 'tenant_id'))
    OR (tenant_id = (SELECT COALESCE(current_setting('app.current_tenant_id', true), '')))
    OR (tenant_id = 'teloxtech_internal')
);
