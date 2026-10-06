# Dockerfile.q — FastAPI + q IPC proxy
# ───────────────────────────────────────────────────────────
# Build:  docker build -f Dockerfile.q -t achest-q .
# Run:    docker run -p 8000:8000 -p 5001:5001 achest-q
#
# Expects kc.lic at build context root (or mount at runtime)
# ───────────────────────────────────────────────────────────

# Dockerfile.q — FastAPI + q IPC proxy
# ───────────────────────────────────────────────────────────
# Prerequisites (place in context root):
#   1. q_latest.zip    — kdb+ Linux binary (from KX downloads)
#   2. kc.lic          — q license file
#
# Build:  docker build -f Dockerfile.q -t achest-q .
# Run:    docker run -p 8000:8000 -p 5001:5001 achest-q
#
# Or via docker-compose (see docker-compose.ec2.yml)
# ───────────────────────────────────────────────────────────

FROM python:3.11-slim

# ── 1) Python dependencies (same as existing Dockerfile) ──
WORKDIR /app
COPY pyproject.toml README.md ./
COPY achest ./achest
RUN pip install --no-cache-dir '.[all]' && pip install --no-cache-dir '.[eulerpool]'

# ── 2) Install q (kdb+) from local zip ────────────────────
# Download q_latest.zip from https://kx.com/download or your KX portal
# Place q_latest.zip and kc.lic in the Docker build context
COPY q_latest.zip /tmp/q_latest.zip
RUN apt-get update && apt-get install -y --no-install-recommends unzip && \
    unzip -j /tmp/q_latest.zip -d /usr/local/bin/ && \
    chmod +x /usr/local/bin/q && \
    rm /tmp/q_latest.zip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── 3) Copy q license ─────────────────────────────────────
COPY kc.lic /root/.kx/kc.lic

# ── 4) Copy q proxy script ───────────────────────────────
COPY achest-kdb-q/qserver_proxy.q /app/qserver_proxy.q

# ── 5) Expose ports ────────────────────────────────────
EXPOSE 8000      
EXPOSE 5001     

# ── 6) Start both services ─────────────────────────────
CMD sh -c '\
  uvicorn achest.server:app --host 0.0.0.0 --port 8000 & \
  sleep 1 && \
  q /app/qserver_proxy.q -p 5001 \
'