-- =============================================================================
-- PHASE 2: Database-Driven Skills Registry & Tenant Episodic Memory
-- Target Project: pmmduhflikdvddzpgwsi (eu-west-1)
-- =============================================================================

-- 1. Database-Driven Agent Skills Registry (`public.agent_skills`)
CREATE TABLE IF NOT EXISTS public.agent_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    service_slug VARCHAR(120) NOT NULL,
    description TEXT NOT NULL,
    tool_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
    default_model_tier VARCHAR(32) NOT NULL DEFAULT 'fast_free',
    token_budget INTEGER NOT NULL DEFAULT 1500,
    max_words INTEGER NOT NULL DEFAULT 130,
    requires_hitl BOOLEAN NOT NULL DEFAULT TRUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_skills_service_active
    ON public.agent_skills(service_slug, active);

ALTER TABLE public.agent_skills ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'agent_skills'
          AND policyname = 'agent_skills_authenticated_read'
    ) THEN
        CREATE POLICY agent_skills_authenticated_read
            ON public.agent_skills
            FOR SELECT
            TO authenticated
            USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'agent_skills'
          AND policyname = 'agent_skills_super_admin_write'
    ) THEN
        CREATE POLICY agent_skills_super_admin_write
            ON public.agent_skills
            FOR ALL
            TO authenticated
            USING ((SELECT public.is_super_admin()))
            WITH CHECK ((SELECT public.is_super_admin()));
    END IF;
END $$;

-- 2. Proactive Tenant Episodic Memory (`public.tenant_episodic_memories`)
CREATE TABLE IF NOT EXISTS public.tenant_episodic_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    memory_type VARCHAR(64) NOT NULL DEFAULT 'interaction',
    skill_slug VARCHAR(100) NULL,
    context_key VARCHAR(200) NOT NULL,
    summary TEXT NOT NULL,
    outcome_score NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_episodic_memories_tenant_type
    ON public.tenant_episodic_memories(tenant_id, memory_type, created_at DESC);

ALTER TABLE public.tenant_episodic_memories ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'tenant_episodic_memories'
          AND policyname = 'tenant_episodic_memories_isolation'
    ) THEN
        CREATE POLICY tenant_episodic_memories_isolation
            ON public.tenant_episodic_memories
            FOR ALL
            TO authenticated
            USING ((SELECT public.is_super_admin()) OR public.is_tenant_member(tenant_id))
            WITH CHECK ((SELECT public.is_super_admin()) OR public.is_tenant_member(tenant_id));
    END IF;
END $$;
