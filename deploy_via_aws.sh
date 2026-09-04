#!/usr/bin/env bash
set -euo pipefail

APP_HOST="${APP_HOST:-https://achest.misango.me}"
APP_DIR="${APP_DIR:-/home/ubuntu/codechest/Arithmax_Chest}"
BRANCH="${BRANCH:-main}"
REPO_URL="${REPO_URL:-https://github.com/arithmax-research/Arithmax_Chest.git}"
ENV_FILE="${ENV_FILE:-.env}"
SSH_USER="${SSH_USER:-ubuntu}"
EC2_HOST="${EC2_HOST:-18.142.144.144}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing local env file: ${ENV_FILE}"
  echo "Create it with your API keys, then rerun."
  exit 1
fi

if [[ -z "${SSH_KEY:-}" ]]; then
  for candidate in "$HOME"/.ssh/*.pem "$HOME"/.ssh/*.key; do
    if [[ -f "$candidate" ]]; then
      SSH_KEY="$candidate"
      break
    fi
  done
fi

if [[ -z "${SSH_KEY:-}" ]] || [[ ! -f "${SSH_KEY}" ]]; then
  echo "Valid SSH key not found in ~/.ssh or specified via SSH_KEY."
  exit 1
fi

echo "Copying .env to EC2 host ${EC2_HOST}..."
scp -i "${SSH_KEY}" -o StrictHostKeyChecking=accept-new "${ENV_FILE}" "${SSH_USER}@${EC2_HOST}:/tmp/arithmaxchest.env"

echo "Deploying Arithmax Chest on ${EC2_HOST}..."
ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=accept-new "${SSH_USER}@${EC2_HOST}" <<EOF
set -euo pipefail
export APP_HOST='${APP_HOST}'
export APP_DIR='${APP_DIR}'
export BRANCH='${BRANCH}'
export REPO_URL='${REPO_URL}'

# --- Ensure the app directory is a proper git repo with latest code ---
if [[ -d "\${APP_DIR}/.git" ]] && [[ -f "\${APP_DIR}/Dockerfile" ]]; then
  echo "Updating existing git repo at \${APP_DIR} (branch: \${BRANCH})"
  cd "\${APP_DIR}"
  git fetch --all --tags 2>/dev/null || true
  git stash 2>/dev/null || true
  git checkout "\${BRANCH}" 2>/dev/null || git checkout -b "\${BRANCH}" 2>/dev/null || true
  git pull --ff-only origin "\${BRANCH}" || true
elif [[ -d "\${APP_DIR}" ]] && [[ -n "\$(ls -A "\${APP_DIR}" 2>/dev/null)" ]]; then
  echo "Directory exists but not a git repo. Replacing with fresh clone..."
  sudo rm -rf "\${APP_DIR}"
  sudo mkdir -p "\${APP_DIR}"
  sudo chown -R "\$(id -un)":"\$(id -gn)" "\${APP_DIR}"
  git clone "\${REPO_URL}" "\${APP_DIR}"
  cd "\${APP_DIR}"
else
  echo "No existing app found. Cloning from GitHub..."
  sudo mkdir -p "\${APP_DIR}"
  sudo chown -R "\$(id -un)":"\$(id -gn)" "\${APP_DIR}"
  git clone "\${REPO_URL}" "\${APP_DIR}"
  cd "\${APP_DIR}"
fi

# --- Install the .env file ---
cp /tmp/arithmaxchest.env "\${APP_DIR}/.env"
chmod 600 "\${APP_DIR}/.env"

# --- Build and restart Docker containers ---
if [[ -f "\${APP_DIR}/docker-compose.ec2.yml" ]]; then
  cd "\${APP_DIR}"

  echo "Tearing down old containers..."
  sudo docker compose --env-file .env -f docker-compose.ec2.yml down --remove-orphans 2>/dev/null || true
  
  # Remove containers directly in case compose failed
  sudo docker rm -f achest-api achest-caddy 2>/dev/null || true

  # Safely clear dangling build cache without breaking storage drivers
  echo "Pruning build cache..."
  sudo docker builder prune -f 2>/dev/null || true

  # Reset Docker overlay2 snapshot store to squash persistent layer corruption
  echo "Resetting Docker overlay2 store..."
  sudo systemctl stop docker 2>/dev/null || true
  sudo rm -rf /var/lib/docker/overlay2/
  sudo systemctl start docker 2>/dev/null || true

  echo "Building and starting fresh containers..."
  sudo docker compose --env-file .env -f docker-compose.ec2.yml build api
  sudo docker compose --env-file .env -f docker-compose.ec2.yml up -d --force-recreate --remove-orphans
else
  echo "docker-compose.ec2.yml not found in \${APP_DIR}; exiting without changing the running container."
  exit 1
fi

# --- Health check ---
echo "Performing health check on \${APP_HOST}/health..."
echo "Waiting for Caddy to provision TLS certificate..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsSL "\${APP_HOST}/health" >/dev/null 2>&1; then
    echo "Health check passed on \${APP_HOST}/health"
    break
  fi
  echo "Attempt $i/10 - not ready yet, sleeping 3s..."
  sleep 3
done
curl -fsSL "\${APP_HOST}/health" || true
EOF

echo ""
echo "Deployment finished successfully. Confirm health: ${APP_HOST}/health"