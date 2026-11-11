# Talox Tech Stream

Master Technical Specification — Custom Python Multi-Tenant SaaS Agent Platform

## Overview

Talox Tech Stream is a modular, production-ready SaaS platform built for multi-tenant AI business services, financial tracking, marketing orchestration, and automated agent operations.

- **Frontend:** Next.js 14 (App Router) + TypeScript + Tailwind CSS + Lucide React + Recharts
- **Backend:** FastAPI + Uvicorn + Pydantic v2 + SlowAPI
- **Automation:** 100% Custom Python AsyncIO Runtime (Strictly **Zero n8n**)
- **Database:** Supabase PostgreSQL with Row Level Security (RLS) & Connection Pooling
- **AI Routing:** Centralized OpenRouter Gateway with Smart Complexity-Tier Routing
- **Cost Protection:** Circuit Breaker & Strict Tenant Daily Token Budgets
- **Messaging:** WhatsApp Business Integration with Meta Embedded Signup
- **Deployment:** Optimized for Google Cloud Always-Free Compute Engine (`e2-micro`) with Caddy Reverse Proxy (Automatic SSL)

---

## Quick Start (Local Development)

### 1. Prerequisites
- Python 3.11+ (or Python 3.12 via Docker)
- Node.js 18+ & npm
- Docker & Docker Compose (Optional for local containerized dev)

### 2. Environment Setup
```bash
# Clone and enter directory
cd talox-tech-stream

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

### 4. Running Backend Tests
```bash
# Run pytest with async support
pytest
```

---

## Documentation
- [Architecture Blueprint](docs/architecture.md)
- [GCP Free-Tier VPS Deployment Guide](docs/deployment.md)

---

## Non-Negotiable Architecture Constraints
1. Zero n8n or external visual workflow tools.
2. Custom Python automation engine using asyncio and database-backed task queues.
3. Supabase Service Role keys must **never** be exposed to frontend clients.
4. Complete tenant isolation enforced via server-side context and database RLS.
5. High-impact operations (refunds, external publishing, account deletion) require human approval.
