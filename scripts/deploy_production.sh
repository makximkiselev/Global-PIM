#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ENV_FILE="${APP_ENV_FILE:-$HOME/.config/global-pim/production.env}"
if [[ -f "${APP_ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${APP_ENV_FILE}"
  set +a
fi

APP_SERVER_HOST="${APP_SERVER_HOST:-}"
APP_SERVER_USER="${APP_SERVER_USER:-}"
APP_SERVER_PATH="${APP_SERVER_PATH:-/opt/projects/global-pim}"
APP_SERVICE_NAME="${APP_SERVICE_NAME:-global-pim.service}"
APP_WORKER_SERVICE_NAME="${APP_WORKER_SERVICE_NAME:-global-pim-ai-match-worker.service}"
APP_VALUE_WORKER_SERVICE_NAME="${APP_VALUE_WORKER_SERVICE_NAME:-global-pim-value-ai-worker.service}"
APP_EXPORT_WORKER_SERVICE_NAME="${APP_EXPORT_WORKER_SERVICE_NAME:-global-pim-export-worker.service}"
APP_SERVER_PORT="${APP_SERVER_PORT:-22}"
APP_SERVER_PASSWORD="${APP_SERVER_PASSWORD:-}"
APP_DB_ROLE="${APP_DB_ROLE:-}"
DB_CA_CERT_PATH="${DB_CA_CERT_PATH:-$HOME/Downloads/ca.crt}"
APP_PUBLIC_BASE_URL="${APP_PUBLIC_BASE_URL:-https://pim.id-smart.ru}"
APP_DEPLOY_BACKUP_KEEP="${APP_DEPLOY_BACKUP_KEEP:-20}"
SSH_TARGET="${APP_SERVER_USER}@${APP_SERVER_HOST}"
RELEASE_ID="$(date +%Y%m%d-%H%M%S)"
REMOTE_TMP_ARCHIVE="/tmp/global-pim-${RELEASE_ID}.tgz"
REMOTE_TMP_EXTRACT="/tmp/global-pim-${RELEASE_ID}"
LOCAL_TMP_DIR="$(mktemp -d /tmp/global-pim-deploy.XXXXXX)"
LOCAL_ARCHIVE="/tmp/global-pim-${RELEASE_ID}.tgz"
REMOTE_SCRIPT_LOCAL="/tmp/global-pim-${RELEASE_ID}.remote.sh"
APP_LOCAL_HEALTH_URL="http://127.0.0.1:18010/api/health"
APP_LOCAL_DB_GRANTS_HEALTH_URL="http://127.0.0.1:18010/api/health/db-grants"
APP_PUBLIC_HEALTH_URL="${APP_PUBLIC_BASE_URL%/}/api/health"
APP_PUBLIC_DB_GRANTS_HEALTH_URL="${APP_PUBLIC_BASE_URL%/}/api/health/db-grants"
APP_RUN_SCENARIO_SMOKE="${APP_RUN_SCENARIO_SMOKE:-0}"
APP_SCENARIO_SMOKE_INSECURE_SSL="${APP_SCENARIO_SMOKE_INSECURE_SSL:-0}"
APP_SCENARIO_SMOKE_BROWSER="${APP_SCENARIO_SMOKE_BROWSER:-0}"
APP_SCENARIO_SMOKE_REQUIRE_AUTH="${APP_SCENARIO_SMOKE_REQUIRE_AUTH:-0}"
APP_SCENARIO_SMOKE_ALLOW_AUTH_WALL="${APP_SCENARIO_SMOKE_ALLOW_AUTH_WALL:-0}"
SKIP_BUILD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --help|-h)
      cat <<USAGE
Usage: scripts/deploy_production.sh [--skip-build]

Environment is loaded automatically from:
  ${APP_ENV_FILE}

Options:
  --skip-build  deploy existing frontend/dist without running npm build

Optional post-deploy scenario smoke:
  APP_RUN_SCENARIO_SMOKE=1 scripts/deploy_production.sh
  APP_SCENARIO_SMOKE_INSECURE_SSL=1 can be used on local machines with a stale Python CA bundle.
  APP_SCENARIO_SMOKE_BROWSER=1 runs Playwright route checks after public checks.
  APP_SCENARIO_SMOKE_REQUIRE_AUTH=1 requires SMARTPIM_SMOKE_EMAIL and SMARTPIM_SMOKE_PASSWORD.
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

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

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: ${name}. Set it in ${APP_ENV_FILE} or export it before running." >&2
    exit 1
  fi
}

