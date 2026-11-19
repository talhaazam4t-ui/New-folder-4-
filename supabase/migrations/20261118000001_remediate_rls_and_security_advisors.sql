-- ==============================================================================
-- TALOX TECH STREAM — RLS, Security & Performance Advisor Remediation Migration
-- Targets live project pmmduhflikdvddzpgwsi:
--   1. Moves SECURITY DEFINER RLS helper functions to non-exposed `private` schema
--      (clears 0028_anon_* and 0029_authenticated_* without breaking RLS).
--   2. Revokes public/anon/authenticated EXECUTE on get_tenant_subscription_tier.
--   3. Replaces overly broad `public.profiles` policies (anon/authenticated true).
--   4. Fixes `auth_rls_initplan` and internal-tenant exposure on `outreach_leads`.
--   5. Drops 3 duplicate indexes, consolidates 10 multiple-permissive policies,
--      converts legacy `{public}` policies to `TO authenticated`, and adds 4 FK indexes.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Non-exposed `private` schema & SECURITY DEFINER RLS helpers
-- ------------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS private;

REVOKE ALL ON SCHEMA private FROM PUBLIC, anon;
GRANT USAGE ON SCHEMA private TO authenticated, service_role;

CREATE OR REPLACE FUNCTION private.is_tenant_member(target_tenant_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT (
    COALESCE((SELECT auth.jwt()) -> 'app_metadata' ->> 'tenant_id', '') = target_tenant_id::text
    OR EXISTS (
      SELECT 1
      FROM public.tenant_members
      WHERE tenant_id = target_tenant_id
        AND user_id = (SELECT auth.uid())
        AND status = 'active'
    )
  );
$$;

CREATE OR REPLACE FUNCTION private.is_tenant_admin(target_tenant_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.tenant_members
    WHERE tenant_id = target_tenant_id
      AND user_id = (SELECT auth.uid())
      AND status = 'active'
      AND role IN ('owner', 'admin', 'billing_admin')
  );
$$;

CREATE OR REPLACE FUNCTION private.get_user_tenant_ids()
RETURNS SETOF UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT tenant_id
  FROM public.tenant_members
  WHERE user_id = (SELECT auth.uid())
    AND status = 'active';
$$;

REVOKE ALL ON FUNCTION private.is_tenant_member(UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.is_tenant_admin(UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.get_user_tenant_ids() FROM PUBLIC, anon;

GRANT EXECUTE ON FUNCTION private.is_tenant_member(UUID) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.is_tenant_admin(UUID) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.get_user_tenant_ids() TO authenticated, service_role;

-- Harden public.is_super_admin() (initPlan-safe auth.jwt(), SECURITY INVOKER)
CREATE OR REPLACE FUNCTION public.is_super_admin()
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
  SELECT (
    COALESCE(
      lower((SELECT auth.jwt()) ->> 'email') IN (
        'talazam40@gmail.com',
        'talhazam4@gmail.com',
        'talhaazam4t@gmail.com'
      ),
      FALSE
    )
    OR COALESCE(
      ((SELECT auth.jwt()) -> 'app_metadata' ->> 'role') = 'super_admin',
      FALSE
    )
  );
$$;

REVOKE ALL ON FUNCTION public.is_super_admin() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_super_admin() TO authenticated, service_role;

-- Unused SECURITY DEFINER function in public: restrict strictly to service_role
DO $$
BEGIN
    IF to_regprocedure('public.get_tenant_subscription_tier(uuid)') IS NOT NULL THEN
        REVOKE ALL ON FUNCTION public.get_tenant_subscription_tier(UUID) FROM PUBLIC, anon, authenticated;
        GRANT EXECUTE ON FUNCTION public.get_tenant_subscription_tier(UUID) TO service_role;
    END IF;
END $$;

-- ------------------------------------------------------------------------------
-- 2. Re-bind all RLS policies from `public.*` helpers to `private.*` helpers
--    and eliminate multiple permissive policies + `{public}` role leakage
-- ------------------------------------------------------------------------------

-- 2.1 tenants
DROP POLICY IF EXISTS tenant_read_policy ON public.tenants;
DROP POLICY IF EXISTS tenant_members_select_tenant ON public.tenants;
DROP POLICY IF EXISTS tenants_select ON public.tenants;
DROP POLICY IF EXISTS "Tenant isolation for tenants" ON public.tenants;
CREATE POLICY "Tenant isolation for tenants" ON public.tenants
    FOR SELECT TO authenticated
    USING (private.is_tenant_member(id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS tenant_admins_update_tenant ON public.tenants;
DROP POLICY IF EXISTS tenants_update ON public.tenants;
DROP POLICY IF EXISTS tenants_delete ON public.tenants;
CREATE POLICY tenant_admins_update_tenant ON public.tenants
    FOR UPDATE TO authenticated
    USING (private.is_tenant_admin(id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_admin(id) OR (SELECT public.is_super_admin()));

-- 2.2 tenant_members (consolidates 3 overlapping policies into per-command policies)
DROP POLICY IF EXISTS tenant_admins_manage_members ON public.tenant_members;
DROP POLICY IF EXISTS tenant_members_policy ON public.tenant_members;
DROP POLICY IF EXISTS tenant_members_select_roster ON public.tenant_members;
DROP POLICY IF EXISTS tenant_members_isolation ON public.tenant_members;
DROP POLICY IF EXISTS tenant_members_select ON public.tenant_members;
DROP POLICY IF EXISTS tenant_members_insert ON public.tenant_members;
DROP POLICY IF EXISTS tenant_members_update ON public.tenant_members;
DROP POLICY IF EXISTS tenant_members_delete ON public.tenant_members;

CREATE POLICY tenant_members_select ON public.tenant_members
    FOR SELECT TO authenticated
    USING (
        private.is_tenant_member(tenant_id)
        OR user_id = (SELECT auth.uid())
        OR (SELECT public.is_super_admin())
    );

CREATE POLICY tenant_members_insert ON public.tenant_members
    FOR INSERT TO authenticated
    WITH CHECK (private.is_tenant_admin(tenant_id) OR (SELECT public.is_super_admin()));

CREATE POLICY tenant_members_update ON public.tenant_members
    FOR UPDATE TO authenticated
    USING (private.is_tenant_admin(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_admin(tenant_id) OR (SELECT public.is_super_admin()));

CREATE POLICY tenant_members_delete ON public.tenant_members
    FOR DELETE TO authenticated
    USING (private.is_tenant_admin(tenant_id) OR (SELECT public.is_super_admin()));

-- 2.3 Drop 5 redundant *_select policies covered by *_mod (FOR ALL) & rebind *_mod
DROP POLICY IF EXISTS approvals_isolation ON public.approvals;
DROP POLICY IF EXISTS approvals_select ON public.approvals;
DROP POLICY IF EXISTS approvals_mod ON public.approvals;
CREATE POLICY approvals_mod ON public.approvals
    FOR ALL TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS integrations_isolation ON public.integrations;
DROP POLICY IF EXISTS integrations_select ON public.integrations;
DROP POLICY IF EXISTS integrations_mod ON public.integrations;
CREATE POLICY integrations_mod ON public.integrations
    FOR ALL TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS marketing_campaigns_isolation ON public.marketing_campaigns;
DROP POLICY IF EXISTS marketing_campaigns_select ON public.marketing_campaigns;
DROP POLICY IF EXISTS marketing_campaigns_mod ON public.marketing_campaigns;
CREATE POLICY marketing_campaigns_mod ON public.marketing_campaigns
    FOR ALL TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS payments_isolation ON public.payments;
DROP POLICY IF EXISTS payments_select ON public.payments;
DROP POLICY IF EXISTS payments_mod ON public.payments;
CREATE POLICY payments_mod ON public.payments
    FOR ALL TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS subscriptions_isolation ON public.service_subscriptions;
DROP POLICY IF EXISTS service_subscriptions_isolation ON public.service_subscriptions;
DROP POLICY IF EXISTS service_subscriptions_select ON public.service_subscriptions;
DROP POLICY IF EXISTS service_subscriptions_mod ON public.service_subscriptions;
CREATE POLICY service_subscriptions_mod ON public.service_subscriptions
    FOR ALL TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

-- 2.4 Remaining standard tenant-scoped tables (rebound to private.is_tenant_member)
DROP POLICY IF EXISTS agent_executions_isolation ON public.agent_executions;
DROP POLICY IF EXISTS agent_executions_select ON public.agent_executions;
CREATE POLICY agent_executions_select ON public.agent_executions
    FOR SELECT TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS agent_tasks_isolation ON public.agent_tasks;
DROP POLICY IF EXISTS "Tenant isolation for agent_tasks" ON public.agent_tasks;
CREATE POLICY "Tenant isolation for agent_tasks" ON public.agent_tasks
    FOR ALL TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS audit_logs_select ON public.audit_logs;
DROP POLICY IF EXISTS audit_logs_insert ON public.audit_logs;
DROP POLICY IF EXISTS "Tenant isolation for audit_logs" ON public.audit_logs;
CREATE POLICY "Tenant isolation for audit_logs" ON public.audit_logs
    FOR SELECT TO authenticated
    USING ((tenant_id IS NOT NULL AND private.is_tenant_member(tenant_id)) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS business_metrics_isolation ON public.business_metrics;
CREATE POLICY business_metrics_isolation ON public.business_metrics
    FOR ALL TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS business_records_isolation ON public.business_records;
CREATE POLICY business_records_isolation ON public.business_records
    FOR ALL TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS financial_accounts_isolation ON public.financial_accounts;
DROP POLICY IF EXISTS financial_accounts_select ON public.financial_accounts;
DROP POLICY IF EXISTS financial_accounts_insert ON public.financial_accounts;
DROP POLICY IF EXISTS financial_accounts_update ON public.financial_accounts;
DROP POLICY IF EXISTS financial_accounts_delete ON public.financial_accounts;
CREATE POLICY financial_accounts_select ON public.financial_accounts
    FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
CREATE POLICY financial_accounts_insert ON public.financial_accounts
    FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
CREATE POLICY financial_accounts_update ON public.financial_accounts
    FOR UPDATE TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
CREATE POLICY financial_accounts_delete ON public.financial_accounts
    FOR DELETE TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS financial_audit_logs_select ON public.financial_audit_logs;
DROP POLICY IF EXISTS financial_audit_logs_insert ON public.financial_audit_logs;
CREATE POLICY financial_audit_logs_select ON public.financial_audit_logs
    FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
CREATE POLICY financial_audit_logs_insert ON public.financial_audit_logs
    FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS financial_transactions_isolation ON public.financial_transactions;
DROP POLICY IF EXISTS financial_transactions_select ON public.financial_transactions;
DROP POLICY IF EXISTS financial_transactions_insert ON public.financial_transactions;
DROP POLICY IF EXISTS financial_transactions_update ON public.financial_transactions;
DROP POLICY IF EXISTS financial_transactions_delete ON public.financial_transactions;
CREATE POLICY financial_transactions_select ON public.financial_transactions
    FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
CREATE POLICY financial_transactions_insert ON public.financial_transactions
    FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
CREATE POLICY financial_transactions_update ON public.financial_transactions
    FOR UPDATE TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
CREATE POLICY financial_transactions_delete ON public.financial_transactions
    FOR DELETE TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS invoices_isolation ON public.invoices;
DROP POLICY IF EXISTS "Tenant isolation for invoices" ON public.invoices;
CREATE POLICY "Tenant isolation for invoices" ON public.invoices
    FOR ALL TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS leads_isolation ON public.leads;
DROP POLICY IF EXISTS "Tenant isolation for leads" ON public.leads;
CREATE POLICY "Tenant isolation for leads" ON public.leads
    FOR ALL TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS marketing_metrics_isolation ON public.marketing_metrics;
DROP POLICY IF EXISTS marketing_metrics_select ON public.marketing_metrics;
DROP POLICY IF EXISTS marketing_metrics_insert ON public.marketing_metrics;
CREATE POLICY marketing_metrics_select ON public.marketing_metrics
    FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
CREATE POLICY marketing_metrics_insert ON public.marketing_metrics
    FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS notifications_isolation ON public.notifications;
DROP POLICY IF EXISTS notifications_select ON public.notifications;
DROP POLICY IF EXISTS notifications_insert ON public.notifications;
CREATE POLICY notifications_select ON public.notifications
    FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
CREATE POLICY notifications_insert ON public.notifications
    FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS rent_schedules_isolation ON public.rent_schedules;
DROP POLICY IF EXISTS rent_schedules_select ON public.rent_schedules;
DROP POLICY IF EXISTS rent_schedules_insert ON public.rent_schedules;
DROP POLICY IF EXISTS rent_schedules_update ON public.rent_schedules;
DROP POLICY IF EXISTS rent_schedules_delete ON public.rent_schedules;
CREATE POLICY rent_schedules_select ON public.rent_schedules
    FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
CREATE POLICY rent_schedules_insert ON public.rent_schedules
    FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
CREATE POLICY rent_schedules_update ON public.rent_schedules
    FOR UPDATE TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
    WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
CREATE POLICY rent_schedules_delete ON public.rent_schedules
    FOR DELETE TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS tenant_agents_isolation ON public.tenant_agents;
DROP POLICY IF EXISTS tenant_agents_select ON public.tenant_agents;
DROP POLICY IF EXISTS tenant_agents_insert ON public.tenant_agents;
CREATE POLICY tenant_agents_select ON public.tenant_agents
    FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
CREATE POLICY tenant_agents_insert ON public.tenant_agents
    FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

DROP POLICY IF EXISTS usage_records_isolation ON public.usage_records;
DROP POLICY IF EXISTS usage_records_select ON public.usage_records;
CREATE POLICY usage_records_select ON public.usage_records
    FOR SELECT TO authenticated
    USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));

-- Guarded auxiliary/extended tables not defined in local migrations 20261111..20261116
DO $$
BEGIN
    IF to_regclass('public.appointments') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS appointments_isolation ON public.appointments;
            DROP POLICY IF EXISTS "Tenant isolation for appointments" ON public.appointments;
            CREATE POLICY "Tenant isolation for appointments" ON public.appointments
                FOR ALL TO authenticated
                USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
                WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.consent_records') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS consent_records_isolation ON public.consent_records;
            DROP POLICY IF EXISTS "Tenant isolation for consent_records" ON public.consent_records;
            CREATE POLICY "Tenant isolation for consent_records" ON public.consent_records
                FOR ALL TO authenticated
                USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
                WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.customers') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS customers_isolation ON public.customers;
            DROP POLICY IF EXISTS "Tenant isolation for customers" ON public.customers;
            CREATE POLICY "Tenant isolation for customers" ON public.customers
                FOR ALL TO authenticated
                USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
                WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.human_tasks') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS human_tasks_isolation ON public.human_tasks;
            DROP POLICY IF EXISTS "Tenant isolation for human_tasks" ON public.human_tasks;
            CREATE POLICY "Tenant isolation for human_tasks" ON public.human_tasks
                FOR ALL TO authenticated
                USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
                WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.subscription_events') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS tenant_billing_admins_view_events ON public.subscription_events;
            CREATE POLICY tenant_billing_admins_view_events ON public.subscription_events
                FOR SELECT TO authenticated
                USING ((tenant_id IS NOT NULL AND private.is_tenant_admin(tenant_id)) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.subscriptions') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS tenant_members_view_subscription ON public.subscriptions;
            CREATE POLICY tenant_members_view_subscription ON public.subscriptions
                FOR SELECT TO authenticated
                USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.tenant_caches') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS tenant_members_view_caches ON public.tenant_caches;
            CREATE POLICY tenant_members_view_caches ON public.tenant_caches
                FOR SELECT TO authenticated
                USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.tool_executions') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS tool_executions_select ON public.tool_executions;
            DROP POLICY IF EXISTS "Tenant isolation for tool_executions" ON public.tool_executions;
            CREATE POLICY "Tenant isolation for tool_executions" ON public.tool_executions
                FOR SELECT TO authenticated
                USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.usage_events') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS tenant_members_view_usage_events ON public.usage_events;
            CREATE POLICY tenant_members_view_usage_events ON public.usage_events
                FOR SELECT TO authenticated
                USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.usage_meters') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS tenant_members_view_meters ON public.usage_meters;
            CREATE POLICY tenant_members_view_meters ON public.usage_meters
                FOR SELECT TO authenticated
                USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.workflow_executions') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS workflow_executions_select ON public.workflow_executions;
            DROP POLICY IF EXISTS "Tenant isolation for workflow_executions" ON public.workflow_executions;
            CREATE POLICY "Tenant isolation for workflow_executions" ON public.workflow_executions
                FOR SELECT TO authenticated
                USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;
END $$;

-- 2.5 Auxiliary tables previously using `{public}` role (tightened to `TO authenticated` + `private.*`)
DO $$
BEGIN
    IF to_regclass('public.ad_campaigns') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS "Tenant members can insert ad campaigns" ON public.ad_campaigns;
            DROP POLICY IF EXISTS "Tenant members can view their ad campaigns" ON public.ad_campaigns;
            CREATE POLICY "Tenant members can view their ad campaigns" ON public.ad_campaigns
                FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can insert ad campaigns" ON public.ad_campaigns
                FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.competitors') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS "Tenant members can insert competitors" ON public.competitors;
            DROP POLICY IF EXISTS "Tenant members can view their competitors" ON public.competitors;
            CREATE POLICY "Tenant members can view their competitors" ON public.competitors
                FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can insert competitors" ON public.competitors
                FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.enriched_leads') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS "Tenant members can insert enriched leads" ON public.enriched_leads;
            DROP POLICY IF EXISTS "Tenant members can view their enriched leads" ON public.enriched_leads;
            CREATE POLICY "Tenant members can view their enriched leads" ON public.enriched_leads
                FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can insert enriched leads" ON public.enriched_leads
                FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.gbp_locations') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS "Tenant members can insert GBP locations" ON public.gbp_locations;
            DROP POLICY IF EXISTS "Tenant members can view their GBP locations" ON public.gbp_locations;
            CREATE POLICY "Tenant members can view their GBP locations" ON public.gbp_locations
                FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can insert GBP locations" ON public.gbp_locations
                FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.gbp_posts') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS "Tenant members can insert GBP posts" ON public.gbp_posts;
            DROP POLICY IF EXISTS "Tenant members can view their GBP posts" ON public.gbp_posts;
            CREATE POLICY "Tenant members can view their GBP posts" ON public.gbp_posts
                FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can insert GBP posts" ON public.gbp_posts
                FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.gbp_reviews') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS "Tenant members can insert GBP reviews" ON public.gbp_reviews;
            DROP POLICY IF EXISTS "Tenant members can view their GBP reviews" ON public.gbp_reviews;
            CREATE POLICY "Tenant members can view their GBP reviews" ON public.gbp_reviews
                FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can insert GBP reviews" ON public.gbp_reviews
                FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.lead_enrichment_jobs') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS "Tenant members can insert lead enrichment jobs" ON public.lead_enrichment_jobs;
            DROP POLICY IF EXISTS "Tenant members can view their lead enrichment jobs" ON public.lead_enrichment_jobs;
            CREATE POLICY "Tenant members can view their lead enrichment jobs" ON public.lead_enrichment_jobs
                FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can insert lead enrichment jobs" ON public.lead_enrichment_jobs
                FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.omnichannel_sessions') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS "Tenant members can view their omnichannel sessions" ON public.omnichannel_sessions;
            DROP POLICY IF EXISTS "Tenant members can insert omnichannel sessions" ON public.omnichannel_sessions;
            DROP POLICY IF EXISTS "Tenant members can update their omnichannel sessions" ON public.omnichannel_sessions;
            DROP POLICY IF EXISTS "Tenant admins can delete omnichannel sessions" ON public.omnichannel_sessions;
            CREATE POLICY "Tenant members can view their omnichannel sessions" ON public.omnichannel_sessions
                FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can insert omnichannel sessions" ON public.omnichannel_sessions
                FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can update their omnichannel sessions" ON public.omnichannel_sessions
                FOR UPDATE TO authenticated
                USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
                WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant admins can delete omnichannel sessions" ON public.omnichannel_sessions
                FOR DELETE TO authenticated USING (private.is_tenant_admin(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.watchdog_alerts') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS "Tenant members can insert watchdog alerts" ON public.watchdog_alerts;
            DROP POLICY IF EXISTS "Tenant members can view their watchdog alerts" ON public.watchdog_alerts;
            CREATE POLICY "Tenant members can view their watchdog alerts" ON public.watchdog_alerts
                FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can insert watchdog alerts" ON public.watchdog_alerts
                FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.website_audits') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS "Tenant members can insert website audits" ON public.website_audits;
            DROP POLICY IF EXISTS "Tenant members can view their website audits" ON public.website_audits;
            CREATE POLICY "Tenant members can view their website audits" ON public.website_audits
                FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can insert website audits" ON public.website_audits
                FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.whatsapp_leads') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS "Tenant members can view their leads" ON public.whatsapp_leads;
            DROP POLICY IF EXISTS "Tenant members can insert leads" ON public.whatsapp_leads;
            DROP POLICY IF EXISTS "Tenant members can update their leads" ON public.whatsapp_leads;
            DROP POLICY IF EXISTS "Tenant admins can delete leads" ON public.whatsapp_leads;
            CREATE POLICY "Tenant members can view their leads" ON public.whatsapp_leads
                FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can insert leads" ON public.whatsapp_leads
                FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can update their leads" ON public.whatsapp_leads
                FOR UPDATE TO authenticated
                USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()))
                WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant admins can delete leads" ON public.whatsapp_leads
                FOR DELETE TO authenticated USING (private.is_tenant_admin(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;

    IF to_regclass('public.whatsapp_messages') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS "Tenant members can view their messages" ON public.whatsapp_messages;
            DROP POLICY IF EXISTS "Tenant members can insert messages" ON public.whatsapp_messages;
            DROP POLICY IF EXISTS "Tenant admins can delete messages" ON public.whatsapp_messages;
            CREATE POLICY "Tenant members can view their messages" ON public.whatsapp_messages
                FOR SELECT TO authenticated USING (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant members can insert messages" ON public.whatsapp_messages
                FOR INSERT TO authenticated WITH CHECK (private.is_tenant_member(tenant_id) OR (SELECT public.is_super_admin()));
            CREATE POLICY "Tenant admins can delete messages" ON public.whatsapp_messages
                FOR DELETE TO authenticated USING (private.is_tenant_admin(tenant_id) OR (SELECT public.is_super_admin()));
        $pol$;
    END IF;
END $$;

-- Drop the old `public` SECURITY DEFINER helpers WITHOUT CASCADE
-- (Postgres will verify zero remaining policy dependencies)
DROP FUNCTION IF EXISTS public.is_tenant_member(UUID);
DROP FUNCTION IF EXISTS public.is_tenant_admin(UUID);
DROP FUNCTION IF EXISTS public.get_user_tenant_ids();
DROP FUNCTION IF EXISTS public.is_tenant_member(TEXT);

-- ------------------------------------------------------------------------------
-- 3. Remediate overly broad `public.profiles` RLS policies
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS profiles_read_policy ON public.profiles;
DROP POLICY IF EXISTS profiles_insert_policy ON public.profiles;
DROP POLICY IF EXISTS profiles_update_policy ON public.profiles;
DROP POLICY IF EXISTS profiles_select ON public.profiles;
DROP POLICY IF EXISTS profiles_insert ON public.profiles;
DROP POLICY IF EXISTS profiles_update ON public.profiles;

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

-- ------------------------------------------------------------------------------
-- 4. Remediate `auth_rls_initplan` & internal-tenant exposure on `outreach_leads`
-- ------------------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('public.outreach_leads') IS NOT NULL THEN
        EXECUTE $pol$
            DROP POLICY IF EXISTS "Tenant isolation for outreach_leads" ON public.outreach_leads;
            DROP POLICY IF EXISTS outreach_leads_isolation ON public.outreach_leads;
            CREATE POLICY outreach_leads_isolation ON public.outreach_leads
                FOR ALL TO authenticated
                USING (
                    (tenant_id = (SELECT NULLIF(COALESCE((SELECT auth.jwt()) -> 'app_metadata' ->> 'tenant_id', (SELECT auth.jwt()) ->> 'tenant_id'), '')))
                    OR (tenant_id = (SELECT NULLIF(COALESCE(current_setting('app.current_tenant_id', true), ''), '')))
                    OR (tenant_id = 'teloxtech_internal' AND (SELECT public.is_super_admin()))
                    OR (SELECT public.is_super_admin())
                )
                WITH CHECK (
                    (tenant_id = (SELECT NULLIF(COALESCE((SELECT auth.jwt()) -> 'app_metadata' ->> 'tenant_id', (SELECT auth.jwt()) ->> 'tenant_id'), '')))
                    OR (tenant_id = (SELECT NULLIF(COALESCE(current_setting('app.current_tenant_id', true), ''), '')))
                    OR (tenant_id = 'teloxtech_internal' AND (SELECT public.is_super_admin()))
                    OR (SELECT public.is_super_admin())
                );
        $pol$;
    END IF;
END $$;

-- ------------------------------------------------------------------------------
-- 5. Drop duplicate indexes & add missing FK covering indexes
-- ------------------------------------------------------------------------------
DROP INDEX IF EXISTS public.idx_audit_logs_tenant_id;
DROP INDEX IF EXISTS public.idx_tenant_members_tenant_id;
DROP INDEX IF EXISTS public.idx_tenant_members_user_id;

CREATE INDEX IF NOT EXISTS idx_agent_tasks_agent_id ON public.agent_tasks(agent_id);
CREATE INDEX IF NOT EXISTS idx_approvals_task_id ON public.approvals(task_id);
CREATE INDEX IF NOT EXISTS idx_business_records_recorded_by ON public.business_records(recorded_by);

DO $$
BEGIN
    IF to_regclass('public.usage_events') IS NOT NULL THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_usage_events_user_id ON public.usage_events(user_id)';
    END IF;
END $$;
