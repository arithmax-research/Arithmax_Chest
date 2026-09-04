#!/usr/bin/env bash
set -euo pipefail

APP_HOST="${APP_HOST:-https://achest.misango.me}"
APP_DIR="${APP_DIR:-/home/ubuntu/codechest/Arithmax_Chest}"
BRANCH="${BRANCH:-main}"
REPO_URL="${REPO_URL:-https://github.com/arithmax-research/Arithmax_Chest.git}"
ENV_FILE="${ENV_FILE:-.env}"
SSH_USER="${SSH_USER:-ubuntu}"
EC2_HOST="${EC2_HOST:-98.93.200.66}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing local env file: ${ENV_FILE}"
  echo "Create it with your API keys, then rerun."
  exit 1
fi

if [[ -n "${SSH_KEY:-}" ]]; then
  :
else
  for candidate in "$HOME"/.ssh/*.pem "$HOME"/.ssh/*.key; do
    if [[ -f "$candidate" ]]; then
      SSH_KEY="$candidate"
      break
    fi
  done
fi

if [[ -z "${SSH_KEY:-}" ]]; then
  echo "No SSH private key found in ~/.ssh."
  echo "Set SSH_KEY to your EC2 private key path and rerun."
  exit 1
fi

if [[ ! -f "${SSH_KEY}" ]]; then
  echo "SSH key not found: ${SSH_KEY}"
  echo "Set SSH_KEY to your EC2 private key path and rerun."
  exit 1
fi

echo "Copying .env to EC2 host ${EC2_HOST}"
scp -i "${SSH_KEY}" -o StrictHostKeyChecking=accept-new "${ENV_FILE}" "${SSH_USER}@${EC2_HOST}:/tmp/arithmaxchest.env"

echo "Deploying Arithmax Chest on ${EC2_HOST}"
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

# --- Install the .env file (handle root-owned file) ---
sudo chown "\$(id -un)":"\$(id -gn)" "\${APP_DIR}/.env" 2>/dev/null || true
cp /tmp/arithmaxchest.env "\${APP_DIR}/.env"
chmod 600 "\${APP_DIR}/.env"

# --- Build and restart Docker containers ---
if [[ -f "\${APP_DIR}/docker-compose.ec2.yml" ]]; then
  cd "\${APP_DIR}"
  sudo docker compose --env-file .env -f docker-compose.ec2.yml down --remove-orphans 2>/dev/null || true
  # Force-remove any stale containers that might have been left behind (name conflict guard)
  sudo docker rm -f achest-api achest-caddy 2>/dev/null || true
  sudo docker compose --env-file .env -f docker-compose.ec2.yml build api
  sudo docker compose --env-file .env -f docker-compose.ec2.yml up -d --force-recreate --remove-orphans
else
  echo "docker-compose.ec2.yml not found in \${APP_DIR}; exiting without changing the running container."
  exit 1
fi

# --- Health check ---
curl -fsSL "\${APP_HOST}/health"
EOF

echo ""
echo "Deployment finished. Confirm health: ${APP_HOST}/health"