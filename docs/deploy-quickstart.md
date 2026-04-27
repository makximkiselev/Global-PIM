# Deploy Quickstart

## Preconditions

- runtime storage у проекта `Postgres-only`
- на сервере должен быть рабочий `backend/.env`
- локально должен существовать CA certificate, если `DATABASE_URL` использует `sslrootcert`
- после любой выкладки нужен явный smoke-check

## Full production deploy

Use the project deploy script when you want to ship the current backend app, frontend dist, and cert bundle.

```bash
cd "/Users/maksimkiselev/Desktop/Global PIM"
APP_SERVER_PASSWORD='<set-password-here>' \
DB_CA_CERT_PATH="$HOME/Downloads/ca.crt" \
./scripts/deploy_production.sh
```

Или из корня:

```bash
make deploy-prod
```

What it updates:

- `/opt/projects/global-pim/backend/app`
- `/opt/projects/global-pim/backend/scripts`
- `/opt/projects/global-pim/backend/main.py`
- `/opt/projects/global-pim/frontend/dist`
- `/opt/projects/global-pim/certs/ca.crt`

Что скрипт не делает за тебя:

- не проверяет бизнес-функции приложения;
- не заменяет post-deploy smoke-check;
- не должен считаться успешным просто по факту завершения shell-команды.

Минимальная проверка после выкладки обязательна.

## Recommended post-deploy smoke

```bash
ssh root@5.129.199.228 "systemctl is-active global-pim && curl -s http://127.0.0.1:18010/api/health"
curl -s https://pim.id-smart.ru/api/health
curl -I -s https://pim.id-smart.ru
```

## Backend-only hot patch

Use this when only backend Python files changed and frontend should stay untouched.

```bash
cd "/Users/maksimkiselev/Desktop/Global PIM"

tar czf /tmp/global-pim-backend-hotfix.tgz \
  backend/app/api/routes/catalog.py \
  backend/app/api/routes/catalog_exchange.py \
  backend/app/api/routes/ozon_market.py \
  backend/app/api/routes/product_groups.py \
  backend/app/api/routes/products.py \
  backend/app/api/routes/templates.py \
  backend/app/api/routes/yandex_market.py \
  backend/app/core/products/variants_repo.py \
  backend/app/storage/relational_pim_store.py
```

Upload:

```bash
expect -c 'set timeout 120; spawn scp /tmp/global-pim-backend-hotfix.tgz root@5.129.199.228:/tmp/global-pim-backend-hotfix.tgz; expect "password:" {send "<server-password>\r"}; expect eof'
```

Apply on server:

```bash
expect -c 'set timeout 180; spawn ssh root@5.129.199.228 "bash -lc \"cd /opt/projects/global-pim && tar xzf /tmp/global-pim-backend-hotfix.tgz && systemctl restart global-pim && sleep 5 && curl -s http://127.0.0.1:18010/api/health\""; expect "password:" {send "<server-password>\r"}; expect eof'
```

## Smoke checks

Local on server:

```bash
ssh root@5.129.199.228 "systemctl is-active global-pim && curl -s http://127.0.0.1:18010/api/health"
```

External:

```bash
curl -s https://pim.id-smart.ru/api/health
```

Frontend shell:

```bash
curl -I -s https://pim.id-smart.ru
```
