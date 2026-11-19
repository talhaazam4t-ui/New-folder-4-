# CURRENT_DEPLOYMENT_ARCHITECTURE — Talox Tech Stream

**Audit Date:** 2026-11-19 (UTC)  
**Canonical Production Domain:** `https://teloxtech.stream`  
**Audit Scope:** Strictly non-destructive live inspection of `https://teloxtech.stream`, Cloudflare DNS, Render (`new-folder-4-hp6h.onrender.com`), Railway (`talox-tech-stream-production.up.railway.app`), Supabase (`pmmduhflikdvddzpgwsi`), and the repository (`talhaazam4t-ui/New-folder-4-`). All secrets are redacted.

---

## 1. Cloudflare Domain Configuration

- **Authoritative Nameservers:** `nikon.ns.cloudflare.com.`, `veronica.ns.cloudflare.com.` (SOA serial `2420220504`).
- **DNS Proxy Mode:** **DNS-only (unproxied / grey-cloud)**. Apex `A` records resolve directly to Render edge IPs (`216.24.57.16`, `216.24.57.18`, TTL `300`), and `www` CNAMEs directly to Render (`new-folder-4-hp6h.onrender.com.`). HTTP responses carry `Server: cloudflare` and `cf-cache-status: DYNAMIC` because **Render's own ingress edge** fronts traffic via Cloudflare (`*.cdn.cloudflare.net`), not because the domain owner's Cloudflare zone is orange-cloud proxying.
- **Active Records:**
  - `teloxtech.stream` (`A`): `216.24.57.16`, `216.24.57.18` (no `AAAA`, no `CNAME`).
  - `teloxtech.stream` (`TXT`): `"google-site-verification=n3lMf_3hfjw2HTGdcyNdDlM8HhUqWsRhrTtqL687KIc"`.
  - `www.teloxtech.stream` (`CNAME`): `new-folder-4-hp6h.onrender.com.` → `gcp-us-west1-1.origin.onrender.com.` → `gcp-us-west1-1.origin.onrender.com.cdn.cloudflare.net.` (`216.24.57.16`, `216.24.57.18`).
- **Absent Records:** No `MX`, `CAA`, SPF (`v=spf1`), or `_dmarc` records. All probed subdomains (`api`, `app`, `admin`, `backend`, `auth`, `webhook`, `webhooks`, `ws`, `cdn`, `docs`, `status`, `staging`, `dev`, `mail`, `n8n`, `render`, `railway`, `portal`, `dashboard`) return `NXDOMAIN`; no wildcard DNS exists.

---

## 2. Railway Services and Roles

Inspected read-only via `railway_mcp` (`list-projects`, `list-services`, `list-variables`, `list-deployments`, `list-domains`):

- **Project:** `ingenious-illumination` (`c47d7d6c-46f2-4595-9a7b-88e0e5a6727a`), workspace `talhaazam4t-ui's Projects`.
- **Environment:** `production` (`a8d89288-136c-40f9-8f56-d726fd165e52`).
- **Service:** `talox-tech-stream` (`61f75941-cab2-45e9-a0f2-bd9a6cca3f42`), region `sfo`, built via `railway.toml` + root multi-stage `Dockerfile` (Next.js static export with `NEXT_PUBLIC_BACKEND_URL=""` + FastAPI Uvicorn on `PORT`).
- **Attached Domain:** `https://talox-tech-stream-production.up.railway.app` (Railway-generated domain only; **no custom domain** attached).
- **Latest Deployment:** `dc4b5162-64fe-4c97-b766-bbc5a59d3089` (`SUCCESS`, `2026-11-17T16:55:55.727Z`) from `master` commit `423c618`.
- **Live Health Check (`GET https://talox-tech-stream-production.up.railway.app/api/v1/health`):**
  ```json
  {"success":true,"data":{"status":"healthy","environment":"production","ai_provider":"openrouter","whatsapp_provider":"mock","payment_provider":"manual"},"message":"All core systems operational"}
  ```
