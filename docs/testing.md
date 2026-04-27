# Testing

## Текущее состояние

В проекте есть минимальный, но уже рабочий baseline проверок.

Сейчас реально поддерживаются:

- backend smoke-тесты через `unittest`
- backend compile-check
- frontend production build

Полноценного набора unit/integration/e2e тестов по всем доменам пока нет.

## Команды

Из корня проекта:

```bash
make test
make smoke-api
make smoke
make check
```

### `make test`

Запускает backend smoke-тесты:

- `/api/health`
- `/api/auth/session` без сессии
- protected auth endpoints без логина
- login / session / logout flow
- owner access к `/api/auth/admin/bootstrap`

### `make smoke`

Запускает:

- `make smoke-api`
- `make test`
- backend compile-check
- `frontend` production build

Это основной минимальный pre-merge / pre-deploy baseline.

### `make smoke-api`

Запускает app-level read smoke-тесты на критичные API endpoints:

- `catalog/nodes`
- `catalog/products/counts`
- `catalog/products-page-data`
- `templates/list`
- `templates/editor-bootstrap/{category_id}`
- `marketplaces/mapping/import/categories`
- `marketplaces/mapping/import/attributes/bootstrap`
- `connectors/status`

Эти тесты не ходят в реальный production storage, а проверяют auth, маршрутизацию и базовый API contract на изолированном app-level harness.

### `make check`

Сейчас эквивалентен базовой технической самопроверке:

- backend tests
- backend compile-check
- frontend build

## Почему тесты изолированы

Runtime storage у проекта `Postgres-only`, но smoke-тесты не должны зависеть от реальной production-like БД.

Поэтому текущие auth smoke-тесты изолируют document storage на уровне `read_doc/write_doc`, а не пытаются эмулировать старый sqlite runtime, которого в проекте уже нет.

## Что стоит добавить дальше

Следующий разумный слой:

1. smoke-тесты на `catalog`
2. smoke-тесты на `templates`
3. smoke-тесты на `sources mapping` read endpoints
4. отдельный API smoke suite для критичных read-models
5. e2e/UI smoke на `sources-mapping`
