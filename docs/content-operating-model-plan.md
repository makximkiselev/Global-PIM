# Content Operating Model Plan

## Зачем этот документ

Это рабочий план перестройки контуров:

1. инфо-модели
2. привязки категорий каналов
3. маппинг экспортных полей
4. создание товаров и контента

Документ привязан к текущей кодовой базе и должен использоваться как опорный план для следующих изменений.

## Важный порядок работ

Этот документ остается целевым продуктовым планом, но не является следующим кодовым этапом.

Текущий порядок такой:

1. сначала закрываем `users / organizations / invites / admin pages`;
2. затем стабилизируем shell/navigation и onboarding;
3. только после этого возвращаемся к перестройке `категории / инфо-модели / экспортные профили`.

Причина:

- пользовательский и административный контур сейчас важнее;
- часть старых domain-экранов все равно будет переписываться;
- значит невыгодно продолжать глубокий refactor бизнес-доменов до фиксации нового UX-контура.

## Текущая проблема

Сейчас в проекте слишком много разных задач сходятся в несколько перегруженных экранов:

- [`frontend/src/pages/SourcesMapping.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/pages/SourcesMapping.tsx)
- [`frontend/src/pages/SourcesMarketplaceSection.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/pages/SourcesMarketplaceSection.tsx)
- [`frontend/src/pages/TemplateEditor.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/pages/TemplateEditor.tsx)

Из-за этого смешаны:

- каноническая инфо-модель товара
- маппинг категорий маркетплейсов
- конкурентные источники
- экспортный field mapping
- подготовка товарного контента

Такой контур не масштабируется и делает любой экран слишком тяжелым.

## Целевая модель

Нужно перейти к схеме:

1. `Инфо-модель`
2. `Категория каталога -> инфо-модель`
3. `Категория каталога -> категория канала`
4. `Инфо-модель -> экспортный профиль канала`
5. `Товар -> заполнение по модели -> готовность к каналу`

Ключевое правило:

- PIM-модель первична
- каналы вторичны
- экспортный маппинг не должен определять структуру ядра

## Что есть сейчас в кодовой базе

### Frontend

Текущие важные разделы:

- `/catalog`
- `/templates`
- `/dictionaries`
- `/sources-mapping`
- `/products`
- `/catalog/import`
- `/catalog/export`

Маршруты:

- [`frontend/src/app/App.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/app/App.tsx)

Навигация:

- [`frontend/src/app/layout/Shell.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/app/layout/Shell.tsx)

### Backend

Текущие доменные API:

- `templates`
- `dictionaries`
- `marketplace_mapping`
- `competitor_mapping`
- `catalog`
- `products`
- `connectors_status`

Роуты:

- [`backend/app/api/routes/templates.py`](/Users/maksimkiselev/Desktop/Global%20PIM/backend/app/api/routes/templates.py)
- [`backend/app/api/routes/marketplace_mapping.py`](/Users/maksimkiselev/Desktop/Global%20PIM/backend/app/api/routes/marketplace_mapping.py)
- [`backend/app/api/routes/competitor_mapping.py`](/Users/maksimkiselev/Desktop/Global%20PIM/backend/app/api/routes/competitor_mapping.py)
- [`backend/app/api/routes/catalog.py`](/Users/maksimkiselev/Desktop/Global%20PIM/backend/app/api/routes/catalog.py)
- [`backend/app/api/routes/products.py`](/Users/maksimkiselev/Desktop/Global%20PIM/backend/app/api/routes/products.py)

## Целевые разделы UI

Не обязательно сразу менять верхнее меню радикально. Можно сделать это поэтапно.

### Этапно целевой UX

**1. Каталог**

Оставить в разделе `Каталог`:

- дерево категорий
- назначение инфо-модели категории
- статистику по товарам

Подразделы:

- `Категории`
- `Готовность контента`

**2. Инфо-модели**

Выделить отдельный раздел вместо текущего смешения в `Шаблонах`:

- список моделей
- редактор модели
- шаблоны моделей
- библиотека атрибутов

На первом этапе можно переиспользовать текущие:

- [`frontend/src/pages/Templates.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/pages/Templates.tsx)
- [`frontend/src/pages/TemplateEditor.tsx`](/Users/maksimkiselev/Desktop/Global%20PIM/frontend/src/pages/TemplateEditor.tsx)

Но логика должна постепенно сместиться от "шаблон категории" к "инфо-модель".

**3. Источники / Каналы**

Оставить в разделе `Источники`:

