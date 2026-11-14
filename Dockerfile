# ==============================================================================
# Multi-Stage Production Dockerfile for Talox Tech Stream FastAPI Backend
# Target: Google Cloud Run (me-central1) with Non-Root User & Dynamic $PORT
# ==============================================================================

# Stage 1: Dependency Builder
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Hardened Production Runner
FROM python:3.12-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r talox && useradd -r -g talox -d /app -s /sbin/nologin taloxuser

# Copy compiled Python dependencies from builder
COPY --from=builder /install /usr/local

# Copy backend application and operational scripts
COPY backend/app ./app
COPY scripts ./scripts

RUN chown -R taloxuser:talox /app

USER taloxuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/v1/health || exit 1

# Bind to $PORT injected by Google Cloud Run (defaults to 8000 locally)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --limit-concurrency 100"]