- **Role in Current Production:** **Secondary / standby full-stack host.** Receives no `teloxtech.stream` DNS traffic. Critically, it lacks `SUPABASE_DATABASE_URL`, `APP_SECRET_KEY`, `AI_PROVIDER`, `DEEPSEEK_API_KEY` (uppercase), `FRONTEND_URL`, `BACKEND_URL`, and `ALLOWED_ORIGINS`, causing `423c618` to fall back to ephemeral container SQLite (`talox_dev.db`) and default `ai_provider: "openrouter"`.

---

## 3. Render Services and Roles

Observed via DNS, TLS, and live HTTP/OpenAPI/bundle probes (no Render API/CLI is present in the environment):

- **Service Hostname:** `new-folder-4-hp6h.onrender.com` (Render ingress `gcp-us-west1-1.origin.onrender.com`, origin server header `x-render-origin-server: uvicorn`).
- **Role in Current Production:** **Primary live production host** serving **both** the Next.js 14 static frontend and the FastAPI `/api/v1/*` backend for `https://teloxtech.stream` from a single Uvicorn process.
- **Deployed Revision:** Built from `origin/master` commit `423c618` (`2026-11-17T16:55:54Z`; live asset `last-modified: Tue, 17 Nov 2026 16:56:32 GMT`, `etag: W/"efc841d9a34b5aaec7fbe53a7f1e696e"`). Does **not** include the uncommitted repairs on branch `teloxtech_saas_environment_setup`.
- **Live Health Check (`GET https://teloxtech.stream/api/v1/health`):**
  ```json
  {"success":true,"data":{"status":"healthy","environment":"development","ai_provider":"Deepseek","whatsapp_provider":"mock","payment_provider":"manual"},"message":"All core systems operational"}
  ```
- **Observed Configuration Drift vs `render.yaml`:**
  - `render.yaml` declares service name `talox-tech-stream` (`oregon`, `APP_ENV=production`, `DEBUG="false"`, `AI_PROVIDER=deepseek`, `Dockerfile` with `NEXT_PUBLIC_BACKEND_URL=""`), whereas the running live service `new-folder-4-hp6h` reports `environment: "development"`, `ai_provider: "Deepseek"` (capital `D`), exposes `/docs` and `/openapi.json` (`DEBUG=true`), and serves JS bundles with `"http://localhost:8000"` baked in (indicating native/custom dashboard build settings or build-time env override `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000` / `NODE_ENV=development` rather than the Blueprint `render.yaml` + `Dockerfile`).
  - Live `GET /api/v1/services` initially returned `[]`, then 6 rows (`created_at: 2026-11-18T18:24:20.918499`) after `GET /api/v1/services/industries` ran, whereas Supabase `public.services` contains 3 rows — indicating Render is likely falling back to ephemeral SQLite rather than persisting to Supabase `pmmduhflikdvddzpgwsi`.

---

## 4. Frontend URL

- **Canonical Production Frontend URL:** `https://teloxtech.stream/`
- **Alternate Redirecting URL:** `https://www.teloxtech.stream/` (`301` redirect → `https://teloxtech.stream/`).
- **Direct Origin Mirror URL:** `https://new-folder-4-hp6h.onrender.com/` (returns identical `etag` and HTML as `https://teloxtech.stream/`).
- **Secondary Staging/Standby URL:** `https://talox-tech-stream-production.up.railway.app/` (not wired to custom domain).
- **Serving Mechanism:** Next.js 14 static export (`output: 'export'`, `trailingSlash: true`) served directly by FastAPI (`backend/app/main.py` via `/_next` StaticFiles mount + catch-all route serving `/app/static`).
- **Live Bundle Defect (Fixed Locally, Pending Deploy):** Live JS chunks on `https://teloxtech.stream` currently contain `"http://localhost:8000"`, breaking browser API requests. Local `frontend/lib/api.ts` (`getBackendUrl()`) and `frontend/components/finance/FinanceDashboard.tsx` (`apiFetchResponse`) have been repaired so non-localhost browser hostnames always resolve to `""` (same-origin `/api/v1/*`), and `frontend/out` builds cleanly with `0` occurrences of `localhost:8000`.

---

## 5. Backend / API URL

