-- ==============================================================================
-- TALOX TECH STREAM — Lock Super Admin RLS Helper to Single Owner Email
-- Restricts public.is_super_admin() email allowlist strictly to talhaazam4t@gmail.com
-- with an explicitly pinned search_path.
-- ==============================================================================

CREATE OR REPLACE FUNCTION public.is_super_admin()
 RETURNS boolean
 LANGUAGE sql
 STABLE
 SET search_path TO 'public'
AS $function$
  select (
    coalesce(
      lower(auth.jwt() ->> 'email') = 'talhaazam4t@gmail.com',
      false
    )
    or
    coalesce(
      (auth.jwt() -> 'app_metadata' ->> 'role') = 'super_admin',
      false
    )
  );
$function$;
