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

## Production Workspace & Build Rules

- **Active Git Repository**: Work in `D:\workspace\teloxtech_saas_environment_setup` (`C:` has limited disk space; do not edit application code in the old `C:` worktree copy, only keep `AGENTS.md` synced).
- **Render Auto-Deploy**: Primary live production (`https://teloxtech.stream`) runs on Render service `New-folder-4-` (`srv-dbsmshpsrm7s73904hq0`) auto-deploying from `origin/master`. Never delete, overwrite, or clear existing Render environment variables.
- **Windows Frontend Build Commands**: In Windows PowerShell, set `$env:NODE_OPTIONS="--max-old-space-size=1024"` and run `npm`/`npx` commands via `cmd /c "..."` (e.g., `cmd /c "npx tsc --noEmit && npm run lint && npm run build"`). Always discard generated `frontend/tsconfig.tsbuildinfo` (`git checkout -- frontend/tsconfig.tsbuildinfo`) before committing.

## Security, Auth & Front-Page Guardrails

- **Strict Single Super Admin**: Only `talhaazam4t@gmail.com` is Platform Super Admin (enforced in `backend/app/config.py` and Supabase `public.is_super_admin()`). Never re-add legacy emails (`talhazam4@gmail.com`, `talazam40@gmail.com`), and never hardcode admin emails in public client JS (`frontend/lib/auth.ts`).
- **No Public Admin Button**: Keep `frontend/app/page.tsx` strictly client-facing without an `Admin Portal` button; Admin signs in via `/login` auto-redirect or bookmarks `/admin`.
- **Payment Lock & Genuine Metrics**: New client automations remain locked until Admin clicks **Confirm Payment & Activate**; never fabricate marketing impressions/ROI; lead scoring is Admin-only using free OpenStreetMap Nominatim (`openstreetmap_live`).

## Live Database & Canonical Catalog Facts (`pmmduhflikdvddzpgwsi`)

- **Supabase RLS Helper Location**: Live `is_tenant_member(tenant_id)` and `is_super_admin()` helper functions reside in schema `public` (not `private`). Apply additive, idempotent DDL (`IF NOT EXISTS` / `DO $$`) via `supabase_mcp` `execute_sql`.
- **7 Canonical Ordered Services (#1–#7)**:
  1. `business-financial-tracking`
  2. `ai-marketing-growth`
  3. `whatsapp-business-concierge`
  4. `lead-crm-qualification`
  5. `office-receptionist`
  6. `multi-agent-orchestration`
  7. `executive-analytics-compliance`
  - Keep legacy duplicate slugs (`whatsapp-automation`, `marketing-growth`, `business-finance`) inactive (`active = false`).

## Integrations & Pending 6-Day Follow-Up Reference (Non-Secret IDs Only)

- **Office Receptionist (AI Voice Agent)**: Powered by **Retell AI + Telnyx Voice (TeXML) + Cal.com** (never re-introduce Twilio, which blocks free trials in Pakistan).
  - Retell Webhook: `https://teloxtech.stream/api/v1/receptionist/webhooks/retell`
  - Telnyx TeXML App: `TALOXTECH Office Receptionist`, Connection ID `3099227472751756795`, Voice Webhook `https://teloxtech.stream/api/v1/receptionist/webhooks/telnyx/voice`, Status Callback `https://teloxtech.stream/api/v1/receptionist/webhooks/telnyx/status` (live PSTN numbers activate once Telnyx billing funds are added).
  - Cal.com Default Booking Link: `https://cal.com/talha-azam-jhhqzd/30min`, Event Type ID `7689754`.
- **Meta WhatsApp App (`2014438705903110`)**:
  - Status `Published`, Privacy Policy URL `https://teloxtech.stream/privacy`, Business Portfolio ID `1329931986881358`.
  - Facebook Login for Business Config: `Teloxtech WhatsApp Signup`, `META_CONFIG_ID` = `1714130023425849` (saved on Render).
  - **Meta OAuth Protocol Rule**: Whenever `META_CONFIG_ID` is set, `/dialog/oauth` must pass `config_id` + `override_default_response_type=true` and omit `scope`.
  - **Pending Follow-Up (Once Business Verification Documents Are Ready)**: Complete Business Verification on Business Portfolio `1329931986881358`, enroll as Tech Provider (`Use cases -> Connect on WhatsApp -> Overview -> Become a Partner -> Become Tech Provider`), switch Config `1714130023425849` to Login variation `WhatsApp Embedded Signup` + Assets `WhatsApp accounts`, and submit App Review for `whatsapp_business_management` & `whatsapp_business_messaging`. Until then, clients connect immediately via the Direct WhatsApp Cloud API Token fallback on `/onboarding`.
- **Google OAuth (`TaloxTech Production`)**: Published `In production`, with all 5 redirect URIs registered (`/onboarding`, `/settings`, `/api/v1/integrations/oauth/gmail/callback`, `/api/v1/integrations/oauth/google_calendar/callback`, `/api/v1/integrations/oauth/google_business/callback`).

## Communication Preference

- Reply in concise, honest, beginner-friendly Roman Urdu mixed with clear English technical terms matching the user's style, always providing clickable `file://` links for referenced files.