- **Canonical Production Backend / API Base URL:** `https://teloxtech.stream/api/v1` (same-origin with the frontend).
- **Health Endpoints:**
  - `https://teloxtech.stream/api/v1/health` (`200 OK`)
  - `https://teloxtech.stream/health` (`200 OK`)
- **Swagger / OpenAPI (Currently Exposed Live Due to `DEBUG=true`):**
  - `https://teloxtech.stream/docs` (`200 OK` live; becomes `404` once `DEBUG=false` is applied).
  - `https://teloxtech.stream/openapi.json` (`200 OK` live).
- **Webhook & OAuth Callback Endpoints:**
  - WhatsApp Meta Webhook: `https://teloxtech.stream/api/v1/integrations/whatsapp/webhook` (`GET` challenge currently returns `200 OK` using default `talox_verify_token`; `POST` signature validation rejects missing/invalid `X-Hub-Signature-256` when `WHATSAPP_APP_SECRET` / `META_APP_SECRET` is configured).
  - OAuth Callback (Fixed Locally, Missing on Live `423c618`): `https://teloxtech.stream/api/v1/integrations/oauth/{provider}/callback` currently returns `404` on live Render; implemented in the local working tree alongside Google redirect URI `https://teloxtech.stream/onboarding`.
  - Payment Webhook: `https://teloxtech.stream/api/v1/payments/webhook` (disabled with `400` while `PAYMENT_PROVIDER=manual`).

---

## 6. Supabase Project Connection

Inspected read-only via `supabase_mcp` targeting `project_id = "pmmduhflikdvddzpgwsi"`:

- **Project Reference & Name:** `pmmduhflikdvddzpgwsi` (`talhaazam4t@gmail.com's Project`), status `ACTIVE_HEALTHY`.
- **Region & Host:** `eu-west-1` (`https://pmmduhflikdvddzpgwsi.supabase.co`, DB host `db.pmmduhflikdvddzpgwsi.supabase.co`, PostgreSQL `17.11.0.011`).
- **Connection Architecture:**
  - **Frontend:** Uses **zero** direct Supabase client calls (`@supabase/supabase-js` and `NEXT_PUBLIC_SUPABASE_*` are absent from `frontend/`). All data access flows through FastAPI `/api/v1/*`.
  - **Backend (`backend/app/database/supabase.py`):** Connects via SQLAlchemy async engine (`asyncpg`) using `SUPABASE_DATABASE_URL`, with `pool_pre_ping=True` and PgBouncer-compatible `statement_cache_size=0` + `prepared_statement_cache_size=0` (added in local working tree). Silent SQLite fallback is now prohibited when `APP_ENV` is `production` or `staging`.
  - **Authentication:** Custom `public.profiles` + bcrypt + HS256 JWTs (`APP_SECRET_KEY`) managed by FastAPI (`auth_service.py`), rather than Supabase GoTrue `auth.users`.
- **Observed Remote Database State:**
  - Row counts: `auth.users = 0`, `public.tenants = 0`, `public.profiles = 2`, `public.services = 3`, `public.agent_registry = 5`.
  - Remote applied migrations (`supabase_migrations.schema_migrations`, 6 entries): `20261115111645`, `20261115111720`, `20261117083522`, `20261117083549`, `20261117083716`, `20261117091828`.
  - Local `supabase/migrations/` contains 8 SQL files, including `20261116000001_reconcile_orm_uuid_schema_and_rls.sql` and `20261118000001_remediate_rls_and_security_advisors.sql` (not yet applied remotely).