shell_quote() {
  printf "'"
  printf "%s" "$1" | sed "s/'/'\\\\''/g"
  printf "'"
}

require_env APP_SERVER_HOST
require_env APP_SERVER_USER
require_env APP_DB_ROLE
require_cmd tar
require_cmd scp
require_cmd ssh
require_cmd rsync
require_cmd curl
if [[ -n "${APP_SERVER_PASSWORD}" ]]; then
  require_cmd expect
fi

require_file "${ROOT_DIR}/backend/app/requirements.txt"
require_file "${ROOT_DIR}/backend/main.py"
require_file "${ROOT_DIR}/backend/.env.example"
require_file "${ROOT_DIR}/frontend/package.json"
require_file "${ROOT_DIR}/frontend/index.html"
require_file "${ROOT_DIR}/deploy/systemd/${APP_WORKER_SERVICE_NAME}"
require_file "${ROOT_DIR}/deploy/systemd/${APP_VALUE_WORKER_SERVICE_NAME}"
require_file "${ROOT_DIR}/deploy/systemd/${APP_EXPORT_WORKER_SERVICE_NAME}"
require_file "${DB_CA_CERT_PATH}"

if [[ "${SKIP_BUILD}" == "1" ]]; then
  require_file "${ROOT_DIR}/frontend/dist/index.html"
  echo "==> Skipping frontend build; using existing frontend/dist"
else
  require_cmd npm
  echo "==> Building frontend"
  ( cd "${ROOT_DIR}/frontend" && npm run build )
fi

ssh_run() {
  local remote_cmd="$1"
  local remote_shell_cmd
  remote_shell_cmd="bash -lc $(shell_quote "${remote_cmd}")"
  if [[ -n "${APP_SERVER_PASSWORD}" ]]; then
    APP_SERVER_PASSWORD="${APP_SERVER_PASSWORD}" \
    APP_SERVER_PORT="${APP_SERVER_PORT}" \
    SSH_TARGET="${SSH_TARGET}" \
    REMOTE_CMD="${remote_shell_cmd}" \
    expect <<'EXPECT'
      set timeout -1
      spawn {*}[list ssh -p $env(APP_SERVER_PORT) -o StrictHostKeyChecking=no $env(SSH_TARGET) $env(REMOTE_CMD)]
      expect {
        -re "(?i)password:" { send -- "$env(APP_SERVER_PASSWORD)\r"; exp_continue }
        eof
      }
      catch wait result
      exit [lindex $result 3]
EXPECT
  else
    ssh -p "${APP_SERVER_PORT}" "${SSH_TARGET}" "${remote_shell_cmd}"
  fi
}

scp_run() {
  local source_path="$1"
  local target_path="$2"
  if [[ -n "${APP_SERVER_PASSWORD}" ]]; then
    APP_SERVER_PASSWORD="${APP_SERVER_PASSWORD}" \
    APP_SERVER_PORT="${APP_SERVER_PORT}" \
    SSH_TARGET="${SSH_TARGET}" \
    SOURCE_PATH="${source_path}" \
    TARGET_PATH="${target_path}" \
    expect <<'EXPECT'
      set timeout -1
      spawn {*}[list scp -P $env(APP_SERVER_PORT) $env(SOURCE_PATH) "$env(SSH_TARGET):$env(TARGET_PATH)"]
      expect {
        -re "(?i)password:" { send -- "$env(APP_SERVER_PASSWORD)\r"; exp_continue }
        eof
      }
      catch wait result
      exit [lindex $result 3]
EXPECT
  else
    scp -P "${APP_SERVER_PORT}" "${source_path}" "${SSH_TARGET}:${target_path}"
  fi
}

curl_retry() {
  local url="$1"
  local attempts="${2:-30}"
  local delay="${3:-1}"

  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if curl -fsS "${url}" >/dev/null; then
      return 0
    fi
    sleep "${delay}"
  done

  curl -fsS "${url}" >/dev/null
}

