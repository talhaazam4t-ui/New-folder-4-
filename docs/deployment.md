# Production Deployment Guide — Render, Railway, Cloudflare & Supabase

This guide describes the production deployment architecture and configuration for **Talox Tech Stream** (`https://teloxtech.stream`).

---

## 1. Production Architecture Summary

Talox Tech Stream builds and runs as a **single unified multi-stage Docker container** defined by the root `Dockerfile`:

1. **Stage 1 (`node:20-alpine`)**: Builds the Next.js 14 frontend (`frontend/next.config.mjs` with `output: 'export'`, `trailingSlash: true`, `images.unoptimized: true`) and `NEXT_PUBLIC_BACKEND_URL=""` so browser API calls target same-origin `/api/v1/*` routes. Outputs static assets to `/build/frontend/out`.
2. **Stage 2 (`python:3.12-slim`)**: Compiles and installs Python dependencies from `requirements.txt`.
3. **Stage 3 (`python:3.12-slim`)**: Copies `backend/app` to `/app/app`, `scripts` to `/app/scripts`, and `/build/frontend/out` to `/app/static`, then launches `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --limit-concurrency 100`.

Hosting & infrastructure layout:
- **Primary Live Host (Render):** Defined in `render.yaml` (`runtime: docker`, `dockerfilePath: ./Dockerfile`, `healthCheckPath: /api/v1/health`, `PORT=10000`), serving `https://teloxtech.stream` (`new-folder-4-hp6h.onrender.com`).
- **Secondary Host (Railway):** Defined in `railway.toml` (`builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"`, `healthcheckPath = "/api/v1/health"`), running `talox-tech-stream-production.up.railway.app`.
- **DNS & TLS (Cloudflare + Render):** Cloudflare manages authoritative DNS for `teloxtech.stream` in DNS-only (unproxied) mode; Render terminates TLS for `teloxtech.stream` and `www.teloxtech.stream`.
- **Database & Auth (Supabase):** Project `pmmduhflikdvddzpgwsi` (`https://pmmduhflikdvddzpgwsi.supabase.co`, region `eu-west-1`).

---

## 2. Prerequisites

1. Source repository: `https://github.com/talhaazam4t-ui/New-folder-4-.git`
2. Supabase project `pmmduhflikdvddzpgwsi` (`eu-west-1`) with pooled Postgres URI and API keys.
3. Cloudflare DNS zone for `teloxtech.stream`.
4. Render service configured via `render.yaml` and Railway service configured via `railway.toml`.
5. DeepSeek API key (`https://api.deepseek.com`).

---

## 3. Production Environment Variables Contract

Ensure the following environment variables are configured in Render and Railway service settings (never commit real secrets to git or expose `SUPABASE_SERVICE_ROLE_KEY` in `frontend/`):

