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
APP_PUBLIC_BASE_URL="${APP_PUBLIC_BASE_URL:-https://pim.id-smart.ru}"
APP_SERVER_PASSWORD="${APP_SERVER_PASSWORD:-}"
SSH_TARGET="${APP_SERVER_USER}@${APP_SERVER_HOST}"
APP_LOCAL_HEALTH_URL="http://127.0.0.1:18010/api/health"
APP_PUBLIC_HEALTH_URL="${APP_PUBLIC_BASE_URL%/}/api/health"

usage() {
  cat <<USAGE
Usage: scripts/server_ops.sh <command>

Commands:
  health         Check local service health through SSH
  public-health  Check public health endpoint
  status         Show systemd service status
  logs           Show last 200 service log lines
  restart        Restart service and wait for local health
  path           Print remote app path
USAGE
}

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

command_name="${1:-}"
case "${command_name}" in
  health)
    ssh_run "curl -fsS ${APP_LOCAL_HEALTH_URL}"
    ;;
  public-health)
    curl -fsS "${APP_PUBLIC_HEALTH_URL}"
    ;;
  status)
    ssh_run "systemctl status ${APP_SERVICE_NAME} --no-pager"
    ;;
  logs)
    ssh_run "journalctl -u ${APP_SERVICE_NAME} -n 200 --no-pager"
    ;;
  restart)
    ssh_run "systemctl restart ${APP_SERVICE_NAME}; for attempt in {1..30}; do curl -fsS ${APP_LOCAL_HEALTH_URL} && exit 0; sleep 1; done; curl -fsS ${APP_LOCAL_HEALTH_URL}"
    ;;
  path)
    printf "%s\n" "${APP_SERVER_PATH}"
    ;;
  --help|-h|"")
    usage
    ;;
  *)
    echo "Unknown command: ${command_name}" >&2
    usage >&2
    exit 1
    ;;
esac
