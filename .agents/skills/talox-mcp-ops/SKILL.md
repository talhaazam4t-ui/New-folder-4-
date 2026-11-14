---
name: talox-mcp-ops
description: >-
  Use this skill when performing MCP-backed operations for Talox Tech Stream,
  including inspecting or syncing Supabase schemas and migrations, running
  security and performance advisors, generating frontend TypeScript types, or
  consulting Google Cloud documentation for GCP e2-micro deployments.
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
   - Compare against local [20261111000001_initial_schema.sql](../../../supabase/migrations/20261111000001_initial_schema.sql) and [seed.sql](../../../supabase/seed.sql).
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

## 4. Vercel Frontend Deployment & Project Management

Vercel MCP (`vercel-plugin_vercel`) is authorized under team `teloxtech` (`team_Yp6nyxVunnoE36zh1C83gJ7Y`).
- **Available Projects**:
  - `teloxtech-pro` (`prj_PhzeIgWkXOHVinGUhFw1hFtWb6D6`)
  - `capabilities-overview` (`prj_qdaDnwgV0aAbG4S6ZAbnV1fQaozT`)
  - `eve-chat-template` (`prj_DW3jFAanuFCjFWd2yDZ4HMeVku3K`)
  - `desktop-tutorial` (`prj_vXbRalZOTolLGOOJVVcmRKXSw4AY`)
- Always pass `teamId: "team_Yp6nyxVunnoE36zh1C83gJ7Y"` when executing Vercel MCP tools (`list_projects`, `get_project`, `create_deployment`, `get_project_env`, etc.).

## 5. Google Cloud Deployment Knowledge Lookup

1. For GCP Always-Free Compute Engine (`e2-micro`), firewall, or Caddy reverse-proxy guidance referenced in [deployment.md](../../../docs/deployment.md), use the `google-cloud-developer` plugin (`developer-knowledge` MCP server) to fetch current official Google Cloud docs.

## 5. Verification Checklist

- Confirm `.mcp.json` parses cleanly and points to `https://mcp.supabase.com/mcp?project_ref=pmmduhflikdvddzpgwsi`.
- Confirm `get_advisors` (`security`) reports zero unresolved warnings after schema or function updates.