tar_supports_flag() {
  local flag="$1"
  local probe_dir
  probe_dir="$(mktemp -d /tmp/global-pim-tar-probe.XXXXXX)"
  printf "probe\n" > "${probe_dir}/probe.txt"
  if tar "${flag}" -C "${probe_dir}" -cf /tmp/global-pim-tar-probe.tar . >/dev/null 2>&1; then
    rm -rf "${probe_dir}" /tmp/global-pim-tar-probe.tar
    return 0
  fi
  rm -rf "${probe_dir}" /tmp/global-pim-tar-probe.tar
  return 1
}

create_release_archive() {
  local source_dir="$1"
  local archive_path="$2"
  local extra_flags=()

  if tar_supports_flag "--no-xattrs"; then
    extra_flags+=("--no-xattrs")
  fi
  if tar_supports_flag "--no-mac-metadata"; then
    extra_flags+=("--no-mac-metadata")
  fi

  COPYFILE_DISABLE=1 tar "${extra_flags[@]}" -C "${source_dir}" -czf "${archive_path}" .
}

echo "==> Preparing release bundle"
mkdir -p "${LOCAL_TMP_DIR}/backend" "${LOCAL_TMP_DIR}/frontend" "${LOCAL_TMP_DIR}/certs" "${LOCAL_TMP_DIR}/deploy/systemd"

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
cp "${ROOT_DIR}/deploy/systemd/${APP_WORKER_SERVICE_NAME}" "${LOCAL_TMP_DIR}/deploy/systemd/${APP_WORKER_SERVICE_NAME}"
cp "${ROOT_DIR}/deploy/systemd/${APP_VALUE_WORKER_SERVICE_NAME}" "${LOCAL_TMP_DIR}/deploy/systemd/${APP_VALUE_WORKER_SERVICE_NAME}"
cp "${ROOT_DIR}/deploy/systemd/${APP_EXPORT_WORKER_SERVICE_NAME}" "${LOCAL_TMP_DIR}/deploy/systemd/${APP_EXPORT_WORKER_SERVICE_NAME}"

if command -v xattr >/dev/null 2>&1; then
  xattr -cr "${LOCAL_TMP_DIR}" 2>/dev/null || true
fi
create_release_archive "${LOCAL_TMP_DIR}" "${LOCAL_ARCHIVE}"

cat > "${REMOTE_SCRIPT_LOCAL}" <<EOF
set -euo pipefail
APP_SERVER_PATH="${APP_SERVER_PATH}"
APP_SERVICE_NAME="${APP_SERVICE_NAME}"
APP_WORKER_SERVICE_NAME="${APP_WORKER_SERVICE_NAME}"
APP_VALUE_WORKER_SERVICE_NAME="${APP_VALUE_WORKER_SERVICE_NAME}"
APP_EXPORT_WORKER_SERVICE_NAME="${APP_EXPORT_WORKER_SERVICE_NAME}"
APP_DB_ROLE="${APP_DB_ROLE}"
REMOTE_TMP_ARCHIVE="${REMOTE_TMP_ARCHIVE}"
REMOTE_TMP_EXTRACT="${REMOTE_TMP_EXTRACT}"
RELEASE_ID="${RELEASE_ID}"
APP_DEPLOY_BACKUP_KEEP="${APP_DEPLOY_BACKUP_KEEP}"

repair_app_db_grants() {
  local database_url
  database_url="\$(grep ^DATABASE_URL= "\${APP_SERVER_PATH}/backend/.env" | cut -d= -f2-)"
  test -n "\${database_url}"
  psql "\${database_url}" -v ON_ERROR_STOP=1 -v app_role="\${APP_DB_ROLE}" <<'SQL'
GRANT USAGE ON SCHEMA public TO :"app_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_role";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO :"app_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :"app_role";
SQL
}

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

