# Talox Tech Stream

Master Technical Specification — Custom Python Multi-Tenant SaaS Agent Platform

## Overview

Talox Tech Stream is a modular, production-ready SaaS platform built for multi-tenant AI business services, financial tracking, marketing orchestration, and automated agent operations.

- **Frontend:** Next.js 14 (App Router, static export via `output: 'export'`) + TypeScript + Tailwind CSS + TanStack Query + Lucide React + Recharts
- **Backend:** FastAPI + Uvicorn + Pydantic v2 + SlowAPI (serves `/api/v1/*` APIs and production `frontend/out` static bundle)
- **Automation:** 100% Custom Python AsyncIO Runtime (Strictly **Zero n8n**)
- **Database:** Supabase PostgreSQL with Row Level Security (RLS) & Connection Pooling (`pmmduhflikdvddzpgwsi`, `eu-west-1`)
- **AI Routing:** DeepSeek API (`https://api.deepseek.com`) with Smart Complexity-Tier Routing (`deepseek-chat` / `deepseek-reasoner`) + offline mock fallback
- **Cost Protection:** Circuit Breaker & Strict Tenant Daily Token Budgets
- **Messaging:** WhatsApp Business Integration with Meta Embedded Signup
- **Deployment:** Unified multi-stage `Dockerfile` deployed on **Render** (`render.yaml`, primary live host for `https://teloxtech.stream` behind Cloudflare DNS) and **Railway** (`railway.toml`), backed by **Supabase** (`eu-west-1`)

---

## Quick Start (Local Development)

### 1. Prerequisites
- Python 3.11+ (or Python 3.12 via Docker)
- Node.js 20+ & npm
- Docker & Docker Compose (Optional for local containerized dev)

### 2. Environment Setup
```bash
# Enter repository directory
cd New-folder-4-  # or your cloned workspace directory

# Copy environment template
cp .env.example .env
```

### 3. Backend Setup
```bash
# Create and activate virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run backend server
uvicorn app.main:app --app-dir backend --reload --port 8000
```

Backend will be available at: `http://localhost:8000`  
Health check endpoint: `http://localhost:8000/api/v1/health`

### 4. Frontend Setup (Local Development)
```bash
cd frontend
npm install
npm run dev
```

Frontend dev server will be available at: `http://localhost:3000`

### 5. Running Tests & Stack Verification
```bash
# Run pytest with async support
pytest

# Run frontend lint, TypeScript check, and backend Ruff check
node verify-stack.mjs
```

---

## Documentation
- [Architecture Blueprint](docs/architecture.md)
- [Production Deployment Guide (Render, Railway & Cloudflare)](docs/deployment.md)

---

## Non-Negotiable Architecture Constraints
1. Zero n8n or external visual workflow tools.
2. Custom Python automation engine using asyncio and database-backed task queues.
3. Supabase Service Role keys must **never** be exposed to frontend clients.
4. Complete tenant isolation enforced via server-side context and database RLS.
5. High-impact operations (refunds, external publishing, account deletion) require human approval.
