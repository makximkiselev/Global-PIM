#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_SERVER_HOST="${APP_SERVER_HOST:-5.129.199.228}"
APP_SERVER_USER="${APP_SERVER_USER:-root}"
APP_SERVER_PATH="${APP_SERVER_PATH:-/opt/projects/global-pim}"
APP_SERVICE_NAME="${APP_SERVICE_NAME:-global-pim.service}"
APP_SERVER_PORT="${APP_SERVER_PORT:-22}"
APP_SERVER_PASSWORD="${APP_SERVER_PASSWORD:-}"
DB_CA_CERT_PATH="${DB_CA_CERT_PATH:-$HOME/Downloads/ca.crt}"
SSH_TARGET="${APP_SERVER_USER}@${APP_SERVER_HOST}"
RELEASE_ID="$(date +%Y%m%d-%H%M%S)"
REMOTE_TMP_ARCHIVE="/tmp/global-pim-${RELEASE_ID}.tgz"
REMOTE_TMP_EXTRACT="/tmp/global-pim-${RELEASE_ID}"
LOCAL_TMP_DIR="$(mktemp -d /tmp/global-pim-deploy.XXXXXX)"
LOCAL_ARCHIVE="/tmp/global-pim-${RELEASE_ID}.tgz"
REMOTE_SCRIPT_LOCAL="/tmp/global-pim-${RELEASE_ID}.remote.sh"

cleanup() {
  rm -rf "${LOCAL_TMP_DIR}" "${LOCAL_ARCHIVE}" "${REMOTE_SCRIPT_LOCAL}"
}
trap cleanup EXIT

require_file() {
  local path="$1"
  if [[ ! -f "${path}" ]]; then
    echo "Missing required file: ${path}" >&2
    exit 1
  fi
}

require_cmd() {
  local cmd="$1"
  command -v "${cmd}" >/dev/null 2>&1 || {
    echo "Missing required command: ${cmd}" >&2
    exit 1
  }
}

require_cmd npm
require_cmd tar
require_cmd scp
require_cmd ssh
require_cmd rsync
if [[ -n "${APP_SERVER_PASSWORD}" ]]; then
  require_cmd expect
fi

require_file "${ROOT_DIR}/backend/app/requirements.txt"
require_file "${ROOT_DIR}/backend/main.py"
require_file "${ROOT_DIR}/backend/.env.example"
require_file "${ROOT_DIR}/frontend/package.json"
require_file "${ROOT_DIR}/frontend/index.html"
require_file "${DB_CA_CERT_PATH}"

echo "==> Building frontend"
( cd "${ROOT_DIR}/frontend" && npm run build )

ssh_run() {
  local remote_cmd="$1"
  if [[ -n "${APP_SERVER_PASSWORD}" ]]; then
    expect -c "
      set timeout -1
      spawn ssh -p ${APP_SERVER_PORT} -o StrictHostKeyChecking=no ${SSH_TARGET} $remote_cmd
      expect \"password:\" { send \"${APP_SERVER_PASSWORD}\r\" }
      expect eof
    "
  else
    ssh -p "${APP_SERVER_PORT}" "${SSH_TARGET}" "${remote_cmd}"
  fi
}

scp_run() {
  local source_path="$1"
  local target_path="$2"
  if [[ -n "${APP_SERVER_PASSWORD}" ]]; then
    expect -c "
      set timeout -1
      spawn scp -P ${APP_SERVER_PORT} ${source_path} ${SSH_TARGET}:${target_path}
      expect \"password:\" { send \"${APP_SERVER_PASSWORD}\r\" }
      expect eof
    "
  else
    scp -P "${APP_SERVER_PORT}" "${source_path}" "${SSH_TARGET}:${target_path}"
  fi
}

echo "==> Preparing release bundle"
mkdir -p "${LOCAL_TMP_DIR}/backend" "${LOCAL_TMP_DIR}/frontend" "${LOCAL_TMP_DIR}/certs"

rsync -a \
  --exclude '.env' \
  --exclude 'data' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  "${ROOT_DIR}/backend/" "${LOCAL_TMP_DIR}/backend/"

