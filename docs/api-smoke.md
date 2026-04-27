# API Smoke

## Назначение

Это короткий список API-проверок, которые полезно прогонять:

- после deploy
- после правок в auth / routing / storage
- после изменений в критичных read-model endpoints

Это не полный API reference и не замена автотестам.

## Базовый минимум

### 1. Health

```bash
curl -s https://pim.id-smart.ru/api/health
```

Ожидание:

- `200`
- тело: `{"ok":true}` или эквивалентный JSON c `ok: true`

### 2. Frontend shell

```bash
curl -I -s https://pim.id-smart.ru
```

Ожидание:

- `200`
- отдается HTML shell, а не `5xx`

### 3. Session endpoint

Без авторизации:

```bash
curl -s https://pim.id-smart.ru/api/auth/session
```

Ожидание:

- `200`
- `authenticated: false`

### 4. Protected endpoint without session

```bash
curl -i -s https://pim.id-smart.ru/api/auth/admin/bootstrap
```

Ожидание:

- `401`
- `AUTH_REQUIRED`

## Authenticated smoke

Это уже лучше делать через браузер или через тестовый клиент с cookie-session.

Минимальный набор:

1. логин успешен
2. `/api/auth/session` возвращает `authenticated: true`
3. `/api/auth/admin/bootstrap` открывается для owner/admin с нужным доступом
4. logout очищает сессию

Автоматически это уже покрывается текущим backend smoke suite:

```bash
make test
```

## Рекомендуемые read-model smoke checks

Когда трогали catalog/templates/sources, полезно проверить хотя бы эти endpoints под авторизованной сессией:

- `GET /api/catalog/nodes`
- `GET /api/catalog/products/counts`
- `GET /api/catalog/products-page-data`
- `GET /api/templates/list`
- `GET /api/templates/editor-bootstrap/{category_id}`
- `GET /api/marketplaces/mapping/import/categories`
- `GET /api/marketplaces/mapping/import/attributes/bootstrap`
- `GET /api/connectors/status`

Ожидание:

- endpoint не падает в `500`
- схема ответа не деградировала очевидным образом
- время ответа остается разумным

## После deploy

Минимальная последовательность:

```bash
ssh root@5.129.199.228 "systemctl is-active global-pim && curl -s http://127.0.0.1:18010/api/health"
curl -s https://pim.id-smart.ru/api/health
curl -I -s https://pim.id-smart.ru
```

Если менялся auth или critical UI:

```bash
make test
```

Если менялся frontend runtime:

```bash
make smoke
```
