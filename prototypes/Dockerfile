# OMEGA_QUANT Production Dockerfile
# Phase 10: Deployment & Go-Live

# Stage 1: Build dependencies
FROM python:3.14-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.14-slim

WORKDIR /app

# Create non-root user
RUN groupadd -r omega && useradd -r -g omega omega
USER omega

# Copy installed packages from builder
COPY --from=builder /home/omega/.local /home/omega/.local
COPY --from=builder /app /app

# Set environment
ENV PATH=/home/omega/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/packages/quant/src:/app/packages/core/src:/app/packages/data/src

# Copy source code
COPY --chown=omega:omega . .

# Create state directory
RUN mkdir -p .ly_state/session .ly_state/logs .ly_state/metrics .ly_state/secrets .ly_state/audit

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "from omega.quant.deployment import check_health; import sys; exit(0 if check_health() else 1)"

# Entry point
ENTRYPOINT ["python", "-m", "omega.quant.pipeline"]