- **Active Security & Performance Advisor Findings (Live `pmmduhflikdvddzpgwsi`):**
  - **Security (`get_advisors`):**
    - `0028_anon_security_definer_function_executable` (3 findings): `public.get_tenant_subscription_tier`, `public.get_user_tenant_ids`, `public.is_tenant_admin` callable by `anon`.
    - `0029_authenticated_security_definer_function_executable` (4 findings): `public.get_tenant_subscription_tier`, `public.get_user_tenant_ids`, `public.is_tenant_admin`, `public.is_tenant_member` callable by `authenticated`.
    - `public.profiles` RLS policies (`profiles_read_policy` `SELECT` for `{anon,authenticated}` `qual=true`; `profiles_insert_policy` for `{anon,authenticated}`; `profiles_update_policy` for `{authenticated}` `qual=true`).
    - `public.outreach_leads` policy `Tenant isolation for outreach_leads` exposes `tenant_id = 'teloxtech_internal'` to any authenticated user.
  - **Performance (`get_advisors`):**
    - 1 `auth_rls_initplan` warning (`public.outreach_leads`).
    - 10 `multiple_permissive_policies` warnings (`approvals`, `integrations`, `marketing_campaigns`, `payments`, `service_subscriptions`, `tenant_members`, `tenants`).
    - 3 `duplicate_index` warnings (`audit_logs`, `tenant_members` x2).
    - 4 `unindexed_foreign_keys` infos (`agent_tasks`, `approvals`, `business_records`, `usage_events`), plus 144 `unused_index` infos (expected on newly provisioned empty tables).

---

## 7. Environment Variable Mapping

Values of all credentials/tokens are **redacted**. Repository targets reflect `render.yaml`, `.env.example`, and `backend/app/config.py`.

| Variable | Repository / `.env.example` / `render.yaml` | Live Render (`new-folder-4-hp6h`, Inferred from Behavior) | Live Railway (`talox-tech-stream`, Observed via MCP) | Production Target Value / Requirement |
|---|---|---|---|---|
| `APP_ENV` | `development` (`.env.example`) / `production` (`render.yaml`) | `development` (from `/api/v1/health`) | Set (`production` via `/api/v1/health`) | `production` |
| `DEBUG` | `true` (`.env.example`) / `"false"` (`render.yaml`) | `true` (`/docs` & `/openapi.json` return `200`) | Set | `false` |
| `PORT` / `HOST` | `8000` / `0.0.0.0` (`.env.example`), `10000` (`Dockerfile`/`render.yaml`) | `10000` (or Render `$PORT`) | Set (`PORT`, `HOST`) | `PORT=10000`, `HOST=0.0.0.0` |
| `APP_SECRET_KEY` | Placeholder in `.env.example`; `sync: false` in `render.yaml` | Unknown (defaults insecure if unset in dev mode) | **Missing** | Strong random 32+ char secret (required by `Settings` in prod) |
| `SUPER_ADMIN_EMAILS` | `["talhazam4@gmail.com","talhaazam4t@gmail.com","talazam40@gmail.com"]` | Likely default | **Missing** (uses code default) | `["talhazam4@gmail.com","talhaazam4t@gmail.com","talazam40@gmail.com"]` |
| `NEXT_PUBLIC_BACKEND_URL` | `http://localhost:8000` (`.env.example`), `""` (`Dockerfile`) | Built as `"http://localhost:8000"` in live JS bundles | `""` (via `Dockerfile`) | `""` (empty string at build time) |
| `FRONTEND_URL` | `http://localhost:3000` (`.env.example`); `sync: false` (`render.yaml`) | Likely `https://teloxtech.stream` or unset | **Missing** | `https://teloxtech.stream` |
| `BACKEND_URL` | `http://localhost:8000` (`.env.example`); `sync: false` (`render.yaml`) | Likely unset/default | **Missing** | `https://teloxtech.stream` |
| `ALLOWED_ORIGINS` | `["http://localhost:3000","http://127.0.0.1:3000"]` | Only `https://teloxtech.stream` passes `OPTIONS` | **Missing** | `["https://teloxtech.stream","https://www.teloxtech.stream"]` |
| `AI_PROVIDER` | `deepseek` | `Deepseek` (capital `D`) | **Missing** (defaults to `openrouter` on `423c618`) | `deepseek` |
| `DEEPSEEK_API_KEY` | `sync: false` (`render.yaml`) | Likely set (unverified) | **Misnamed lowercase** `deepseek_api_key` (uppercase missing) | `<REDACTED>` (`DEEPSEEK_API_KEY` uppercase) |
| `DEEPSEEK_BASE_URL` / Models | `https://api.deepseek.com`, `deepseek-chat`, `deepseek-reasoner` | Default | Unset (uses code default) | Keep defaults (`https://api.deepseek.com`, `deepseek-chat`, `deepseek-reasoner`) |
| `SUPABASE_URL` | `https://pmmduhflikdvddzpgwsi.supabase.co` | Unknown | Set (`SUPABASE_URL`) | `https://pmmduhflikdvddzpgwsi.supabase.co` |
| `SUPABASE_ANON_KEY` | `sync: false` | Unknown | Set (`SUPABASE_ANON_KEY` + duplicate lowercase `supabase_anon_key`) | `<REDACTED>` (uppercase only) |
| `SUPABASE_SERVICE_ROLE_KEY` | `sync: false` (server-side only) | Unknown | **Misnamed lowercase** `supabase_service_role_key` | `<REDACTED>` (`SUPABASE_SERVICE_ROLE_KEY` uppercase, backend-only) |
| `SUPABASE_JWT_SECRET` | `sync: false` | Unknown | **Misnamed lowercase** `supabase_jwt_secret` | `<REDACTED>` (`SUPABASE_JWT_SECRET` uppercase) |
| `SUPABASE_DATABASE_URL` | `postgresql+asyncpg://...` (`sync: false`) | **Likely missing/failing** (services count drifted from Supabase) | **Missing** (using ephemeral SQLite) | `<REDACTED>` pooled/direct `postgresql+asyncpg://...` to `pmmduhflikdvddzpgwsi` |
| `WHATSAPP_PROVIDER` | `mock` | `mock` | Unset (`mock` default) | `meta` (once Meta app configured) or `mock` |
| `WHATSAPP_VERIFY_TOKEN` | `talox_verify_token` | `talox_verify_token` (verified live!) | Unset (`talox_verify_token` default) | Strong random verify token (rotated from default) |
| `WHATSAPP_APP_SECRET` / `META_APP_ID` / `META_APP_SECRET` | `sync: false` | Unknown | **Missing** | `<REDACTED>` Meta app credentials (required for webhook HMAC in prod) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | `sync: false` (`http://localhost:3000/onboarding` in `.env.example`) | Unknown | **Missing** | `<REDACTED>` + `GOOGLE_REDIRECT_URI=https://teloxtech.stream/onboarding` |
| `PAYMENT_PROVIDER` | `manual` | `manual` | Unset (`manual` default) | `manual` (or `stripe` when keys set) |
| Unused Railway Vars | Removed/absent in repo | N/A | `GOOGLE_SHEET_DASHBOARD_ID`, `LEMON_SQUEEZY_PRODUCT_ID`, `LEMON_SQUEEZY_STORE_ID` | Candidate for cleanup on Railway (unused in codebase) |

