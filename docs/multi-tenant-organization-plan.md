# Multi-Tenant Organization Plan

## Зачем этот документ

Это рабочий implementation-plan для перехода PIM к модели:

1. регистрация пользователя
2. автоматическое создание организации
3. membership пользователей в нескольких организациях
4. глобальная роль разработчика
5. tenant-isolated data storage
6. переключение между организациями в UI

Документ должен использоваться как основной план для следующих изменений в auth, storage, routing и frontend shell.

## Текущий статус

Уже сделано:

- подготовлен control-plane foundation в backend;
- добавлены control-plane таблицы и seed platform roles;
- расширен `/api/auth/session` до additive org-aware контракта;
- добавлены `GET /api/platform/organizations` и `POST /api/platform/organizations/switch`;
- добавлены backend smoke/auth тесты на новый session contract и переключение организации.
- frontend подключен к org-aware session;
- в shell добавлен organization switcher рядом с пользователем;
- в shell добавлен `Developer` badge и backend roundtrip при смене организации.
- добавлен `POST /api/platform/register`;
- добавлен backend foundation для создания организации и owner membership;
- добавлены invite endpoints с email binding;
- добавлены тесты на registration и invite accept contract.
- добавлен экран регистрации;
- добавлен экран принятия invite;
- onboarding flow встроен в routing рядом с login.
- добавлен provisioning status endpoint для текущей организации;
- shell показывает `organization.status` и job status для текущей организации;
- добавлены тесты на provisioning status contract.
- добавлен request-scoped tenant context в backend middleware;
- добавлен endpoint текущего tenant context;
- подготовлен tenant resolver от `current_organization` в session.
- завершен tenant runtime split foundation без перевода бизнес-доменов;
- следующим active slice выбран `connectors status` как первый безопасный tenant-local домен.
- `connectors status` переведен на tenant-local read/write path;
- connector state изолирован по `organization_id`;
- scheduler сохранен в compatibility-режиме на default organization;
- добавлены тесты на org-level isolation для connector state.
- `marketplace category mappings` переведены на tenant-local read/write path;
- request-scoped tenant context теперь доступен через `contextvar` внутри storage/runtime;
- category mappings изолированы по `organization_id`;
- marketplace mapping caches разнесены по организациям;
- добавлен integration-тест на `login -> switch org -> category mapping`.
- `marketplace attribute mappings` переведены на tenant-local read/write path;
- `attribute_value_refs` переведены на tenant-local related read model;
- attribute mapping storage изолирован по `organization_id`;
- добавлен integration-тест на `login -> switch org -> attribute mapping`.
- `competitor mapping` переведен на tenant-local storage contract;
- category/template competitor mappings изолированы по `organization_id`;
- bootstrap cache competitor mapping разнесен по организациям;
- добавлен integration-тест на `login -> switch org -> competitor mapping`.
- `product marketplace status` переведен на tenant-local readiness contract;
- `catalog product page summary` переведен на tenant-local storage contract, чтобы org-level readiness не подтекал через page rows;
- `catalog/products-page-data` caches разнесены по `organization_id`;
- добавлен integration-тест на `login -> switch org -> catalog products page data`.
- `templates` переведены на tenant-local storage contract;
- `template attributes` и `category template links` переведены на tenant-local storage contract;
- `category template resolution` переведен на tenant-local storage contract;
- добавлен integration-тест на `login -> switch org -> templates + category resolution`.
- `dictionaries` переведены на tenant-local storage contract;
- `dictionary values`, `aliases`, `provider refs` и `export maps` переведены на tenant-local storage contract;
- глобальные атрибуты теперь читаются и создаются в org-local dictionary context;
- добавлен integration-тест на `login -> switch org -> global attributes`.
- корневой `pim.id-smart.ru` для неавторизованного пользователя теперь ведет в единый auth-entry portal;
- `login/register` сведены в одно окно с переключением вкладок внутри одной панели;
- auth entry приведен к общей dark-layout композиции с единым визуальным языком для login/register/invite;
- frontend build подтверждает рабочий state нового auth entry.
- auth entry доведен до бренд-стиля PIM: светлая база, оранжевый акцент, фирменный градиент, переписанный продуктовый текст и viewport-fit без вертикального скролла на десктопе.
- `регистрация` вынесена в отдельный самостоятельный экран с другим визуальным режимом и route-level переходом, вместо таба внутри одной и той же сцены.

