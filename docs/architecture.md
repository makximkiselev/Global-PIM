# Architecture

## Коротко

`Global PIM` — это SPA на React + backend на FastAPI. Backend является единой точкой входа: он обслуживает `/api`, управляет auth-сессией, работает с хранилищем и в production отдает собранный frontend.

## Модули

### Frontend

Основные зоны:

- `frontend/src/app/` — shell, router, auth context, layout.
- `frontend/src/pages/` — экранные страницы.
- `frontend/src/lib/` — клиентские helper-утилиты, включая API client.
- `frontend/src/styles/` — page-level CSS.

Frontend не ходит напрямую во внешние системы. Все сетевые запросы идут в backend через `frontend/src/lib/api.ts`.

### Backend

Основные зоны:

- `backend/app/main.py` — сборка FastAPI app, middleware, proxy/static fallback.
- `backend/app/api/routes/` — HTTP API по доменам.
- `backend/app/core/` — доменная логика, auth, storage, ingestion, competitors, products.
- `backend/app/storage/` — storage-слой.

Сейчас архитектура backend ближе к modular-monolith: домены разведены по модулям, но живут в одном приложении и одном runtime.

## Основные домены

- `catalog` — дерево категорий и базовая структура каталога.
- `templates` — мастер-шаблоны и атрибуты шаблонов.
- `dictionaries` и `attributes` — словари, параметры и reference-слой.
- `products`, `variants`, `product_groups` — товары и производные read-модели.
- `marketplace_mapping` — сопоставление категорий и параметров маркетплейсов.
- `competitor_mapping` — ссылки и поля конкурентных источников.
- `connectors_status`, `yandex_market`, `ozon_market` — интеграции и их runtime state.

## Потоки данных

### UI -> API

1. Пользователь работает в SPA.
2. Frontend вызывает `fetch("/api/...")` с cookie-based session.
3. Middleware в backend валидирует auth для непубличных API.
4. Роут вызывает доменный слой в `app.core.*`.
5. Ответ возвращается в JSON.

### Frontend delivery

Локально:

- backend может проксировать SPA-запросы на Vite (`DEV_PROXY=1`);
- Vite отдает JS/CSS, backend отдает API.

В production:

- frontend сначала собирается в `frontend/dist`;
- backend монтирует `/assets`;
- все не-API маршруты получают `index.html` как SPA fallback.

### Интеграции

Внешние интеграции у проекта сейчас такие:

- Yandex Market
- Ozon Seller
- конкурентные сайты по ссылкам категории
- S3-compatible object storage
- LLM endpoint
- ComfyUI

Внешние вызовы не должны делаться из frontend.

## Хранилище

Текущий runtime storage у проекта `Postgres-only`.

Что это значит на практике:

- backend не поддерживает рабочий sqlite runtime;
- document storage живет в Postgres, базовая таблица для document-layer это `json_documents`;
- часть доменов уже читает и пишет в нормализованные реляционные таблицы;
- часть доменов еще опирается на document-layer в Postgres как на compatibility слой.

Исторически проект пришел из JSON-файлового хранения. Эти файлы важны как источник миграционного контекста, но не как текущий production runtime.

Подробности по этапам:

- [`docs/json-to-relational-migration.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/json-to-relational-migration.md)

SQL-срезы лежат в:

- `deploy/sql/001_*.sql` ... `deploy/sql/012_*.sql`

Сейчас в проекте нет Alembic или другой автоматической migration framework. Миграции применяются как SQL-файлы и должны быть idempotent насколько это возможно.

## Auth и доступ

- cookie-based session
- auth-check делается в backend middleware
- публичными остаются только health/login/session/logout
- авторизация по страницам и действиям живет в `app.core.auth`

## Что важно не ломать

- `/api/...` как единую точку входа для frontend
- cookie-auth flow и редирект на `/login`
- SPA fallback в production
- dev proxy между backend и Vite
- Postgres-only runtime и его contracts
- compatibility слоя между `json_documents` и нормализованными таблицами, пока migration cleanup не завершен