- category mapping к маркетплейсам
- competitor links / competitor source ingestion
- connectors status

Убрать оттуда роль главного места проектирования PIM-модели.

**4. Экспортные профили**

Новый отдельный экран:

- `Инфо-модель + канал + категория канала`
- mapping полей
- enum mapping
- unit / transform rules
- required field validation

Это не должен быть тот же экран, что category mapping.

**5. Товары**

Оставить создание и редактирование товара в `Товарах`, но:

- товар должен рождаться из категории
- категория тянет инфо-модель
- инфо-модель определяет обязательные поля
- каналы считают readiness

## Какие сущности нужны

### 1. `InfoModel`

Назначение:

- каноническая модель товарного семейства

Минимальные поля:

- `id`
- `code`
- `name`
- `description`
- `base_model_id`
- `status`

### 2. `InfoModelAttribute`

Назначение:

- атрибут модели

Минимальные поля:

- `id`
- `info_model_id`
- `code`
- `name`
- `type`
- `group`
- `required`
- `dictionary_id`
- `unit`
- `multivalue`
- `sort_order`

### 3. `CatalogCategory.info_model_id`

Назначение:

- привязать категорию каталога к основной модели

На первом этапе отдельная таблица не обязательна. Достаточно связи:

- `catalog_category_id`
- `info_model_id`

### 4. `ChannelCategoryMapping`

Назначение:

- привязка категории каталога к категории канала

Минимальные поля:

- `catalog_category_id`
- `channel`
- `channel_category_id`
- `channel_category_name`

### 5. `ExportProfile`

Назначение:

- профиль выгрузки модели на конкретный канал

Минимальные поля:

- `id`
- `info_model_id`
- `channel`
- `channel_category_id`
- `name`
- `status`

### 6. `ExportFieldMapping`

Назначение:

- маппинг атрибута модели в поле канала

Минимальные поля:

- `export_profile_id`
- `info_model_attr_code`
- `channel_field_code`
- `required_on_channel`
- `transform_type`
- `transform_config`
- `fallback_value`

## Как переиспользовать существующие сущности

### Что можно использовать почти сразу

**Templates как transitional InfoModel layer**

Текущий `templates` слой уже близок к модели.

Можно использовать как переходный слой:

- `template` временно считать `info_model`
- `template attributes` временно считать `info_model attributes`

Но важно зафиксировать новое product meaning:

- шаблон больше не "просто шаблон категории"
- шаблон становится "канонической моделью"

### Dictionaries / Attributes

Текущий словарный слой подходит как база для:

- library of reusable attributes
- enum dictionaries
- reusable value sets

Это нужно не выбрасывать, а сделать основой нормального model builder.

### Marketplace / competitor mapping

Текущие:

- `marketplace_mapping`
- `competitor_mapping`

оставить как channel/source layer.

Не тянуть их в ядро модели.

## Целевой продуктовый workflow

Принятое решение от 2026-04-27:

- основной сценарий создания инфо-модели — `draft из источников -> модерация -> утверждение`;
- ручное создание остается запасным режимом;
- создание инфо-модели нельзя смешивать с category/channel mapping;
- `/sources` работает как mapping-layer после появления модели, а не как место проектирования базовой PIM-структуры.

### Шаг 1. Собрать draft инфо-модели

Пользователь:

- выбирает категорию без модели;
- запускает `Собрать draft-модель`;
- выбирает источники:
  - Я.Маркет;
  - Ozon;
  - Excel/import;
  - competitors `re-store` и `store77`;
  - текущие товары категории;
- получает предложенные группы, параметры, типы, обязательность-кандидаты и словари.

Система обязана хранить provenance каждого предложенного параметра:

- источник;
- исходное имя;
- примеры значений;
- частотность;
- confidence;
- предложенную группу;
- suggested type.

### Шаг 2. Модерировать и утвердить инфо-модель

Пользователь:

- принимает или отклоняет параметры;
- объединяет дубли;
- переименовывает параметры;
- раскладывает параметры по группам;
- задает типы значений;
- задает обязательность;
- привязывает словари;
- утверждает модель.

После утверждения:

- категория получает активную инфо-модель;
- товары категории получают ожидаемые параметры;
- открывается следующий шаг: сопоставление параметров.

### Шаг 3. Назначить или унаследовать модель категории

Пользователь:

- выбирает категорию каталога
- назначает основную инфо-модель
- или явно оставляет наследование от родителя

### Шаг 4. Привязать категории каналов

Пользователь:

