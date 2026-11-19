---
name: talox-mcp-ops
description: >-
  Use this skill when performing MCP-backed operations for Talox Tech Stream,
  including inspecting or syncing Supabase schemas and migrations, running
  security and performance advisors, generating frontend TypeScript types,
  inspecting Railway/Render container deployments, or consulting Google
  documentation when needed.
---

# Talox Tech Stream MCP Operations

Target Supabase project for this workspace:
- **`project_id` / `project_ref`**: `pmmduhflikdvddzpgwsi`
- **API URL**: `https://pmmduhflikdvddzpgwsi.supabase.co`

Never run `supabase_mcp` read or write operations against any other project in the organization.

## 1. Inspect & Sync Schema with Remote Supabase

1. List remote tables and row counts:
   - Call `supabase_mcp` `list_tables` with `project_id: "pmmduhflikdvddzpgwsi"`, `schemas: ["public"]`, `verbose: true` when column/constraint details are needed.
2. Check recorded migrations:
   - Call `supabase_mcp` `list_migrations` with `project_id: "pmmduhflikdvddzpgwsi"`.
   - Compare against all local migrations in `supabase/migrations/` (starting with [20261111000001_initial_schema.sql](../../../supabase/migrations/20261111000001_initial_schema.sql)) and [seed.sql](../../../supabase/seed.sql).
3. Test iterative SQL changes safely:
   - Use `supabase_mcp` `execute_sql` for queries and DDL iteration before finalizing migration files.

## 2. Run & Remediate Security and Performance Advisors

1. After any DDL or RLS change, run both advisor checks via `supabase_mcp`:
   - `get_advisors` with `project_id: "pmmduhflikdvddzpgwsi"`, `type: "security"`
   - `get_advisors` with `project_id: "pmmduhflikdvddzpgwsi"`, `type: "performance"`
2. Remediate findings promptly:
   - For `function_search_path_mutable` (e.g., `public.handle_updated_at`), inspect the function in `pg_proc` and run `ALTER FUNCTION public.<fn>(<args>) SET search_path = public;`.
   - Verify every exposed `public` table has RLS enabled and scoped `TO authenticated` policies.
3. Re-run `get_advisors` to confirm findings are cleared.

## 3. Generate TypeScript Types for Frontend

1. Call `supabase_mcp` `generate_typescript_types` with `project_id: "pmmduhflikdvddzpgwsi"`.
2. Write or update the generated database types in `frontend/` without exposing `SUPABASE_SERVICE_ROLE_KEY`.

## 4. Production Hosting (Render & Railway) & Legacy Vercel Note

- `https://teloxtech.stream` builds a Next.js static export (`frontend/out` -> `/app/static`) inside the unified root `Dockerfile` and serves both static assets and `/api/v1/*` via FastAPI on **Render** (`render.yaml`, primary live host behind Cloudflare DNS-only records) and **Railway** (`railway.toml`, inspectable via `railway_mcp`).
- `vercel-plugin_vercel` (`teamId: "team_Yp6nyxVunnoE36zh1C83gJ7Y"`) is **not** used for `teloxtech.stream` and only applies if explicitly inspecting unrelated/legacy Vercel projects.

## 5. Google APIs Documentation Lookup

1. Use the `google-cloud-developer` plugin (`developer-knowledge` MCP server) only when consulting official Google documentation for Google OAuth or Google Places APIs (see [deployment.md](../../../docs/deployment.md) for current hosting details).

## 6. Verification Checklist

- Confirm `.mcp.json` parses cleanly and points to `https://mcp.supabase.com/mcp?project_ref=pmmduhflikdvddzpgwsi`.
- Confirm `get_advisors` (`security`) reports zero unresolved warnings after schema or function updates.
