# Server Ops Quickstart

## Main coordinates

- host: `5.129.199.228`
- user: `root`
- app path: `/opt/projects/global-pim`
- service: `global-pim`
- domain: `https://pim.id-smart.ru`
- local health: `http://127.0.0.1:18010/api/health`

## Basic access

```bash
expect -c 'set timeout 60; spawn ssh -o StrictHostKeyChecking=no root@5.129.199.228 "echo ok && hostname && systemctl is-active global-pim"; expect "password:" {send "<server-password>\r"}; expect eof'
```

## Service control

Status:

```bash
ssh root@5.129.199.228 "systemctl status global-pim --no-pager"
```

Restart:

```bash
ssh root@5.129.199.228 "systemctl restart global-pim && sleep 3 && curl -s http://127.0.0.1:18010/api/health"
```

Recent logs:

```bash
ssh root@5.129.199.228 "journalctl -u global-pim -n 200 --no-pager"
```

Tail logs:

```bash
ssh root@5.129.199.228 "journalctl -u global-pim -f"
```

## Runtime paths

- backend: `/opt/projects/global-pim/backend`
- frontend dist: `/opt/projects/global-pim/frontend/dist`
- cert: `/opt/projects/global-pim/certs/ca.crt`
- systemd unit: `/etc/systemd/system/global-pim.service`
- nginx site: `/etc/nginx/sites-available/pim.id-smart.ru.conf`
- venv: `/opt/projects/global-pim/.venv`
- app process port: `18010`

## Runtime notes

- backend runtime storage: `Postgres-only`
- frontend в production отдается из `frontend/dist`
- systemd запускает `uvicorn app.main:app --workers 4`

## Fast checks after deploy

```bash
ssh root@5.129.199.228 "cd /opt/projects/global-pim && systemctl is-active global-pim && curl -s http://127.0.0.1:18010/api/health"
curl -s https://pim.id-smart.ru/api/health
curl -I -s https://pim.id-smart.ru
```

## Known operational notes

- frontend `index.html` should be served without cache; hashed assets can stay immutable
- backend is intended to run with multiple workers
- for backend-only fixes, prefer hot patch tarball instead of full deploy when frontend is dirty locally
- после каждого deploy нужен явный smoke-check, даже если deploy script завершился без ошибки
