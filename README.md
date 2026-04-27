# Global PIM

Внутренний PIM для каталога, шаблонов, словарей, товаров, маппинга источников и интеграций с маркетплейсами и конкурентными источниками.

## Структура

- `frontend/` — React + Vite SPA.
- `backend/` — FastAPI-приложение, которое отдает API и в production раздает собранный фронт.
- `backend/app/api/routes/` — HTTP-роуты.
- `backend/app/core/` — бизнес-логика, auth, storage, конкурентные и товарные сервисы.
- `deploy/sql/` — SQL-миграции для реляционного слоя.
- `docs/` — проектовая и операционная документация.
- `scripts/` — вспомогательные скрипты деплоя и сопровождения.

## Быстрый старт

### 1. Backend

```bash
cd "/Users/maksimkiselev/Desktop/Global PIM"
python3 -m venv .venv
.venv/bin/pip install -r backend/app/requirements.txt
cp .env.example backend/.env
.venv/bin/python backend/main.py
```

По умолчанию backend поднимается на `http://127.0.0.1:8010`.

Важно:

- runtime storage у проекта сейчас `Postgres-only`;
- для backend нужен валидный `DATABASE_URL` или `PIM_DATABASE_URL`;
- `PIM_STORAGE_BACKEND` должен быть `postgres`.

### 2. Frontend

```bash
cd "/Users/maksimkiselev/Desktop/Global PIM/frontend"
npm install
npm run dev
```

По умолчанию Vite поднимается на `http://127.0.0.1:5173`.

### 3. Как это работает локально

- В dev-режиме backend проксирует SPA-запросы на Vite через `DEV_PROXY=1`.
- API всегда идет через backend по `/api/...`.
- В production backend раздает `frontend/dist`.

## Полезные команды

Из корня проекта:

```bash
make backend-install
make frontend-install
make backend-dev
make frontend-dev
make frontend-build
make smoke
make test
make check
```

## Тесты и проверки

Сейчас в репе есть только минимальный smoke-тест backend:

```bash
make test
```

Что он проверяет:

- импорт FastAPI-приложения;
- ответ `/api/health`.

Дополнительно есть быстрая самопроверка:

```bash
make check
```

Она выполняет:

- `python -m unittest`
- `python -m py_compile` по backend;
- `npm run build` по frontend.

Отдельно:

```bash
make smoke
```

Сейчас это короткий рабочий baseline:

- backend smoke-тесты;
- backend compile-check;
- frontend production build.

Полноценного unit/integration/e2e контура пока нет. Это технический долг, а не скрытая возможность.

## Переменные окружения

- корневой пример: `.env.example`
- backend-ориентированный пример: `backend/.env.example`

Секреты в репу не кладем. Рабочий `.env` держим локально или на сервере.

Минимум для локального backend:

- `PIM_STORAGE_BACKEND=postgres`
- `DATABASE_URL=...`

## Production deploy

Основной скрипт:

```bash
./scripts/deploy_production.sh
```

Детали:

- [`docs/deploy-quickstart.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/deploy-quickstart.md)
- [`docs/server-ops-quickstart.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/server-ops-quickstart.md)

## Документация

- [`docs/architecture.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/architecture.md)
- [`docs/conventions.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/conventions.md)
- [`.codex/skills/smartpim-ui/SKILL.md`](/Users/maksimkiselev/Desktop/Global%20PIM/.codex/skills/smartpim-ui/SKILL.md)
- [`.codex/skills/smartpim-data-screens/SKILL.md`](/Users/maksimkiselev/Desktop/Global%20PIM/.codex/skills/smartpim-data-screens/SKILL.md)
- [`docs/tasks.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/tasks.md)
- [`docs/roadmap.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/roadmap.md)
- [`docs/content-operating-model-plan.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/content-operating-model-plan.md)
- [`docs/smartpim-full-rebuild-master-plan.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/smartpim-full-rebuild-master-plan.md)
- [`docs/multi-tenant-organization-plan.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/multi-tenant-organization-plan.md)
- [`docs/multi-tenant-foundation-spec.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/multi-tenant-foundation-spec.md)
- [`docs/testing.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/testing.md)
- [`docs/api-smoke.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/api-smoke.md)
- [`docs/json-to-relational-migration.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/json-to-relational-migration.md)

## Единый рабочий план полной переделки

Для текущего трека полной переделки продукта основной и единственный актуальный документ со статусами только один:

- [`docs/smartpim-full-rebuild-master-plan.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/smartpim-full-rebuild-master-plan.md)

Что это значит:

- активный execution slice хранится только там;
- завершенные slices хранятся только там;
- `docs/tasks.md` теперь только указывает на этот файл;
- промежуточные redesign/frontend/full-rebuild документы для этого трека удалены.