Работаем дальше от этого состояния, а не от нуля.

## Текущий этап

Меняем приоритет работ.

Дальше не продолжаем tenant-local split бизнес-доменов каталога до завершения пользовательского контура и новых страниц.

Сейчас делаем следующий product/admin этап:

1. страницы `Организации`;
2. страницы `Сотрудники`;
3. страницы `Приглашения`;
4. страницы `Администрирование`;
5. усиливаем backend contract под org management и invite management;
6. доводим shell/navigation до нормального пользовательского контура;
7. только после этого возвращаемся к категориям, инфо-моделям и content domains.

Сейчас уже сделан первый org-management slice:

- добавлен backend workspace bootstrap для `organizations + members + invites`;
- добавлены control-plane list functions для overview, members и invites;
- shell расширен маршрутами `admin/organizations`, `admin/members`, `admin/invites`, `admin/platform`;
- собрана единая рабочая org-management страница поверх этого backend contract;
- invite creation теперь сразу возвращает usable invite-link flow с prefilled `email`.

## Новый порядок внедрения

Следующий порядок считаем основным:

1. `Users / Organizations / Invites / Admin pages`
2. `Shell / navigation / onboarding polish`
3. `Новая продуктовая структура экранов`
4. `Категории / инфо-модели / экспортные профили`
5. только потом дальнейший tenant-local split тяжелых content-доменов

## Требования

Нужно обеспечить:

1. при регистрации создается организация
2. организация имеет своих сотрудников
3. один пользователь может состоять в нескольких организациях
4. идентификация пользователя идет по `email`
5. есть механизм пригласительных ссылок
6. есть роль `developer`, которая имеет доступ ко всем организациям
7. на фронте есть переключение текущей организации рядом с пользователем
8. БД изолирована для каждой организации

## Ключевое архитектурное решение

Если требование на изоляцию жесткое, нельзя делать только `org_id` в общей бизнес-БД.

Целевая схема должна быть такой:

1. `Control DB`
2. `Tenant DB per organization`

### 1. Control DB

Общая служебная БД платформы. В ней нет товарных данных PIM.

Хранит:

- platform users
- organizations
- memberships
- invites
- tenant registry
- provisioning jobs
- global roles
- platform audit

### 2. Tenant DB

Отдельная БД на каждую организацию.

Хранит:

- каталог
- инфо-модели
- словари
- товары
- category mappings
- export profiles
- connector state
- media refs
- tenant-local audit и jobs

## Почему не shared DB с `org_id`

Такой вариант не подходит под требование "БД изолирована для каждой организации", потому что:

- это логическая, а не настоящая изоляция
- выше риск утечки данных
- сложнее backup/restore для отдельной организации
- сложнее объяснять security boundary

## Рекомендуемая целевая архитектура

### Control plane

Единый платформенный слой отвечает за:

- регистрация
- логин
- membership
- org switching
- invite flow
- tenant provisioning
- global roles

### Tenant application layer

Весь текущий PIM runtime живет в tenant-контексте:

- categories
- products
- templates / info models
- dictionaries
- sources mapping
- exports

Даже если кодбейс один, логически нужно разделить:

- `platform context`
- `tenant context`

## Role model

Нужны два уровня ролей.

### 1. Platform roles

Глобальные роли control plane.

Минимально:

- `developer`
- `platform_admin`
- `platform_support`

Главное требование:

- `developer` имеет доступ ко всем организациям

Это platform-level роль, а не org-level.

### 2. Organization roles

Роли внутри конкретной организации.

Минимально:

- `org_owner`
- `org_admin`
- `org_editor`
- `org_viewer`

Они действуют только в рамках конкретной организации.

## User model

