# Roadmap

Не годовой стратегический документ, а ближайшая очередь инженерных направлений после текущих активных задач.

## Near-term

### 1. Multi-tenant control plane

- ввести control-plane таблицы для users, organizations, memberships и invites
- расширить auth/session contract до org-aware модели
- добавить org switch endpoint и shell dropdown
- подготовить registration bootstrap и foundation для tenant provisioning

### 2. Sources mapping stabilization

- добить UX рабочего экрана источников
- сократить визуальный шум
- добавить больше smoke-защиты для runtime этого экрана

### 3. API smoke expansion

- добавить smoke на `catalog`
- добавить smoke на `templates`
- добавить smoke на `marketplace_mapping` read endpoints
- выделить отдельный `smoke-api` контур, если список вырастет

### 4. Storage cleanup

- уменьшать зависимость hot domains от document-layer
- выносить оставшиеся read/write paths в нормализованные таблицы
- сокращать compatibility code после стабилизации доменов

### 5. Deploy hardening

- довести `deploy_production.sh` до более надежного post-check flow
- убрать ложноположительные ощущения "deploy complete"
- формализовать post-deploy smoke

## Mid-term

### 1. Tenant runtime split

- начать tenant-aware backend context
- подготовить tenant registry resolution
- переносить бизнес-домены из monolith storage в tenant-local runtime

### 2. UI e2e smoke

- завести e2e smoke на login
- завести e2e smoke на `sources-mapping`
- завести e2e smoke на 1-2 критичных read flows каталога

### 3. Stronger backend checks

- больше smoke/integration тестов вокруг auth
- smoke на connectors status
- smoke на templates editor bootstrap

### 4. Docs maturity

- постепенно отделить operational docs, architecture docs и product/workflow docs
- держать docs синхронными с runtime, а не историей проекта

## Правило

`docs/tasks.md` — это текущий активный фокус.

`docs/roadmap.md` — это следующая очередь после него.