---

## 8. DNS and SSL Status

Verified via `Resolve-DnsName`, DoH (`cloudflare-dns.com`, `dns.google`), `.NET SslStream`, and `curl.exe`:

| Hostname | DNS Record | Resolved Target | TLS Status & Issuer | Validity Window (UTC) | Redirect / HTTP Notes |
|---|---|---|---|---|---|
| `teloxtech.stream` | `A` (TTL 300) | `216.24.57.16`, `216.24.57.18` | **Valid** (`ChainValid: True`, TLS 1.2 / AES-128, `CN=WE1`, Google Trust Services) | `2026-11-15` to `2027-02-13` | `http://` → `301` `https://teloxtech.stream/`. `https://` → `200 OK`. **No HSTS header.** |
| `www.teloxtech.stream` | `CNAME` | `new-folder-4-hp6h.onrender.com.` → Render edge `.16`/`.18` | **Valid** (`ChainValid: True`, TLS 1.2 / AES-128, `CN=WE1`, Google Trust Services) | `2026-11-15` to `2027-02-13` | `http://` → `301` `https://www.teloxtech.stream/` → `301` `https://teloxtech.stream/`. |
| `new-folder-4-hp6h.onrender.com` | Render managed | `gcp-us-west1-1.origin.onrender.com.cdn.cloudflare.net.` | **Valid** (`*.onrender.com`, `CN=WE1`) | `2026-09-21` to `2026-12-20` | `https://` → `200 OK` (same `etag` as apex). |
| `talox-tech-stream-production.up.railway.app` | Railway managed | Railway edge | Valid Railway TLS | Managed | `https://` → `200 OK` (`/api/v1/health` verified). |