Идентичность пользователя должна быть глобальной, по `email`.

То есть:

- один user = одна запись в platform users
- у user может быть несколько memberships в organizations

Это важно для:

- приглашений
- переключения между организациями
- одной точки логина

## Control DB entities

## 1. `platform_users`

Поля:

- `id`
- `email`
- `password_hash`
- `password_salt` или внешний auth reference
- `name`
- `status`
- `created_at`
- `updated_at`
- `last_login_at`

Правила:

- `email` уникален и case-insensitive
- логин как отдельное поле можно убрать или сделать производным/legacy

## 2. `platform_roles`

Поля:

- `id`
- `code`
- `name`
- `description`

Минимальные коды:

- `developer`
- `platform_admin`
- `platform_support`

## 3. `platform_user_roles`

Поля:

- `platform_user_id`
- `platform_role_id`

Назначение:

- глобальные роли вне tenant membership

## 4. `organizations`

Поля:

- `id`
- `slug`
- `name`
- `status`
- `created_at`
- `updated_at`

Статусы:

- `provisioning`
- `active`
- `suspended`
- `deleted`

## 5. `organization_members`

Поля:

- `id`
- `organization_id`
- `platform_user_id`
- `org_role_code`
- `status`
- `created_at`
- `updated_at`

Статусы:

- `active`
- `invited`
- `disabled`

## 6. `organization_invites`

Поля:

- `id`
- `organization_id`
- `email`
- `org_role_code`
- `token_hash`
- `status`
- `expires_at`
- `created_by_user_id`
- `accepted_at`

Статусы:

- `pending`
- `accepted`
- `expired`
- `revoked`

## 7. `tenant_registry`

Поля:

- `organization_id`
- `db_host`
- `db_port`
- `db_name`
- `db_user`
- `db_secret_ref`
- `status`
- `schema_version`
- `created_at`
- `updated_at`

Важно:

- пароль БД не хранить plaintext в самой таблице
- использовать secret manager или encrypted secret storage

## 8. `tenant_provisioning_jobs`

Поля:

- `id`
- `organization_id`
- `status`
- `attempt`
- `error`
- `created_at`
- `updated_at`

## Tenant DB scope

В tenant DB должны переехать все бизнес-данные организации.

Минимально:

- categories
- info models / templates
- attributes / dictionaries
- products
- sources mapping
- export profiles
- connectors state
- media references

Текущее состояние проекта:

- сейчас основной runtime еще monolithic
- auth и PIM логически не разделены по control/tenant

Это нужно менять поэтапно, не одномоментно.

## Регистрация

Целевой flow:

1. пользователь вводит `email`, `password`, `name`, `organization_name`
2. создается `platform_user`
3. создается `organization`
4. создается membership с ролью `org_owner`
5. создается `tenant_registry` record в статусе `provisioning`
6. запускается provisioning job
7. job создает tenant DB
8. применяются tenant migrations
9. создается tenant bootstrap
10. organization становится `active`

## Пригласительные ссылки

Нужен flow:

1. org admin создает invite
2. система генерирует token
3. email привязки хранится в invite
4. пользователь открывает ссылку
5. если email уже существует:
   - логинится
   - membership добавляется в организацию
6. если email не существует:
   - проходит регистрацию
   - создается `platform_user`
   - membership добавляется в организацию

Важно:

- приглашение должно быть привязано к email
- membership создается только для указанного email

## Organization switcher

На frontend нужен org switcher рядом с именем пользователя в shell.

Текущая точка:

- [`frontend/src/app/layout/Shell.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/app/layout/Shell.tsx)

Нужно добавить:

- текущую организацию
- dropdown со списком доступных организаций
- action "переключить организацию"

### Session payload должен начать возвращать

Дополнительно к текущему auth session:

- `current_organization`
- `organizations[]`
- `platform_roles[]`
- `is_developer`

## Developer role

Требование:

- developer видит все организации

Это должно работать не через memberships ко всем org, а через global platform role.

### Поведение

Если user имеет role `developer`:

- может открыть любую организацию
- org switcher показывает все organizations
- может impersonate tenant context без membership

Но:

- это должно быть явно отражено в audit
- желательно показывать badge/platform context

## Tenant resolution

Нужен `tenant resolver`.

Он должен определять активную организацию:

1. по session-selected organization
2. по subdomain/slug, если такой режим будет позже

На первом этапе достаточно:

- организация хранится в session context
- frontend умеет переключать текущую организацию

## Auth/session changes

Текущий auth довольно плоский:

- user
- roles
- pages/actions

Точки:

- [`backend/app/api/routes/auth.py`](/Users/maksimkiselev/Desktop/Global%20PIM/backend/app/api/routes/auth.py)
- [`backend/app/core/auth.py`](/Users/maksimkiselev/Desktop/Global%20PIM/backend/app/core/auth.py)
- [`frontend/src/app/auth/AuthContext.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/app/auth/AuthContext.tsx)

Нужно перейти к модели session:

- `user`
- `platform_roles`
- `organizations`
- `current_organization`
- `effective_org_role`
- `pages/actions` уже в контексте текущей организации

## Что нужно поменять в backend

## Phase 1. Platform foundation

Цель:

- ввести control-plane модели, не ломая текущий tenant runtime

Нужно:

1. новые control-plane таблицы
2. новый session payload
3. org memberships
4. org switch endpoint
5. invite entities

Минимальные новые API:

- `POST /api/platform/register`
- `POST /api/platform/organizations/switch`
- `GET /api/platform/organizations`
- `POST /api/platform/organizations/{id}/invites`
- `POST /api/platform/invites/accept`

## Phase 2. Tenant registry and provisioning

Цель:

- создать отдельную tenant DB на организацию

Нужно:

1. tenant registry
2. provisioning worker/service
3. tenant migrations bootstrap
4. org status lifecycle

## Phase 3. Tenant-aware request context

Цель:

- каждый tenant route работает уже в контексте активной организации

Нужно:

1. request-scoped tenant context
2. tenant DB connection resolver
3. tenant-aware repositories

## Phase 4. Move current PIM domain into tenant DB

Цель:

- текущий PIM storage становится tenant-local

Нужно:

1. categories
2. templates / info models
3. dictionaries
4. products
5. mappings
6. connector states

## Что нужно поменять во frontend

## Phase 1

Текущие точки:

- [`frontend/src/app/auth/AuthContext.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/app/auth/AuthContext.tsx)
- [`frontend/src/app/layout/Shell.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/app/layout/Shell.tsx)

Нужно:

1. расширить session model
2. хранить current organization
3. добавить organization switcher
4. показать global developer role в UI

## Phase 2

Нужны новые platform-level screens:

- `Registration`
- `Accept Invite`
- `Organizations admin`

## Навигационные решения

Сейчас верхний shell рассчитан на single-org восприятие.

Нужно добавить в user area:

- current org selector
- org role / developer badge
- возможно быстрый переход в org admin

## Безопасность и audit

Обязательно фиксировать:

- кто создал организацию
- кто создал invite
- кто принял invite
- кто переключился в организацию
- когда developer вошел в чужую организацию

## Что НЕ делать

- не делать shared business DB только с `org_id`, если нужна реальная изоляция
- не делать developer через memberships во всех org
- не привязывать user identity к org-local login
- не делать invites без email binding
- не встраивать org switch только на frontend без backend session-aware context

## Порядок внедрения без попытки сломать все сразу

### Step 1

Начать перенос первых бизнес-доменов в tenant-local runtime

- выбрать первый домен для tenant split;
- отвязать его от общего runtime пути;
- начать реальное использование tenant context в read/write flow.

### Step 2

После этого начинать переносить текущий PIM runtime в tenant DB

## Текущий практический шаг

Следующая задача по этому плану должна быть не про все домены сразу, а про первый безопасный tenant-local домен:

1. выбрать первый домен для tenant split
2. подключить его к tenant context
3. сохранить compatibility для остального runtime
4. только потом расширять migration на следующие домены

После этого переходить в domain migration.