| Variable | Production Target / Requirement | Notes |
|---|---|---|
| `APP_ENV` | `production` | Disables SQLite fallback and enables production guardrails |
| `DEBUG` | `false` | Disables `/docs`, `/openapi.json`, and SQL echo |
| `PORT` | `10000` | Matches `render.yaml` and root `Dockerfile` default |
| `HOST` | `0.0.0.0` | Container listen address |
| `APP_SECRET_KEY` | `<strong-32+-char-random-secret>` | Signs application JWTs |
| `SUPER_ADMIN_EMAILS` | JSON list of super-admin emails | Platform owner accounts |
| `FRONTEND_URL` | `https://teloxtech.stream` | Canonical frontend origin |
| `BACKEND_URL` | `https://teloxtech.stream` | Canonical backend origin |
| `ALLOWED_ORIGINS` | `["https://teloxtech.stream","https://www.teloxtech.stream"]` | Strict CORS allowlist |
| `NEXT_PUBLIC_BACKEND_URL` | `""` (empty string) | Baked at build time in `Dockerfile` for same-origin `/api/v1/*` |
| `AI_PROVIDER` | `deepseek` | Routes via DeepSeek API |
| `DEEPSEEK_API_KEY` | `<deepseek-api-key>` | Server-side AI API key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek endpoint |
| `AI_DEFAULT_FAST_MODEL` | `deepseek-chat` | Fast/structured workload tier |
| `AI_DEFAULT_REASONING_MODEL` | `deepseek-reasoner` | Deep reasoning/audit tier |
| `SUPABASE_URL` | `https://pmmduhflikdvddzpgwsi.supabase.co` | Supabase project URL |
| `SUPABASE_ANON_KEY` | `<supabase-anon-key>` | Public anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | `<supabase-service-role-key>` | **Server-side only** |
| `SUPABASE_JWT_SECRET` | `<supabase-jwt-secret>` | Supabase JWT verification secret |
| `SUPABASE_DATABASE_URL` | `postgresql+asyncpg://...` | Required in production (never omit) |
| `WHATSAPP_PROVIDER` | `meta` (or `mock` before onboarding) | Meta WhatsApp Cloud API mode |
| `WHATSAPP_VERIFY_TOKEN` | `<strong-verify-token>` | Webhook verification token |
| `WHATSAPP_APP_SECRET` / `META_APP_SECRET` | `<meta-app-secret>` | Webhook HMAC signature validation |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | `<google-oauth-credentials>` | Google OAuth integration |
| `GOOGLE_REDIRECT_URI` | `https://teloxtech.stream/onboarding` | Production OAuth callback target |

---

## 4. Render Deployment (`render.yaml`)

`render.yaml` defines the Render Web Service blueprint:
- `runtime: docker` with `dockerfilePath: ./Dockerfile`
- `region: oregon`
- `healthCheckPath: /api/v1/health`
- `autoDeploy: true`

Render pulls changes from the configured GitHub branch, executes the multi-stage `Dockerfile` build, injects service environment variables, and manages TLS certificates for `teloxtech.stream` and `www.teloxtech.stream`.

---

## 5. Railway Deployment (`railway.toml`)

`railway.toml` configures the secondary Railway deployment using the same root `Dockerfile`:
- `builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"`
- `healthcheckPath = "/api/v1/health"`
- `restartPolicyType = "ON_FAILURE"`

Ensure all uppercase production variables (especially `SUPABASE_DATABASE_URL`, `APP_SECRET_KEY`, `AI_PROVIDER=deepseek`, `DEEPSEEK_API_KEY`, `FRONTEND_URL`, `BACKEND_URL`, and `ALLOWED_ORIGINS`) are populated in Railway so the service connects to Supabase `pmmduhflikdvddzpgwsi` rather than failing startup.

---

## 6. Cloudflare DNS Configuration

Cloudflare serves authoritative DNS for `teloxtech.stream` in **DNS-only (unproxied)** mode:
- Apex `A` records point to Render edge IPs (`216.24.57.16`, `216.24.57.18`).
- `www.teloxtech.stream` `CNAME` points to `new-folder-4-hp6h.onrender.com.` (redirecting to `https://teloxtech.stream/`).

Do not delete DNS records or alter proxy/SSL/nameserver settings without explicit operational approval.

---

## 7. Local Development & Container Verification

### Local Dev Compose (`docker-compose.yml`)
```bash
# Start local development container on http://localhost:8000 with backend live reload
docker compose up -d
```

### Local Production-Mode Container Verification (`docker-compose.prod.yml`)
```bash
# Build and run production container locally on port 10000
docker compose -f docker-compose.prod.yml up -d --build

# Check container status and logs
docker compose -f docker-compose.prod.yml ps
docker logs -f talox_backend_prod
```

### Readiness & Stack Checks
```bash
# Verify DB connectivity, DeepSeek AI routing, deployment URLs, and guardrails
python scripts/health_check.py

# Verify frontend lint, TypeScript types, and backend Ruff lint
node verify-stack.mjs
```
