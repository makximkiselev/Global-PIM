#!/usr/bin/env bash
set -euo pipefail

APP_ENV_FILE="${APP_ENV_FILE:-$HOME/.config/global-pim/production.env}"
if [[ -f "${APP_ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${APP_ENV_FILE}"
  set +a
fi

APP_SERVER_HOST="${APP_SERVER_HOST:-5.129.199.228}"
APP_SERVER_USER="${APP_SERVER_USER:-root}"
APP_SERVER_PORT="${APP_SERVER_PORT:-22}"
APP_SERVER_PATH="${APP_SERVER_PATH:-/opt/projects/global-pim}"
APP_SERVICE_NAME="${APP_SERVICE_NAME:-global-pim.service}"
NGINX_SITE_NAME="${NGINX_SITE_NAME:-pim.id-smart.ru.conf}"
APP_SERVER_PASSWORD="${APP_SERVER_PASSWORD:-}"
SSH_TARGET="${APP_SERVER_USER}@${APP_SERVER_HOST}"
STAMP="$(date +%Y%m%d-%H%M%S)"
REMOTE_ARCHIVE="${APP_SERVER_PATH}/backups/server-config-${STAMP}.tgz"
REMOTE_SCRIPT_LOCAL="/tmp/global-pim-config-backup-${STAMP}.sh"

cleanup() {
  rm -f "${REMOTE_SCRIPT_LOCAL}"
}
trap cleanup EXIT

cat > "${REMOTE_SCRIPT_LOCAL}" <<EOF
set -euo pipefail
APP_SERVER_PATH="${APP_SERVER_PATH}"
APP_SERVICE_NAME="${APP_SERVICE_NAME}"
NGINX_SITE_NAME="${NGINX_SITE_NAME}"
REMOTE_ARCHIVE="${REMOTE_ARCHIVE}"

mkdir -p "\${APP_SERVER_PATH}/backups"
tar -czf "\${REMOTE_ARCHIVE}" \
  "/etc/systemd/system/\${APP_SERVICE_NAME}" \
  "/etc/nginx/sites-available/\${NGINX_SITE_NAME}" \
  "/etc/nginx/sites-enabled/\${NGINX_SITE_NAME}" \
  "\${APP_SERVER_PATH}/backend/.env" \
  "\${APP_SERVER_PATH}/certs/ca.crt"

printf "%s\n" "\${REMOTE_ARCHIVE}"
rm -f "/tmp/global-pim-config-backup-${STAMP}.sh"
EOF

if [[ -n "${APP_SERVER_PASSWORD}" ]]; then
  command -v expect >/dev/null 2>&1 || {
    echo "Missing required command: expect" >&2
    exit 1
  }
  APP_SERVER_PASSWORD="${APP_SERVER_PASSWORD}" \
  APP_SERVER_PORT="${APP_SERVER_PORT}" \
  SSH_TARGET="${SSH_TARGET}" \
  REMOTE_SCRIPT_LOCAL="${REMOTE_SCRIPT_LOCAL}" \
  REMOTE_SCRIPT_PATH="/tmp/global-pim-config-backup-${STAMP}.sh" \
  expect <<'EXPECT'
    set timeout -1
    spawn {*}[list scp -P $env(APP_SERVER_PORT) $env(REMOTE_SCRIPT_LOCAL) "$env(SSH_TARGET):$env(REMOTE_SCRIPT_PATH)"]
    expect {
      -re "(?i)password:" { send -- "$env(APP_SERVER_PASSWORD)\r"; exp_continue }
      eof
    }
    catch wait result
    exit [lindex $result 3]
EXPECT
  APP_SERVER_PASSWORD="${APP_SERVER_PASSWORD}" \
  APP_SERVER_PORT="${APP_SERVER_PORT}" \
  SSH_TARGET="${SSH_TARGET}" \
  REMOTE_SCRIPT_PATH="/tmp/global-pim-config-backup-${STAMP}.sh" \
  expect <<'EXPECT'
    set timeout -1
    spawn {*}[list ssh -p $env(APP_SERVER_PORT) -o StrictHostKeyChecking=no $env(SSH_TARGET) bash $env(REMOTE_SCRIPT_PATH)]
    expect {
      -re "(?i)password:" { send -- "$env(APP_SERVER_PASSWORD)\r"; exp_continue }
      eof
    }
    catch wait result
    exit [lindex $result 3]
EXPECT
else
  scp -P "${APP_SERVER_PORT}" "${REMOTE_SCRIPT_LOCAL}" "${SSH_TARGET}:/tmp/global-pim-config-backup-${STAMP}.sh"
  ssh -p "${APP_SERVER_PORT}" "${SSH_TARGET}" "bash /tmp/global-pim-config-backup-${STAMP}.sh"
fi