mkdir -p "${LOCAL_TMP_DIR}/frontend/dist"
rsync -a \
  --exclude '.DS_Store' \
  "${ROOT_DIR}/frontend/dist/" "${LOCAL_TMP_DIR}/frontend/dist/"

cp "${DB_CA_CERT_PATH}" "${LOCAL_TMP_DIR}/certs/ca.crt"

tar -C "${LOCAL_TMP_DIR}" -czf "${LOCAL_ARCHIVE}" .

cat > "${REMOTE_SCRIPT_LOCAL}" <<EOF
set -euo pipefail
APP_SERVER_PATH="${APP_SERVER_PATH}"
APP_SERVICE_NAME="${APP_SERVICE_NAME}"
REMOTE_TMP_ARCHIVE="${REMOTE_TMP_ARCHIVE}"
REMOTE_TMP_EXTRACT="${REMOTE_TMP_EXTRACT}"
RELEASE_ID="${RELEASE_ID}"

mkdir -p "\${APP_SERVER_PATH}" "\${APP_SERVER_PATH}/backups"
rm -rf "\${REMOTE_TMP_EXTRACT}"
mkdir -p "\${REMOTE_TMP_EXTRACT}"
tar -C "\${REMOTE_TMP_EXTRACT}" -xzf "\${REMOTE_TMP_ARCHIVE}"

if [[ -d "\${APP_SERVER_PATH}/backend" ]]; then
  tar -C "\${APP_SERVER_PATH}" -czf "\${APP_SERVER_PATH}/backups/app-\${RELEASE_ID}.tgz" \
    --exclude='backups' \
    --exclude='backend/.env' \
    --exclude='certs' \
    backend frontend 2>/dev/null || true
fi

mkdir -p "\${APP_SERVER_PATH}/backend" "\${APP_SERVER_PATH}/frontend" "\${APP_SERVER_PATH}/certs"
rm -rf "\${APP_SERVER_PATH}/backend/app" "\${APP_SERVER_PATH}/backend/scripts" "\${APP_SERVER_PATH}/frontend/dist"

cp -R "\${REMOTE_TMP_EXTRACT}/backend/app" "\${APP_SERVER_PATH}/backend/app"
cp -R "\${REMOTE_TMP_EXTRACT}/backend/scripts" "\${APP_SERVER_PATH}/backend/scripts"
cp "\${REMOTE_TMP_EXTRACT}/backend/main.py" "\${APP_SERVER_PATH}/backend/main.py"
cp "\${REMOTE_TMP_EXTRACT}/backend/.env.example" "\${APP_SERVER_PATH}/backend/.env.example"
cp -R "\${REMOTE_TMP_EXTRACT}/frontend/dist" "\${APP_SERVER_PATH}/frontend/dist"
cp "\${REMOTE_TMP_EXTRACT}/certs/ca.crt" "\${APP_SERVER_PATH}/certs/ca.crt"

if [[ ! -d "\${APP_SERVER_PATH}/.venv" ]]; then
  python3 -m venv "\${APP_SERVER_PATH}/.venv"
fi
"\${APP_SERVER_PATH}/.venv/bin/pip" install -r "\${APP_SERVER_PATH}/backend/app/requirements.txt"

systemctl restart "\${APP_SERVICE_NAME}"
sleep 2
curl -s http://127.0.0.1:18010/api/health >/dev/null

rm -rf "\${REMOTE_TMP_EXTRACT}" "\${REMOTE_TMP_ARCHIVE}" "/tmp/global-pim-\${RELEASE_ID}.remote.sh"
EOF

echo "==> Uploading archive to ${SSH_TARGET}"
scp_run "${LOCAL_ARCHIVE}" "${REMOTE_TMP_ARCHIVE}"
scp_run "${REMOTE_SCRIPT_LOCAL}" "/tmp/global-pim-${RELEASE_ID}.remote.sh"

echo "==> Deploying on server"
ssh_run "'bash /tmp/global-pim-${RELEASE_ID}.remote.sh'"

echo "==> Deploy complete"
echo "Server: ${SSH_TARGET}"
echo "App path: ${APP_SERVER_PATH}"
echo "Health: https://pim.id-smart.ru/api/health"
