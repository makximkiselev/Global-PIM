# Conventions

## Общий принцип

Проект pragmatic-first. Сначала сохраняем работоспособность runtime и совместимость данных в текущем `Postgres-only` контуре, потом улучшаем форму кода.

## Naming

### Frontend

- React-компоненты: `PascalCase`
- hooks/helpers/локальные функции: `camelCase`
- CSS-классы: page/module prefix, без глобального мусора
- page-файлы: по смыслу страницы, например `SourcesMarketplaceSection.tsx`

### Backend

- python modules/functions: `snake_case`
- route handlers: глагол или предметный action без лишней абстракции
- storage entities/read models: suffix `*_rel` для реляционных таблиц и проекций, если это уже принято в коде

## Функции

- одна функция отвечает за один уровень абстракции
- если функция трогает storage и бизнес-правила одновременно, лучше вынести storage-часть в отдельный helper/repo слой
- если логика нужна только одному роуту и не переиспользуется, не нужно делать фальшивую универсализацию

## API-роуты

Текущая структура:

- каждый домен живет в своем файле в `backend/app/api/routes/`
- файл роутов не должен разрастаться в свалку для нескольких доменов
- тонкий роут предпочтительнее: валидация запроса, auth-check, вызов доменной логики, сериализация ответа

Практические правила:

- не мешать новый unrelated endpoint в чужой доменный файл
- не тянуть тяжелую бизнес-логику внутрь route handler, если она уже живет в `app.core`
- ошибки отдавать предсказуемо, а не через silent fallback

## Миграции

Сейчас миграции ведутся SQL-файлами в `deploy/sql/`.

Правила:

- новый SQL-файл только с новым номером
- не переписывать старые миграции задним числом, если они уже были применены
- миграции должны быть по возможности idempotent
- если меняется storage contract, нужно обновить docs и runtime notes

Пока в проекте нет Alembic. Если будем заводить migration framework, это нужно делать отдельной задачей, не в фоне.

## Что нельзя ломать

- auth middleware и session cookie flow
- `/api` contract для frontend
- prod SPA fallback
- dev proxy на Vite
- document-layer в Postgres (`json_documents`) там, где домен еще не вынесен в нормализованные таблицы
- compatibility слой между document storage и реляционными read/write path, где migration cleanup еще не завершен
- рабочие интеграции с Yandex/Ozon и конкурентными источниками без явного migration path

## Frontend changes

- сначала проверяем, как экран встроен в существующий shell и auth-flow
- не плодим новые UI-паттерны, если экран уже имеет свой established pattern
- если меняется layout критичного рабочего экрана, нужен локальный smoke-check через build и желательно визуальная проверка
- если состояние derived, не дублируем его лишним `useState`
- для заметных UI-изменений в этом проекте используем проектный skill [`smartpim-ui`](/Users/maksimkiselev/Desktop/Global%20PIM/.codex/skills/smartpim-ui/SKILL.md) как основной визуальный стандарт
- для data-heavy интерфейсов (`mapping`, `admin`, `catalog`, `sources`, таблицы, панели`) используем project skill [`smartpim-data-screens`](/Users/maksimkiselev/Desktop/Global%20PIM/.codex/skills/smartpim-data-screens/SKILL.md) вместе с [`smartpim-ui`](/Users/maksimkiselev/Desktop/Global%20PIM/.codex/skills/smartpim-ui/SKILL.md)
- после любой browser/UI-проверки через Playwright нужно завершать все связанные Playwright-процессы и браузерные рантаймы; нельзя оставлять `playwright`, `cliDaemon`, `playwright-mcp` или временные playwright-browser instances висеть в фоне после окончания работы

## Backend changes

- для новых env-переменных обновляем `.env.example`
- для новых API-срезов документируем expected input/output хотя бы на уровне README/docs
- избегаем скрытых fallback-режимов, которые маскируют ошибку данных
- не добавляем новые runtime ветки под `sqlite`; storage runtime у проекта сейчас `Postgres-only`

## Документация

Нужно обновлять:

- `README.md` — если меняются команды запуска или структура
- `docs/architecture.md` — если меняется модульная схема или data flow
- `docs/conventions.md` — если вводим новый engineering rule
- `docs/tasks.md` — если меняется активный рабочий фокус

### Правило этапов

Если работа идет по этапному `.md`-плану, то в конце завершенного этапа и перед началом следующего нужно в той же серии изменений:

- обновить основной рабочий `.md`
- убрать из active checklist уже выполненные пункты
- добавить согласованные пункты следующего этапа
- только после этого продолжать код следующего этапа

То есть проектовый `.md` должен быть не исторической заметкой, а актуальным рабочим состоянием плана.
