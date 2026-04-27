# Multi-Tenant Foundation Spec

## Статус

Этот документ фиксирует первый технический этап multi-tenant перехода.

Цель этапа:

1. не переносить весь PIM runtime сразу
2. ввести platform/control-plane foundation
3. подготовить session, membership и organization switching
4. не ломать текущий monolithic tenant runtime до появления tenant resolver

Основной план:

- [`docs/multi-tenant-organization-plan.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/multi-tenant-organization-plan.md)

## Выполнено

Этот backend foundation slice уже сделан:

1. SQL migration для control-plane таблиц
2. backend foundation module для platform users / organizations / memberships
3. additive session model с `organizations`, `current_organization`, `platform_roles`, `flags`
4. `GET /api/platform/organizations`
5. `POST /api/platform/organizations/switch`
6. backend tests на session contract и org switching
7. frontend `AuthContext` подключен к org-aware session
8. в shell добавлен organization switcher и `Developer` badge
9. `POST /api/platform/register`
10. invite create / accept endpoints
11. backend tests на registration и invite contract
12. экран регистрации
13. экран принятия invite
14. routing для onboarding flows
15. provisioning status endpoint для current organization
16. shell visibility для `organization.status` и latest job status
17. тесты на provisioning status contract
18. request-scoped tenant context в backend middleware
19. endpoint текущего tenant context
20. тесты на tenant context contract
21. foundation подготовлен для первого tenant-local migration slice
22. `connectors status` переведен на tenant-aware storage contract
23. connector state изолирован по `organization_id`
24. добавлены тесты на organization-level isolation для connectors state
25. `marketplace category mappings` переведены на tenant-aware storage contract
26. request-scoped tenant context вынесен в `contextvar` для nested runtime/storage access
27. marketplace mapping caches разнесены по `organization_id`
28. добавлен integration-тест на org-level isolation для category mappings
29. `marketplace attribute mappings` переведены на tenant-aware storage contract
30. `attribute_value_refs` переведены на tenant-aware related read model
31. добавлен integration-тест на org-level isolation для attribute mappings
32. `competitor mapping` переведен на tenant-aware storage contract
33. bootstrap cache competitor mapping разнесен по `organization_id`
34. добавлен integration-тест на org-level isolation для competitor mapping
35. `product marketplace status` переведен на tenant-aware readiness contract
36. `catalog product page summary` переведен на tenant-aware storage contract
37. `catalog/products-page-data` cache keys разнесены по `organization_id`
38. добавлен integration-тест на org-level isolation для catalog products page readiness
39. `templates` переведены на tenant-aware storage contract
40. `template attributes` и `category template links` переведены на tenant-aware storage contract
41. `category template resolution` переведен на tenant-aware storage contract
42. добавлен integration-тест на org-level isolation для templates + category resolution
43. `dictionaries` переведены на tenant-aware storage contract
44. `dictionary values`, `aliases`, `provider refs` и `export maps` переведены на tenant-aware storage contract
45. global attributes переведены на org-local dictionary context
46. добавлен integration-тест на org-level isolation для global attributes
47. корневой `/` для неавторизованного пользователя переведен в единый auth-entry portal
48. `login/register` сведены в одно окно с переключением вкладок внутри одной панели
49. login/register/invite сведены к единому визуальному auth-entry контуру
50. frontend build подтверждает рабочий state нового auth entry
51. auth-entry доведен до фирменного стиля PIM: светлая база, теплый градиент, продуктовый copy
52. viewport-fit auth-entry подтвержден визуальной проверкой на проде без вертикального скролла на десктопе
53. `register` вынесен в отдельный экран с другим визуальным режимом вместо таба в той же сцене
54. визуально подтверждено, что `login` и `register` стали двумя разными публичными auth-сценами на проде
55. добавлен backend workspace bootstrap для `organizations + members + invites`
56. добавлены control-plane list functions для org overview, members и invites
57. shell расширен маршрутами `admin/organizations`, `admin/members`, `admin/invites`, `admin/platform`
58. собрана единая рабочая org-management страница поверх нового backend contract
59. invite-link flow теперь возвращает usable ссылку с prefilled `email`

Соответственно ниже этот документ остается как contract/spec, а не как список невыполненных задач.

## Scope Phase 1

В рамках первого этапа делаем только foundation:

1. control-plane data model
2. registration with organization bootstrap
3. invite flow with email binding
4. global platform role `developer`
5. session payload with current organization
6. organization switch endpoint
7. frontend organization switcher contract

Не делаем на этом этапе:

1. полный перенос PIM-доменов в tenant DB
2. tenant-aware repositories по всему backend
3. production-grade background provisioning orchestrator
4. полноценный subdomain routing

## Next Implementation Checklist

Следующий этап больше не про очередной runtime migration slice.

Текущий пакет:

1. дожать org-management actions: member role changes, revoke/resend invite, basic org settings;
2. проверить developer/platform visibility и actions уже на реальных страницах;
3. довести shell/navigation до нормального пользовательского контура без временных заглушек;
4. только после этого возвращаться к category/content domain redesign;
5. отложить дальнейшие tenant-local миграции `catalog/templates/products` до стабилизации нового UX-контура.

## Current Code Constraints

Текущее состояние кода:

- auth живет в [`backend/app/core/auth.py`](/Users/maksimkiselev/Desktop/Global%20PIM/backend/app/core/auth.py)
- auth routes живут в [`backend/app/api/routes/auth.py`](/Users/maksimkiselev/Desktop/Global%20PIM/backend/app/api/routes/auth.py)
- frontend auth context живет в [`frontend/src/app/auth/AuthContext.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/app/auth/AuthContext.tsx)
- shell header живет в [`frontend/src/app/layout/Shell.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/app/layout/Shell.tsx)

Текущее ограничение:

- auth модель single-tenant
- session не хранит текущую организацию
- pages/actions считаются напрямую от user roles без org context

Значит первый этап должен быть сделан как compatibility migration, а не как big bang rewrite.

## Control DB: Required Tables

Ниже не финальный DDL, а canonical schema contract.

### 1. `platform_users`

Назначение:

- глобальная identity по `email`

Поля:

- `id uuid primary key`
- `email citext unique not null`
- `password_hash text not null`
- `name text not null`
- `status text not null default 'active'`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`
- `last_login_at timestamptz null`

Правила:

- логин как primary identifier больше не нужен
- legacy `login` можно вычислять из `email` либо держать как deprecated field только для совместимости UI

### 2. `platform_roles`

Назначение:

- глобальные платформенные роли

Поля:

- `id uuid primary key`
- `code text unique not null`
- `name text not null`
- `description text null`

Минимальные записи:

- `developer`
- `platform_admin`
- `platform_support`

### 3. `platform_user_roles`

Назначение:

- many-to-many между user и platform role

Поля:

- `platform_user_id uuid not null`
- `platform_role_id uuid not null`
- `created_at timestamptz not null`

Constraint:

- unique(`platform_user_id`, `platform_role_id`)

### 4. `organizations`

Назначение:

- корневая сущность tenant

Поля:

- `id uuid primary key`
- `slug text unique not null`
- `name text not null`
- `status text not null`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

Статусы:

- `provisioning`
- `active`
- `suspended`
- `deleted`

### 5. `organization_members`

Назначение:

- membership пользователя в организации

Поля:

- `id uuid primary key`
- `organization_id uuid not null`
- `platform_user_id uuid not null`
- `org_role_code text not null`
- `status text not null`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

Constraint:

- unique(`organization_id`, `platform_user_id`)

Минимальные `org_role_code`:

- `org_owner`
- `org_admin`
- `org_editor`
- `org_viewer`

### 6. `organization_invites`

Назначение:

- invite flow с email binding

Поля:

- `id uuid primary key`
- `organization_id uuid not null`
- `email citext not null`
- `org_role_code text not null`
- `token_hash text not null`
- `status text not null`
- `expires_at timestamptz not null`
- `created_by_user_id uuid not null`
- `accepted_by_user_id uuid null`
- `accepted_at timestamptz null`
- `created_at timestamptz not null`

Правила:

- raw invite token в БД не хранить
- membership создается только для invite email

### 7. `tenant_registry`

Назначение:

- метаданные tenant DB

Поля:

- `organization_id uuid primary key`
- `db_host text not null`
- `db_port integer not null`
- `db_name text not null`
- `db_user text not null`
- `db_secret_ref text not null`
- `status text not null`
- `schema_version text null`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

### 8. `tenant_provisioning_jobs`

Назначение:

- контроль lifecycle создания tenant DB

Поля:

- `id uuid primary key`
- `organization_id uuid not null`
- `status text not null`
- `attempt integer not null default 0`
- `error text null`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

## Session Contract v2

Текущий `/api/auth/session` слишком плоский. Нужен новый contract.

### Response shape

```json
{
  "authenticated": true,
  "user": {
    "id": "usr_123",
    "email": "owner@example.com",
    "name": "Owner User",
    "status": "active"
  },
  "platform_roles": [
    { "code": "developer", "name": "Developer" }
  ],
  "organizations": [
    {
      "id": "org_1",
      "slug": "acme",
      "name": "Acme",
      "status": "active",
      "membership_role": "org_owner"
    },
    {
      "id": "org_2",
      "slug": "beta",
      "name": "Beta",
      "status": "active",
      "membership_role": "org_editor"
    }
  ],
  "current_organization": {
    "id": "org_1",
    "slug": "acme",
    "name": "Acme",
    "status": "active",
    "membership_role": "org_owner"
  },
  "effective_access": {
    "pages": ["dashboard", "catalog", "sources_mapping"],
    "actions": ["products.manage", "sources.manage"]
  },
  "flags": {
    "is_developer": true
  },
  "catalog": {
    "pages": [],
    "actions": []
  }
}
```

### Notes

- `roles` как flat список текущих auth roles нужно убрать из публичного session payload
- `effective_access.pages/actions` считаются уже в контексте `current_organization`
- `developer` может иметь полный org visibility без membership, но effective access все равно должен быть явно вычислен

## Session Storage Decision

На первом этапе в session нужно хранить:

- `platform_user_id`
- `current_organization_id`
- `issued_at`
- `expires_at`

Это позволит:

- быстро переключать org context
- не зашивать org choice только во frontend state

## API Contract: Phase 1

### 1. `POST /api/platform/register`

Создает:

1. `platform_user`
2. `organization`
3. `organization_member` с `org_owner`
4. `tenant_registry` в `provisioning`
5. initial session

Request:

```json
{
  "email": "owner@example.com",
  "password": "secret123",
  "name": "Owner User",
  "organization_name": "Acme"
}
```

### 2. `GET /api/platform/organizations`

Возвращает список доступных organizations:

- memberships пользователя
- или все organizations, если user имеет `developer`

### 3. `POST /api/platform/organizations/switch`

Меняет `current_organization_id` в session.

Request:

```json
{
  "organization_id": "org_1"
}
```

Response:

- новый session payload v2

### 4. `POST /api/platform/organizations/{organization_id}/invites`

Создает invite по email.

Request:

```json
{
  "email": "editor@example.com",
  "org_role_code": "org_editor"
}
```

### 5. `POST /api/platform/invites/accept`

Принимает invite token.

Потоки:

1. если user уже существует, делает membership
2. если user не существует, требует registration completion

## Frontend Contract

### AuthContext changes

Нужно расширить типы в:

- [`frontend/src/app/auth/AuthContext.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/app/auth/AuthContext.tsx)

Добавить:

- `platformRoles`
- `organizations`
- `currentOrganization`
- `switchOrganization(organizationId)`
- `isDeveloper`

### Shell changes

Нужно поменять шапку в:

- [`frontend/src/app/layout/Shell.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/app/layout/Shell.tsx)

Добавить:

1. dropdown текущей организации рядом с user meta
2. список доступных организаций
3. badge `Developer`, если у user есть глобальная роль

UX правило:

- если organization одна, dropdown не должен быть шумным
- если user developer, в dropdown должен быть виден полный список org
- переключение должно делать roundtrip в backend, а не менять только local state

## Migration Strategy

### Step 1

Ввести control-plane таблицы и repository layer.

### Step 2

Сделать compatibility login:

- текущий `/api/auth/login` может временно оставаться
- но identity должна уже подниматься из `platform_users`

### Step 3

Расширить `/api/auth/session` до нового payload.

### Step 4

Добавить org switcher на frontend.

### Step 5

Только после этого делать registration и invite UI.

## Next Implementation Checklist

Следующий кодовый пакет должен сделать первый domain migration slice:

1. выбрать первый бизнес-домен для tenant split
2. подключить его к request-scoped tenant context
3. сохранить compatibility с остальным runtime
4. smoke/check coverage для первого tenant-local path

После этого следующий пакет:

1. перенос следующих доменов
2. tenant-local storage/runtime
3. затем cleanup compatibility layers

## Out of Scope Warnings

Не надо на первом этапе:

1. сразу распиливать все routes на отдельные apps
2. сразу мигрировать весь storage в tenant DB
3. делать memberships через неограниченные role matrices
4. хранить developer доступ как memberships во всех org

Это усложнит foundation и затянет запуск.
