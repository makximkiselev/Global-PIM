#!/usr/bin/env bash
set -euo pipefail

APP_ENV_FILE="${APP_ENV_FILE:-$HOME/.config/global-pim/production.env}"
if [[ -f "${APP_ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${APP_ENV_FILE}"
  set +a
fi

APP_SERVER_HOST="${APP_SERVER_HOST:-}"
APP_SERVER_USER="${APP_SERVER_USER:-}"
APP_SERVER_PORT="${APP_SERVER_PORT:-22}"
APP_SERVER_PATH="${APP_SERVER_PATH:-/opt/projects/global-pim}"
APP_SERVER_PASSWORD="${APP_SERVER_PASSWORD:-}"
APP_DB_ROLE="${APP_DB_ROLE:-}"
SSH_TARGET="${APP_SERVER_USER}@${APP_SERVER_HOST}"

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: ${name}. Set it in ${APP_ENV_FILE} or export it before running." >&2
    exit 1
  fi
}

require_env APP_SERVER_HOST
require_env APP_SERVER_USER
require_env APP_DB_ROLE

require_cmd() {
  local cmd="$1"
  command -v "${cmd}" >/dev/null 2>&1 || {
    echo "Missing required command: ${cmd}" >&2
    exit 1
  }
}

shell_quote() {
  printf "'"
  printf "%s" "$1" | sed "s/'/'\\\\''/g"
  printf "'"
}

ssh_run() {
  local remote_cmd="$1"
  local remote_shell_cmd
  remote_shell_cmd="bash -lc $(shell_quote "${remote_cmd}")"
  if [[ -n "${APP_SERVER_PASSWORD}" ]]; then
    require_cmd expect
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

ssh_run "cd ${APP_SERVER_PATH}/backend && DATABASE_URL=\$(grep ^DATABASE_URL= .env | cut -d= -f2-) && test -n \"\$DATABASE_URL\" && psql \"\$DATABASE_URL\" -v ON_ERROR_STOP=1 -v app_role='${APP_DB_ROLE}' <<'SQL'
GRANT USAGE ON SCHEMA public TO :\"app_role\";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :\"app_role\";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO :\"app_role\";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :\"app_role\";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :\"app_role\";
SELECT current_user, current_database();
SQL"

echo "DB grants repaired for role ${APP_DB_ROLE}."
