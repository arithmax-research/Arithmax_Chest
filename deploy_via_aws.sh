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

if [[ -d "\${APP_DIR}" ]] && [[ -f "\${APP_DIR}/Dockerfile" ]] && [[ -f "\${APP_DIR}/docker-compose.ec2.yml" ]] && [[ -d "\${APP_DIR}/achest" ]]; then
  echo "Using existing app checkout at \${APP_DIR}"
  cd "\${APP_DIR}"

  if git -C "\${APP_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "\${APP_DIR}" fetch --all --tags || true
    git -C "\${APP_DIR}" checkout "\${BRANCH}" || true
    git -C "\${APP_DIR}" pull --ff-only origin "\${BRANCH}" || true
  else
    echo "No git repo detected; reusing the existing app copy already on the EC2 instance."
  fi
else
  if [[ -d "\${APP_DIR}" ]] && [[ -n "\$(ls -A "\${APP_DIR}" 2>/dev/null)" ]]; then
    echo "Directory exists at \${APP_DIR} but is not a valid app checkout. Reusing current contents without cloning."
  else
    if [[ -n "\${REPO_URL}" ]]; then
      echo "No valid app found at \${APP_DIR}; cloning from GitHub"
      sudo mkdir -p "\${APP_DIR}"
      sudo chown -R "\$(id -un)":"\$(id -gn)" "\${APP_DIR}"
      git clone "\${REPO_URL}" "\${APP_DIR}"
    else
      echo "No repo found at \${APP_DIR} and no REPO_URL configured."
      exit 1
    fi
  fi
  cd "\${APP_DIR}"
fi

cp /tmp/arithmaxchest.env "\${APP_DIR}/.env"
chmod 600 "\${APP_DIR}/.env"
chown "\$(id -un)":"\$(id -gn)" "\${APP_DIR}/.env"

cd "\${APP_DIR}"
set -a
source "\${APP_DIR}/.env"
set +a
: "\${DATA_API_TOKEN:?DATA_API_TOKEN is required}"

if [[ -f "docker-compose.ec2.yml" ]]; then
  sudo docker compose --env-file .env -f docker-compose.ec2.yml down --remove-orphans || true
  sudo docker compose --env-file .env -f docker-compose.ec2.yml build api
  sudo docker compose --env-file .env -f docker-compose.ec2.yml up -d --force-recreate
else
  echo "docker-compose.ec2.yml not found in \${APP_DIR}; exiting without changing the running container."
  exit 1
fi

curl -fsSL "\${APP_HOST}/health"
EOF

echo "Deployment finished. Confirm health: ${APP_HOST}/health"
