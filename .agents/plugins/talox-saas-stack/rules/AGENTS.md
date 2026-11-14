# Multi-Tenant SaaS Workspace Guidelines

## Architecture Overview
- **Frontend**: Next.js 14 App Router, TypeScript strict mode, Tailwind CSS, TanStack Query.
- **Backend**: FastAPI with async SQLAlchemy, Pydantic v2 validation, slowapi rate limiting.
- **Database**: Supabase PostgreSQL with strict Row Level Security (RLS) multi-tenant policies.

## Development Rules

### 1. Multi-Tenant Isolation
- Every database query touching tenant-scoped tables must enforce tenant isolation either via Supabase RLS (`auth.jwt() -> app_metadata -> tenant_id`) or explicit backend tenant context filters.
- Never bypass RLS policies using service role keys in client-facing requests.

### 2. Frontend Conventions
- Place routes under `frontend/src/app` or `frontend/app`.
- Prefer React Server Components (RSC) for initial page renders and data fetching.
- Use `'use client'` only when state, browser APIs, or interactivity are required.
- Maintain zero lint warnings (`npm run lint`) and zero TypeScript compiler errors (`tsc --noEmit`).

### 3. Backend Conventions
- Organize routers under `backend/app/api/v1/`.
- Validate all incoming payloads with Pydantic models.
- Handle database sessions using async context managers.

### 4. Quality & Safety Gates
- Every file write or replacement triggers `.agents/verify-stack.mjs`.
- Always verify frontend linting and type contracts before concluding tasks.
