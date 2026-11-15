-- ==============================================================================
-- TALOX TECH STREAM — Database Performance Remediation Migration v1.4
-- Adds covering indexes for high-frequency foreign keys identified by Supabase Advisor
-- ==============================================================================

-- 1. appointments foreign keys
CREATE INDEX IF NOT EXISTS idx_appointments_customer_id ON public.appointments(customer_id);
CREATE INDEX IF NOT EXISTS idx_appointments_lead_id ON public.appointments(lead_id);

-- 2. human_tasks foreign keys
CREATE INDEX IF NOT EXISTS idx_human_tasks_lead_id ON public.human_tasks(lead_id);

-- 3. invoices foreign keys
CREATE INDEX IF NOT EXISTS idx_invoices_customer_id ON public.invoices(customer_id);

-- 4. marketing_metrics foreign keys
CREATE INDEX IF NOT EXISTS idx_marketing_metrics_tenant_id ON public.marketing_metrics(tenant_id);