if [[ "\${APP_DEPLOY_BACKUP_KEEP}" =~ ^[0-9]+$ && "\${APP_DEPLOY_BACKUP_KEEP}" -gt 0 ]]; then
  mapfile -t OLD_APP_BACKUPS < <(find "\${APP_SERVER_PATH}/backups" -maxdepth 1 -type f -name 'app-*.tgz' -printf '%T@ %p\n' | sort -nr | tail -n +"$((APP_DEPLOY_BACKUP_KEEP + 1))" | cut -d' ' -f2-)
  if [[ "\${#OLD_APP_BACKUPS[@]}" -gt 0 ]]; then
    rm -f -- "\${OLD_APP_BACKUPS[@]}"
  fi
fi

mkdir -p "\${APP_SERVER_PATH}/backend" "\${APP_SERVER_PATH}/frontend" "\${APP_SERVER_PATH}/certs"
rm -rf "\${APP_SERVER_PATH}/backend/app" "\${APP_SERVER_PATH}/backend/scripts" "\${APP_SERVER_PATH}/frontend/dist"

cp -R "\${REMOTE_TMP_EXTRACT}/backend/app" "\${APP_SERVER_PATH}/backend/app"
cp -R "\${REMOTE_TMP_EXTRACT}/backend/scripts" "\${APP_SERVER_PATH}/backend/scripts"
cp "\${REMOTE_TMP_EXTRACT}/backend/main.py" "\${APP_SERVER_PATH}/backend/main.py"
cp "\${REMOTE_TMP_EXTRACT}/backend/.env.example" "\${APP_SERVER_PATH}/backend/.env.example"
cp -R "\${REMOTE_TMP_EXTRACT}/frontend/dist" "\${APP_SERVER_PATH}/frontend/dist"
cp "\${REMOTE_TMP_EXTRACT}/certs/ca.crt" "\${APP_SERVER_PATH}/certs/ca.crt"

if [[ -f "\${REMOTE_TMP_EXTRACT}/deploy/systemd/\${APP_WORKER_SERVICE_NAME}" ]]; then
  cp "\${REMOTE_TMP_EXTRACT}/deploy/systemd/\${APP_WORKER_SERVICE_NAME}" "/etc/systemd/system/\${APP_WORKER_SERVICE_NAME}"
fi
if [[ -f "\${REMOTE_TMP_EXTRACT}/deploy/systemd/\${APP_VALUE_WORKER_SERVICE_NAME}" ]]; then
  cp "\${REMOTE_TMP_EXTRACT}/deploy/systemd/\${APP_VALUE_WORKER_SERVICE_NAME}" "/etc/systemd/system/\${APP_VALUE_WORKER_SERVICE_NAME}"
fi
if [[ -f "\${REMOTE_TMP_EXTRACT}/deploy/systemd/\${APP_EXPORT_WORKER_SERVICE_NAME}" ]]; then
  cp "\${REMOTE_TMP_EXTRACT}/deploy/systemd/\${APP_EXPORT_WORKER_SERVICE_NAME}" "/etc/systemd/system/\${APP_EXPORT_WORKER_SERVICE_NAME}"
fi
systemctl daemon-reload
if [[ -f "/etc/systemd/system/\${APP_WORKER_SERVICE_NAME}" ]]; then
  systemctl enable "\${APP_WORKER_SERVICE_NAME}" >/dev/null
fi
if [[ -f "/etc/systemd/system/\${APP_VALUE_WORKER_SERVICE_NAME}" ]]; then
  systemctl enable "\${APP_VALUE_WORKER_SERVICE_NAME}" >/dev/null
fi
if [[ -f "/etc/systemd/system/\${APP_EXPORT_WORKER_SERVICE_NAME}" ]]; then
  systemctl enable "\${APP_EXPORT_WORKER_SERVICE_NAME}" >/dev/null
fi

if [[ ! -d "\${APP_SERVER_PATH}/.venv" ]]; then
  python3 -m venv "\${APP_SERVER_PATH}/.venv"
fi

REQ_HASH="\$(sha256sum "\${APP_SERVER_PATH}/backend/app/requirements.txt" | awk '{print \$1}')"
REQ_HASH_FILE="\${APP_SERVER_PATH}/.requirements.sha256"
if [[ ! -f "\${REQ_HASH_FILE}" || "\$(cat "\${REQ_HASH_FILE}")" != "\${REQ_HASH}" ]]; then
  "\${APP_SERVER_PATH}/.venv/bin/pip" install -r "\${APP_SERVER_PATH}/backend/app/requirements.txt"
  printf "%s\n" "\${REQ_HASH}" > "\${REQ_HASH_FILE}"
