# Production deploy

## Runtime

- App server: `5.129.199.228`
- App path: `/opt/projects/global-pim`
- Service: `global-pim.service`
- Domain: `pim.id-smart.ru`
- Data:
  - PostgreSQL: managed external DB
  - Files: Timeweb S3

## One-time assumptions

- Server already has:
  - `nginx`
  - `python3`
  - `/etc/systemd/system/global-pim.service`
  - `/etc/nginx/sites-available/pim.id-smart.ru.conf`
  - `/opt/projects/global-pim/backend/.env`
- Local machine has DB CA cert at:
  - `$HOME/Downloads/ca.crt`

## Required backend runtime

`global-pim.service` must run `uvicorn` with multiple workers.

Required `ExecStart`:

```text
ExecStart=/opt/projects/global-pim/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 18010 --workers 4
```

Why this is required:

- single-worker `uvicorn` let one blocked request stall the whole API;
- nginx then returned upstream timeouts on:
  - `/api/auth/session`
  - `/api/health`
  - `/api/marketplaces/mapping/import/attributes/*`
- with `--workers 4`, login and parameter-mapping reads returned to acceptable latency.

The tracked reference unit now lives in:

```text
deploy/systemd/global-pim.service
```

## Deploy code

```bash
cd "/Users/maksimkiselev/Desktop/Global PIM"
./scripts/deploy_production.sh
```

Optional overrides:

```bash
APP_SERVER_HOST=5.129.199.228 \
APP_SERVER_USER=root \
APP_SERVER_PATH=/opt/projects/global-pim \
DB_CA_CERT_PATH="$HOME/Downloads/ca.crt" \
./scripts/deploy_production.sh
```

## Backup current server config

```bash
cd "/Users/maksimkiselev/Desktop/Global PIM"
./scripts/backup_server_config.sh
```

The script stores the archive on the server under:

```text
/opt/projects/global-pim/backups/server-config-YYYYMMDD-HHMMSS.tgz
```

## What deploy updates

- `backend/app`
- `backend/scripts`
- `backend/main.py`
- `backend/.env.example`
- `frontend/dist`
- `certs/ca.crt`
- Python packages from `backend/app/requirements.txt`

## What deploy does not overwrite

- `backend/.env`
- nginx config
- systemd unit
- S3 data
- PostgreSQL data
