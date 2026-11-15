-- ==============================================================================
-- TALOX TECH STREAM — Security Hardening Migration v1.3
-- Patches is_super_admin() privilege escalation vector, hardens search_path & grants
-- ==============================================================================

-- 1. Patch is_super_admin() to strictly eliminate user_metadata forgery
CREATE OR REPLACE FUNCTION public.is_super_admin()
RETURNS BOOLEAN
LANGUAGE sql
SECURITY INVOKER
SET search_path = public
STABLE
AS $$
  SELECT COALESCE(
    -- Sole Platform Administrator email whitelist (verified claims only)
    (auth.jwt() ->> 'email') IN ('talazam40@gmail.com', 'talhazam4@gmail.com', 'talhaazam4t@gmail.com')
    -- Server-managed app_metadata ONLY (client cannot modify or forge this)
    OR (auth.jwt() -> 'app_metadata' ->> 'role') = 'super_admin',
    FALSE
  );
$$;

-- 2. Harden is_tenant_member() with explicit text casting and active status check
CREATE OR REPLACE FUNCTION public.is_tenant_member(target_tenant_id TEXT)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY INVOKER
SET search_path = public
STABLE
AS $$
  SELECT (
    COALESCE(auth.jwt() -> 'app_metadata' ->> 'tenant_id' = target_tenant_id, FALSE)
    OR EXISTS (
      SELECT 1 FROM public.tenant_members
      WHERE tenant_id::TEXT = target_tenant_id
        AND user_id = auth.uid()
        AND status = 'active'
    )
  );
$$;

-- 3. Revoke public/anon execute and restrict to authenticated and service_role
REVOKE EXECUTE ON FUNCTION public.is_super_admin() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.is_tenant_member(TEXT) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_super_admin() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.is_tenant_member(TEXT) TO authenticated, service_role;