else
  echo "Requirements unchanged; skipping pip install"
fi

repair_app_db_grants

systemctl restart "\${APP_SERVICE_NAME}"
if systemctl list-unit-files "\${APP_WORKER_SERVICE_NAME}" >/dev/null 2>&1; then
  systemctl restart "\${APP_WORKER_SERVICE_NAME}"
fi
if systemctl list-unit-files "\${APP_VALUE_WORKER_SERVICE_NAME}" >/dev/null 2>&1; then
  systemctl restart "\${APP_VALUE_WORKER_SERVICE_NAME}"
fi
if systemctl list-unit-files "\${APP_EXPORT_WORKER_SERVICE_NAME}" >/dev/null 2>&1; then
  systemctl restart "\${APP_EXPORT_WORKER_SERVICE_NAME}"
fi
for attempt in {1..30}; do
  if curl -fsS "${APP_LOCAL_HEALTH_URL}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "${APP_LOCAL_HEALTH_URL}" >/dev/null
curl -fsS "${APP_LOCAL_DB_GRANTS_HEALTH_URL}" >/dev/null

rm -rf "\${REMOTE_TMP_EXTRACT}" "\${REMOTE_TMP_ARCHIVE}" "/tmp/global-pim-\${RELEASE_ID}.remote.sh"
EOF

echo "==> Uploading archive to ${SSH_TARGET}"
scp_run "${LOCAL_ARCHIVE}" "${REMOTE_TMP_ARCHIVE}"
scp_run "${REMOTE_SCRIPT_LOCAL}" "/tmp/global-pim-${RELEASE_ID}.remote.sh"

echo "==> Deploying on server"
ssh_run "bash /tmp/global-pim-${RELEASE_ID}.remote.sh"

echo "==> Post-deploy smoke"
ssh_run "systemctl is-active ${APP_SERVICE_NAME} && systemctl is-active ${APP_WORKER_SERVICE_NAME} && systemctl is-active ${APP_VALUE_WORKER_SERVICE_NAME} && systemctl is-active ${APP_EXPORT_WORKER_SERVICE_NAME} && curl -fsS ${APP_LOCAL_HEALTH_URL} && curl -fsS ${APP_LOCAL_DB_GRANTS_HEALTH_URL}"
curl_retry "${APP_PUBLIC_HEALTH_URL}" 30 1
curl_retry "${APP_PUBLIC_DB_GRANTS_HEALTH_URL}" 30 1
curl -I -fsS "${APP_PUBLIC_BASE_URL}" >/dev/null
if [[ "${APP_RUN_SCENARIO_SMOKE}" == "1" ]]; then
  echo "==> Scenario smoke"
  smoke_args=(--base-url "${APP_PUBLIC_BASE_URL}")
  if [[ "${APP_SCENARIO_SMOKE_BROWSER}" != "1" ]]; then
    smoke_args+=(--public-only)
  else
    smoke_args+=(--browser)
  fi
  if [[ "${APP_SCENARIO_SMOKE_REQUIRE_AUTH}" == "1" ]]; then
    smoke_args+=(--require-auth)
  fi
  if [[ "${APP_SCENARIO_SMOKE_ALLOW_AUTH_WALL}" == "1" ]]; then
    smoke_args+=(--allow-auth-wall)
  fi
  if [[ "${APP_SCENARIO_SMOKE_INSECURE_SSL}" == "1" ]]; then
    smoke_args+=(--insecure-ssl)
  fi
  python3 "${ROOT_DIR}/scripts/scenario_smoke.py" "${smoke_args[@]}"
fi

echo "==> Deploy complete"
echo "Server: ${SSH_TARGET}"
echo "App path: ${APP_SERVER_PATH}"
echo "Health: ${APP_PUBLIC_HEALTH_URL}"
echo "DB grants health: ${APP_PUBLIC_DB_GRANTS_HEALTH_URL}"
