---
name: saas-setup
description: Runbook for provisioning, database migrations, and tenant lifecycle in the Talox SaaS stack.
---

# SaaS Stack Setup & Migration Runbook

## Overview
This runbook guides multi-tenant provisioning, database migration syncing, and environment initialization for Next.js, FastAPI, and Supabase.

## 1. Database Migrations
- Check existing Supabase migrations in `supabase/migrations/`.
- To apply migrations locally or remotely:
  ```bash
  npx supabase db push
  ```
- To inspect schema drift:
  ```bash
  npx supabase db diff
  ```

## 2. Multi-Tenant Onboarding Flow
1. Insert tenant record into `public.tenants` with a unique slug and subscription tier.
2. Ensure tenant owner user exists in `auth.users` with `app_metadata.tenant_id` populated.
3. Validate RLS policy isolation by executing a scoped query test.

## 3. Local Development Startup
- Start Frontend:
  ```bash
  npm run dev:frontend
  ```
- Start Backend:
  ```bash
  uvicorn backend.app.main:app --reload --port 8000
  ```