- **Note on Local TLS 1.3 Probe:** Windows Schannel `curl.exe --tlsv1.3` failed locally with `SEC_E_ALGORITHM_MISMATCH` (client-side Schannel constraint); TLS 1.2 chain and certificates verified valid via `.NET SslStream`.

---

## 9. Deployment Dependencies

```text
User Browser (https://teloxtech.stream)
   │
   ├─► Cloudflare DNS (DNS-only: apex A -> 216.24.57.16/18, www CNAME -> new-folder-4-hp6h.onrender.com)
   │      │
   │      ▼
   └─► Render Web Service (new-folder-4-hp6h.onrender.com) [PRIMARY LIVE HOST]
          │  Single Uvicorn container/process:
          │    ├─ Static Next.js 14 UI (/app/static)
          │    └─ FastAPI /api/v1/* Backend
          ├──► Supabase PostgreSQL (pmmduhflikdvddzpgwsi, eu-west-1) [DATABASE]
          ├──► DeepSeek API (api.deepseek.com) [AI PROVIDER]
          └──► Meta Graph API / Google OAuth & Places [OPTIONAL INTEGRATIONS]

Secondary Standby (No live domain traffic):
   └─► Railway Service (talox-tech-stream-production.up.railway.app)
          └─ Root Dockerfile + railway.toml -> currently isolated on SQLite until env vars synced
```

- **Are Both Render and Railway Necessary?**
  - **Render** is strictly required today because `teloxtech.stream` and `www.teloxtech.stream` point directly to Render (`216.24.57.16`/`.18` and `new-folder-4-hp6h.onrender.com`), and Render serves **both** frontend and backend in a single origin.
  - **Railway** (`talox-tech-stream`) serves **no** `teloxtech.stream` traffic and is a redundant/standby single-container deployment of the same codebase. Per **R2 Preservation**, neither service has been deleted or modified; Railway should either be maintained as a configured standby (by syncing its env vars to `pmmduhflikdvddzpgwsi`) or explicitly retired later by the user.
- **Confirmed-Unused Infra Cleaned Up Locally (R4):** `Caddyfile`, `cloudbuild.yaml`, `frontend/Dockerfile`, and GCP/Caddy/OpenRouter assumptions in `README.md`, `docs/deployment.md`, `docs/architecture.md`, and `docker-compose.prod.yml` were confirmed unused by Render, Railway, and Cloudflare and were removed/updated locally in the repository.

---

## 10. Remaining Configuration Issues & Approval-Gated Production Changes

All safe code-level, type-safety, frontend bundle, R4 documentation, and local SQL migration preparations are complete and verified in the local working tree (`node verify-stack.mjs`, `mypy`, `pytest` 52/52, `npm run build` with `0` `localhost:8000` bundle hits). **None** of the following external/production changes have been executed (per R2/R3); each requires explicit user approval:

| # | Target Platform | Exact Issue Observed | Exact Approval-Gated Change Required | Risk / Impact |
|---|---|---|---|---|
| 1 | **GitHub (`talhaazam4t-ui/New-folder-4-`)** | Live hosts run `master@423c618`; local repairs (`frontend/lib/api.ts`, `backend/app/*`, `docs/*`, `railway.toml`, migrations) are uncommitted on `teloxtech_saas_environment_setup`. | Review diff, commit verified local changes, and push/merge to the branch tracked by Render and Railway. | Triggers `autoDeploy` on Render if `autoDeploy: true` is active. |
| 2 | **Render (`new-folder-4-hp6h`)** | 1) Live JS bundles bake `http://localhost:8000` (breaks all browser API calls).<br>2) `APP_ENV=development`, `DEBUG=true` (`/docs` exposed).<br>3) `AI_PROVIDER=Deepseek` (mixed case), `WHATSAPP_VERIFY_TOKEN=talox_verify_token` (default).<br>4) `ALLOWED_ORIGINS` rejects `www.teloxtech.stream` and `new-folder-4-hp6h.onrender.com`.<br>5) `SUPABASE_DATABASE_URL` likely unset/failing (ephemeral SQLite drift).<br>6) Service uses dashboard settings instead of Docker `render.yaml`. | Set Render build/runtime env vars:<br>• `NEXT_PUBLIC_BACKEND_URL=""` (and switch Render service to Docker runtime using root `Dockerfile` or align `render.yaml`)<br>• `APP_ENV=production`, `DEBUG=false`, `PORT=10000`, `HOST=0.0.0.0`<br>• `APP_SECRET_KEY=<32+ char secret>`<br>• `FRONTEND_URL=https://teloxtech.stream`, `BACKEND_URL=https://teloxtech.stream`<br>• `ALLOWED_ORIGINS=["https://teloxtech.stream","https://www.teloxtech.stream"]`<br>• `AI_PROVIDER=deepseek`, `DEEPSEEK_API_KEY=<secret>`<br>• `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `SUPABASE_DATABASE_URL=postgresql+asyncpg://...` (to `pmmduhflikdvddzpgwsi`)<br>• Rotate `WHATSAPP_VERIFY_TOKEN`, set `WHATSAPP_APP_SECRET`, `META_APP_ID`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI=https://teloxtech.stream/onboarding`<br>• Trigger manual deploy after commit/push. | **Critical:** Restores live login, dashboard, APIs, CORS, DB persistence, and OAuth callbacks on `https://teloxtech.stream`. |
| 3 | **Railway (`talox-tech-stream`)** | Missing `SUPABASE_DATABASE_URL`, `APP_SECRET_KEY`, `ALLOWED_ORIGINS`, `FRONTEND_URL`, `BACKEND_URL`, `AI_PROVIDER`, `DEEPSEEK_API_KEY` (only lowercase `deepseek_api_key` exists), `SUPER_ADMIN_EMAILS`; has 4 lowercase duplicate/misnamed vars and 3 unused vars (`GOOGLE_SHEET_DASHBOARD_ID`, `LEMON_SQUEEZY_*`). | Either:<br>**Option A (Keep as Standby):** Set `DEBUG=false`, `APP_SECRET_KEY`, `SUPABASE_DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `DEEPSEEK_API_KEY`, `AI_PROVIDER=deepseek`, `FRONTEND_URL`, `BACKEND_URL`, `ALLOWED_ORIGINS`, `SUPER_ADMIN_EMAILS`; remove lowercase duplicates and 3 unused vars; redeploy.<br>**Option B (Retire Standby):** User explicitly confirms decommissioning `talox-tech-stream` on Railway. | Required because updated `backend/app/database/supabase.py` & `config.py` intentionally refuse to boot in `APP_ENV=production` without `APP_SECRET_KEY` and `SUPABASE_DATABASE_URL`. |
| 4 | **Supabase (`pmmduhflikdvddzpgwsi`)** | Remote DB lacks local migrations `20261116000001_reconcile_orm_uuid_schema_and_rls.sql` and `20261118000001_remediate_rls_and_security_advisors.sql`; Security Advisor reports 7 `SECURITY DEFINER` executable warnings (`anon`/`authenticated`), overly broad `public.profiles` policies, and `auth_rls_initplan` / duplicate indexes. | Approve applying `20261116000001` (if needed after schema diff verification) and `20261118000001_remediate_rls_and_security_advisors.sql` via `supabase_mcp` `apply_migration`, then re-run `get_advisors` (`security` + `performance`). | Eliminates public `anon`/`authenticated` RPC & `profiles` RLS exposure while preserving backend `service_role` access. |
| 5 | **Cloudflare (`teloxtech.stream`)** | Missing HSTS header (`Strict-Transport-Security`), `CAA`, `MX`, SPF, and `_dmarc` DNS records. | Optional hardening (only with explicit approval): add `CAA` record (`pki.goog` for Render Google Trust Services), SPF/DMARC anti-spoofing TXT records if domain does not send email (`v=spf1 -all`), and enable HSTS at Render/Cloudflare. Do **not** switch apex/www to orange-cloud proxy without validating Render TLS renewal behavior. | Hardens domain security without breaking Render SSL auto-renewal. |
