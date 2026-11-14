---
name: qa-browser
description: Reusable browser auto-QA workflow for end-to-end verification of Next.js frontend (http://localhost:3000) and FastAPI backend (http://127.0.0.1:8000/docs).
---

# Reusable Browser Auto-QA Workflow

This skill guides the browser subagent or manual QA runner through verifying the full-stack multi-tenant SaaS application.

## 1. Prerequisites Check
Ensure the local services are reachable before initiating UI navigation:
- Frontend: `http://localhost:3000` (Next.js 14)
- Backend Docs: `http://127.0.0.1:8000/docs` (FastAPI Swagger UI)
- Backend Health: `http://127.0.0.1:8000/health`

## 2. Test Execution Flow

### Step A: Frontend Core Smoke Test (`http://localhost:3000`)
1. **Navigate to root**: Open `http://localhost:3000`.
2. **Hydration & Console Verification**:
   - Check developer tools console logs.
   - Assert **0** uncaught JavaScript exceptions.
   - Assert **0** React hydration mismatch errors.
3. **UI Elements & Viewport**:
   - Verify primary navbar and branding elements render.
   - Check responsive viewport transitions (desktop 1280px, mobile 375px).
4. **Tenant Authentication / Navigation**:
   - Verify redirection to login or dashboard depending on session state.
   - Confirm login form fields (`email`, `password`) are interactable.

### Step B: Backend API Docs Smoke Test (`http://127.0.0.1:8000/docs`)
1. **Navigate to docs**: Open `http://127.0.0.1:8000/docs`.
2. **Swagger Verification**:
   - Verify OpenAPI specs load cleanly without JSON parsing errors.
   - Confirm presence of core tenant router tags:
     - `/api/v1/auth`
     - `/api/v1/tenants`
     - `/api/v1/users`
3. **Interactive Endpoint Check**:
   - Expand the `/health` endpoint and execute "Try it out".
   - Confirm status code `200 OK` with JSON response containing `"status": "healthy"`.

### Step C: Network & Performance Audit
1. Monitor network tab during page transitions.
2. Ensure no asset returns HTTP 404, 500, or CORS errors.
3. Verify static assets load within expected performance thresholds.

## 3. Reporting Results
Upon completion, format findings:
```markdown
### Browser Auto-QA Verification Report
- **Frontend (localhost:3000)**: [PASS / FAIL] (Hydration clean, UI rendered)
- **Backend (127.0.0.1:8000/docs)**: [PASS / FAIL] (Swagger UI responsive, /health 200 OK)
- **Console Errors**: 0 detected
- **Network Failures**: 0 detected
```
