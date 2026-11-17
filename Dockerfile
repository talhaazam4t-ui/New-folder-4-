# ==============================================================================
# Multi-Stage Production Dockerfile for Talox Tech Stream
# Target: Render / Google Cloud Run / Container Platforms
# Builds Next.js frontend static assets and serves via FastAPI on $PORT
# ==============================================================================

# Stage 1: Build Frontend Static Assets
FROM node:20-alpine AS frontend-builder
RUN apk add --no-cache libc6-compat
WORKDIR /build/frontend

# Install dependencies
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

# Copy frontend source files
COPY frontend/ ./

# Build static assets (exported to /build/frontend/out)
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production \
    NEXT_PUBLIC_APP_NAME="Talox Tech Stream" \
    NEXT_PUBLIC_BACKEND_URL="" \
    NODE_OPTIONS="--max-old-space-size=2048"

RUN npm run build

# Stage 2: Python Backend Dependency Builder
FROM python:3.12-slim AS backend-builder
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 3: Hardened Production Runner (Render & Cloud Run Compatible)
FROM python:3.12-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r talox && useradd -r -g talox -d /app -s /sbin/nologin taloxuser

# Copy compiled Python dependencies from backend-builder
COPY --from=backend-builder /install /usr/local

# Copy backend application and operational scripts
COPY backend/app ./app
COPY scripts ./scripts

# Copy compiled frontend static assets from frontend-builder into /app/static
COPY --from=frontend-builder /build/frontend/out ./static

RUN chown -R taloxuser:talox /app

USER taloxuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=10000

# Render default port is 10000; Cloud Run / local default is 8000
EXPOSE 10000 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-10000}/api/v1/health || curl -f http://localhost:${PORT:-8000}/api/v1/health || exit 1

# Bind to dynamic $PORT injected by Render (10000) or Cloud Run / Docker Compose (8000)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --limit-concurrency 100"]