- открывает category mapping
- задает Я.Маркет / Ozon
- задает competitor sources

### Шаг 5. Сопоставить параметры и значения

Пользователь:

- выбирает инфо-модель
- выбирает канал
- выбирает категорию канала
- сопоставляет поля
- сопоставляет значения:
  - PIM value;
  - marketplace value;
  - alternative value spellings;
  - competitor observed value.

### Шаг 6. Создать или насытить товар

Пользователь:

- создает товар в категории
- система подставляет модель
- товар заполняется по обязательным/рекомендуемым полям
- система считает readiness по каналам

## Что надо сделать в UI поэтапно

## Phase 1

Цель:

- не ломая весь текущий проект, развести смысл экранов

Задачи:

1. Зафиксировать в UI, что:
   - `Templates` = временный слой инфо-моделей
2. Упростить `SourcesMapping` до:
   - category mapping
   - parameter mapping после появления модели
   - value mapping после появления модели
   - competitor sources как отдельный tab
   - без попытки быть главным редактором инфо-модели
3. Пересобрать `/templates/:categoryId` вокруг state machine:
   - `none`
   - `collecting`
   - `draft`
   - `review`
   - `approved`
   - `needs_update`
4. Добавить новый placeholder / thin page для `Экспортные профили`

### Phase 1 frontend

Новые страницы:

- `frontend/src/pages/InfoModels.tsx`
- `frontend/src/pages/ExportProfiles.tsx`

Переходный вариант:

- `InfoModels.tsx` может оборачивать текущий `Templates`
- `ExportProfiles.tsx` сначала может быть тонким read/workbench screen

### Phase 1 backend

Пока можно не вводить новый storage слой целиком.

Нужно:

1. в `templates` API добавить semantics, удобные для model-centric UI
2. добавить endpoints для связи категории и модели
3. не трогать старый `marketplace_mapping` контракт без необходимости

Минимальные новые endpoints:

- `GET /api/info-models`
- `GET /api/info-models/{id}`
- `GET /api/info-models/by-category/{categoryId}`
- `POST /api/info-models/draft-from-sources`
- `PUT /api/info-models/{id}/draft`
- `POST /api/info-models/{id}/approve`
- `POST /api/catalog/categories/{id}/info-model`
- `GET /api/info-models/{id}/source-candidates`

На первом этапе эти endpoints могут быть adapter layer поверх `templates`.

## Phase 2

Цель:

- вынести экспортный mapping в отдельный продуктовый слой

Нужно:

1. отдельная страница экспортных профилей
2. отдельная сущность `ExportProfile`
3. separate field mapping UI

### Phase 2 frontend

Экран `ExportProfiles`:

- слева список моделей
- центр список PIM атрибутов
- справа поля канала

### Phase 2 backend

Новые API:

- `GET /api/export-profiles`
- `GET /api/export-profiles/{id}`
- `PUT /api/export-profiles/{id}`
- `POST /api/export-profiles/bootstrap-from-channel`

## Phase 3

Цель:

- усилить создание моделей после появления базового draft workflow

Нужно:

1. copy model
2. create from base model
3. reusable attribute library
4. quality suggestions for draft update

### Phase 3 backend

Новые API:

- `POST /api/info-models/{id}/clone`
- `POST /api/info-models/create-from-base`
- `POST /api/info-models/{id}/suggest-update-from-sources`

## Что НЕ делать

- не строить инфо-модель прямо из category mapping screen
- не смешивать category mapping и export field mapping в одном тяжелом экране
- не делать competitor fields источником истины для ядра модели
- не тянуть channel-specific обязательность в базовую PIM-модель

## Порядок внедрения без большого рефактора

### Step 1

Сделать документационное и продуктовое переименование:

- `Templates` воспринимать как `Info models`

### Step 2

Добавить связь:

- `Category -> InfoModel`

### Step 3

Вынести из `SourcesMapping` все, что относится к field mapping, в отдельный новый экран `ExportProfiles`

### Step 4

Начать использовать экспортные профили для readiness/export validation

### Step 5

Только после этого делать полноценный storage cleanup и отдельные доменные сущности

## Следующая реалистичная задача

Если идти по этому плану без лишнего разлета, следующая задача должна быть такой:

1. добавить новый UI-раздел `Инфо-модели`
2. привязать его к текущему `templates` слою
3. добавить на категорию явное поле `основная инфо-модель`
4. сузить смысл `SourcesMapping` до category/source mapping

Это даст первый полезный сдвиг без попытки сразу переписать полпроекта.
