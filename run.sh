#!/usr/bin/env bash
# Start JARVIS (backend + frontend) for local development.
#
#   ./run.sh
#
# Backend  http://127.0.0.1:8000  (API docs at /docs)
# Frontend http://127.0.0.1:3000
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

echo "==> Preparing backend"
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt

echo "==> Preparing frontend"
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  npm install --silent
fi

echo "==> Starting backend on :$BACKEND_PORT"
cd "$ROOT/backend"
PYTHONPATH=. ./.venv/bin/python -m uvicorn app.main:app \
  --host 0.0.0.0 --port "$BACKEND_PORT" > /tmp/jarvis-backend.log 2>&1 &
BACKEND_PID=$!

echo "==> Starting frontend on :$FRONTEND_PORT"
cd "$ROOT/frontend"
JARVIS_BACKEND_URL="http://127.0.0.1:$BACKEND_PORT" \
  npx vite --host 0.0.0.0 --port "$FRONTEND_PORT" > /tmp/jarvis-frontend.log 2>&1 &
FRONTEND_PID=$!

cleanup() {
  echo
  echo "==> Stopping JARVIS"
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo
echo "  JARVIS is starting."
echo "  Frontend : http://127.0.0.1:$FRONTEND_PORT"
echo "  Backend  : http://127.0.0.1:$BACKEND_PORT"
echo "  API docs : http://127.0.0.1:$BACKEND_PORT/docs"
echo "  Logs     : /tmp/jarvis-backend.log  /tmp/jarvis-frontend.log"
echo
echo "  Press Ctrl+C to stop."
wait
