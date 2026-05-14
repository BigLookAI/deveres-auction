# Deviours Auction — Dockerfile
# Multi-stage build for a lean production image.
# Runs on x86_64 and ARM64 (Apple Silicon M1/M2/M3).

# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

# Install dependencies into an isolated prefix
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.13-slim

LABEL org.opencontainers.image.title="Deviours Auction"
LABEL org.opencontainers.image.description="Bidder evaluation and invitation intelligence platform"
LABEL org.opencontainers.image.source="https://github.com/santosh-biglook/deviours-auction"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY api.py .
COPY pipeline/ ./pipeline/
COPY data/ ./data/
COPY skills/ ./skills/

# Create output directory
RUN mkdir -p output/reports

# Expose API port
EXPOSE 8003

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')" || exit 1

# Environment defaults (override via docker-compose.yml or -e flags)
ENV HOST=0.0.0.0
ENV PORT=8003
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8003", "--log-level", "info"]
