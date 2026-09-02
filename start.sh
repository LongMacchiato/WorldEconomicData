#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

API_HOST="${DBNOMICS_API_HOST:-127.0.0.1}"
API_PORT="${DBNOMICS_API_PORT:-8001}"
OPEN_BROWSER="${DBNOMICS_OPEN_BROWSER:-1}"

VENV_DIR="${ROOT_DIR}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
FRONTEND_DIR="${ROOT_DIR}/frontend"

BACKEND_PID=""

cleanup() {
  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    echo "Stopping API (pid ${BACKEND_PID})..."
    kill "${BACKEND_PID}" 2>/dev/null || true
    wait "${BACKEND_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

load_nvm() {
  export NVM_DIR="${NVM_DIR:-${HOME}/.nvm}"
  if [[ -s "${NVM_DIR}/nvm.sh" ]]; then
    # shellcheck source=/dev/null
    . "${NVM_DIR}/nvm.sh"
    if [[ -f "${ROOT_DIR}/.nvmrc" ]]; then
      nvm use
    elif [[ -f "${FRONTEND_DIR}/.nvmrc" ]]; then
      nvm use --silent "${FRONTEND_DIR}"
    fi
  elif ! command -v node >/dev/null 2>&1; then
    echo "Node.js not found. Install Node 24 or configure nvm." >&2
    exit 1
  fi
}

ensure_python_env() {
  if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "Creating Python virtual environment in .venv..."
    python3 -m venv "${VENV_DIR}"
  fi

  if ! "${VENV_PYTHON}" -m uvicorn --help >/dev/null 2>&1; then
    echo "Installing Python dependencies..."
    "${VENV_PYTHON}" -m pip install -r requirements.txt
  fi
}

ensure_frontend_deps() {
  if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
    echo "Installing frontend dependencies..."
    load_nvm
    npm --prefix "${FRONTEND_DIR}" ci
  fi
}

wait_for_api() {
  local health_url="http://${API_HOST}:${API_PORT}/health"
  echo "Waiting for API at ${health_url}..."
  for _ in $(seq 1 60); do
    if curl -sf "${health_url}" >/dev/null 2>&1; then
      return 0
    fi
    if [[ -n "${BACKEND_PID}" ]] && ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
      echo "API process exited before becoming ready." >&2
      return 1
    fi
    sleep 0.5
  done
  echo "Timed out waiting for API at ${health_url}" >&2
  return 1
}

start_backend() {
  echo "Starting API on http://${API_HOST}:${API_PORT} ..."
  "${VENV_PYTHON}" -m uvicorn app.main:app \
    --app-dir backend \
    --host "${API_HOST}" \
    --port "${API_PORT}" \
    --reload &
  BACKEND_PID=$!
}

start_frontend() {
  load_nvm
  echo "Starting frontend (Vite proxies /api to port ${API_PORT})..."
  echo "App URL: http://localhost:5173"
  echo "API docs: http://${API_HOST}:${API_PORT}/docs"
  echo "Press Ctrl+C to stop both servers."
  echo

  if [[ "${OPEN_BROWSER}" == "1" ]] && command -v open >/dev/null 2>&1; then
    (sleep 2 && open "http://localhost:5173") &
  fi

  npm --prefix "${FRONTEND_DIR}" run dev
}

main() {
  ensure_python_env
  ensure_frontend_deps
  start_backend
  wait_for_api
  start_frontend
}

main "$@"
