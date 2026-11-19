# Talox Tech Stream — Workspace Rules

## MCP Server Target Configuration

- **Primary Supabase Project (`supabase_mcp`)**: Always target `project_id` / `project_ref` = `pmmduhflikdvddzpgwsi` (`https://pmmduhflikdvddzpgwsi.supabase.co`, region `eu-west-1`) when calling `supabase_mcp` tools (`list_tables`, `execute_sql`, `list_migrations`, `get_advisors`, `generate_typescript_types`, etc.).
- **Isolation Guardrail**: Never run queries or mutations against unrelated projects in the organization (such as `ovujtddhddtvglulrqvf`).
- **Project MCP Config**: `.mcp.json` at the repository root scopes the Supabase MCP endpoint to `?project_ref=pmmduhflikdvddzpgwsi`.
- **Available Plugin MCP Servers**:
  - `supabase_mcp`: Primary database, auth, migrations, advisors, and type generation for `pmmduhflikdvddzpgwsi`.
  - `google-cloud-developer` (`developer-knowledge`): Official Google documentation lookup for Google APIs (OAuth / Google Places) when needed. Production hosting runs on Render (`render.yaml`) and Railway (`railway.toml`) behind Cloudflare DNS.
  - `vercel-plugin` (`vercel`): Available plugin MCP under team `teloxtech` (`team_Yp6nyxVunnoE36zh1C83gJ7Y`) for unrelated/legacy Vercel projects only — **not** used by `teloxtech.stream`, whose Next.js static export (`frontend/out`) is served directly by FastAPI on Render and Railway.
  - `railway_mcp`: Read/inspect secondary Railway service (`talox-tech-stream`) configured via `railway.toml` + `Dockerfile`. Primary live production (`https://teloxtech.stream`) runs on Render (`render.yaml`) behind Cloudflare DNS-only records.

## Schema & Security Rules

- Use `execute_sql` (via `supabase_mcp`) for iterative schema inspection and testing; always run `get_advisors` (`security` and `performance`) after any DDL changes and remediate reported warnings.
- Always pin an explicit `search_path` on database functions (e.g., `SET search_path = public`) to avoid mutable `search_path` vulnerabilities.
- Enable Row Level Security (RLS) on every table in `public` and other exposed schemas, using explicit `TO authenticated` (or `TO anon`) clauses and ownership/tenant predicates rather than deprecated `auth.role()` checks or open policies.
- Keep `SUPABASE_SERVICE_ROLE_KEY` strictly server-side (FastAPI backend only); never expose service role or secret keys in `frontend/` or `NEXT_PUBLIC_*` environment variables.

## Architecture Constraints

- **Zero n8n**: Do not introduce n8n or external visual workflow tools; use the custom Python `asyncio` automation engine and database-backed task queues.
- **Strict Multi-Tenant Isolation**: Enforce tenant isolation via server-side JWT/session context and database RLS policies.
- **Human-in-the-Loop Approvals**: High-impact operations (financial refunds, external campaign publishing, cascading tenant/account deletions) require explicit approval through `ApprovalManager`.
