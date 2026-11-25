-- Phase 3: pgvector Extension, 1-Click RAG Knowledge Base, and HITL Inbox Columns

-- 1. Enable pgvector strictly inside extensions schema
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- 2. Tenant-Isolated Knowledge Documents
CREATE TABLE IF NOT EXISTS public.knowledge_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    title text NOT NULL,
    source_type text NOT NULL CHECK (source_type IN ('url', 'pdf', 'text')),
    source_url text,
    status text NOT NULL DEFAULT 'indexed' CHECK (status IN ('processing', 'indexed', 'failed')),
    chunk_count integer NOT NULL DEFAULT 0,
    char_count integer NOT NULL DEFAULT 0,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_tenant_created
    ON public.knowledge_documents (tenant_id, created_at DESC);

ALTER TABLE public.knowledge_documents ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'knowledge_documents' AND policyname = 'knowledge_documents_member_or_admin_select'
    ) THEN
        CREATE POLICY knowledge_documents_member_or_admin_select
            ON public.knowledge_documents
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR public.is_tenant_member(tenant_id)
            );
    END IF;
END $$;

-- 3. Tenant-Isolated Vector Knowledge Chunks (768-dim pgvector + JSON mirror)
CREATE TABLE IF NOT EXISTS public.knowledge_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    document_id uuid NOT NULL REFERENCES public.knowledge_documents(id) ON DELETE CASCADE,
    chunk_index integer NOT NULL DEFAULT 0,
    content text NOT NULL,
    embedding_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    embedding extensions.vector(768),
    token_estimate integer NOT NULL DEFAULT 0,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_tenant
    ON public.knowledge_chunks (tenant_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_doc
    ON public.knowledge_chunks (document_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding_hnsw
    ON public.knowledge_chunks USING hnsw (embedding extensions.vector_cosine_ops);

ALTER TABLE public.knowledge_chunks ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'knowledge_chunks' AND policyname = 'knowledge_chunks_member_or_admin_select'
    ) THEN
        CREATE POLICY knowledge_chunks_member_or_admin_select
            ON public.knowledge_chunks
            FOR SELECT
            TO authenticated
            USING (
                (SELECT public.is_super_admin())
                OR public.is_tenant_member(tenant_id)
            );
    END IF;
END $$;

-- 4. Reuse existing omnichannel_sessions with additive HITL live-takeover columns
ALTER TABLE public.omnichannel_sessions
    ADD COLUMN IF NOT EXISTS human_takeover boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS takeover_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS takeover_at timestamptz,
    ADD COLUMN IF NOT EXISTS contact_name text;

CREATE INDEX IF NOT EXISTS idx_omnichannel_sessions_takeover_by
    ON public.omnichannel_sessions (takeover_by);
