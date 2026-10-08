#!/usr/bin/env bash
#
# rebuild_server.sh — one-shot rebuild for the Arithmax Chest API on the server.
#
# Run this ON THE EC2 host (not your laptop). It pulls the latest main branch,
# rebuilds the `api` container from the local Dockerfile, recreates it, and
# health-checks the result.
#
# Usage (on the server):
#     bash rebuild_server.sh
#
# Optional overrides:
#     APP_DIR=/home/ubuntu/codechest/Arithmax_Chest bash rebuild_server.sh
#     BRANCH=main APP_HOST=https://achestv2.misango.me bash rebuild_server.sh
#     SKIP_PULL=1 bash rebuild_server.sh       # rebuild current checkout, no git pull
#     SKIP_BUILDCLEAN=1 bash rebuild_server.sh # keep BuildKit/buildx state (faster)
#
# The server's .env is gitignored and left untouched.
#
set -euo pipefail

APP_DIR="${APP_DIR:-}"
BRANCH="${BRANCH:-main}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.ec2.yml}"
SERVICE="${SERVICE:-api}"
CONTAINER="${CONTAINER:-achest-api}"
APP_HOST="${APP_HOST:-https://achestv2.misango.me}"
# Host port the api container is published on (see docker-compose.ec2.yml).
LOCAL_PORT="${LOCAL_PORT:-8001}"
SKIP_PULL="${SKIP_PULL:-0}"
SKIP_BUILDCLEAN="${SKIP_BUILDCLEAN:-0}"

log() { printf '\n=== %s ===\n' "$*"; }

# --- Locate the repo -------------------------------------------------------
if [[ -z "${APP_DIR}" ]]; then
  for candidate in \
    "${HOME}/codechest/Arithmax_Chest" \
    "/home/ubuntu/codechest/Arithmax_Chest" \
    "/opt/Arithmax_Chest" \
    "$(pwd)"
  do
    if [[ -f "${candidate}/${COMPOSE_FILE}" && -f "${candidate}/Dockerfile" ]]; then
      APP_DIR="${candidate}"
      break
    fi
  done
fi

if [[ -z "${APP_DIR}" || ! -f "${APP_DIR}/${COMPOSE_FILE}" ]]; then
  echo "ERROR: could not find ${COMPOSE_FILE}. Set APP_DIR explicitly, e.g.:" >&2
  echo "  APP_DIR=/path/to/Arithmax_Chest bash rebuild_server.sh" >&2
  exit 1
fi

cd "${APP_DIR}"
echo "App directory: ${APP_DIR}"

# --- Pick a docker compose command ----------------------------------------
if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  echo "ERROR: neither 'docker compose' nor 'docker-compose' is available." >&2
  exit 1
fi

SUDO=()
if ! docker info >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO=(sudo)
  else
    echo "ERROR: cannot access the Docker daemon and sudo is unavailable." >&2
    exit 1
  fi
fi
DC=("${SUDO[@]}" "${DC[@]}")

# --- Ensure the .env exists (do not overwrite it) -------------------------
if [[ ! -f .env ]]; then
  echo "ERROR: ${APP_DIR}/.env is missing — the container has no API keys." >&2
  echo "Copy your .env into ${APP_DIR} then rerun." >&2
  exit 1
fi

# --- Update the code -------------------------------------------------------
if [[ "${SKIP_PULL}" != "1" ]]; then
  if [[ -d .git ]]; then
    log "Updating code (branch: ${BRANCH})"
    git fetch --all --tags
    # .env is gitignored, so a hard reset is safe here.
    git checkout "${BRANCH}"
    git reset --hard "origin/${BRANCH}"
    git --no-pager log --oneline -1
  else
    echo "WARNING: ${APP_DIR} is not a git repo; skipping pull (rebuilding current files)."
  fi
else
  echo "SKIP_PULL=1 — rebuilding the current checkout without pulling."
fi

# --- Tear down the running container --------------------------------------
log "Stopping existing ${CONTAINER} container"
"${DC[@]}" --env-file .env -f "${COMPOSE_FILE}" down --remove-orphans || true
"${SUDO[@]}" docker rm -f "${CONTAINER}" 2>/dev/null || true

# --- Optional: clear corrupted BuildKit/buildx state ----------------------
if [[ "${SKIP_BUILDCLEAN}" != "1" ]]; then
  log "Clearing buildx/buildkit state"
  "${SUDO[@]}" docker buildx rm default-builder0 2>/dev/null || true
  "${SUDO[@]}" docker buildx prune -f --all 2>/dev/null || true

  if command -v systemctl >/dev/null 2>&1; then
    echo "Restarting Docker to clear stale BuildKit storage..."
    "${SUDO[@]}" systemctl stop docker || true
    "${SUDO[@]}" rm -rf /var/lib/docker/buildkit || true
    "${SUDO[@]}" systemctl start docker || true
    sleep 3
  fi
  "${SUDO[@]}" docker builder prune -f 2>/dev/null || true
fi

# --- Build + start ---------------------------------------------------------
log "Building ${SERVICE} image (no cache)"
"${DC[@]}" --env-file .env -f "${COMPOSE_FILE}" build --no-cache "${SERVICE}"

log "Starting containers"
"${DC[@]}" --env-file .env -f "${COMPOSE_FILE}" up -d --force-recreate --remove-orphans

# --- Health checks ---------------------------------------------------------
log "Waiting for the API container to come up"
ok=0
for i in $(seq 1 20); do
  if curl -fsSL "http://127.0.0.1:${LOCAL_PORT}/health" >/dev/null 2>&1; then
    echo "Local health check passed (http://127.0.0.1:${LOCAL_PORT}/health)"
    ok=1
    break
  fi
  echo "  attempt ${i}/20 — sleeping 3s..."
  sleep 3
done

if [[ "${ok}" != "1" ]]; then
  echo "" >&2
  echo "WARNING: local health check did not pass. Recent container logs:" >&2
  "${DC[@]}" -f "${COMPOSE_FILE}" logs --tail=60 "${SERVICE}" >&2 || true
fi

if [[ -n "${APP_HOST}" ]]; then
  log "Public health check on ${APP_HOST}/health"
  for i in $(seq 1 10); do
    if curl -fsSL "${APP_HOST}/health"; then
      echo ""
      echo "Public health check passed."
      break
    fi
    echo "  attempt ${i}/10 — waiting for TLS/proxy... sleeping 3s..."
    sleep 3
  done
fi

# --- Verify the fixed forex path ------------------------------------------
log "Verifying the fixed forex path (EUR/USD via eulerpool)"
# Read DATA_API_TOKEN from .env if not already in the environment.
if [[ -z "${DATA_API_TOKEN:-}" && -f .env ]]; then
  DATA_API_TOKEN="$(sed -n 's/^[[:space:]]*DATA_API_TOKEN=//p' .env | tail -n1 | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
fi
if [[ -n "${DATA_API_TOKEN:-}" ]]; then
  AUTH=(-H "Authorization: Bearer ${DATA_API_TOKEN}")
else
  AUTH=()
fi
curl -sS -X POST "http://127.0.0.1:${LOCAL_PORT}/v1/data" \
  "${AUTH[@]}" \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["EUR/USD"],"start":"2026-04-01","end":"2026-04-04","resolution":"daily","provider":"eulerpool","format":"csv"}' \
  -w '\nHTTP %{http_code}\n' || true

echo ""
echo "Rebuild complete. Container: ${CONTAINER} (host port ${LOCAL_PORT})"
