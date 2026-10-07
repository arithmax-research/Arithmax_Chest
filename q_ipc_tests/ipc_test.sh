#!/usr/bin/env bash
# ipc_test.sh — one-stop IPC test & deploy helper
# Usage:
#   ./q_ipc_tests/ipc_test.sh bench                  # run benchmark with defaults
#   ./q_ipc_tests/ipc_test.sh bench AAPL ...         # custom params
#   ./q_ipc_tests/ipc_test.sh deploy                 # scp + restart proxy on server
#   ./q_ipc_tests/ipc_test.sh deploy 13.212.15.78    # custom host

set -euo pipefail
HOST="${2:-13.212.15.78}"
PORT="${3:-5001}"
SSH_USER="${SSH_USER:-ubuntu}"
APP_DIR="${APP_DIR:-/home/ubuntu/codechest/Arithmax_Chest}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/arithmax.pem}"

case "${1:-bench}" in
  bench)
    shift 2>/dev/null || true
    cd "$(dirname "$0")/.."
    q q_ipc_tests/ipc_bench.q "$@"
    ;;
  deploy)
    echo "→ Copying qserver_proxy.q to ${HOST}..."
    scp -i "${SSH_KEY}" -o StrictHostKeyChecking=accept-new \
      achest-kdb-q/qserver_proxy.q \
      "${SSH_USER}@${HOST}:${APP_DIR}/achest-kdb-q/qserver_proxy.q"

    echo "→ Copying achest.q (client lib)…"
    scp -i "${SSH_KEY}" -o StrictHostKeyChecking=accept-new \
      achest-kdb-q/achest.q \
      "${SSH_USER}@${HOST}:${APP_DIR}/achest-kdb-q/achest.q"

    echo "→ Restarting q proxy on ${HOST}:${PORT}..."
    ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=accept-new "${SSH_USER}@${HOST}" <<EOF
      pkill -f "qserver_proxy.q" 2>/dev/null || true
      sleep 1
      cd "${APP_DIR}"
      nohup q achest-kdb-q/qserver_proxy.q -p ${PORT} > nohup.out 2>&1 &
      sleep 1
      echo "Proxy PID: \$(pgrep -f qserver_proxy.q)"
      ss -tulpn | grep ':${PORT}' || echo "⚠ Port ${PORT} not listening"
EOF
    echo "✓ Deployed. Run './q_ipc_tests/ipc_test.sh bench' to test."
    ;;
  *)
    echo "Usage: $0 {bench|deploy} [args...]"
    exit 1
    ;;
esac