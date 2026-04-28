# SmartPim Full Rebuild Master Plan

## Статус

Это единый рабочий документ для полной переделки `SmartPim`.

Дальше работа по этому треку должна идти только по этому файлу.

Это также единственный актуальный документ со статусами по этому треку.

Все статусы исполнения, активный этап, завершенные slices и текущее состояние должны обновляться только здесь.

Все остальные документы по redesign/frontend/full-rebuild для этой задачи считаются:

- reference;
- историей решений;
- архивом промежуточных этапов.

Но не основным рабочим планом.

### Единый статус трека

Актуальный статус полной переделки продукта:

1. единственный source of truth: этот файл;
2. текущий активный execution slice: `Final Review / Next Visual QA`;
3. завершенные execution slices:
   - `Control Center`
   - `Product List`
   - `Product Workspace`
   - `Info Model Workspace`
   - `Channel Mapping Workspace`
   - `Sources / Import`
   - `Organizations / Admin`
4. reopened / not accepted:
   - тяжелые рабочие страницы после каталога
5. reference-only документы для этого трека:
   - `docs/tasks.md`
   - `README.md`

---

## Как пользоваться этим документом

Этот файл большой. Чтобы по нему реально работать, читать его нужно не целиком каждый раз, а по слоям.

### Что читать всегда

Это sections, которые считаются базовыми правилами и не должны забываться:

1. `2. Зафиксированные продуктовые решения`
2. `7. Инвентарь страниц и новый порядок переделки`
3. `8. Обязательная схема разбора каждой страницы`
4. `9. Жесткие правила верстки и UX`
5. `10. Universal blocks, feature blocks, individual blocks`
6. `12. Правило выполнения работ`
7. `14. Universal Blocks by Page Type`
8. `25. Execution Protocol`

### Что читать перед началом конкретной страницы

Перед implementation конкретной страницы обязательно читать:

1. соответствующий `execution slice`;
2. `12. Правило выполнения работ`;
3. `25. Execution Protocol`.

### Что читать при работе над БД

Для data model и БД использовать:

1. `11. Подход к БД и data model`
2. `13. Page / Source / Result Map`
3. связанные execution slices, если таблица относится к конкретной странице/контурy.

### Какой порядок исполнения

Исполнять строго по порядку:

1. `16. Первый execution slice: Control Center`
2. `17. Второй execution slice: Product List`
3. `18. Третий execution slice: Product Workspace`
4. `20. Четвертый execution slice: Catalog Workspace`
5. `21. Пятый execution slice: Info Model Workspace`
6. `22. Шестой execution slice: Channel Mapping Workspace`
7. `23. Седьмой execution slice: Sources / Import`
8. `24. Восьмой execution slice: Organizations / Admin`
9. `26. Девятый execution slice: Competitor Product Discovery Pipeline`

Нельзя перепрыгивать дальше, пока текущий slice не закрыт по правилам документа.

### Что обновлять после каждого этапа

После завершения каждого execution slice обязательно обновлять:

1. `Статус`;
2. блок `Активный этап`;
3. блок `Завершенные execution slices`;
4. при необходимости сам execution slice;
5. `docs/tasks.md`, если меняется активный этап.

---

## Активный этап

Текущий execution slice:

1. `Final Review / Next Visual QA`

Текущее состояние:

1. planning-фаза по основному фронтовому периметру собрана;
2. `Control Center` доведен до рабочего состояния;
3. `Product List` доведен до рабочего состояния;
4. `Product Workspace` доведен до рабочего состояния;
5. `Catalog Workspace` был отмечен как завершенный ошибочно: визуальная проверка 2026-04-26 показала, что текущий экран не соответствует уровню продукта;
6. `Info Model Workspace` доведен до рабочего состояния;
7. live-summary hot-path, auth/session hot-path, product detail hot-path и template editor bootstrap hot-path стабилизированы;
8. browser-check выполнен на живом проде с реальной сессией и переходами `catalog -> products -> templates`;
9. `Channel Mapping Workspace` доведен до рабочего состояния;
10. следующим активным slice становится `Sources / Import`;
11. верхний page-shell `sources-mapping` переведен на новый workspace-contract без старого poster-header;
12. categories-view и parameter-view подтверждены реальным browser-check на проде;
13. nested states и modal states (`Изменить`, `clear descendants`, sticky actions, toasts) приведены к одному page-level contract;
14. browser-verified cold-start/reload для `tab=params`: leaf-category из URL не теряет `Текущий контур`, имя категории гидратируется корректно;
15. AI apply-path на проде подтвержден browser-check: URL не ломается, кнопка возвращается в normal-state, счетчики обновляются;
16. background bootstrap после AI apply больше не падает в `500`: full-save path для `attribute_value_refs` дедуплирует canonical collisions;
17. `/catalog/import` и `/catalog/export` переведены на единый `Sources / Import` workspace-contract вместо старого `catalog-exchange` poster-layout;
18. embedded `CatalogExchangePicker` используется как общий reusable block в import и export потоках;
19. browser-check на проде подтверждает live export batch-state и live import run-state на малой ветке каталога;
20. `Organizations / Admin` доведен до рабочего состояния;
21. `Competitor Product Discovery Pipeline` временно поставлен на паузу до исправления базовых рабочих экранов;
22. `Catalog Workspace Rework` выполнен первым рабочим проходом: default tab стал `Товары`, дерево получило filters/counts, справа остался lightweight inspector, browser-check через `@browser-use` на production прошел без console errors;
23. `Navigation Shell / Menu` выполнен первым рабочим проходом: компактный rail сохранен, expanded panel стал full-height, пользователь/организация/роль/theme toggle видны в общем shell, browser-check через `@browser-use` прошел без console errors;
24. `Parameter Values Workspace` выполнен first-pass: tab `Значения` подключен, direct URL с category гидратирует контур, embedded dictionary editor уплотнен, browser-check через `@browser-use` прошел без console errors;
25. `Channel Mapping Workspace Rework` выполнен first-pass: старый hero/title заменен компактным `Каналы и источники`, декоративные intro-блоки скрыты из above-the-fold, browser-check через `@browser-use` прошел без console errors;
26. `Sources / Import Rework` выполнен first-pass: `/catalog/import` и `/catalog/export` получили compact modern shell styles, sticky sidebar/inspector, theme-safe colors и sticky table headers, browser-check через `@browser-use` прошел без console errors;
27. `Organizations / Admin Rework` выполнен first-pass: admin headers уплотнены, sidebars закреплены, old local access layout получил sticky/sidebar contract, browser-check через `@browser-use` прошел без console errors;
28. `Product Workspace Final Polish` проверен через `@browser-use`: карточка товара открывается, workflow tabs и source/evidence блоки присутствуют, console errors отсутствуют;
29. `Product Creation Wizard` выполнен first-pass: экран `/products/new` уплотнен, получил рабочий rail-summary, success-state с переходом на `/products/:id`, browser-check через `@browser-use` прошел без console errors;
30. `Catalog Workspace Rework` получил второй visual pass: основной режим `Товары` убрал отдельные context/tabs cards над таблицей, category command/tabs/actions перенесены в единый compact bar прямо над product registry, browser-check через `@browser-use` прошел без console errors;
31. `Catalog UX Copy Pass` выполнен: технические термины `модель/каналы/контекст категории` заменены на пользовательские `поля товара/выгрузка/выбранная категория`, browser-check через `@browser-use` прошел без console errors;
32. продуктовый принцип `Clean Catalog` согласован: `/catalog` должен быть чистым финальным экраном структуры и SKU, а поля, выгрузка, импорт, сопоставления, валидация и промежуточная диагностика должны жить на отдельных страницах;
33. `Clean Catalog Implementation` выполнен первым проходом: из `/catalog` убраны tabs/термины про поля, выгрузку, импорт и маркетплейсы, tree badges заменены на чистые counts, embedded `ProductRegistry` получил reusable `catalogClean` variant;
34. `Catalog SKU Move Flow` подключен в `ProductRegistry.catalogClean`: строка SKU получила действие `Переместить`, modal выбирает новую категорию, сохранение идет через существующий `PATCH /products/{id}` и после успеха обновляет список/counts;
35. browser-check через `@browser-use` на `https://pim.id-smart.ru/catalog` подтвердил отсутствие старых рабочих терминов в main catalog DOM, наличие clean tree/table/actions и открытие move modal без отправки реального изменения данных;
36. текущий активный фокус: `Catalog Extended Visual QA`.
37. продуктовый принцип `Info Model Draft Workflow` согласован: основной путь создания инфо-модели — `draft из источников -> модерация -> утверждение`, ручное создание остается запасным режимом.
38. `/templates/:categoryId` должен быть пересобран вокруг state machine `none / collecting / draft / review / approved / needs_update`; `/sources` не должен создавать базовую модель, а должен работать как mapping-layer после появления модели.
39. активный implementation plan для перехода к реальным данным: [`docs/superpowers/plans/2026-04-27-info-model-draft-real-data.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/superpowers/plans/2026-04-27-info-model-draft-real-data.md).

### Что использовать как инструкцию прямо сейчас

Для ближайшего execution шага читать в таком порядке:

1. `20. Четвертый execution slice: Catalog Workspace`
2. `27.4 Heavy Pages To Rework`
3. `27. Reopened Design Debt Queue`
4. `12. Правило выполнения работ`
5. `25. Execution Protocol`
6. `14. Universal Blocks by Page Type`
7. `11. Подход к БД и data model`
8. `13. Page / Source / Result Map`

### Что нельзя забывать

Перед любой страницей обязательно:

1. перечислить все states;
2. перечислить все tabs;
3. перечислить все drawers/modals;
4. выделить universal / feature / individual blocks;
5. проверить light/dark;
6. проверить страницу в реальном браузере;
7. не переходить к следующей странице, пока текущая не закрыта полностью.

---

## Завершенные execution slices

Завершенные execution slices:

1. `Control Center`
2. `Product List`
3. `Product Workspace`
4. `Info Model Workspace`
5. `Channel Mapping Workspace`
6. `Sources / Import`
7. `Organizations / Admin`

Что закрыто по `Control Center`:

1. страница пересобрана в новый `Overview`-contract;
2. live summary больше не зависает в вечной загрузке;
3. backend hot-path `templates/dictionaries` стабилизирован для этого контура;
4. browser-check подтверждает загрузку реальных метрик и рабочих CTA;
5. следующий активный slice — `Product List`.

Что закрыто по `Product List`:

1. маршрут `/products` перестал быть редиректом в каталог и стал отдельной рабочей страницей;
2. страница пересобрана в `List + Inspector` contract;
3. фильтры, queue modes, bulk actions и inspector собраны на universal/data layer;
4. sticky toolbar, horizontal table scroll и right inspector проверены в браузере;
5. список больше не зависит от хрупких media preview в рабочей таблице;
6. browser-check подтверждает загрузку реальных SKU, выбор строки и рабочий inspector;
7. следующий активный slice — `Product Workspace`.

Что закрыто по `Product Workspace`:

1. deep link `login -> /products/:id` больше не зависает на вечной загрузке;
2. authenticated `session` hot-path перестал зависать из-за межпоточного reuse одного PostgreSQL connection;
3. detail endpoint `/api/products/:id` больше не тянет всю товарную таблицу ради variant-family;
4. товарный workspace открывается живым browser-flow и рендерит summary, секции, inspector и actions;
5. optional `channels-summary` переведен в bounded fetch и не блокирует основной товарный экран;
6. изменения выкачены в прод, post-deploy smoke green;
7. следующий активный slice — `Catalog Workspace`.

Что закрыто по `Catalog Workspace`:

1. страница перестала быть старым деревом с embedded registry и пересобрана в `Tree + Canvas + Inspector`;
2. дерево категорий загружается отдельным hot-path и больше не блокируется вторичным category-mapping bootstrap;
3. центральный canvas теперь показывает category summary, model state, channel state и product preview вместо старого реестра;
4. inspector оставлен только для контекста и действий, без дублирования центральной рабочей зоны;
5. проверены state без модели, state с моделью, tree search и переход `catalog -> products`;
6. browser-check выполнен на проде с живой сессией;
7. следующий активный slice — `Info Model Workspace`.

Что закрыто по `Info Model Workspace`:

1. страница `/templates` пересобрана в новый `Info Model Workspace` с category tree, рабочим canvas и inspector без старого catalog-layout;
2. страница `/templates/:categoryId` пересобрана в плотный editor-workspace для пустой и существующей модели;
3. editor bootstrap больше не тянет тяжелый source-enrichment и не пересобирает default attrs с нуля на каждом запросе;
4. hot-path `/api/templates/editor-bootstrap/:categoryId` ускорен на проде до рабочего уровня для первого открытия и теплого повторного запроса;
5. browser-check выполнен на проде для `templates`, пустой модели, существующей модели, `Import/Export` modal и `Dictionary` modal;
6. Playwright-процессы после проверки закрыты;
7. следующий активный slice — `Channel Mapping Workspace`.

Что закрыто по `Channel Mapping Workspace`:

1. страница `sources-mapping` переведена на новый `Channel Mapping Workspace` contract без старого poster-header;
2. categories-view, parameter-view и leaf redirect из `root -> working leaf` работают стабильно;
3. nested states и modal states (`Изменить`, `clear descendants`, sticky actions, toasts) приведены к единому page-level behavior;
4. tree interaction больше не ломается из-за вложенной button-структуры;
5. AI apply-path больше не висит на Ollama и работает через bounded timeout;
6. background bootstrap после AI apply больше не падает в `500`: storage full-save path дедуплирует canonical collisions в `attribute_value_refs`;
7. browser-check на проде подтверждает `login -> sources-mapping -> params -> Сопоставить с AI` без редиректа, без новых console errors и с обновлением счетчиков;
8. Playwright-процессы после проверки закрыты;
9. следующий активный slice — `Sources / Import`.

Что закрыто по `Sources / Import`:

1. страницы `/catalog/import` и `/catalog/export` перестали быть старым `catalog-exchange` экраном и собраны как единый `Sources / Import` workspace;
2. shared `CatalogExchangePicker` стал embedded reusable block для выбора области и SKU в обоих потоках;
3. import-flow покрывает baseline overview, run summary, result table, conflict state и empty state в одном рабочем контуре;
4. export-flow покрывает target selection, batch preparation, queue table и empty state в том же контуре;
5. browser-check на проде подтверждает живой export batch-state и живой import run-state на ветке `ТВ и приставки`;
6. Playwright-процессы после проверки закрыты;
7. следующий активный slice — `Organizations / Admin`.

Что закрыто по `Organizations / Admin`:

1. страницы `/admin/organizations`, `/admin/members`, `/admin/invites`, `/admin/platform` собраны в единый `List + Inspector` admin-workspace;
2. режимы организаций, сотрудников и инвайтов используют общий `PageTabs`, `DataTable`, `MetricGrid`, `InspectorPanel`, `Badge`, `Field`, `TextInput`, `Select`, `Button`, `EmptyState`;
3. `/admin/platform` для пользователя без developer-доступа не ломает страницу и возвращает безопасный organization-mode;
4. список организаций, список сотрудников, pending invite, invite form и inspector states проверены на живом проде;
5. universal `DataTable` исправлен для `light/dark`, чтобы темная тема не давала светлые строки с нечитаемым текстом;
6. browser-check на проде подтверждает login-flow, маршруты admin-раздела, таблицы, inspector и dark-mode на desktop viewport `1600px`;
7. следующий активный slice — `Competitor Product Discovery Pipeline`.

---

## 1. Цель

Полностью пересобрать продукт как новый desktop-first PIM/SaaS, а не как старую систему с новой темой.

Итоговый продукт должен:

1. ощущаться как новый `Attio-like premium SaaS`;
2. быть построен вокруг `товара` как главной рабочей сущности;
3. иметь единый shell, единые page patterns и единый visual language;
4. быть спроектирован page-by-page, без локальных импровизаций;
5. иметь новую, более цельную product/data structure;
6. проходить browser-проверку на каждой странице до перехода к следующей.

---

## 2. Зафиксированные продуктовые решения

### 2.1 Позиционирование и UX-направление

- ориентир: `Attio-like premium SaaS`;
- платформа: `desktop only`;
- темы: `light + dark`;
- приоритет: `wow + motion + высокая рабочая плотность`;
- продукт должен ощущаться как система для повседневной операционной работы, а не как внутренняя админка.

### 2.2 Главная рабочая сущность

Главная рабочая сущность: `товар`.

Это значит:

- пользователь большую часть времени работает в товаре;
- все остальное в основном настраивается реже;
- архитектура интерфейса должна строиться от `Product Workspace`.

### 2.3 Source of truth

Принята `смешанная модель`.

То есть:

- у товара есть собственная PIM-структура;
- у каналов есть свои требования;
- система должна явно разделять:
  - внутренние данные;
  - данные канала;
  - маппинг;
  - readiness/validation по каждому каналу.

### 2.4 Канальная модель

Один и тот же товар может одновременно публиковаться в нескольких каналах.

Для каждого канала существуют:

- свои категории;
- свои обязательные поля;
- свои правила;
- свой readiness;
- свой экспортный статус.

### 2.5 SKU и варианты

Зафиксировано:

- одна запись товара = один `SKU`;
- варианты тоже являются отдельными товарами со своим `SKU`;
- варианты в UX схлопываются в группу;
- значит нужны:
  - отдельная сущность товара;
  - grouping layer;
  - понятный variant/group UX.

### 2.6 Стартовая страница

После логина стартовая страница должна быть `Control Center`.

Не:

- лендинговый hero;
- голый список товаров;
- чисто технический dashboard.

А:

- операционный центр;
- с входами в работу;
- со статусами;
- с проблемами;
- с приоритетами.

---

## 3. Зафиксированный рабочий pipeline

Пользовательский pipeline:

1. регистрация организации;
2. пользователи и права;
3. подключение каналов импорта/экспорта;
4. создание каталога категорий;
5. создание инфо-моделей для категорий;
6. заливка товаров и распределение по группам и категориям;
7. связка категорий каталога с категориями маркетплейсов;
8. сопоставление параметров инфо-модели с категориями маркетплейсов;
9. наполнение товаров:
   - источники;
   - импорт;
   - Excel;
   - медиа;
   - связанные товары;
   - аналоги;
   - описания;
10. экспорт;
11. валидация.

Важная оговорка:

- наполнение товара может начинаться раньше;
- workflow не должен быть жестко линейным;
- продукт обязан поддерживать плавающий операционный процесс.

---

## 4. Product Workspace как ядро системы

Предварительный состав секций товара:

1. `Обзор`
2. `Основное`
3. `Параметры`
4. `Медиа`
5. `Источники`
6. `Каналы`
7. `Валидация`
8. `Связи`
9. `Аналоги`
10. `Сопутствующие`
11. `Варианты`

Целевой паттерн:

1. список товаров;
2. открытие товара;
3. detail workspace товара:
   - левое меню секций;
   - sticky summary/action bar сверху;
   - центральная рабочая область;
   - правый optional inspector/status panel.

Одна длинная карточка товара вниз не допускается как основной паттерн.

---

## 5. Новый глобальный layout продукта

### 5.1 Shell

Целевой shell:

1. `Left Rail`
2. `Full-height Context Panel`
3. `Workspace Topbar`
4. `Page Canvas`

Правила:

- rail всегда узкий и стабильный;
- context panel всегда full-height;
- organization/user/service actions не смешиваются с навигацией страницы;
- рабочий холст должен начинаться быстро, без декоративного пролога.

### 5.2 Page contract

Каждая рабочая страница должна собираться по одному из системных типов:

1. `Overview`
2. `Tree + Canvas + Inspector`
3. `List + Inspector`
4. `Editor`

Новые страницы запрещено строить как ad-hoc layout.

---

## 6. Page types

### 6.1 Overview

Для:

- `Control Center`
- platform/admin overview
- readiness/quality overview

Структура:

1. page header;
2. compact status row;
3. key metrics;
4. queue/problems;
5. quick actions;
6. recent activity.

### 6.2 Tree + Canvas + Inspector

Для:

- `Catalog Workspace`
- `Info Model Workspace`
- `Channel Mapping Workspace`
- часть `Sources`

Структура:

1. левое дерево/контекст;
2. центральный рабочий canvas;
3. правый inspector.

### 6.3 List + Inspector

Для:

- `Organizations / Users / Invites`
- `Dictionaries`
- `Connectors`
- `Product Groups`

Структура:

1. header;
2. toolbar/filter row;
3. list/table;
4. inspector выбранной сущности.

### 6.4 Editor

Для:

- `Product Workspace`
- `Template/Info Model Editor`
- `Dictionary Value Editor`
- import/mapping editors

Структура:

1. sticky summary/action bar;
2. sectional navigation;
3. main editor canvas;
4. правый status/validation/context panel.

---

## 7. Инвентарь страниц и новый порядок переделки

Ниже рабочий порядок переделки. Пока текущая страница не доведена до конца и не проверена в браузере, к следующей не переходим.

### Этап 1. Control Center

Цель:

- сделать правильную стартовую страницу после логина;
- превратить текущий dashboard в операционный центр.

Тип:

- `Overview`

### Этап 2. Product List

Цель:

- сделать список товаров как главную рабочую очередь;
- обеспечить быстрый вход в товар;
- поддержать группировку, фильтрацию, статусы, channel-readiness.

Тип:

- `List + Inspector`

### Этап 3. Product Workspace

Цель:

- сделать главный detail workspace товара;
- превратить товар в ядро всей системы.

Тип:

- `Editor`

### Этап 4. Catalog Workspace

Цель:

- проектирование и работа с категориями;
- связь категорий, групп и товарного контекста;
- поддержка tree-based workflow.

Тип:

- `Tree + Canvas + Inspector`

### Этап 5. Info Model Workspace

Цель:

- проектирование инфо-моделей;
- работа с полями, группами, обязательностью, связями с категориями.

Тип:

- `Tree + Canvas + Inspector`

### Этап 6. Channel Mapping Workspace

Цель:

- category mapping;
- parameter mapping;
- readiness per channel;
- канал-специфичный контекст.

Тип:

- `Tree + Canvas + Inspector`

### Этап 7. Sources / Import

Цель:

- источники;
- импорт;
- enrichment;
- Excel/import flows.

Тип:

- гибрид `List + Inspector` и `Editor` в зависимости от конкретной страницы.

### Этап 8. Organizations / Admin

Цель:

- организация;
- пользователи;
- роли;
- инвайты;
- platform admin.

Тип:

- `List + Inspector`

---

## 8. Обязательная схема разбора каждой страницы

Для каждой страницы до начала редизайна обязательно фиксируем:

### 8.1 Route и роль страницы

- route;
- зачем страница существует;
- primary user intent;
- что является финальным результатом работы на этой странице.

### 8.2 Data flow

Нужно описать:

- откуда пользователь приходит;
- куда уходит дальше;
- какой объект является исходником;
- какой объект является результатом;
- какие API и сущности участвуют.

### 8.3 Block inventory

Каждый блок страницы классифицируем как:

1. `Universal`
2. `Feature-level`
3. `Individual`

Правило:

- если блок встречается больше одного раза в системе или явно будет переиспользоваться — это не individual;
- individual допускается только при реально уникальной логике.

### 8.4 Layout contract

Нужно явно определить:

- тип страницы;
- sticky elements;
- scroll containers;
- horizontal scroll behavior;
- inspector behavior;
- empty/error/loading states.

### 8.5 Browser acceptance

До завершения страницы обязательно проверить:

1. desktop viewport;
2. отсутствие налезаний;
3. отсутствие выпадающих текстов;
4. sticky behavior;
5. horizontal scroll на длинных таблицах;
6. hover/focus/dropdown behavior;
7. светлую и темную темы;
8. реальную работу в браузере, а не только `npm run build`.

---

## 9. Жесткие правила верстки и UX

### 9.1 Что запрещено

- hero/poster над рабочими экранами;
- giant headlines ради атмосферы на operational pages;
- лишний вертикальный пролог перед рабочей зоной;
- card-inside-card-inside-card;
- локальные page-specific button/input/table implementations;
- локальные mobile-костыли для desktop-only продукта;
- таблицы без явного horizontal scroll contract;
- случайные sticky-элементы без явной причины.

### 9.2 Что обязательно

- рабочий экран должен начинаться быстро;
- page-title должен быть спокойным и функциональным;
- основной холст должен быть выше fold, без необходимости скроллить ради начала работы;
- sticky использовать только там, где это реально повышает эффективность;
- длинные таблицы обязаны иметь нормальный horizontal scroll;
- все dropdown/flyout/panel состояния должны быть устойчивыми;
- цвета должны давать читаемость, а не “атмосферу любой ценой”.

### 9.3 Темы

Обе темы обязательны:

- `light`
- `dark`

Правила:

- структура одинакова;
- темы меняют surface/text/accent model;
- dark theme не должна ломать читаемость;
- нельзя использовать hardcoded light colors в dark surfaces;
- нельзя делать разные UX-паттерны для разных тем.

---

## 10. Universal blocks, feature blocks, individual blocks

### 10.1 Universal

Кандидаты в shared system:

- buttons;
- inputs;
- selects;
- textareas;
- fields;
- badges/chips;
- status pills;
- dropdown/context menu;
- modal/drawer;
- tabs/section nav;
- sticky toolbar;
- search bar;
- table shell;
- tree row;
- list row;
- pagination;
- filter row;
- inspector shell;
- readiness/validation panel shell;
- empty/loading/error states.

### 10.2 Feature-level

Кандидаты в feature composites:

- product workspace;
- catalog workspace;
- info-model workspace;
- channel mapping workspace;
- media composition area;
- variants/relations manager;
- control center widgets;
- organizations/members/invites surfaces.

### 10.3 Individual

Разрешены только там, где блок реально уникален и встречается один раз.

Но даже внутри individual block:

- controls;
- table behavior;
- forms;
- menus;
- chips;
- toolbars

все равно должны собираться из универсального слоя.

---

## 11. Подход к БД и data model

### 11.1 Что уже зафиксировано

- organization-aware platform;
- product-centered system;
- mixed model;
- multi-channel state;
- one product row = one SKU;
- variants are separate SKU records grouped in UX.

### 11.2 Что нужно обсудить отдельно

Перед переделкой БД нужно зафиксировать:

1. минимальный состав таблиц;
2. одна ли у нас действительно центральная `products` таблица;
3. где хранятся:
   - channel-specific fields;
   - readiness/validation;
   - media;
   - relations/analogs/related;
   - imports/sources;
   - variant grouping;
   - model/category binding;
4. что является нормализованным слоем, а что — derived/read-model слоем.

### 11.3 Предварительный принцип

Новая схема БД должна строиться от следующего:

1. минимизировать количество сущностей без искусственной денормализации, которая убивает сопровождение;
2. держать `product` центральной таблицей;
3. не плодить отдельные сущности только потому, что так исторически было в старом проекте;
4. при этом не пытаться запихнуть весь мир в одну таблицу, если это ломает канальные состояния, отношения и versioned values.

### 11.4 Обязательный отдельный deliverable по БД

До начала DB migration нужен отдельный утвержденный раздел в этом же master-plan:

1. `Core tables`
2. `Support tables`
3. `Derived/read models`
4. `Channel state model`
5. `Product grouping model`
6. `Import/source model`
7. `Validation/export model`

Без этого к переделке БД не переходим.

### 11.5 Зафиксированный baseline для структуры БД

Текущий согласованный baseline:

#### Core tables

1. `organizations`
2. `users`
3. `organization_members`
4. `channels`
5. `catalog_categories`
6. `info_models`
7. `products`
8. `product_groups`

#### Support tables

1. `product_values`
2. `product_media`
3. `product_relations`
4. `product_channel_state`
5. `category_channel_mapping`
6. `info_model_channel_mapping`
7. `imports`
8. `exports`

#### Derived / read models

1. `product_readiness_summary`
2. `product_search_index`
3. `control_center_counters`

#### Главный принцип

1. `products` — одна центральная таблица на один SKU;
2. тяжелые многозначные и канальные данные не должны запихиваться в одну giant-record структуру;
3. support-слой должен оставаться минимальным, без искусственного раздувания количества таблиц;
4. derived/read-model слой должен обслуживать UI и аналитические surfaces, а не быть source of truth.

Это baseline-структура.

Следующий обязательный шаг — зафиксировать:

1. как хранить media;
2. как хранить relations / analogs / related;
3. как хранить variant grouping.

### 11.6 Зафиксированный baseline для `products`

Текущий согласованный baseline для центральной таблицы `products`:

1. `id`
2. `organization_id`
3. `sku`
4. `title`
5. `status`
6. `category_id`
7. `info_model_id`
8. `product_group_id`
9. `brand`
10. `created_at`
11. `updated_at`
12. `created_by`
13. `updated_by`
14. `archived_at` nullable

#### Принцип

В `products` лежит только то, что нужно для:

1. идентичности товара;
2. принадлежности товара;
3. быстрого списка товаров;
4. основных операционных read-models.

Это значит:

1. динамические и расширяемые параметры не хранятся прямо в `products`;
2. channel-specific поля не хранятся прямо в `products`;
3. `products` не должен превращаться в giant-table со всеми возможными атрибутами.

### 11.7 Зафиксированный baseline для `product_values`

Текущий согласованный baseline для `product_values`:

1. `id`
2. `organization_id`
3. `product_id`
4. `attribute_code`
5. `value_type`
6. `value_text`
7. `value_number`
8. `value_boolean`
9. `value_json`
10. `unit`
11. `source_type`
12. `source_ref`
13. `is_manual`
14. `updated_at`

#### Принцип

1. одна строка = одно значение одного атрибута товара;
2. `attribute_code` ссылается на атрибутный слой инфо-моделей / глобальных атрибутов;
3. `product_values` хранит именно товарные значения;
4. channel-specific readiness, relations и media в эту таблицу не кладутся.

#### Multi-value правило

Если значение реально участвует в:

- фильтрации;
- поиске;
- группировке;
- аналитике;

то multivalue лучше хранить отдельными строками.

Если значение:

- структурно сложное;
- вспомогательное;
- не требует нормальной табличной фильтрации;

то допускается хранение в `value_json`.

### 11.8 Зафиксированный baseline для `product_channel_state`

Текущий согласованный baseline для `product_channel_state`:

1. `id`
2. `organization_id`
3. `product_id`
4. `channel_id`
5. `channel_category_id`
6. `channel_status`
7. `readiness_status`
8. `validation_errors_json`
9. `missing_fields_json`
10. `mapped_attributes_json`
11. `export_status`
12. `last_export_at`
13. `last_validation_at`
14. `payload_hash`
15. `updated_at`

#### Принцип

1. одна строка = один товар в одном канале;
2. все channel-specific состояния живут в этой таблице;
3. readiness и export считаются per channel, а не globally на товаре;
4. `product_channel_state` не заменяет `product_values` и не хранит всю товарную карточку.

### 11.9 Зафиксированный baseline для `product_media`

Текущий согласованный baseline для `product_media`:

1. `id`
2. `organization_id`
3. `product_id`
4. `media_type`
5. `storage_provider`
6. `storage_bucket`
7. `storage_key`
8. `source_url`
9. `alt_text`
10. `sort_order`
11. `is_primary`
12. `channel_usage_json`
13. `created_at`
14. `updated_at`

#### Принцип

1. одна строка = один медиа-объект товара;
2. порядок медиа нормализован;
3. главное изображение не хранится отдельным полем в `products`, а флагом `is_primary` в `product_media`;
4. storage-contract строится от S3-совместимого хранилища, а не от локальных файлов;
5. `storage_key` — это ключ объекта в bucket, а не filesystem path;
6. если каналы используют медиа по-разному, это отражается через `channel_usage_json` до тех пор, пока не понадобится отдельный support-слой.

#### Storage note

Зафиксировано:

- медиа живет в `S3`-хранилище;
- значит product/media layer должен опираться на object-storage модель:
  - `bucket`
  - `key`
  - provider
  - позже при необходимости `region`, `etag`, `content_type`, `width`, `height`, `size_bytes`.

### 11.10 Зафиксированный baseline для `product_relations`

Текущий согласованный baseline для `product_relations`:

1. `id`
2. `organization_id`
3. `source_product_id`
4. `target_product_id`
5. `relation_type`
6. `sort_order`
7. `created_at`
8. `updated_at`

#### Значения `relation_type`

1. `related`
2. `analog`
3. `accessory`

#### Принцип

1. одна строка = одна связь между двумя SKU;
2. смысл связи определяется полем `relation_type`;
3. аналоги, сопутствующие и связанные товары не разносятся по разным таблицам, если storage-логика у них одна и та же;
4. UI и read-models могут разделять эти связи по секциям, но source of truth остается единым relation-layer.

### 11.11 Зафиксированный baseline для `product_groups / variants`

Текущий согласованный baseline:

#### Таблица `product_groups`

1. `id`
2. `organization_id`
3. `group_code`
4. `group_title`
5. `group_type`
6. `created_at`
7. `updated_at`

#### Логика

1. каждый вариант остается отдельным товаром в `products`;
2. связь SKU с группой идет через `products.product_group_id`;
3. группа нужна для variant-family UX и логики объединения, а не как замена товару.

#### Значения `group_type`

1. `variant_family`
2. `manual_group`

#### Принцип

1. source of truth для вариантов остается в `products`;
2. `product_groups` задает grouping layer;
3. при необходимости aggregated variant summary должен жить в derived/read-model слое, а не внутри core source-of-truth таблиц.

---

## 12. Правило выполнения работ

### 12.1 Нельзя

- параллельно переделывать много страниц;
- перепрыгивать к следующей странице до завершения текущей;
- пропускать страницы, подстраницы, табы, секции или вложенные рабочие состояния;
- оставлять старые локальные элементы внутри новой страницы только потому, что “и так работает”;
- сначала “чуть поменять UI”, а потом думать о структуре;
- тащить старую page structure в новый продукт;
- говорить “готово”, если страница не проверена в браузере.

### 12.2 Нужно

Для каждой страницы:

1. разобрать route/data flow;
2. выделить universal/feature/individual blocks;
3. перечислить все табы, секции, подэкраны, drawers, modals и nested states;
4. зафиксировать layout contract;
5. переделать страницу с нуля под новый контракт;
6. проверить в браузере каждый tab/state;
7. исправить layout/scroll/dropdown/sticky issues;
8. убедиться, что все повторяющиеся элементы сведены в universal или feature-level слой;
9. только после этого отметить страницу как завершенную;
10. обновить этот документ;
11. и только потом идти дальше.

### 12.3 Обязательное правило полноты проработки

Для каждой страницы запрещено:

1. переделать только “главный экран”, но не тронуть вложенные табы;
2. переделать основной list, но оставить старые modals/drawers/forms;
3. переделать layout, но не проверить hover/focus/open states;
4. переделать шапку, но не дойти до рабочего содержимого;
5. переделать центральную зону, но оставить старый inspector;
6. переделать один сценарий, но не проверить соседние режимы экрана.

Это означает:

1. каждая route-страница проходит полный аудит;
2. каждый tab и nested state проходит проверку;
3. каждый повторяющийся элемент должен быть либо universal, либо feature-level;
4. individual block допускается только когда он действительно уникален.

---

## 13. Page / Source / Result Map

Ниже baseline-карта основных продуктовых потоков.

### 13.1 Control Center

- исходник: aggregated operational state;
- дальше пользователь идет в:
  - товары;
  - ошибки;
  - каналы;
  - импорт;
- финальный результат: пользователь быстро выбрал рабочую зону и вошел в действие.

### 13.2 Product List

- исходник: `products`;
- дальше пользователь идет в: `Product Workspace`;
- финальный результат: выбран конкретный SKU или группа SKU для работы.

### 13.3 Product Workspace

- исходник: один `product` + связанные состояния;
- дальше пользователь идет в:
  - экспорт;
  - валидацию;
  - редактирование;
  - группу вариантов;
  - канал;
- финальный результат: товар приведен в состояние, достаточное для публикации или дальнейшей обработки.

### 13.4 Catalog Workspace

- исходник: `catalog_categories`;
- дальше пользователь идет в:
  - инфо-модель;
  - товары категории;
  - category-channel mapping;
- финальный результат: категория настроена и связана с моделью и каналами.

### 13.5 Info Model Workspace

- исходник: `info_models`;
- дальше пользователь идет в:
  - product fields;
  - category binding;
  - channel mapping;
- финальный результат: структура модели готова для товаров и каналов.

### 13.6 Channel Mapping Workspace

- исходник:
  - `category_channel_mapping`
  - `info_model_channel_mapping`
- дальше пользователь идет в:
  - readiness;
  - export per channel;
- финальный результат: категория и параметры сопоставлены с каналом.

### 13.7 Sources / Import

- исходник: import/source jobs;
- дальше пользователь идет в:
  - enrichment товаров;
  - проверку обновлений;
- финальный результат: данные попали в товар или обновили товар.

### 13.8 Organizations / Admin

- исходник: organization and membership state;
- дальше пользователь идет в:
  - users;
  - roles;
  - invites;
  - channels;
- финальный результат: рабочее пространство организации настроено и доступно для команды.

---

## 14. Universal Blocks by Page Type

Ниже фиксируется минимальный обязательный набор универсальных блоков для каждого системного типа страницы.

Правило:

- сначала собирается universal layer;
- потом из него строится feature layer;
- только потом добавляется individual logic конкретной страницы.

### 14.1 Общие universal blocks для всего продукта

Эти блоки должны быть едины для всей системы:

1. `AppShell`
2. `Rail`
3. `ContextPanel`
4. `WorkspaceTopbar`
5. `PageHeader`
6. `PageSubheader`
7. `ActionBar`
8. `SearchBar`
9. `FilterBar`
10. `SegmentedSwitch`
11. `Button`
12. `IconButton`
13. `Dropdown`
14. `Menu`
15. `Modal`
16. `Drawer`
17. `Inspector`
18. `StatusBadge`
19. `EmptyState`
20. `ErrorState`
21. `Skeleton`
22. `StickySection`
23. `HorizontalScroller`

### 14.2 Overview pages

Для страниц типа `Overview` обязательны:

1. `PageHeader`
2. `ActionBar`
3. `MetricGrid`
4. `StatusStrip`
5. `QueueList`
6. `IssueList`
7. `QuickActionsPanel`
8. `RecentActivityList`
9. `Inspector` optional

Примеры:

- `Control Center`
- platform overview

### 14.3 Tree + Canvas + Inspector

Для страниц типа `Tree + Canvas + Inspector` обязательны:

1. `PageHeader`
2. `ActionBar`
3. `TreeSidebar`
4. `TreeToolbar`
5. `TreeRow`
6. `CanvasHeader`
7. `CanvasToolbar`
8. `WorkspaceCanvas`
9. `Inspector`
10. `StickyInspector`
11. `HorizontalScroller` для длинных таблиц внутри canvas

Примеры:

- `Catalog Workspace`
- `Info Model Workspace`
- `Channel Mapping Workspace`

### 14.4 List + Inspector

Для страниц типа `List + Inspector` обязательны:

1. `PageHeader`
2. `SearchBar`
3. `FilterBar`
4. `SegmentedSwitch`
5. `DataTable` или `DataList`
6. `TableToolbar`
7. `TableCell primitives`
8. `BulkActionBar`
9. `Inspector`
10. `Pagination`
11. `HorizontalScroller`

Примеры:

- `Product List`
- `Organizations / Users / Invites`
- `Dictionaries`
- `Connectors`

### 14.5 Editor

Для страниц типа `Editor` обязательны:

1. `StickySummaryBar`
2. `SectionNav`
3. `SectionAnchor`
4. `EditorToolbar`
5. `Field`
6. `TextInput`
7. `Select`
8. `Textarea`
9. `RichTextArea` если нужно
10. `MediaGrid`
11. `RelationPicker`
12. `VariantPanel`
13. `ValidationPanel`
14. `ReadinessPanel`
15. `Inspector`
16. `HorizontalScroller` для табличных секций

Примеры:

- `Product Workspace`
- `Template / Info Model Editor`
- import/mapping editors

### 14.6 Табличные и скролл-контракты

Для всех data-heavy страниц обязательно:

1. длинная таблица не ломает layout;
2. таблица живет внутри явного horizontal scroll container;
3. sticky header не конфликтует с page shell;
4. sticky bulk bar не перекрывает данные;
5. inspector и canvas имеют предсказуемые scroll boundaries.

### 14.7 Sticky rules

Sticky разрешен только для:

1. workspace topbar;
2. summary/action bar;
3. section nav;
4. inspector;
5. bulk action bar;
6. table header, если это реально повышает usability.

Sticky запрещен для декоративных intro-блоков и нерабочих поверхностей.

---

## 15. Текущий рабочий статус

Сейчас мы находимся в фазе `master planning`.

До завершения planning-фазы:

- к page-by-page redesign не приступаем;
- к DB redesign не приступаем;
- сначала закрываем master-plan полностью.

Следующий обязательный блок planning:

1. фиксация первого execution slice: `Control Center`;
2. затем page-by-page redesign по этому документу.

### 15.1 Зафиксированный baseline для Control Center

Текущий согласованный порядок блоков `Control Center` сверху вниз:

1. рабочая очередь товаров;
2. ошибки и проблемы по каналам;
3. readiness по каналам;
4. последние импорт/экспорт операции;
5. быстрые действия.

Это baseline-структура.

Если в процессе детализации продукта станет понятно, что порядок должен быть другим, меняем уже в этом документе, а не в чате.

### 15.2 Зафиксированный baseline для Product List

Текущий согласованный baseline для `Product List`:

Сверху вниз:

1. строка поиска и быстрых фильтров;
2. переключение режимов просмотра:
   - все;
   - мои;
   - проблемные;
   - готовы к экспорту;
3. таблица или список товаров;
4. правый inspector выбранного товара;
5. массовые действия;
6. нижний sticky bulk/action bar при выборе строк.

Базовый состав строки товара:

1. название;
2. SKU;
3. категория;
4. группа / вариант;
5. заполненность;
6. readiness по каналам;
7. статус;
8. последнее изменение.

Это baseline-структура.

Если в процессе детального проектирования `Product List` потребуется ее изменить, изменение вносится в этот документ.

### 15.3 Зафиксированный baseline для Product Workspace

Текущий согласованный baseline для `Product Workspace`:

#### Верхняя зона товара

1. название товара;
2. SKU;
3. категория;
4. группа / вариант;
5. общий статус;
6. readiness по каналам;
7. primary actions:
   - сохранить;
   - экспортировать;
   - открыть канал;
   - открыть историю.

#### Левая навигация секций

1. Обзор
2. Основное
3. Параметры
4. Медиа
5. Источники
6. Каналы
7. Валидация
8. Связи
9. Аналоги
10. Сопутствующие
11. Варианты

#### Правая панель

1. ошибки и предупреждения;
2. readiness summary;
3. связанные channel states;
4. история изменений / последних действий.

#### Поведение

1. верхняя summary/action bar sticky;
2. левая навигация секций sticky;
3. правая панель sticky;
4. центральная рабочая область скроллится;
5. длинные таблицы внутри секций имеют свой horizontal scroll contract.

Это baseline-структура.

Если в процессе детализации `Product Workspace` потребуется изменение, оно вносится в этот документ.

---

## 16. Первый execution slice: Control Center

Ниже фиксируется первый исполняемый slice новой системы.

После завершения planning-фазы именно по этому разделу можно начинать переделку первой страницы.

### 16.1 Роль страницы

`Control Center` — это главная стартовая страница после логина.

Это не:

- лендинговый экран;
- декоративный dashboard;
- дублирующий список товаров экран.

Это:

- операционный центр;
- входная точка в ежедневную работу команды;
- место, где пользователь видит, что требует внимания прямо сейчас.

### 16.2 Source / result

#### Source

Страница строится не от одной сущности, а от агрегированного operational state:

1. `products`
2. `product_channel_state`
3. `imports`
4. `exports`
5. `product_readiness_summary`
6. derived counters/read models

#### Result

Финальный результат работы на странице:

1. пользователь понимает, что сейчас требует внимания;
2. выбирает конкретную рабочую зону;
3. переходит в:
   - `Product List`
   - конкретный товар
   - проблемный канал
   - импорт/экспорт операцию

### 16.3 Тип страницы

Тип страницы:

- `Overview`

Но не “marketing overview”, а `operational overview`.

### 16.4 Структура сверху вниз

Согласованный baseline:

1. рабочая очередь товаров;
2. ошибки и проблемы по каналам;
3. readiness по каналам;
4. последние импорт/экспорт операции;
5. быстрые действия.

### 16.5 Детальная композиция страницы

#### Зона 1. Header

Содержит:

1. спокойный заголовок страницы;
2. короткое описание текущего состояния рабочего контура;
3. 1-3 primary actions.

Правила:

- без giant hero;
- без большого вертикального intro;
- работа должна начинаться сразу в пределах первого экрана.

#### Зона 2. Priority row

Содержит:

1. рабочую очередь товаров;
2. критические ошибки по каналам;
3. быстрый вход в проблемные сущности.

Это верхняя и самая важная рабочая зона страницы.

#### Зона 3. Readiness section

Содержит:

1. readiness per channel;
2. количество готовых/неготовых товаров;
3. возможность перейти в filtered product list или channel workspace.

#### Зона 4. Operations section

Содержит:

1. последние импорты;
2. последние экспорты;
3. статусы операций;
4. ошибки/предупреждения по операциям.

#### Зона 5. Quick actions

Содержит:

1. создать товар;
2. открыть список товаров;
3. перейти к импорту;
4. перейти в каталог;
5. перейти в каналы/маппинг.

### 16.6 Universal / feature / individual split

#### Universal blocks

1. `PageHeader`
2. `ActionBar`
3. `MetricGrid`
4. `StatusStrip`
5. `QueueList`
6. `IssueList`
7. `RecentActivityList`
8. `QuickActionsPanel`
9. `Inspector` optional
10. `StatusBadge`
11. `EmptyState`
12. `ErrorState`
13. `Skeleton`

#### Feature-level blocks

1. `ControlCenterQueue`
2. `ControlCenterChannelProblems`
3. `ControlCenterReadiness`
4. `ControlCenterOperations`
5. `ControlCenterQuickActions`

#### Individual blocks

Допускаются только если реально будет одна уникальная orchestration-обертка страницы:

1. `ControlCenterLayout`
2. `ControlCenterPriorityBoard`

Но даже в них внутренние controls должны собираться из universal layer.

### 16.7 Layout rules

1. страница должна быть full-width desktop workspace;
2. рабочая зона должна начинаться above the fold;
3. giant poster/introduction запрещены;
4. на первом экране пользователь должен видеть рабочие сигналы, а не только заголовок;
5. primary queue и channel issues должны находиться выше readiness и операций;
6. page должна дышать, но без чрезмерного whitespace;
7. блоки не должны выглядеть как пустые серые карточки;
8. light и dark темы должны быть одинаково читаемыми.

### 16.8 Motion rules

1. появление страницы мягкое, короткое, без театральности;
2. hover и focus на actionable blocks должны быть заметными;
3. quick action tiles и queue items могут иметь короткий reveal;
4. motion не должен замедлять чтение operational signals.

### 16.9 Acceptance checklist

Перед тем как считать `Control Center` завершенным, обязательно проверить:

1. страница не требует скролла ради начала работы;
2. заголовок не кричащий и не съедает экран;
3. верхний fold содержит реальные рабочие блоки;
4. блоки читаются и в `light`, и в `dark`;
5. нет выпадающих текстов;
6. нет схлопывающихся по высоте блоков;
7. hover/active/focus состояния устойчивые;
8. переходы в целевые рабочие зоны логичны;
9. проверка сделана в реальном браузере.

### 16.10 Definition of done

`Control Center` считается завершенным только если:

1. собран по новому layout contract;
2. не тянет старую структуру dashboard;
3. использует только universal + feature blocks;
4. browser-verified;
5. светлая и темная темы обе читаемы;
6. после завершения обновлен этот master-документ;
7. только после этого можно переходить к `Product List`.

---

## 17. Второй execution slice: Product List

Ниже фиксируется второй исполняемый slice новой системы.

После завершения `Control Center` следующей страницей в redesign должен идти именно `Product List`.

### 17.1 Роль страницы

`Product List` — это основная рабочая очередь системы.

Это не:

- вторичный реестр ради навигации;
- техническая таблица;
- dump всех SKU без рабочего смысла.

Это:

- главный operational entry в товары;
- место фильтрации, отбора и приоритизации SKU;
- точка входа в `Product Workspace`.

### 17.2 Source / result

#### Source

Страница строится от:

1. `products`
2. `product_readiness_summary`
3. `product_channel_state`
4. `product_groups`
5. derived search / list read models

#### Result

Финальный результат работы на странице:

1. выбран SKU или группа SKU;
2. пользователь понимает, какие товары требуют внимания;
3. пользователь переходит в:
   - `Product Workspace`
   - filtered action flow
   - bulk operation

### 17.3 Тип страницы

Тип страницы:

- `List + Inspector`

### 17.4 Структура сверху вниз

Согласованный baseline:

1. строка поиска и быстрых фильтров;
2. переключение режимов просмотра:
   - все;
   - мои;
   - проблемные;
   - готовы к экспорту;
3. таблица или список товаров;
4. правый inspector выбранного товара;
5. массовые действия;
6. нижний sticky bulk/action bar при выборе строк.

### 17.5 Детальная композиция страницы

#### Зона 1. Header

Содержит:

1. спокойный title;
2. короткий operational subtitle;
3. 1-3 primary actions.

Примеры primary actions:

1. создать товар;
2. импортировать;
3. открыть проблемные.

#### Зона 2. Search and filters

Содержит:

1. глобальный поиск по товарам;
2. быстрые фильтры;
3. channel-related filters;
4. category / group / status filters;
5. mode switch.

Эта зона должна быть плотной, быстрой и всегда читаемой.

#### Зона 3. Product list/table

Главная рабочая зона страницы.

Базовый состав строки товара:

1. название;
2. SKU;
3. категория;
4. группа / вариант;
5. заполненность;
6. readiness по каналам;
7. статус;
8. последнее изменение.

#### Зона 4. Inspector

Правый inspector выбранного товара должен показывать:

1. краткое summary товара;
2. статус и readiness;
3. связанные channel states;
4. быстрые действия;
5. переход в полный `Product Workspace`.

#### Зона 5. Bulk actions

При выборе строк должен появляться sticky bulk/action bar.

Он должен поддерживать:

1. массовое изменение;
2. массовую валидацию;
3. массовый экспорт;
4. массовые служебные действия.

### 17.6 Universal / feature / individual split

#### Universal blocks

1. `PageHeader`
2. `ActionBar`
3. `SearchBar`
4. `FilterBar`
5. `SegmentedSwitch`
6. `DataTable`
7. `TableToolbar`
8. `TableCell primitives`
9. `Inspector`
10. `Pagination`
11. `BulkActionBar`
12. `StatusBadge`
13. `ReadinessBadge`
14. `HorizontalScroller`
15. `EmptyState`
16. `ErrorState`
17. `Skeleton`

#### Feature-level blocks

1. `ProductListFilters`
2. `ProductListTable`
3. `ProductListInspector`
4. `ProductBulkActions`

#### Individual blocks

Допускаются только если действительно нужен уникальный orchestration-block:

1. `ProductListWorkspace`
2. `ProductQueueSwitch`

И даже в них внутренние элементы должны собираться из universal layer.

### 17.7 Layout rules

1. список товаров должен быть главной визуальной массой страницы;
2. фильтры не должны разрастаться в отдельный poster-блок;
3. таблица обязана иметь нормальный horizontal scroll contract;
4. inspector не должен ломать ширину таблицы;
5. строка товара должна читаться быстро;
6. плотность должна быть высокой, но без визуального мусора;
7. bulk bar не должен перекрывать важные данные.

### 17.8 Motion rules

1. selection строки должна ощущаться ясно;
2. inspector должен открываться мягко и быстро;
3. hover по строкам должен быть заметным, но не шумным;
4. массовые действия должны появляться без резких скачков layout.

### 17.9 Acceptance checklist

Перед тем как считать `Product List` завершенным, обязательно проверить:

1. поиск и фильтры читаемы и не ломают layout;
2. таблица не разваливается на длинных данных;
3. горизонтальный скролл у длинной таблицы работает нормально;
4. sticky bulk bar работает корректно;
5. inspector не конфликтует со scroll behavior;
6. строки и badges читаются в `light` и `dark`;
7. нет выпадающих текстов и схлопывающихся колонок;
8. переход в `Product Workspace` удобен;
9. проверка сделана в реальном браузере.

### 17.10 Definition of done

`Product List` считается завершенным только если:

1. страница реально стала главной рабочей очередью товаров;
2. она не выглядит как старый registry с новой skin-оболочкой;
3. list/table/inspector работают по новому contract;
4. browser-verified;
5. светлая и темная темы обе рабочие;
6. после завершения обновлен этот master-документ;
7. только после этого можно переходить к `Product Workspace`.

### 17.11 Revision: product entry must be product-first

Текущая постановка меняет приоритеты для входа в товары.

Проблема:

1. пользователь открывает товарный раздел и видит dashboard-like верхнюю зону вместо товаров;
2. страница ощущается как презентационный экран, а не рабочий каталог;
3. первый экран не отвечает на вопрос “где товары и что с ними делать”;
4. верстка в текущем виде допускает сжатие, пустоты и кривые рабочие зоны.

Новый обязательный принцип:

1. выше fold должны быть сразу товары, поиск, фильтры и actions;
2. dashboard/hero/intro сверху запрещены для товарного entry;
3. метрики допустимы только как компактная служебная строка или chips, не как отдельная плашка;
4. основная визуальная масса страницы — product table/list;
5. выбранный товар должен открываться в inspector или вести в e-commerce-style product card;
6. empty/loading/error states должны сохранять тот же product-first layout, а не заменяться декоративным экраном.

Новый acceptance для `Product List`:

1. первый экран показывает строки товаров без скролла через intro;
2. поиск и быстрые фильтры находятся прямо над списком;
3. create/import/export actions доступны, но не доминируют;
4. длинные названия товаров, категории и SKU не ломают таблицу;
5. список работает как каталог интернет-магазина/операционная очередь, а не как dashboard.

### 17.12 Execution status: Product List / Catalog Entry

Статус: production-deployed and browser-verified.

Что изменено:

1. dashboard/hero/summary-strip сверху убраны из товарного entry;
2. первый экран начинается с compact product entry bar, поиска, queue-фильтров, фильтров каталога и таблицы;
3. create/import/export actions оставлены в верхней строке, но не забирают рабочую площадь;
4. таблица стала основной массой страницы;
5. справа оставлен компактный inspector выбранного SKU;
6. table scroller ограничен по высоте, чтобы рабочая зона не уезжала вниз;
7. для зависающих catalog API добавлен timeout fallback, чтобы UI не оставался в бесконечной skeleton-загрузке;
8. `uiSelect`, `pn-input`, `pn-select`, `pn-textarea` приведены к системным theme tokens, чтобы light/dark не ломали читаемость.

Проверено:

1. `CI=1 npm run build` в `frontend` проходит;
2. production deploy проходит;
3. `global-pim.service` active;
4. `https://pim.id-smart.ru/api/health` возвращает `{"ok":true}`;
5. production `/products` показывает `1087 SKU`, `50 на экране`, строки товаров above fold;
6. console errors на production `/products`: `0`;
7. light theme проверена через production screenshot;
8. dark theme проверена через production screenshot после переключения `smartpim.theme=dark`.

Оставшиеся риски для следующих slices:

1. общий shell/sidebar еще не является финальным целевым дизайном;
2. product card все еще требует e-commerce-style redesign по разделу `18.13`;
3. product creation все еще требует compact wizard по разделу `18.14`.

---

## 18. Третий execution slice: Product Workspace

Ниже фиксируется третий исполняемый slice новой системы.

После завершения `Product List` следующей страницей в redesign должен идти именно `Product Workspace`.

### 18.1 Роль страницы

`Product Workspace` — это главный detail workspace всей системы.

Это не:

- длинная форма вниз;
- набор разрозненных вкладок без иерархии;
- старый editor, натянутый на новую тему.

Это:

- основное место ежедневной работы с товаром;
- главный рабочий контур продукта;
- точка, где сходятся:
  - PIM-данные;
  - каналы;
  - readiness;
  - media;
  - relations;
  - варианты;
  - validation.

### 18.2 Source / result

#### Source

Страница строится от:

1. `products`
2. `product_values`
3. `product_media`
4. `product_relations`
5. `product_channel_state`
6. `product_groups`
7. related read models / validation summaries

#### Result

Финальный результат работы на странице:

1. товар приведен в нужное состояние;
2. пользователь понимает готовность товара по каналам;
3. товар подготовлен к публикации, обновлению или дальнейшей обработке;
4. пользователь может быстро перейти:
   - к варианту;
   - к группе;
   - к каналу;
   - к истории;
   - к связанным сущностям.

### 18.3 Тип страницы

Тип страницы:

- `Editor`

### 18.4 Верхняя структура страницы

Согласованный baseline:

#### Верхняя зона товара

1. название товара;
2. SKU;
3. категория;
4. группа / вариант;
5. общий статус;
6. readiness по каналам;
7. primary actions:
   - сохранить;
   - экспортировать;
   - открыть канал;
   - открыть историю.

#### Левая навигация секций

1. Обзор
2. Основное
3. Параметры
4. Медиа
5. Источники
6. Каналы
7. Валидация
8. Связи
9. Аналоги
10. Сопутствующие
11. Варианты

#### Правая панель

1. ошибки и предупреждения;
2. readiness summary;
3. связанные channel states;
4. история изменений / последних действий.

### 18.5 Детальная композиция страницы

#### Зона 1. Sticky summary/action bar

Содержит:

1. идентичность товара;
2. ключевые статусы;
3. primary actions;
4. быстрый вход в канальный контекст.

Эта зона должна оставаться короткой, рабочей и не превращаться в hero.

#### Зона 2. Section navigation

Левая секционная навигация должна:

1. быть sticky;
2. показывать активную секцию;
3. позволять быстро прыгать по товару;
4. быть стабильной при длинном содержимом центральной части.

#### Зона 3. Main editor canvas

Главная рабочая область товара.

Внутри нее рендерятся секции:

1. `Обзор`
2. `Основное`
3. `Параметры`
4. `Медиа`
5. `Источники`
6. `Каналы`
7. `Валидация`
8. `Связи`
9. `Аналоги`
10. `Сопутствующие`
11. `Варианты`

#### Зона 4. Right status panel

Показывает:

1. ошибки;
2. предупреждения;
3. readiness summary;
4. channel statuses;
5. историю изменений;
6. быстрые contextual actions.

### 18.6 Секции `Product Workspace`

#### Обзор

Показывает:

1. общий summary товара;
2. ключевые статусы;
3. что заполнено / не заполнено;
4. какие каналы заблокированы;
5. основные next actions.

#### Основное

Содержит:

1. title;
2. бренд;
3. базовую идентичность;
4. категорию;
5. принадлежность к группе;
6. базовые статусы.

#### Параметры

Содержит:

1. товарные атрибуты;
2. группировку полей;
3. ручные значения и source-aware значения;
4. визуальное разделение обязательных и дополнительных полей.

#### Медиа

Содержит:

1. список/сетку media;
2. reorder;
3. primary media;
4. channel/media context при необходимости.

#### Источники

Содержит:

1. происхождение значений;
2. источники enrichment;
3. импортированные данные;
4. ручные overrides.

#### Каналы

Содержит:

1. channel states;
2. channel category;
3. mapped/unmapped состояние;
4. export context;
5. links в channel-specific workflows.

#### Валидация

Содержит:

1. ошибки;
2. предупреждения;
3. missing fields;
4. readiness blockers;
5. разрез по каналам.

#### Связи

Содержит:

1. связанные сущности товара;
2. другие product-level связи, не относящиеся прямо к аналогам/аксессуарам.

#### Аналоги

Содержит список relation-type `analog`.

#### Сопутствующие

Содержит список relation-type `accessory`.

#### Варианты

Содержит:

1. текущую variant family;
2. другие SKU в группе;
3. переходы к ним;
4. различающие признаки вариантов.

### 18.7 Universal / feature / individual split

#### Universal blocks

1. `StickySummaryBar`
2. `SectionNav`
3. `SectionAnchor`
4. `EditorToolbar`
5. `Field`
6. `TextInput`
7. `Select`
8. `Textarea`
9. `StatusBadge`
10. `ReadinessBadge`
11. `ValidationList`
12. `MediaGrid`
13. `RelationList`
14. `VariantList`
15. `Inspector`
16. `HorizontalScroller`
17. `EmptyState`
18. `ErrorState`
19. `Skeleton`

#### Feature-level blocks

1. `ProductSummaryBar`
2. `ProductSectionNav`
3. `ProductOverviewSection`
4. `ProductMainSection`
5. `ProductAttributesSection`
6. `ProductMediaSection`
7. `ProductSourcesSection`
8. `ProductChannelsSection`
9. `ProductValidationSection`
10. `ProductRelationsSection`
11. `ProductAnalogsSection`
12. `ProductAccessoriesSection`
13. `ProductVariantsSection`
14. `ProductStatusInspector`

#### Individual blocks

Допускаются только если реально нужна одна orchestration-обертка:

1. `ProductWorkspaceLayout`
2. `ProductWorkspaceRouter`

Но все внутренние controls и sections должны собираться из universal/feature layers.

### 18.8 Layout rules

1. summary bar должна быть компактной и sticky;
2. левая навигация должна быть всегда доступна;
3. основная рабочая область не должна начинаться после большого intro;
4. правая панель не должна съедать центральный canvas;
5. длинные секции с таблицами должны иметь horizontal scroll contract;
6. скролл должен быть предсказуем:
   - summary sticky;
   - left nav sticky;
   - right panel sticky;
   - центр скроллится.

### 18.9 Motion rules

1. переключение между секциями должно быть быстрым и читаемым;
2. section nav должна ясно показывать active section;
3. inspector и channel state details должны открываться мягко;
4. motion не должен мешать редактированию полей;
5. сохранение и смена статусов должны иметь короткий, понятный feedback.

### 18.10 Acceptance checklist

Перед тем как считать `Product Workspace` завершенным, обязательно проверить:

1. пользователь попадает сразу в рабочую область, а не в декоративный экран;
2. summary bar короткая и полезная;
3. section nav работает и не ломается при длинном контенте;
4. правый inspector читаем и не ломает canvas;
5. длинные секции с таблицами имеют horizontal scroll;
6. все секции читаемы в `light` и `dark`;
7. нет выпадающих текстов, налезаний и схлопываний;
8. поля, медиа, связи, варианты и каналы живут в понятной иерархии;
9. проверка сделана в реальном браузере.

### 18.11 Definition of done

`Product Workspace` считается завершенным только если:

1. он стал главным рабочим контуром продукта;
2. не ощущается как старая форма с новыми цветами;
3. секции реально разделены по смыслам;
4. каналы, валидация, связи и варианты встроены в одну систему;
5. browser-verified;
6. обе темы рабочие и читаемые;
7. после завершения обновлен этот master-документ;
8. только после этого можно переходить к `Catalog Workspace`.

### 18.12 Current implementation status: content cockpit

Текущий implementation slice по `Product Workspace`:

1. карточка товара переведена с длинной stacked-структуры на active-section cockpit;
2. декоративный hero внутри карточки товара убран, чтобы рабочий экран начинался сразу после compact SKU header;
3. левая навигация стала основным workflow товара:
   - `Сводка`;
   - `Параметры`;
   - `Источники`;
   - `Площадки`;
   - `Конкуренты`;
   - `Медиа`;
   - `Валидация`;
   - `Связи`;
   - `Варианты`;
   - `Создание`;
4. правый inspector на карточке товара убран из текущей grid-композиции, потому что он дублировал summary и сжимал центральный canvas;
5. основной canvas получил больше ширины и не должен ломать рабочую область параметров;
6. секция `Параметры` получила `ProductAttributeWorkbench`;
7. `ProductAttributeWorkbench` показывает:
   - очередь параметров;
   - заполненность `filled/total`;
   - conflict count;
   - selected canonical value;
   - source evidence по `raw/resolved/canonical`;
   - marketplace projections;
8. для marketplace projections добавлена первая UI-нормализация display value:
   - canonical/PIM `256 ГБ`;
   - `Ozon` -> `256GB`;
   - `Wildberries` -> `256`;
9. секция `Источники` получила table-view трассировки source values;
10. секция `Создание` получила preview будущего product creation wizard;
11. browser-check локально подтверждает `/products/product_1`:
   - страница открывается после login и switch в `org_default`;
   - `Параметры` переключаются через левый workflow;
   - `Встроенная память` показывает `256 ГБ`, `Ozon -> 256GB`, `Wildberries -> 256`;
   - console errors `0`;
12. остающийся следующий sub-slice по Product Workspace:
   - заменить preview `Создание` на настоящий wizard создания SKU;
   - добавить сохранение/override выбранного значения параметра;
   - добавить полноценные channel-specific rules вместо первой display-нормализации;
   - проверить dark theme после production deploy.

### 18.13 Revision: product card must read like an e-commerce product page

Текущая постановка меняет смысл `Product Workspace`.

Проблема:

1. cockpit-структура полезна для операций, но карточка товара должна сначала читаться как товар;
2. контент-менеджеру нужно видеть товар “как покупатель”, а служебные PIM-слои должны дополнять карточку, а не заменять ее;
3. текущая рабочая область все еще может ощущаться как админская панель параметров, а не как понятная карточка товара;
4. страница должна быть компактнее и визуально ближе к интернет-магазину.

Новый обязательный принцип:

1. `Product Workspace` должен быть e-commerce-style product card с PIM-инструментами;
2. первый экран должен показывать:
   - media/gallery;
   - название;
   - SKU;
   - бренд;
   - категорию;
   - статус;
   - основные действия;
   - краткую готовность;
3. ниже или рядом должны быть product tabs:
   - `Описание`;
   - `Характеристики`;
   - `Маркетплейсы`;
   - `Источники`;
   - `Медиа`;
   - `Связи`;
   - `Варианты`;
   - `Валидация`;
4. характеристики должны читаться как спецификация товара:
   - группы параметров;
   - значения;
   - source evidence;
   - marketplace display values;
5. служебные данные `raw/resolved/canonical`, competitor mapping и validation должны быть доступны в контексте выбранной характеристики, но не превращать страницу в технический dump;
6. карточка товара должна быть compact-first:
   - минимум больших заголовков;
   - минимум повторяющихся рамок;
   - плотные строки;
   - понятные badge/status;
   - никакого наложения текста.

Новый acceptance для `Product Workspace`:

1. страница визуально читается как карточка товара в интернет-магазине;
2. пользователь без объяснений понимает, что это за товар;
3. media/gallery и основная информация видны above the fold;
4. характеристики компактные и не превращаются в бесконечный список без структуры;
5. marketplace values видны рядом с canonical/PIM value;
6. source evidence доступен без перегруза первого экрана;
7. links/analogs/accessories/variants не смешаны с характеристиками;
8. browser-check должен пройти все product tabs.

### 18.13.1 Execution status: e-commerce Product Workspace

Статус: production-deployed and browser-verified.

Что изменено:

1. первый экран товара переведен в e-commerce-style карточку:
   - media/gallery;
   - крупное название товара;
   - brand/SKU/category chips;
   - ключевые характеристики;
   - readiness по параметрам, медиа, каналам и связям;
   - actions для параметров, медиа, площадок и возврата к списку;
2. старый topbar с большим повтором названия уплотнен до compact SKU header;
3. category path больше не теряется при загрузке полной карточки:
   - summary read-model и product endpoint теперь merge-ятся;
   - `category_id`, `group_id`, `sku_gt`, `sku_pim` берутся из summary, если полный endpoint их не вернул;
4. `/catalog/nodes` в Product Workspace исправлен на актуальный shape `{ nodes: [...] }`;
5. добавлены системные token aliases `--line-rgb` и `--surface-rgb`, чтобы старые CSS-секции не получали invalid `rgba(var(...))`;
6. PIM-слои остались как рабочие sections:
   - параметры;
   - источники;
   - площадки;
   - конкуренты;
   - медиа;
   - валидация;
   - связи;
   - варианты;
   - preview нового create-flow.

Проверено:

1. `CI=1 npm run build` в `frontend` проходит;
2. production deploy проходит;
3. `global-pim.service` active;
4. `https://pim.id-smart.ru/api/health` возвращает `{"ok":true}`;
5. production `/products/product_70` открывается;
6. category path отображается как `Смартфоны / Apple / iPhone 16 / iPhone 16 Pro Max`;
7. production console errors на `/products/product_70`: `0`;
8. проверены sections:
   - overview;
   - attributes;
   - channels;
   - media;
9. light theme проверена через production screenshot;
10. dark theme проверена через production screenshot.

Оставшиеся риски для следующего slice:

1. кнопка `Сохранить` пока визуальная и не является новым полноценным edit flow;
2. create-flow пока preview внутри карточки, реальная страница `/products/new` должна быть заменена отдельным compact wizard по `18.14`;
3. связи/аналоги/сопутствующие требуют полноценного UX редактирования после wizard.

### 18.14 Product creation must become compact wizard

Текущая постановка для `/products/new`.

Проблема:

1. создание товара сейчас воспринимается как длинная и перегруженная форма;
2. пользователь не видит последовательность работы;
3. category/template/variants/params/sources смешиваются в один тяжелый экран;
4. после создания пользователь должен сразу попадать в новую карточку товара.

Новый обязательный принцип:

1. `/products/new` должен быть compact wizard, а не длинная форма;
2. шаги:
   - `01 База`;
   - `02 Категория`;
   - `03 Варианты`;
   - `04 Параметры`;
   - `05 Источники / конкуренты`;
   - `06 Preview + создать`;
3. каждый шаг должен помещаться в рабочий desktop viewport без необходимости сначала пролистывать декоративные блоки;
4. слева или сверху должен быть progress/stepper;
5. справа допустим compact preview создаваемого SKU;
6. preview перед созданием должен показывать:
   - название;
   - SKU;
   - категорию;
   - variant group;
   - заполненность параметров;
   - источники;
   - предупреждения;
7. после успешного создания route должен вести в `Product Workspace` нового товара.

Новый acceptance для `/products/new`:

1. создание товара ощущается как пошаговый сценарий, а не как простыня;
2. category selection не ломает layout;
3. variants не смешаны с основными данными;
4. параметры не показываются огромным списком до выбора категории/модели;
5. competitor/source enrichment подключается отдельным шагом;
6. финальный preview понятен до нажатия `Создать`;
7. browser-check должен пройти все wizard steps.

### 18.14.1 Execution status: Product Creation Wizard

Статус: production-deployed and browser-verified.

Что изменено:

1. `/products/new` заменен на compact desktop wizard вместо длинной формы;
2. структура wizard:
   - `01 База`;
   - `02 Варианты`;
   - `03 Источники`;
   - `04 Контент`;
   - `05 Связи`;
   - `06 Проверка`;
3. category может приходить из query string `category_id`, поэтому переход из каталога сразу открывает создание в нужной категории;
4. шаг `База` показывает только основное:
   - название;
   - категория;
   - тип товара `single` или `multi`;
   - compact preview;
5. шаг `Варианты` отделен от базовых данных и показывает SKU/family-логику отдельно;
6. источники, контент, связи и финальная проверка разведены по отдельным шагам;
7. competitor links больше не блокируют создание SKU: ссылки можно добавить позже в карточке товара;
8. после успешного создания route ведет в `Product Workspace` нового товара;
9. исправлен backend hot-path `/api/products/create`:
   - root cause: `create_product_service()` использовал `query_products_full()` без импорта после перехода на relational store;
   - исправление: `query_products_full` импортирован из `app.storage.relational_pim_store`;
   - без этого wizard получал plain-text `Internal Server Error`, а клиент показывал JSON parse error.

Universal / feature-level blocks:

1. wizard использует существующий app-shell и системные theme tokens;
2. form controls приведены к shared token styling через `pn-*` и system variables;
3. category picker, parameter picker и product picker не дублируются, а переиспользуются из текущего `ProductNewFeature`;
4. локальные стили допустимы только как feature-level layout для wizard, не как новый глобальный design-system primitive.

Проверено:

1. `python3 -m py_compile backend/app/core/products/service.py` проходит;
2. `CI=1 npm run build` в `frontend` проходит;
3. production deploy проходит;
4. `global-pim.service` active;
5. `https://pim.id-smart.ru/api/health` возвращает `{"ok":true}`;
6. production `/products/new?category_id=bb40de87-254b-4170-84d7-8e5d3925b251` открывается в compact wizard;
7. step rail и шаг `База` отображаются без старой длинной простыни;
8. сценарий `База -> Проверка -> Создать и открыть карточку` на проде создал SKU и открыл `/products/product_1088`;
9. новая карточка показала товар `Codex Test Product Wizard 20260426 D`, SKU GT `53422`, SKU PIM `1088`;
10. production console errors после успешного создания и открытия карточки: `0`;
11. dark theme для `/products/new` проверена на проде, console errors: `0`.

Оставшиеся риски:

1. старый JSX create-flow физически еще остается в файле как unreachable legacy block и должен быть удален при следующей чистке `ProductNewFeature`;
2. multi-variant сценарий требует отдельного browser-check после финализации UX variant-family;
3. источники/контент/связи в wizard сейчас компактно подготавливают создание SKU, но полноценное редактирование должно жить в `Product Workspace`;
4. category query был проверен на существующей категории `Смартфоны`; leaf-category сценарий нужно дополнительно пройти из нового `Catalog Workspace`.

---

## 19. Единый рабочий документ

Для этого трека основной рабочий документ только один:

- [`docs/smartpim-full-rebuild-master-plan.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/smartpim-full-rebuild-master-plan.md)

Все промежуточные redesign-документы этого трека удалены из активного контура и больше не используются.

---

## 20. Четвертый execution slice: Catalog Workspace

Ниже фиксируется четвертый исполняемый slice новой системы.

После завершения `Product Workspace` следующей страницей в redesign должен идти `Catalog Workspace`.

### 20.1 Роль страницы

`Catalog Workspace` — это чистая рабочая витрина структуры каталога и SKU, а не центр всех настроек PIM.

Это не:

- боковое дерево ради навигации;
- технический экран настроек;
- старая категория-страница с новой skin-оболочкой.
- экран диагностики полей, выгрузки, импорта и валидации.

Это:

- место, где пользователь работает со структурой каталога;
- место, где пользователь смотрит финальный список SKU выбранной категории;
- место, где пользователь перемещает SKU между категориями;
- место, где пользователь создает, переименовывает, сортирует и перемещает категории;
- исходный чистый контекст для перехода в отдельные рабочие страницы.

### 20.1.1 Clean Catalog Principle

Решение от 2026-04-26:

`/catalog` должен быть максимально чистым.

Каталог отвечает только за:

1. просмотр структуры категорий;
2. просмотр SKU внутри выбранной категории;
3. перемещение SKU между категориями;
4. создание, переименование, сортировку и перемещение категорий;
5. быстрый переход в карточку товара;
6. быстрый переход к созданию SKU в выбранной категории.

Каталог не должен быть местом для:

1. настройки полей товара;
2. настройки инфо-моделей;
3. сопоставления категорий с маркетплейсами;
4. диагностики выгрузки;
5. импорта Excel;
6. разбора ошибок импорта;
7. промежуточных статусов сопоставления;
8. валидации перед экспортом;
9. отображения всей грязи рабочего процесса.

Все это должно жить в отдельных рабочих страницах:

1. `Поля товара` / templates:
   - характеристики категории;
   - обязательные поля;
   - наследование;
   - шаблоны;
   - ошибки заполнения структуры.
2. `Выгрузка` / sources-mapping:
   - связка категорий SmartPim с площадками;
   - правила площадок;
   - marketplace requirements;
   - альтернативные значения;
   - статусы готовности к экспорту.
3. `Импорт`:
   - Excel;
   - источники;
   - ошибки;
   - промежуточные результаты;
   - сопоставления;
   - конфликтные значения.
4. `Качество / Валидация`:
   - незаполненные поля;
   - ошибки перед выгрузкой;
   - требования площадок;
   - очереди исправления.

Каталог должен показывать финальный рабочий слой, а не процесс подготовки.

### 20.2 Source / result

#### Source

Страница строится от:

1. `catalog_categories`
2. `products`
3. `info_models`
4. `category_channel_mapping`
5. derived category summaries

#### Result

Финальный результат работы на странице:

1. выбрана и отредактирована категория;
2. пользователь видит SKU выбранной категории;
3. пользователь может переместить SKU в другую категорию;
4. пользователь может перейти:
   - к карточке SKU;
   - к созданию SKU;
   - к чистому списку товаров;
   - к отдельным страницам настройки, если они нужны.

### 20.3 Тип страницы

Тип страницы:

- `Tree + Product Table + Minimal Actions`

### 20.4 Верхняя структура страницы

Базовая композиция:

1. compact `PageHeader`;
2. `TreeSidebar`;
3. `ProductTable`;
4. optional `ActionPanel` или contextual drawer.

Рабочий принцип:

1. слева всегда дерево категорий;
2. в центре всегда SKU выбранной категории;
3. справа только действия с выбранной категорией, если они не перегружают экран.

### 20.5 Детальная композиция страницы

#### Зона 1. Header

Содержит:

1. спокойный title;
2. короткий operational subtitle;
3. 1-3 primary actions.

#### Зона 2. Tree sidebar

Содержит:

1. поиск по категориям;
2. expand/collapse controls;
3. tree rows;
4. счетчик SKU;
5. быстрый переход к нужной категории.

Не содержит:

1. badges `Поля`;
2. badges `Выгрузка`;
3. технические readiness-индикаторы;
4. диагностику связанных процессов.

#### Зона 3. Main canvas

Показывает товары выбранной категории.

Внутри должны быть:

1. compact title выбранной категории;
2. счетчик SKU;
3. поиск по товарам;
4. фильтры товаров:
   - все;
   - проблемные;
   - без фото;
   - без группы;
5. таблица SKU;
6. действия:
   - открыть товар;
   - добавить SKU;
   - переместить SKU;
   - массово переместить выбранные SKU.

Не содержит:

1. tabs `Поля товара`;
2. tabs `Выгрузка`;
3. tabs `Импорт`;
4. tabs `История`;
5. summary readiness;
6. blocks про модели/площадки.

#### Зона 4. Action panel / drawer

Если правая панель остается, она показывает только:

1. выбранную категорию;
2. количество SKU;
3. количество подкатегорий;
4. actions:
   - создать подкатегорию;
   - переименовать;
   - удалить ветку;
   - перейти к настройке полей;
   - перейти к настройке выгрузки.

Правило:

1. actions `перейти к настройке полей` и `перейти к настройке выгрузки` допустимы как ссылки;
2. сами настройки и статусы не показываются внутри каталога.

### 20.6 Universal / feature / individual split

#### Universal blocks

1. `PageHeader`
2. `ActionBar`
3. `TreeSidebar`
4. `TreeToolbar`
5. `TreeRow`
6. `SearchBar`
7. `WorkspaceCanvas`
8. `Inspector`
9. `StatusBadge`
10. `MetricTile`
11. `EmptyState`
12. `ErrorState`
13. `Skeleton`

#### Feature-level blocks

1. `CatalogTreePanel`
2. `CatalogCategorySummary`
3. `CatalogCategoryInspector`
4. `CatalogCategoryActions`
5. `CatalogCategoryLinks`

#### Individual blocks

Допускаются только для orchestration-уровня:

1. `CatalogWorkspaceLayout`

### 20.7 Табы и nested states, которые нельзя пропускать

В clean catalog tab-структура внутри `/catalog` не нужна.

Запрещенные tabs внутри `/catalog`:

1. `Поля товара`;
2. `Выгрузка`;
3. `Импорт`;
4. `История`;
5. `Обзор`.

Если в будущем у `Catalog Workspace` появятся:

1. внутренние табы;
2. drawers;
3. modals;
4. alternate modes;
5. selection states;

они обязаны быть перечислены в документе перед implementation и проверены после implementation.

Нельзя завершать `Catalog Workspace`, пока не проверены:

1. tree search;
2. expand/collapse;
3. empty category state;
4. category with model;
5. category without model;
6. category with channel bindings;
7. category without channel bindings;
8. переходы в связанные workflows.

### 20.8 Layout rules

1. дерево должно оставаться рабочим и читаемым;
2. canvas должен быть главным рабочим полем, а не декоративным summary;
3. inspector не должен забирать слишком много ширины;
4. работа с категорией должна начинаться без giant intro;
5. tree, canvas и inspector должны образовывать один устойчивый workspace.

### 20.9 Motion rules

1. tree interactions должны быть быстрыми и стабильными;
2. смена категории должна ощущаться как смена рабочего контекста, а не полный перерендер хаоса;
3. inspector должен открываться мягко;
4. hover/active по tree rows должны быть заметными, но не шумными.

### 20.10 Acceptance checklist

Перед тем как считать `Catalog Workspace` завершенным, обязательно проверить:

1. дерево стабильно работает;
2. длинные названия категорий не ломают layout;
3. все category states читаемы;
4. переходы в связанные flows понятны, но не перегружают catalog screen;
5. inspector не конфликтует с canvas;
6. light/dark обе читаемы;
7. нет выпадающих текстов, налезаний, схлопываний;
8. browser-check сделан по всем основным category states.

### 20.11 Definition of done

`Catalog Workspace` считается завершенным только если:

1. это реально новый category workspace;
2. он не ощущается как старое дерево с новыми цветами;
3. tree/canvas/inspector работают как единая система;
4. все tab/nested states проверены;
5. browser-verified;
6. после завершения обновлен этот master-документ;
7. только после этого можно переходить к `Info Model Workspace`.

### 20.12 Reopened status after visual review

Статус: first rework pass completed, browser-verified, accepted for moving to next reopened slice.

Причина:

1. visual review 2026-04-26 показал, что текущий `/catalog` не соответствует ожидаемому уровню PIM/SaaS-продукта;
2. экран выглядит как набор тяжелых внутренних панелей, а не как рабочий каталог;
3. центральная область дублирует summary категории и не дает пользователю сразу работать с товарами;
4. дерево категорий выглядит технически и перегружено бейджами;
5. inspector справа слишком тяжелый и конкурирует с основным рабочим полем;
6. текущий дизайн нельзя считать завершенным только потому, что функционал стал лучше.

Новый визуальный ориентир:

1. брать за основу не текущую внутреннюю стилизацию, а зрелые PIM/SaaS-паттерны уровня:
   - `Brandquad`;
   - `PIM Cloud`;
   - аналогичные enterprise PIM/product-data platforms;
2. визуальная цель:
   - спокойная enterprise-плотность;
   - читабельные таблицы и списки;
   - меньше декоративных cards;
   - больше рабочей поверхности;
   - понятные primary actions;
   - легкий inspector;
   - строгие sticky-зоны;
   - clear hover/focus/selected states;
3. `Product Workspace` остается позитивным reference внутри нашего продукта:
   - карточка товара уже кратно ближе к нужному уровню;
   - нужно доработать мелочи, но не ломать текущую основу;
   - тяжелые страницы должны подтягиваться к этому уровню качества.

Новая структура `/catalog`:

1. page header должен быть компактным:
   - без кричащего hero;
   - без больших dashboard-плашек;
   - только path/title/search/actions;
2. левая колонка:
   - компактное дерево;
   - поиск;
   - фильтры `Все`, `С товарами`, `Без модели`, `Без каналов`;
   - аккуратные статусы без визуального шума;
   - sticky внутри viewport;
3. центральная колонка:
   - сразу рабочая зона товаров выбранной категории;
   - tabs или segmented control:
     - `Товары`;
     - `Инфо-модель`;
     - `Каналы`;
     - `Импорт`;
     - `История`;
   - `Товары` должен быть default tab;
   - empty-state должен объяснять следующий шаг, а не показывать декоративный summary;
4. правая колонка:
   - lightweight inspector;
   - максимум 280-320px;
   - контекст, readiness, быстрые действия;
   - без дублирования центрального контента;
5. все тяжелые summaries переносить:
   - либо в inspector;
   - либо в tab `Обзор`, если он реально нужен;
   - не above the fold вместо работы.

### 20.12.1 Execution status: Catalog Workspace Rework

Дата: 2026-04-26.

Что сделано:

1. `/catalog` перестроен от рабочего сценария, а не от summary-dashboard;
2. default рабочая область стала `Товары`;
3. product list встроен в selected-category workspace через reusable `ProductRegistry`;
4. дерево категорий получило рабочие фильтры:
   - `Все`;
   - `С товарами`;
   - `Без модели`;
   - `Без каналов`;
5. counts товаров в дереве берутся из `/catalog/products/counts`;
6. верхние декоративные summary cards убраны из основного потока;
7. selected category header стал компактным;
8. tabs `Товары`, `Инфо-модель`, `Каналы`, `Импорт`, `История` стали основой страницы;
9. right inspector оставлен легким и контекстным;
10. production deploy выполнен;
11. `@browser-use` проверка на `https://pim.id-smart.ru/catalog` прошла:
    - login/session работает;
    - counts в дереве отображаются;
    - tabs переключаются;
    - список товаров выбранной категории загружается;
    - console errors отсутствуют.

Статус после решения `Clean Catalog`:

1. этот first-pass больше не считается финальным направлением для `/catalog`;
2. tabs `Поля товара`, `Выгрузка`, `Импорт`, `История` должны быть вынесены из catalog screen;
3. badges `Поля` и `Выгрузка` должны быть убраны из tree;
4. right inspector должен быть упрощен до action panel или drawer;
5. catalog должен остаться только про структуру и SKU.

Ограничение проверки:

1. screenshot capture через Browser Use в текущей сессии timeout-ился на CDP `Page.captureScreenshot`;
2. вместо screenshot использованы live DOM snapshot, клики/переходы и console logs;
3. визуальный human-review все равно обязателен перед окончательным закрытием всего redesign-трека.

Новые обязательные задачи для `/catalog`:

1. убрать текущий большой summary canvas;
2. сделать `Товары` главным рабочим состоянием;
3. встроенный `ProductRegistry` привести к компактному category-scoped виду;
4. добавить readable empty-state для пустой категории;
5. добавить category filters в tree;
6. переработать tree row visual hierarchy;
7. упростить inspector;
8. проверить category root, leaf, empty, with-products, with-model, without-model, with-channel, without-channel;
9. проверить создание подкатегории, переименование, импорт Excel modal, delete confirmation;
10. проверить light/dark через `@browser-use`;
11. закрыть Playwright-процессы после работы, если Playwright использовался как fallback.

---

## 21. Пятый execution slice: Info Model Workspace

Ниже фиксируется пятый исполняемый slice новой системы.

После завершения `Catalog Workspace` следующей страницей в redesign должен идти `Info Model Workspace`.

### 21.1 Роль страницы

`Info Model Workspace` — это рабочая среда проектирования структуры товарных данных.

Это не:

- список полей в таблице ради таблицы;
- технический экран настроек;
- старый template-editor с новой skin-оболочкой.

Это:

- место, где проектируется структура инфо-модели;
- место, где определяются поля, группы, обязательность, типы значений;
- связующий контур между категориями, товарами и каналами.

### 21.2 Source / result

#### Source

Страница строится от:

1. `info_models`
2. attribute/meta layer
3. `catalog_categories`
4. `info_model_channel_mapping`
5. derived summaries использования модели

#### Result

Финальный результат работы на странице:

1. инфо-модель структурирована;
2. поля и группы приведены в рабочий вид;
3. обязательность и типы значений зафиксированы;
4. модель связана с категориями и каналами;
5. пользователь может перейти:
   - к категориям;
   - к товарам по модели;
   - к channel mapping.

### 21.3 Тип страницы

Тип страницы:

- `Tree + Canvas + Inspector`

### 21.4 Верхняя структура страницы

Базовая композиция:

1. `PageHeader`
2. `ModelSidebar`
3. `Canvas`
4. `Inspector`

Рабочий принцип:

1. слева список/дерево моделей или групп полей;
2. в центре рабочий canvas модели;
3. справа contextual inspector.

### 21.5 Детальная композиция страницы

#### Зона 1. Header

Содержит:

1. спокойный title;
2. короткий subtitle;
3. 1-3 primary actions.

Примеры primary actions:

1. создать модель;
2. создать поле;
3. связать с категорией.

#### Зона 2. Sidebar

Содержит:

1. поиск по моделям;
2. список моделей;
3. grouping по типу/статусу;
4. быстрый переход к нужной модели;
5. при необходимости режим просмотра структуры выбранной модели.

#### Зона 3. Main canvas

Показывает выбранную модель как рабочий объект.

Внутри должны быть:

1. summary модели;
2. группы полей;
3. список атрибутов;
4. обязательные поля;
5. типы значений;
6. связка с категориями;
7. связка с каналами;
8. quick actions для добавления/перемещения/редактирования полей.

#### Зона 4. Inspector

Показывает:

1. мета модели;
2. использование модели;
3. количество категорий и товаров на модели;
4. channel-related context;
5. contextual actions по выбранному полю или группе.

### 21.6 Табы и nested states, которые нельзя пропускать

Если у `Info Model Workspace` будут:

1. табы;
2. drawers;
3. модальные формы;
4. alternate editing modes;
5. selected field / selected group states;

они обязаны быть перечислены перед implementation и проверены после implementation.

Минимальный обязательный набор состояний:

1. пустая модель;
2. модель с одной группой;
3. модель с несколькими группами;
4. обязательное поле;
5. необязательное поле;
6. enum/dictionary field;
7. числовое поле;
8. привязанная к категории модель;
9. модель без category binding;
10. модель с channel mapping;
11. модель без channel mapping.

### 21.7 Universal / feature / individual split

#### Universal blocks

1. `PageHeader`
2. `ActionBar`
3. `SearchBar`
4. `TreeSidebar`
5. `TreeRow`
6. `WorkspaceCanvas`
7. `Inspector`
8. `SectionList`
9. `FieldRow`
10. `StatusBadge`
11. `TypeBadge`
12. `EmptyState`
13. `ErrorState`
14. `Skeleton`
15. `Modal`
16. `Drawer`
17. `HorizontalScroller`

#### Feature-level blocks

1. `InfoModelSidebar`
2. `InfoModelSummary`
3. `InfoModelGroups`
4. `InfoModelFields`
5. `InfoModelBindings`
6. `InfoModelInspector`
7. `InfoModelFieldEditor`
8. `InfoModelGroupEditor`

#### Individual blocks

Допускаются только для orchestration-уровня:

1. `InfoModelWorkspaceLayout`

### 21.8 Layout rules

1. workspace должен начинаться сразу с рабочей зоны;
2. модель не должна тонуть в декоративной шапке;
3. главный акцент — на структуре полей и групп;
4. inspector не должен быть визуально тяжелее canvas;
5. частые действия должны быть близко к рабочей структуре, а не спрятаны глубоко;
6. длинные списки полей должны поддерживать устойчивый scroll contract.

### 21.9 Motion rules

1. добавление/редактирование полей должно ощущаться быстрым и точным;
2. раскрытие групп должно быть мягким и предсказуемым;
3. выбор поля или группы должен явно читаться;
4. motion не должен мешать плотной настройке модели.

### 21.10 Acceptance checklist

Перед тем как считать `Info Model Workspace` завершенным, обязательно проверить:

1. структура модели читается быстро;
2. группы и поля не ломают layout;
3. длинные названия не выпадают;
4. drawers/modals/редакторы полей работают корректно;
5. sidebar, canvas и inspector образуют один устойчивый workspace;
6. light/dark обе читаемы;
7. browser-check сделан по всем основным states модели;
8. ни один tab/nested state не пропущен.

### 21.11 Definition of done

`Info Model Workspace` считается завершенным только если:

1. он стал реальным workspace проектирования модели;
2. не ощущается как старая template-page с новой skin-оболочкой;
3. все states модели проверены;
4. browser-verified;
5. после завершения обновлен этот master-документ;
6. только после этого можно переходить к `Channel Mapping Workspace`.

### 21.12 Visual correction: Info Model Catalog

Дата: 2026-04-27.

Причина возврата:

1. production screenshot показал, что `/templates` визуально сломан:
   - oversized hero-заголовок в центральном canvas;
   - KPI карточки налезают на текст;
   - рабочая зона ощущается как декоративный poster, а не как инструмент настройки полей;
   - длинные lock/status тексты в дереве раздувают строки.

Исправлено:

1. центральный hero `Info Model Workspace` заменен на compact summary header `Поля товара`;
2. статус модели вынесен в отдельную state-card внутри нормальной grid-структуры;
3. KPI `Всего полей / Обязательных / Подтверждено` вынесены в отдельную строку под summary, без абсолютных наложений;
4. type scale уменьшен: заголовок модели больше не занимает половину canvas;
5. tree rows уплотнены, длинные названия и lock reason обрезаются через ellipsis / line-clamp;
6. workspace grid для `/templates` зафиксирован как `sidebar / canvas / inspector` на wide desktop и безопасно складывается на меньшей ширине.

Verification:

1. `npm run build` во frontend прошел;
2. production deploy прошел, `global-pim.service` active, `/api/health` вернул `{"ok":true}`;
3. browser-use verification на `https://pim.id-smart.ru/templates` подтвердил:
   - заголовок и KPI больше не перекрываются;
   - выбранная категория `Аксессуары` читается;
   - дерево моделей не разваливает левую колонку;
   - центральный canvas начинается с рабочего summary, а не с гигантского hero.

### 21.13 Visual correction: Info Model Editor

Дата: 2026-04-27.

Причина возврата:

1. production URL `/templates/b2f026d9-a3e2-4821-9034-d17ac1b65065?tab=base` был непонятен даже владельцу продукта:
   - слишком широкая простыня из формы и таблицы;
   - заголовок, метрики, название модели и список полей дублировали друг друга;
   - sidebar и inspector повторяли один и тот же context;
   - системные поля выглядели как редактируемые, хотя почти все controls disabled;
   - не было понятного ответа “что здесь делать”.

Исправлено:

1. header editor переписан на конкретный смысл `Настройка полей товара`;
2. центральный oversized `Info Model Editor` заменен на компактную карточку `Поля товара`;
3. метрики сведены к рабочим счетчикам `Всего / Обяз. / Категория`;
4. блок `Название модели` оставлен рядом с summary, а не отдельной разорванной строкой;
5. второй набор метрик перед таблицей удален;
6. sidebar стал навигацией модели:
   - категория;
   - режим;
   - tabs `Все / Основа / Категория`;
   - быстрые переходы;
7. duplicate selected-field card в sidebar удален, потому что selected field уже живет в inspector;
8. attr board получил bounded scroll area и sticky table header;
9. строки атрибутов уплотнены, колонки приведены к стабильной сетке;
10. full-width editor grid зафиксирован как `navigation / field workbench / inspector`.

Verification:

1. `npm run build` во frontend прошел;
2. production deploy прошел, `global-pim.service` active, `/api/health` вернул `{"ok":true}`;
3. browser-use verification на конкретном URL подтвердила:
   - текст header стал понятнее;
   - sidebar больше не дублирует selected-field context;
   - центральный editor начинается с компактного summary;
   - список полей отображается как рабочий список, а не как набор несвязанных cards.

Оставшийся продуктовый долг:

1. текущая модель все еще показывает системные поля как disabled form controls;
2. следующий шаг должен разделить:
   - locked system fields как read-only reference rows;
   - editable category fields как настоящий конструктор;
   - groups/sections модели как отдельный уровень структуры;
3. это уже не “подкрутить CSS”, а отдельный UX slice `Info Model Field Builder`;
4. после продуктового решения от 2026-04-27 этот slice должен строиться не как ручной editor-first flow, а как `draft из источников -> модерация -> утверждение`.

### 21.14 Product correction: Draft-first Info Model Workflow

Дата: 2026-04-27.

Принятое решение:

1. основной сценарий создания инфо-модели — `draft из источников -> модерация -> утверждение`;
2. ручное создание модели остается запасным режимом;
3. источники draft:
   - Я.Маркет;
   - Ozon;
   - Excel/import;
   - competitors `re-store` и `store77`;
   - уже существующие товары выбранной категории;
   - похожие или наследуемые категории;
4. каждый предложенный параметр должен показывать provenance:
   - источник;
   - исходное имя;
   - пример значения;
   - частотность;
   - confidence;
   - предложенную группу;
   - предложенный тип;
5. `/sources` не создает базовую модель, а работает только как mapping-layer:
   - category mapping;
   - parameter mapping;
   - value mapping;
   - competitor candidates;
6. карточка товара использует утвержденную модель, показывает trace значений и readiness, но не редактирует структуру инфо-модели.

Обязательная state machine для `/templates/:categoryId`:

1. `none` — модели нет, главное действие `Собрать draft-модель`;
2. `collecting` — система собирает источники и строит кандидатов;
3. `draft` — пользователь модерирует группы и параметры;
4. `review` — модель готова к утверждению;
5. `approved` — модель утверждена и используется товарами;
6. `needs_update` — появились новые источники или параметры, которые требуют пересмотра.

Новый implementation scope для следующего прохода по `Info Model Workspace`:

1. сделать state screens `none / draft / approved`;
2. добавить действие `Собрать draft-модель`;
3. заменить длинные disabled forms на draft moderation layout;
4. разделить:
   - source candidates;
   - editable PIM fields;
   - locked system/reference fields;
   - groups/sections;
5. добавить source/provenance panel для выбранного параметра;
6. в `/sources` показать понятный empty state, если у категории нет модели;
7. после browser-use проверки обновить этот master-plan.

Implementation status:

1. backend adapter `/api/info-models/draft-from-sources` added;
2. draft metadata is stored under `template.meta.info_model`;
3. relational storage now persists `template.meta` through `templates*_rel.meta_json`;
4. lightweight DB migration runs even when schema bootstrap marker already exists;
5. `/templates/:categoryId` can collect draft from real product data and keep `draft` state after reload;
6. `/sources` is guarded so mapping does not pretend to create models;
7. browser-use production check completed on `Oura Ring 4`;
8. verified production behavior: `Draft на модерации` is shown, false `Утверждена` fallback is fixed.
9. marketplace source collectors added for Я.Маркет and Ozon category requirements;
10. draft generation resolves nearest ancestor category mapping when the current leaf category has no direct mapping.

Production check on `Oura Ring 4`:

1. direct category mapping is absent on `Oura Ring 4`;
2. nearest ancestor mapping is resolved from `Умные кольца`;
3. draft generation returns 60 marketplace candidates;
4. UI shows marketplace parameters in `Draft из источников`;
5. approval button is enabled once candidates exist.

Remaining source gap:

1. existing attribute mapping rows are not yet merged as first-class draft candidates;
2. competitor-derived parameters are not yet merged as draft candidates;
3. product feature extraction depends on `content.features`; imported products without normalized features still rely on marketplace sources.

Документированный spec:

- [`docs/superpowers/specs/2026-04-27-info-model-draft-workflow-design.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/superpowers/specs/2026-04-27-info-model-draft-workflow-design.md)

Implementation plan:

- [`docs/superpowers/plans/2026-04-27-info-model-draft-real-data.md`](/Users/maksimkiselev/Desktop/Global%20PIM/docs/superpowers/plans/2026-04-27-info-model-draft-real-data.md)

---

## 22. Шестой execution slice: Channel Mapping Workspace

Ниже фиксируется шестой исполняемый slice новой системы.

После завершения `Info Model Workspace` следующей страницей в redesign должен идти `Channel Mapping Workspace`.

### 22.1 Роль страницы

`Channel Mapping Workspace` — это рабочая среда сопоставления внутренних сущностей PIM с требованиями канала.

Это не:

- просто технический экран “маппинга полей”;
- dump channel-параметров;
- старая mapping-page с новой skin-оболочкой.

Это:

- место, где соединяются:
  - категории каталога;
  - инфо-модели;
  - категории каналов;
  - параметры каналов;
  - readiness и validation;
- место, где пользователь доводит модель и категорию до состояния пригодности для публикации в конкретном канале.

### 22.2 Source / result

#### Source

Страница строится от:

1. `catalog_categories`
2. `info_models`
3. `channels`
4. `category_channel_mapping`
5. `info_model_channel_mapping`
6. channel metadata / required fields
7. derived readiness summaries

#### Result

Финальный результат работы на странице:

1. категория каталога сопоставлена с категорией канала;
2. параметры инфо-модели сопоставлены с параметрами канала;
3. пользователь понимает:
   - какие поля покрыты;
   - какие поля не покрыты;
   - какие поля обязательны;
   - что блокирует readiness;
4. пользователь может перейти:
   - к категории;
   - к инфо-модели;
   - к товарам в этом контексте;
   - к channel readiness / export.

### 22.3 Тип страницы

Тип страницы:

- `Tree + Canvas + Inspector`

### 22.4 Верхняя структура страницы

Базовая композиция:

1. `PageHeader`
2. `ContextSidebar`
3. `MappingCanvas`
4. `Inspector`

Рабочий принцип:

1. слева выбирается контекст:
   - категория;
   - канал;
   - при необходимости модель;
2. в центре живет рабочий mapping canvas;
3. справа inspector со status/readiness/warnings.

### 22.5 Детальная композиция страницы

#### Зона 1. Header

Содержит:

1. спокойный title;
2. короткий operational subtitle;
3. 1-3 primary actions.

Примеры primary actions:

1. сохранить mapping;
2. открыть категорию канала;
3. открыть проблемные поля.

#### Зона 2. Context sidebar

Содержит:

1. выбор канала;
2. дерево категорий или список контекстов;
3. индикаторы:
   - есть ли category mapping;
   - есть ли parameter mapping;
   - есть ли unresolved required fields;
4. быстрый переход между контекстами.

#### Зона 3. Mapping canvas

Главная рабочая зона.

Внутри должны быть:

1. summary выбранного контекста;
2. category mapping block;
3. parameter mapping block;
4. required fields block;
5. missing/unmapped block;
6. quick actions для:
   - auto-map;
   - review missing;
   - review conflicts.

#### Зона 4. Inspector

Показывает:

1. readiness summary;
2. unresolved blockers;
3. warnings;
4. channel-specific notes;
5. contextual actions.

### 22.6 Табы и nested states, которые нельзя пропускать

Если у `Channel Mapping Workspace` будут:

1. табы по каналам;
2. alternate modes;
3. drawers;
4. modals;
5. mapping detail panels;
6. auto-map preview states;

они обязаны быть перечислены перед implementation и проверены после implementation.

Минимальный обязательный набор состояний:

1. категория без channel mapping;
2. категория с channel mapping;
3. модель без parameter mapping;
4. модель с частичным mapping;
5. модель с полным mapping;
6. required fields missing;
7. auto-map результат;
8. conflict state;
9. clean/ready state.

### 22.7 Universal / feature / individual split

#### Universal blocks

1. `PageHeader`
2. `ActionBar`
3. `SearchBar`
4. `TreeSidebar`
5. `ContextSelector`
6. `WorkspaceCanvas`
7. `Inspector`
8. `StatusBadge`
9. `ReadinessBadge`
10. `FieldMappingRow`
11. `RequiredFieldList`
12. `WarningList`
13. `EmptyState`
14. `ErrorState`
15. `Skeleton`
16. `Modal`
17. `Drawer`
18. `HorizontalScroller`

#### Feature-level blocks

1. `ChannelMappingSidebar`
2. `CategoryChannelMappingBlock`
3. `ParameterMappingBlock`
4. `RequiredFieldsBlock`
5. `MappingIssuesBlock`
6. `ChannelMappingInspector`
7. `AutoMapPreview`

#### Individual blocks

Допускаются только для orchestration-уровня:

1. `ChannelMappingWorkspaceLayout`

### 22.8 Layout rules

1. рабочая зона должна начинаться сразу;
2. mapping должен быть главным визуальным содержимым, а не только summary;
3. missing/required/problem states должны быть видны сразу;
4. inspector не должен затмевать canvas;
5. длинные mapping-списки должны иметь устойчивый scroll contract;
6. category context и channel context должны читаться без путаницы.

### 22.9 Motion rules

1. переход между контекстами должен быть быстрым и понятным;
2. auto-map preview должен появляться мягко и читабельно;
3. warnings/missing states должны выделяться ясно, но не шумно;
4. motion не должен мешать сравнению полей.

### 22.10 Acceptance checklist

Перед тем как считать `Channel Mapping Workspace` завершенным, обязательно проверить:

1. category context работает стабильно;
2. channel switching не ломает layout;
3. partial/full/empty mapping states читаемы;
4. required fields и missing fields видны сразу;
5. длинные mapping lists не ломают страницу;
6. drawers/modals/auto-map preview работают корректно;
7. light/dark обе читаемы;
8. browser-check сделан по всем основным mapping states;
9. ни один tab/nested state не пропущен.

### 22.11 Definition of done

`Channel Mapping Workspace` считается завершенным только если:

1. он стал реальным рабочим mapping-контуром;
2. не ощущается как техническая таблица с полями;
3. category/channel/model контекст собраны в одну систему;
4. все основные states проверены;
5. browser-verified;
6. после завершения обновлен этот master-документ;
7. только после этого можно переходить к `Sources / Import`.

---

## 23. Седьмой execution slice: Sources / Import

Ниже фиксируется седьмой исполняемый slice новой системы.

После завершения `Channel Mapping Workspace` следующей страницей в redesign должен идти `Sources / Import`.

### 23.1 Роль страницы

`Sources / Import` — это рабочая среда загрузки, enrichment и происхождения данных товара.

Это не:

- технический экран загрузки файла;
- набор разрозненных import-форм;
- старый sources-screen с новой skin-оболочкой.

Это:

- контур, через который данные попадают в товар;
- контур, где пользователь понимает происхождение значений;
- контур, где видно:
  - что импортировано;
  - что обновлено;
  - что отклонено;
  - что требует ручного вмешательства.

### 23.2 Source / result

#### Source

Страница строится от:

1. `imports`
2. source jobs / source connectors
3. `products`
4. `product_values`
5. enrichment/read-model summaries

#### Result

Финальный результат работы на странице:

1. данные загружены или обновлены;
2. пользователь понимает происхождение данных;
3. пользователь может перейти:
   - к конкретному товару;
   - к проблемной записи импорта;
   - к источнику;
   - к результатам enrichment.

### 23.3 Тип страницы

Основной тип:

- гибрид `List + Inspector` и `Editor`

Практически это означает:

1. список операций / источников;
2. detail area выбранной операции;
3. inspector со статусом и последствиями.

### 23.4 Верхняя структура страницы

Базовая композиция:

1. `PageHeader`
2. `SourceList / ImportList`
3. `OperationCanvas`
4. `Inspector`

### 23.5 Детальная композиция страницы

#### Зона 1. Header

Содержит:

1. спокойный title;
2. subtitle по текущему operational контексту;
3. primary actions.

Примеры primary actions:

1. новый импорт;
2. загрузить Excel;
3. запустить enrichment;
4. открыть проблемные загрузки.

#### Зона 2. Source/operation list

Содержит:

1. список источников или jobs;
2. поиск;
3. фильтры:
   - status;
   - source type;
   - date;
   - errors only;
4. быстрый выбор конкретной операции.

#### Зона 3. Operation canvas

Показывает выбранную операцию или источник как рабочий объект.

Внутри должны быть:

1. summary операции;
2. affected products;
3. updated fields;
4. skipped/rejected items;
5. conflict resolution area;
6. links в товар или товары.

#### Зона 4. Inspector

Показывает:

1. статус операции;
2. ошибки и предупреждения;
3. source metadata;
4. статистику по изменениям;
5. contextual actions.

### 23.6 Табы и nested states, которые нельзя пропускать

Если у `Sources / Import` будут:

1. разные типы импортов;
2. wizard steps;
3. preview states;
4. conflict resolution states;
5. success/error detail states;
6. nested drawers/modals;

они обязаны быть перечислены перед implementation и проверены после implementation.

Минимальный обязательный набор состояний:

1. пустой import list;
2. успешная операция;
3. частично успешная операция;
4. failed operation;
5. preview перед импортом;
6. conflict resolution;
7. links в affected products;
8. manual override после импорта.

### 23.7 Universal / feature / individual split

#### Universal blocks

1. `PageHeader`
2. `ActionBar`
3. `SearchBar`
4. `FilterBar`
5. `DataList`
6. `DataTable`
7. `Inspector`
8. `StatusBadge`
9. `WarningList`
10. `PreviewTable`
11. `ConflictList`
12. `EmptyState`
13. `ErrorState`
14. `Skeleton`
15. `Modal`
16. `Drawer`
17. `HorizontalScroller`

#### Feature-level blocks

1. `ImportOperationsList`
2. `ImportOperationSummary`
3. `ImportPreviewBlock`
4. `ImportConflictsBlock`
5. `ImportAffectedProductsBlock`
6. `SourceInspector`
7. `ExcelImportFlow`
8. `EnrichmentRunBlock`

#### Individual blocks

Допускаются только для orchestration-уровня:

1. `SourcesImportWorkspaceLayout`

### 23.8 Layout rules

1. пользователь должен быстро понимать статус операции;
2. список операций не должен превращаться в бесполезный лог;
3. preview/conflicts должны быть рабочими, а не декоративными;
4. affected products должны быть доступны без лишних переходов;
5. длинные preview tables обязаны иметь horizontal scroll contract;
6. problem states должны быть видны сразу.

### 23.9 Motion rules

1. preview и conflict states должны появляться мягко и ясно;
2. статусные изменения jobs должны быть заметными;
3. motion не должен мешать чтению diff/preview таблиц.

### 23.10 Acceptance checklist

Перед тем как считать `Sources / Import` завершенным, обязательно проверить:

1. все основные source/import states покрыты;
2. preview не ломает layout;
3. conflict resolution читаем;
4. affected product links работают;
5. длинные import tables не ломают страницу;
6. light/dark обе читаемы;
7. browser-check сделан по всем основным operation states;
8. ни один tab/nested state не пропущен.

### 23.11 Definition of done

`Sources / Import` считается завершенным только если:

1. это реальный operational import/enrichment workspace;
2. пользователь понимает источник и результат изменений;
3. все ключевые states операций покрыты;
4. browser-verified;
5. после завершения обновлен этот master-документ;
6. только после этого можно переходить к `Organizations / Admin`.

---

## 24. Восьмой execution slice: Organizations / Admin

Ниже фиксируется восьмой исполняемый slice новой системы.

После завершения `Sources / Import` следующей страницей в redesign должен идти `Organizations / Admin`.

### 24.1 Роль страницы

`Organizations / Admin` — это рабочий административный контур организации и платформы.

Это не:

- случайный набор таблиц про пользователей;
- техническая админка;
- вторичный экран без общего product-contract.

Это:

- контур управления организацией;
- контур доступа, ролей и инвайтов;
- platform-level контур для developer/admin visibility.

### 24.2 Source / result

#### Source

Страница строится от:

1. `organizations`
2. `users`
3. `organization_members`
4. invites
5. platform roles
6. channel connections / org-level state

#### Result

Финальный результат работы на странице:

1. организация настроена;
2. пользователи и роли управляются;
3. инвайты управляются;
4. developer/admin видит platform-level контекст;
5. пользователь может перейти:
   - к организации;
   - к сотруднику;
   - к инвайту;
   - к настройкам организации;
   - к платформенным действиям.

### 24.3 Тип страницы

Тип страницы:

- `List + Inspector`

### 24.4 Верхняя структура страницы

Базовая композиция:

1. `PageHeader`
2. `EntityList / Table`
3. `Inspector`

Внутри administrative flow могут быть отдельные modes:

1. организации;
2. сотрудники;
3. приглашения;
4. platform view.

### 24.5 Детальная композиция страницы

#### Зона 1. Header

Содержит:

1. спокойный title;
2. subtitle по текущему admin-контексту;
3. primary actions.

Примеры primary actions:

1. пригласить пользователя;
2. создать организацию;
3. открыть platform view;
4. сменить контекст организации.

#### Зона 2. Main list/table

Содержит:

1. поиск;
2. фильтры;
3. entity table/list;
4. status badges;
5. role/status columns;
6. pagination при необходимости.

#### Зона 3. Inspector

Показывает:

1. summary выбранной сущности;
2. роли/статусы;
3. invite details;
4. organization metadata;
5. contextual actions.

### 24.6 Табы и nested states, которые нельзя пропускать

Если у `Organizations / Admin` будут:

1. режимы организаций/сотрудников/инвайтов/platform;
2. drawers/modals;
3. invite accept/manage flows;
4. role change states;
5. revoke/resend actions;

они обязаны быть перечислены перед implementation и проверены после implementation.

Минимальный обязательный набор состояний:

1. список организаций;
2. список сотрудников;
3. список инвайтов;
4. пустой state;
5. pending invite;
6. accepted invite;
7. revoked invite;
8. owner/member/developer/admin role views;
9. organization switch flow.

### 24.7 Universal / feature / individual split

#### Universal blocks

1. `PageHeader`
2. `SearchBar`
3. `FilterBar`
4. `SegmentedSwitch`
5. `DataTable`
6. `DataList`
7. `Inspector`
8. `StatusBadge`
9. `RoleBadge`
10. `EmptyState`
11. `ErrorState`
12. `Skeleton`
13. `Modal`
14. `Drawer`
15. `Pagination`
16. `HorizontalScroller`

#### Feature-level blocks

1. `OrganizationsList`
2. `MembersList`
3. `InvitesList`
4. `OrganizationInspector`
5. `MemberInspector`
6. `InviteInspector`
7. `InviteFlow`
8. `RoleChangePanel`
9. `PlatformAdminPanel`

#### Individual blocks

Допускаются только для orchestration-уровня:

1. `OrganizationsAdminWorkspaceLayout`

### 24.8 Layout rules

1. admin-контур должен быть плотным, но не тяжелым;
2. главная сущность режима должна читаться сразу;
3. role/invite/actions не должны быть размазаны по разным углам страницы;
4. inspector должен ускорять действия, а не дублировать таблицу;
5. длинные таблицы обязаны иметь horizontal scroll contract;
6. platform mode не должен ломать organization mode.

### 24.9 Motion rules

1. переключение режимов должно быть быстрым и ясным;
2. invite/role actions должны иметь понятный feedback;
3. inspector и modals должны открываться мягко, но без тормозов.

### 24.10 Acceptance checklist

Перед тем как считать `Organizations / Admin` завершенным, обязательно проверить:

1. все admin modes покрыты;
2. список организаций читаем;
3. список сотрудников читаем;
4. список инвайтов читаем;
5. role/invite states не ломают layout;
6. organization switch flow не ломает страницу;
7. light/dark обе читаемы;
8. browser-check сделан по всем основным admin states;
9. ни один tab/nested state не пропущен.

### 24.11 Definition of done

`Organizations / Admin` считается завершенным только если:

1. это полноценный рабочий admin-contour;
2. organization/member/invite/platform modes собраны в одну систему;
3. все основные states покрыты;
4. browser-verified;
5. после завершения обновлен этот master-документ.

---

## 26. Девятый execution slice: Competitor Product Discovery Pipeline

Ниже фиксируется следующий продуктовый slice: автоматический поиск конкурентных товарных ссылок из разрешенного пула сайтов, сопоставление с нашими SKU и отправка результата на модерацию контент-менеджерам.

### 26.1 Роль модуля

`Competitor Product Discovery Pipeline` — это не ручное поле `competitor_url` и не скрытая автопривязка без контроля.

Это:

1. контур поиска конкурентных карточек;
2. контур извлечения evidence с сайтов из разрешенного пула;
3. контур автоматического matching к нашим SKU;
4. очередь модерации для content team;
5. источник для дальнейшего мониторинга цен, описаний, медиа, характеристик и наличия.

### 26.2 Source / result

#### Source

Модуль строится от:

1. наших `products`;
2. `SKU`;
3. бренда;
4. модели;
5. артикула производителя;
6. EAN/GTIN/UPC, если есть;
7. названия товара;
8. категории товара;
9. пула разрешенных competitor-sites: `re-store` и `store77` как первые обязательные источники;
10. правил конкретного сайта;
11. уже подтвержденных/отклоненных связок.

#### Result

Финальный результат работы модуля:

1. для каждого нашего SKU найден список candidate competitor product URLs;
2. каждому candidate присвоен confidence score;
3. у каждого candidate есть evidence: совпавшие поля, source, дата обхода, сырой URL, normalized title, price/availability при наличии;
4. candidates попадают в moderation queue;
5. контент-менеджер подтверждает, отклоняет или отправляет candidate на повторную проверку;
6. подтвержденная связка сохраняется как relation товара, а не как неструктурированная строка;
7. отклоненные связки не предлагаются повторно без нового evidence.

### 26.3 Тип модуля

Тип:

- `Pipeline + Review Queue + Inspector`

Основные рабочие экраны:

1. `Discovery Sources`
2. `Candidate Queue`
3. `Product Match Review`
4. `Confirmed Competitor Links`
5. `Crawler Runs / Logs`

### 26.4 Data model draft

Минимальные сущности:

1. `competitor_sources`
   - id;
   - organization_id;
   - name;
   - base_url;
   - status;
   - crawl_policy;
   - rate_limit;
   - parser_strategy;
   - created_at;
   - updated_at.
2. `competitor_product_candidates`
   - id;
   - organization_id;
   - product_id;
   - source_id;
   - url;
   - normalized_url;
   - title;
   - brand;
   - model;
   - sku;
   - gtin;
   - price;
   - availability;
   - image_url;
   - confidence_score;
   - confidence_reasons;
   - status: `new`, `needs_review`, `approved`, `rejected`, `stale`;
   - first_seen_at;
   - last_seen_at;
   - reviewed_by;
   - reviewed_at.
3. `competitor_product_links`
   - id;
   - organization_id;
   - product_id;
   - source_id;
   - candidate_id;
   - url;
   - status;
   - confirmed_by;
   - confirmed_at;
   - last_checked_at.
4. `competitor_crawl_runs`
   - id;
   - organization_id;
   - source_id;
   - status;
   - started_at;
   - finished_at;
   - scanned_urls_count;
   - candidates_count;
   - errors_count;
   - log_summary.

### 26.5 Matching logic

Matching должен быть layered, а не одним fuzzy search.

Обязательные уровни:

1. exact match по EAN/GTIN/UPC;
2. exact или normalized match по manufacturer SKU / model;
3. brand + model + category;
4. title similarity;
5. attribute similarity;
6. image similarity как дополнительный сигнал, если будет доступен;
7. price sanity check как слабый сигнал, не главный критерий;
8. negative signals: другой бренд, другой объем/размер/цвет, incompatible category, bundle вместо single SKU.

Confidence score должен объясняться пользователю:

1. `GTIN совпал`;
2. `бренд совпал`;
3. `модель совпала`;
4. `название похоже на 91%`;
5. `категория совпадает`;
6. `найден конфликт по размеру/цвету`.

### 26.6 UX contract

Контент-менеджер не должен вручную искать ссылки.

Рабочий flow:

1. пользователь открывает товар или очередь candidates;
2. система показывает найденные конкурентные карточки;
3. каждый candidate виден как карточка/table row с score и evidence;
4. пользователь быстро выбирает `Подтвердить`, `Отклонить`, `Не тот товар`, `Проверить позже`;
5. подтвержденные links попадают в товарный workspace;
6. отклоненные links остаются в истории и используются как negative training signal;
7. спорные candidates остаются в moderation queue.

### 26.7 Compliance / safety rules

Модуль должен работать только с разрешенным пулом сайтов.

Обязательные правила:

1. respect `robots.txt`, если для источника не настроено иное легальное основание;
2. rate limits на источник;
3. user-agent и crawl policy должны быть явно заданы;
4. не обходить paywall, login wall, captcha и технические ограничения;
5. хранить source/evidence и дату получения;
6. не делать blind auto-approval на первом этапе;
7. auto-approval можно включать позже только для high-confidence exact match и после накопления статистики модерации.

### 26.8 Universal / feature / individual split

#### Universal blocks

1. `PageHeader`
2. `PageTabs`
3. `DataTable`
4. `InspectorPanel`
5. `MetricGrid`
6. `Badge`
7. `Button`
8. `Select`
9. `TextInput`
10. `EmptyState`
11. `Alert`
12. `Progress`
13. `JobStatus`

#### Feature-level blocks

1. `CompetitorSourcesList`
2. `CandidateQueue`
3. `CandidateEvidencePanel`
4. `MatchConfidenceBadge`
5. `CompetitorLinkInspector`
6. `CrawlRunTimeline`
7. `ModerationActions`

#### Individual blocks

Допускаются только для orchestration:

1. `CompetitorDiscoveryWorkspace`

### 26.9 Acceptance checklist

Перед implementation нужно отдельно зафиксировать:

1. список первых competitor-sites: `re-store` и `store77`;
2. какие поля точно есть у наших товаров для matching;
3. где пользователь будет видеть candidates: внутри товара, отдельной очередью или в обоих местах;
4. какие роли могут подтверждать links;
5. нужны ли фоновые scheduled runs или только manual run;
6. какие источники нельзя обходить;
7. как долго хранить rejected candidates.

Перед тем как считать slice завершенным, обязательно проверить:

1. source list;
2. crawl run state;
3. candidate queue;
4. product-level candidates;
5. approve/reject flow;
6. empty/error/loading states;
7. long table horizontal scroll;
8. inspector;
9. light/dark;
10. browser-check на проде или staging.

### 26.10 Execution status

Текущий статус реализации:

1. backend discovery API добавлен в существующий `competitor_mapping` route, без параллельного локального контура;
2. sources endpoint возвращает первые обязательные источники: `re-store` и `store77`;
3. candidate queue хранится в tenant-aware competitor mapping store в секции `discovery`;
4. moderation endpoint поддерживает `approve` и `reject`;
5. `approve` создает confirmed competitor link для пары `product_id:source_id`;
6. frontend tab `Конкуренты` добавлен в `/sources-mapping`;
7. UI использует universal blocks: `PageTabs`, `MetricGrid`, `DataTable`, `InspectorPanel`, `Badge`, `Button`, `EmptyState`;
8. `re-store` получил первый bounded HTTP search extractor по `/search/?q=...`, parser покрыт тестами;
9. synchronous manual run ограничен 3 товарами и одним search term, чтобы не ловить nginx timeout;
10. `store77` подключен как source, moderation target и получил первый browser-backed search adapter через общий browser fetch;
11. manual discovery запускается как background run, UI poll-ит `/discovery/runs/{run_id}` и не блокирует HTTP request;
12. run polling защищен от multi-worker race: валидный `run_*` не превращается в пользовательский `Run not found`;
13. storage migration bug исправлен: tenant `competitor_mapping_org_default.json` больше не затирается legacy `competitor_mapping.json` из-за `Path.exists()` в Postgres/SQL mode;
14. production browser-check подтверждает `/sources-mapping?tab=competitors`, source list, background run, заполнение queue реальными candidates, inspector, console errors `0`;
15. последняя production-проверка: run completed, `scanned_products_count=3`, `candidates=15`, все candidates попали в таблицу и статус `На модерации`.
16. добавлен product-level endpoint `GET /api/competitor-mapping/discovery/products/{product_id}`;
17. `Product Workspace` получил секцию `Конкуренты` без локальных UI primitives: используются `Card`, `Button`, `Badge`, `EmptyState`;
18. product-level panel показывает metrics, candidates list, inspector, evidence, moderation actions и confirmed links;
19. browser-check на production подтвердил `/products/product_1`: секция `Конкуренты` открывается, API context грузится, console errors `0`;
20. reject flow проверен в production на заведомо неверном candidate; approve flow покрыт backend-тестом, browser approve намеренно не выполнялся, чтобы не создать неверную confirmed link;
21. matching score усилен brand negative-signal: конфликт известных брендов (`Apple` vs `Xiaomi`/`Samsung` и т.д.) дает score `0` и candidate не попадает в новую выдачу;
22. добавлен stale reconciliation: если после повторного discovery старый `needs_review` candidate для того же `product_id/source_id` больше не найден, он переводится в `stale`;
23. product-level counts теперь включают `stale`, чтобы модератор видел, почему старые candidates ушли из активной очереди;
24. production browser-check после повторного запуска подтвердил: run `completed`, `needs_review=0`, `stale=4`, `rejected=1`, console errors `0`;
25. внешний crawler выключен по умолчанию внутри web API worker через `ENABLE_HTTP_COMPETITOR_DISCOVERY` и `ENABLE_BROWSER_COMPETITOR_DISCOVERY`, потому что production показал смерть uvicorn worker при live crawling; extractor code и tests оставлены для worker-mode;
26. добавлен isolated worker entrypoint `app.workers.competitor_discovery_run`;
27. background run больше не использует `asyncio.create_task` внутри FastAPI worker: API сохраняет `queued` run и запускает отдельный Python worker-process;
28. web-launched worker работает в safe mode (`ENABLE_HTTP_COMPETITOR_DISCOVERY=0`, `ENABLE_BROWSER_COMPETITOR_DISCOVERY=0`) и делает deterministic reconciliation/stale без live crawling;
29. production browser-check после worker-slice подтвердил: run `queued -> completed`, `scanned_products_count=1`, console errors `0`;
30. production journal после worker-slice проверен: после последнего deploy нет `Child process died` на discovery run.
31. matching ужесточен: score больше не имеет базового бонуса за “разрешенный домен”, candidate обязан пройти обязательные product tokens;
32. для Apple/iPhone SKU обязательными стали brand/model/generation/variant tokens: например `Apple iPhone 17 Pro 256Gb eSIM Silver` не может матчиться с `iPhone 16`, `Xiaomi` или бытовой техникой;
33. добавлены tests на bad suggestions: wrong brand, same-brand wrong generation и close variant match;
34. production browser-check после stricter matching подтвердил: product discovery run `completed`, `needs_review=0`, `active=[]`, console errors `0`;
35. рабочее правило для competitor discovery: лучше вернуть пустую очередь на модерацию, чем отправить контент-менеджеру нерелевантные candidates.

Оставшиеся обязательные sub-slices:

1. dedicated crawler service/cron для live HTTP/browser crawling с включенными `ENABLE_HTTP_COMPETITOR_DISCOVERY=1` / `ENABLE_BROWSER_COMPETITOR_DISCOVERY=1`, отдельно от web-launched safe worker;
2. перенос `re-store`/`store77` live crawling в long-running worker с таймаутами, retries, rate limits, логами и durable run state;
3. approve browser-check на высокоуверенном реальном candidate и проверка confirmed link после approve;
4. tuning matching score и dedupe на реальных candidates после включения worker;
5. UI-state для источников, которые доступны как parser, но live crawling выключен до worker-слоя.
6. расширить normalizer под русские цвета/память/SIM-алиасы и реальные naming patterns `re-store`/`store77`, когда появятся валидные live samples.

### 26.11 Competitor Links To Product Values Flow

Дата фиксации: 2026-04-26.

Проблема:

1. discovery links и загрузка параметров из competitor-сайтов не должны смешиваться в один шаг;
2. если сразу тянуть параметры из каждого найденного candidate, неверный match может загрязнить source values товара;
3. пользователь должен понимать, где происходит matching ссылок и где начинается enrichment параметров.

Решение:

1. `Competitor Discovery` отвечает только за поиск и сопоставление ссылок:
   - источник: наши товары + разрешенные сайты `re-store` / `store77`;
   - экран: `/sources-mapping?tab=competitors`;
   - product-level экран: карточка товара, tab `Конкуренты`;
   - результат: `candidate` со score/evidence/status;
   - финальный шаг: `approve` / `reject`.
2. `Competitor Enrichment` начинается только после `approve`:
   - источник: confirmed competitor links;
   - действие: загрузить specs/media/description/price/availability;
   - результат: source-aware values для товара, а не сразу canonical product values.
3. `Product Workspace` показывает enrichment в двух местах:
   - tab `Конкуренты`: какие ссылки подтверждены, что они дают, когда последний раз проверялись;
   - tab `Источники`: какие raw/resolved/canonical values пришли из competitor links, Excel, import или ручного ввода.
4. `Параметры` товара показывают:
   - итоговое canonical значение;
   - source evidence;
   - альтернативные значения по источникам;
   - marketplace output value после value mapping.
5. `Значения параметров` / `Parameter Values Workspace` отвечает за словари и альтернативные написания:
   - `256 ГБ` как canonical;
   - `256GB`, `256 gb`, `256Гб`, `256 ГБ встроенной памяти` как source/provider variants;
   - отдельные output labels для маркетплейсов.

Правильный пользовательский порядок в PIM:

1. организация создана;
2. пользователи и права настроены;
3. каналы подключены;
4. каталог категорий создан;
5. инфо-модели категорий настроены;
6. категории PIM сопоставлены с категориями площадок;
7. параметры инфо-модели сопоставлены с параметрами площадок;
8. товары созданы или импортированы;
9. товары разложены по категориям и группам;
10. content manager запускает competitor discovery:
    - глобально из `/sources-mapping?tab=competitors`;
    - или точечно из карточки товара, tab `Конкуренты`;
11. система предлагает competitor candidates;
12. content manager подтверждает или отклоняет candidates;
13. confirmed links запускают competitor enrichment;
14. specs/media/description из competitor links попадают в source evidence товара;
15. content manager смотрит tab `Источники` и tab `Параметры`;
16. система предлагает canonical value на основании source values, info model и dictionaries;
17. content manager подтверждает/исправляет canonical values;
18. value mapping превращает canonical values в channel-specific output values;
19. validation проверяет заполненность и правила площадок;
20. export отправляет готовые данные.

Что должно быть реализовано следующим sub-slice:

1. `Competitor Enrichment Job`:
   - берет confirmed links;
   - вызывает существующие extractors `competitor-content-batch` / `competitor-fields`;
   - сохраняет результат как source evidence по товару;
   - не перезаписывает canonical values без user review.
2. `Product Workspace`:
   - tab `Конкуренты` должен показывать кнопку `Загрузить данные из подтвержденных ссылок`;
   - tab `Источники` должен показывать source rows `competitor:restore` / `competitor:store77`;
   - tab `Параметры` должен явно показывать source evidence и proposed canonical value.
3. `Parameter Values Workspace`:
   - должен показывать canonical value и marketplace/output alternatives;
   - должен объяснять, как `256 ГБ` будет отображаться на разных площадках.
4. Acceptance:
   - неверный candidate не может попасть в source values без approve;
   - rejected candidate становится negative signal;
   - enrichment run имеет loading/error/success state;
   - source evidence виден в карточке товара;
   - canonical value и marketplace output values визуально различимы.

Статус реализации first-pass enrichment, 2026-04-26:

1. Backend:
   - добавлен `POST /competitor-mapping/discovery/products/{product_id}/enrich`;
   - endpoint берет только `confirmed` links из discovery storage;
   - вызывает существующий `extract_competitor_content` для `re-store` / `store77`;
   - сохраняет найденные specs в `content.features[*].source_values.competitor.{restore|store77}`;
   - не перезаписывает `feature.value` и не меняет canonical product values автоматически;
   - unmatched specs, media и description сохраняются в `content.source_evidence.competitors`;
   - `last_enriched_at` фиксируется на confirmed link.
2. Frontend:
   - в tab `Конкуренты` добавлена action `Загрузить данные из ссылок`;
   - после enrichment карточка товара перезагружается;
   - вкладки `Параметры` и `Источники` используют существующий universal source-values renderer.
3. Verification:
   - `python3 -m py_compile backend/app/api/routes/competitor_mapping.py` прошел;
   - `npm run build` во frontend прошел;
   - production deploy прошел, `global-pim.service` active, `/api/health` вернул `{"ok":true}`;
   - browser-use проверка `/products/product_113`, tab `Конкуренты`: панель открывается, `Найти ссылки` видна, confirmed links отсутствуют у текущего SKU, поэтому action enrichment скрыта корректно.

Статус fix competitor discovery, 2026-04-26:

1. Найден root cause плохого поиска по Store77:
   - `_query_terms_for_product` начинал с внутреннего `sku_gt` (`50046`) и из-за прежнего `terms[:1] не доходил до товарного title;
   - Store77 использует реальные URL вида `/apple_iphone_16_pro_2/...` и `/telefony_apple/...`, а parser принимал только `/catalog|product|tovar|goods`;
   - production worker зависал на live HTTP discovery для `re-store`, поэтому до Store77 очередь могла не доходить.
2. Исправлено:
   - query terms теперь приоритизируют cleaned product title и только потом внутренние SKU;
   - Store77 parser принимает реальные section/product URL patterns;
   - для Apple iPhone добавлен deterministic Store77 seed candidate по модели, памяти, SIM и цвету;
   - `re-store` live HTTP discovery выключен в worker по умолчанию, чтобы не блокировать Store77;
   - Store77 browser crawling оставлен как fallback, но точный iPhone candidate формируется без browser crawl.
3. Verification:
   - добавлены и пройдены tests:
     - `test_competitor_query_terms_prioritize_title_over_internal_sku`;
     - `test_store77_search_html_candidates_extract_real_section_links`;
     - `test_store77_category_urls_are_derived_from_iphone_title`;
     - `test_store77_seed_candidate_builds_exact_iphone_product_url`;
     - `test_store77_search_html_candidates_extract_product_links`;
   - local discovery для `product_113` вернул Store77 candidate за `0.0s`;
   - production deploy прошел, `global-pim.service` active, `/api/health` вернул `{"ok":true}`;
   - browser-use на `/products/product_113`, tab `Конкуренты`: после `Найти ссылки` появился candidate `https://store77.net/apple_iphone_16_pro_2/telefon_apple_iphone_16_pro_128gb_esim_natural_titanium/`, score `93%`, status `На модерации`.

Статус SIM / variant moderation pass, 2026-04-27:

1. Product rule:
   - `eSIM only` и `nano SIM + eSIM` считаются разными SIM-профилями;
   - candidate с конфликтующим SIM-профилем не должен попадать в moderation queue как валидный match;
   - одинаковые `model + memory + color`, но разные SIM-варианты группируются в один match group, чтобы content manager видел варианты рядом.
2. Backend:
   - добавлен `_sim_profile()` для нормализации `nano SIM+eSIM`, `eSIM only`, `Dual SIM`, physical SIM;
   - добавлен `_model_memory_color_group_key()` для группировки вариантов без смешивания SIM-профиля;
   - `_confidence_for_candidate()` теперь возвращает `0.0` при конфликте SIM-профиля;
   - deterministic Store77 seed для iPhone теперь сохраняет корректный `nano_sim_esim` slug, если наш SKU содержит `nano SIM+eSIM`;
   - approve одного candidate автоматически отклоняет sibling candidates того же `product_id + source_id + match_group_key` со статусом `needs_review`;
   - добавлен manual confirmed link endpoint `POST /competitor-mapping/discovery/products/{product_id}/links`;
   - ручная ссылка подтверждается сразу и отклоняет pending candidates выбранного source для этого SKU.
3. Frontend:
   - tab `Конкуренты` в карточке товара показывает candidates группами / carousel variants;
   - candidate card показывает score, status и распознанный SIM-профиль;
   - inspector показывает `SIM в PIM` и `SIM candidate`;
   - добавлен блок `Ручная ссылка`, чтобы content manager мог вставить точную карточку после отклонения всех вариантов.
4. Verification:
   - backend targeted tests прошли:
     - `test_sim_profile_conflict_blocks_esim_only_candidate_for_nano_esim_product`;
     - `test_store77_seed_candidate_preserves_nano_esim_slug`;
     - `test_approving_candidate_rejects_sibling_variants`;
     - `test_manual_competitor_link_confirms_link_and_rejects_pending_source_candidates`;
     - плюс Store77/query/parser regression tests;
   - `npm run build` во frontend прошел на Vite `8.0.9`;
   - production deploy прошел, `global-pim.service` active, `/api/health` вернул `{"ok":true}`;
   - browser-use verification на `/products/product_113`, tab `Конкуренты`: после `Найти ссылки` появился Store77 candidate `nano SIM+eSIM`, старый `eSIM` candidate стал `Устарело`, inspector показывает `SIM в PIM = nano SIM + eSIM` и `SIM candidate = nano SIM + eSIM`.

### 26.12 Product Creation / Import / Enrichment Process

Дата фиксации: 2026-04-26.

Главное продуктовое правило:

1. создание товара вручную и импорт товаров через XLS должны сходиться в один enrichment pipeline;
2. импорт товаров без немедленного насыщения — нормальный сценарий;
3. пользователь может сначала загрузить пустые/полупустые SKU, а потом отдельной операцией насыщать их параметрами, медиа, описаниями, связями и marketplace-ready значениями;
4. competitor discovery и source enrichment не должны быть обязательным blocking step для создания SKU.

Два входа в pipeline:

#### Вход A. Ручное создание товара

Порядок:

1. пользователь создает SKU через `/products/new`;
2. выбирает базу:
   - название;
   - категорию;
   - SKU;
   - тип single / variant-family;
   - группу вариантов, если нужна;
3. после создания пользователь попадает в `Product Workspace`;
4. система автоматически может поставить задачу `Find competitor candidates` для этого SKU;
5. candidates появляются в tab `Конкуренты`;
6. пользователь подтверждает/отклоняет candidates;
7. после approve запускается enrichment из confirmed links;
8. параметры попадают в source evidence;
9. пользователь подтверждает canonical values;
10. validation/export проверяют готовность.

UX-следствие:

1. `/products/new` не должен требовать вручную заполнить все параметры до создания;
2. `/products/new` должен показывать, что после создания будет доступен этап насыщения;
3. в success-state нового SKU нужно предлагать:
   - открыть карточку;
   - найти competitor candidates;
   - перейти к параметрам;
   - перейти к медиа.

#### Вход B. Импорт товаров через XLS

Порядок:

1. пользователь загружает XLS через `/catalog/import` или source/import workspace;
2. система создает/обновляет SKU и category/group assignments;
3. import result показывает:
   - создано;
   - обновлено;
   - пропущено;
   - ошибки;
   - сколько SKU требуют enrichment;
4. пользователь может не насыщать товары сразу — это нормальное состояние;
5. после импорта пользователь запускает batch enrichment:
   - по всей import batch;
   - по выбранной категории;
   - по выбранным SKU;
   - по товарам без параметров / без фото / без competitor links;
6. batch enrichment сначала запускает competitor discovery;
7. candidates уходят в moderation queue;
8. после approve confirmed links идут в enrichment;
9. параметры/медиа/описания попадают в source evidence;
10. пользователь подтверждает canonical values пакетно или точечно.

UX-следствие:

1. import screen должен иметь post-import action `Запустить насыщение`;
2. product list должен иметь queue/filter `Требуют насыщения`;
3. карточка товара должна показывать, из какого import batch пришел товар;
4. source evidence должен отличать:
   - `import:xls`;
   - `competitor:restore`;
   - `competitor:store77`;
   - `manual`;
   - будущие marketplace/source connectors.

### 26.13 Marketplace Creation When Product Does Not Exist On Marketplace

Дата фиксации: 2026-04-26.

Проблема:

1. товара может не быть на маркетплейсе;
2. тогда marketplace data нельзя подтянуть как existing card;
3. PIM должен не искать “что уже есть на площадке”, а собрать payload для создания карточки на площадке.

Решение:

1. для каждого marketplace/channel есть два разных режима:
   - `match existing marketplace card`;
   - `create new marketplace card`;
2. если existing marketplace card не найден:
   - система показывает `Карточки на площадке нет`;
   - пользователь видит checklist обязательных данных для создания;
   - PIM предлагает, какие параметры передать на площадку;
   - values берутся из canonical product values + channel value mapping + source evidence;
3. marketplace output layer должен явно показывать:
   - PIM canonical value;
   - source evidence;
   - marketplace required field;
   - marketplace output value;
   - статус: готово / нужно заполнить / конфликт / unsupported;
4. competitor sources могут помочь заполнить параметры, даже если товара на маркетплейсе нет.

Пример:

1. canonical product value: `Встроенная память = 256 ГБ`;
2. source values:
   - `re-store`: `256GB`;
   - `store77`: `256 Гб`;
   - XLS: `256`;
3. marketplace output:
   - Я.Маркет: значение из справочника/allowed values;
   - Ozon: значение и формат по требованиям Ozon;
   - если значение не найдено в allowed values — статус `нужен mapping`.

Обязательный future UI:

1. в `Product Workspace` tab `Маркетплейсы`:
   - режим `existing card` / `new card`;
   - readiness checklist;
   - required fields;
   - output values;
   - причины блокировки export/create;
2. в `Parameter Values Workspace`:
   - canonical dictionary;
   - source variants;
   - marketplace output variants;
   - conflict resolution;
3. в `Validation`:
   - отдельная очередь `Создание карточек на площадках`;
   - ошибки по required fields;
   - ошибки по allowed values;
   - ошибки по медиа/описанию.

### 26.14 Unified Enrichment Queue

Дата фиксации: 2026-04-26.

Нужна единая очередь enrichment, потому что товары могут появляться из разных источников.

Входы в очередь:

1. новый SKU создан вручную;
2. SKU создан/обновлен через XLS;
3. SKU перемещен в категорию с новой инфо-моделью;
4. SKU потерял обязательные параметры после изменения инфо-модели;
5. confirmed competitor link добавлен вручную или через approve;
6. marketplace mapping изменился;
7. validation обнаружила missing/invalid values.

Типы задач:

1. `find_competitor_candidates`;
2. `review_competitor_candidates`;
3. `extract_competitor_values`;
4. `extract_competitor_media`;
5. `normalize_source_values`;
6. `propose_canonical_values`;
7. `map_values_to_marketplace`;
8. `validate_marketplace_payload`;
9. `prepare_export_or_create_card`.

Минимальный UI:

1. Product List:
   - фильтр `Требуют насыщения`;
   - счетчик missing params/media/marketplace readiness.
2. Product Workspace:
   - compact enrichment status;
   - actions по текущему SKU.
3. Sources / Import:
   - batch enrichment для import batch.
4. Competitor Queue:
   - moderation candidates.
5. Validation:
   - финальные блокеры перед export/create marketplace card.

---

## 25. Execution Protocol

Ниже фиксируется обязательный протокол выполнения.

Этот раздел определяет не “что строим”, а “как именно идем по работе”.

### 25.1 Общий принцип

Переделка идет строго:

1. page-by-page;
2. в порядке, зафиксированном в этом документе;
3. без перескоков;
4. без частичной готовности;
5. без локальных временных решений, которые потом “как-нибудь уберем”.

### 25.2 Порядок работы с каждой страницей

Для каждой страницы обязательный порядок такой:

1. определить route и роль страницы;
2. зафиксировать source/result;
3. перечислить все states страницы;
4. перечислить все tabs;
5. перечислить все drawers;
6. перечислить все modals;
7. перечислить все nested states;
8. перечислить все повторяющиеся блоки;
9. разделить блоки на:
   - universal;
   - feature-level;
   - individual;
10. определить page type;
11. определить layout contract;
12. определить sticky contract;
13. определить horizontal scroll contract;
14. только после этого переходить к implementation.

### 25.3 Инвентаризация элементов

Для каждой страницы нужно отдельно пройтись по элементам и классифицировать их:

#### Universal

Если элемент:

1. встречается больше одного раза;
2. является типовым control или display pattern;
3. может использоваться на других страницах;

то он обязан быть universal.

#### Feature-level

Если элемент:

1. характерен для одной продуктовой зоны;
2. повторяется внутри одной feature;
3. не подходит как глобальный primitive;

то он должен быть feature-level.

#### Individual

Individual допускается только если:

1. блок реально встречается один раз;
2. блок выражает уникальную orchestration-логику;
3. он не дублирует уже существующие universal/feature-level паттерны.

### 25.4 Что нельзя пропускать

При переделке каждой страницы нельзя пропускать:

1. ни один route;
2. ни один tab;
3. ни один nested mode;
4. ни один drawer;
5. ни один modal;
6. ни один dropdown state;
7. ни один hover/focus/active state;
8. ни один error/loading/empty state;
9. ни один длинный table/list state;
10. ни один inspector state.

Если что-то есть на странице, это должно быть:

1. перечислено;
2. переделано;
3. проверено.

### 25.5 Layout protocol

Для каждой страницы нужно явно зафиксировать:

1. где начинается рабочая зона;
2. какие блоки видны above the fold;
3. какие элементы sticky;
4. где живет вертикальный scroll;
5. где живет horizontal scroll;
6. какие контейнеры не должны ломать друг друга;
7. какие поверхности главные, а какие вторичные.

### 25.6 Browser verification protocol

После implementation каждой страницы обязательна browser-проверка:

1. открыть страницу в реальном браузере через `@browser-use`;
2. пройти все tabs;
3. пройти все nested states;
4. проверить dropdown/flyout/menu states;
5. проверить sticky behavior;
6. проверить horizontal scroll;
7. проверить длинные тексты;
8. проверить empty/error/loading states;
9. проверить `light`;
10. проверить `dark`.

Правило инструмента:

1. для визуального просмотра и пользовательской оценки использовать `@browser-use`;
2. Playwright использовать только как fallback для автоматизации, если `@browser-use` недоступен или не подходит для конкретной проверки;
3. если Playwright был использован, после работы обязательно закрыть процессы;
4. финальная отметка `browser-verified` допустима только после просмотра глазами пользователя, а не только после DOM/screenshot smoke-check.

Нельзя считать страницу завершенной только по:

1. `npm run build`;
2. screenshot;
3. статической оценке кода.

### 25.7 Definition of done for every page

Любая страница считается завершенной только если:

1. page role и source/result зафиксированы;
2. все states перечислены и покрыты;
3. все повторяющиеся элементы вынесены правильно;
4. layout contract собран;
5. страница не тащит старую структуру;
6. browser-verified;
7. light/dark рабочие;
8. документ обновлен;
9. только после этого разрешен переход к следующей странице.

### 25.8 Порядок выполнения redesign

Строгий порядок:

1. `Control Center`
2. `Product List / Catalog Entry`
3. `Product Workspace as e-commerce product card`
4. `Product Creation Wizard`
5. `Catalog Workspace`
6. `Info Model Workspace`
7. `Channel Mapping Workspace`
8. `Sources / Import`
9. `Organizations / Admin`

Если по ходу выясняется, что для страницы нужен дополнительный sub-slice, он добавляется в этот документ перед implementation.

### 25.9 Правило обновления master-документа

После завершения каждой страницы обязательно:

1. обновить этот документ;
2. отметить, какие states уже покрыты;
3. зафиксировать, какие universal blocks были реально использованы;
4. убрать выполненный execution step из активного состояния;
5. только потом переходить к следующей странице.

### 25.10 Что считается нарушением протокола

Нарушением считается:

1. начать следующую страницу, не завершив текущую;
2. оставить старый tab/modals/drawers без переделки;
3. заявить “готово” без browser-check;
4. оставить локальный duplicated element вместо universal/feature-level блока;
5. поменять только skin, но не поменять структуру страницы;
6. не обновить master-документ после завершения этапа.

---

## 27. Reopened Design Debt Queue

Эта секция фиксирует задачи, которые были преждевременно отмечены как закрытые или требуют повторного дизайнерского прохода.

### 27.1 Активная задача

Текущая активная задача:

1. `Catalog Workspace Rework`

Причина:

1. текущий каталог функционально стал лучше, но визуально не соответствует уровню PIM/SaaS;
2. дизайн должен быть перестроен от рабочих сценариев, а не от декоративных summary cards.

### 27.2 Design reference direction

Ориентиры:

1. `Brandquad`;
2. `PIM Cloud`;
3. mature enterprise PIM / product data platforms;
4. внутренний позитивный reference: текущий `Product Workspace`, потому что карточка товара уже ближе к нужному уровню.

Что брать из этих ориентиров:

1. плотность рабочих экранов;
2. аккуратные списки и таблицы;
3. не декоративные, а служебные panels;
4. clear primary/secondary actions;
5. readable inspector;
6. компактное меню;
7. спокойные контрасты в light/dark.

Что не делать:

1. не копировать marketing-стили;
2. не добавлять hero/dashboard поверх рабочих страниц;
3. не делать огромные cards там, где пользователь ожидает таблицу, список или редактор;
4. не прятать главный workflow ниже первого экрана.

### 27.3 Navigation Shell / Menu

Статус: first rework pass completed, browser-verified.

Задача:

1. сделать нормальное современное меню, а не технический rail;
2. пользователь должен быть виден в shell:
   - имя или email;
   - организация;
   - роль;
3. переключатель темы должен быть виден и доступен:
   - light;
   - dark;
4. меню должно экономить место:
   - collapsed rail по умолчанию;
   - readable expanded state;
   - hover/focus без случайных dropdown-прыжков;
5. разделы должны быть понятны:
   - Рабочее пространство;
   - Каталог;
   - Товары;
   - Модели;
   - Источники;
   - Каналы;
   - Медиа;
   - Администрирование;
6. меню должно пройти browser-check через `@browser-use`:
   - collapsed;
   - expanded;
   - hover;
   - active route;
   - theme toggle;
   - user/org area.

Execution status 2026-04-26:

1. общий `ShellSidebarNav` получил reusable `railFooter` и `panelFooter`;
2. профиль, организация, роль, статус организации и действия аккаунта перенесены в общий shell;
3. theme toggle теперь виден в collapsed rail на всех рабочих страницах;
4. expanded navigation panel стала fixed/full-height вместо короткого dropdown-фрагмента;
5. admin-only topbar больше не является единственным местом, где пользователь видит аккаунт;
6. production deploy выполнен;
7. `@browser-use` проверка на `https://pim.id-smart.ru/catalog` прошла:
   - меню открывается;
   - раздел `Каталог` показывает links `Товары` и `Обмен`;
   - `Default organization`, user/email, role/status и theme toggle присутствуют;
   - активная страница каталога продолжает отображать товары;
   - console errors отсутствуют.

Дальше:

1. после heavy pages нужно вернуться к визуальной полировке shell-icons и spacing;
2. если появятся новые разделы, добавлять их только в shared shell config, не локально на страницах.

### 27.3.1 Catalog Workspace second visual pass

Дата: 2026-04-26.

Статус: second visual pass completed, browser-verified.

Причина повторного прохода:

1. первый catalog pass функционально стал лучше, но основной режим `Товары` все еще держал сверху отдельные cards:
   - category context;
   - tabs;
   - product table header;
2. для рабочего каталога это выглядело как dashboard над таблицей, а пользователь должен сразу попадать в рабочий список SKU.

Что сделано:

1. в `products` mode отдельные `catalogWorkHeader` и `catalogTabBarCard` скрываются;
2. category title, path, model state, SKU count, subcategory count и channel count перенесены в compact command-bar внутри `catalogProductsWorkspace`;
3. primary actions перенесены туда же:
   - `Добавить SKU`;
   - `Импорт Excel`;
   - `Полный список`;
4. tabs перенесены в compact horizontal row прямо над product registry;
5. высота product table увеличена за счет удаления лишних верхних cards;
6. production deploy выполнен;
7. `@browser-use` проверка на `https://pim.id-smart.ru/catalog` прошла:
   - category command виден;
   - inline tabs видны;
   - product table видна;
   - старый отдельный context-copy `приоритет 0` в products mode не отображается;
   - console errors отсутствуют.

Ограничение:

1. in-app browser viewport сейчас узкий и режет desktop grid по горизонтали;
2. продуктовый target остается desktop, поэтому полноценную широкую visual QA нужно повторить инструментом, который стабильно выставляет viewport `1600px+`.

### 27.3.2 Catalog UX Copy Pass

Дата: 2026-04-26.

Статус: completed, browser-verified.

Проблема:

1. экран говорил внутренними сущностями:
   - `Каналы`;
   - `Модель`;
   - `Контекст категории`;
2. для пользователя это не объясняет, что делать дальше;
3. каталог должен говорить рабочими задачами контент-менеджера.

Что сделано:

1. `Модель` заменена на `Поля товара`;
2. `Каналы` заменены на `Выгрузка` / `площадки`;
3. `Контекст категории` заменен на `Выбранная категория`;
4. tree badges заменены:
   - `Модель` -> `Поля`;
   - `Каналы` -> `Выгрузка`;
   - `Черновик` -> `Нужна настройка`;
5. фильтры заменены:
   - `Без модели` -> `Без полей`;
   - `Без каналов` -> `Без выгрузки`;
6. tab labels заменены:
   - `Товары` -> `SKU`;
   - `Инфо-модель` -> `Поля товара`;
   - `Каналы` -> `Выгрузка`;
7. inspector copy переписан на:
   - где находится категория;
   - какие поля товара настроены;
   - куда выгружаются товары;
   - какие действия доступны;
8. production deploy выполнен;
9. `@browser-use` проверка на `https://pim.id-smart.ru/catalog` прошла:
   - новые пользовательские labels видны;
   - старые visible terms `Контекст категории`, `Inspector`, `Инфо-модель категории`, `Канальные связи`, `Без модели`, `Без каналов` не найдены;
   - product table видна;
   - console errors отсутствуют.

Ограничение:

1. это copy/meaning pass, а не финальная композиционная переделка всего каталога;
2. следующим catalog-pass нужно решить, нужна ли правая панель вообще или ее лучше заменить на contextual action drawer.

### 27.3.3 Clean Catalog Decision

Дата: 2026-04-26.

Статус: first-pass implemented, extended visual QA pending.

Решение:

1. `/catalog` должен быть чистым экраном просмотра структуры и SKU;
2. все промежуточные процессы должны жить на отдельных страницах;
3. каталог показывает финальный слой, а не грязь подготовки.

Что оставить в `/catalog`:

1. page title `Каталог`;
2. tree категорий;
3. поиск по категориям;
4. сортировка/развернуть;
5. счетчики SKU;
6. таблица SKU выбранной категории;
7. поиск по SKU;
8. фильтры:
   - все;
   - без фото;
   - без группы;
9. действия:
   - добавить SKU;
   - открыть SKU;
   - переместить SKU;
   - создать категорию;
   - создать подкатегорию;
   - переименовать категорию;
   - удалить ветку.

Что убрать из `/catalog`:

1. tabs:
   - `Поля товара`;
   - `Выгрузка`;
   - `Импорт`;
   - `История`;
2. tree badges:
   - `Поля`;
   - `Выгрузка`;
3. filters:
   - `Без полей`;
   - `Без выгрузки`;
4. right-panel readiness по полям/выгрузке;
5. кнопка `Импорт Excel` как основное действие каталога;
6. колонка `Мастер-файл`, если она относится к подготовке, а не к финальному просмотру;
7. marketplace diagnostic statuses, если они не являются финальным фактом карточки;
8. любые объяснения про маппинг, поля, каналы, правила площадок.

Куда вынести:

1. `Поля товара`:
   - `/templates`;
   - `/templates/:categoryId`.
2. `Выгрузка`:
   - `/sources-mapping`;
   - dedicated category mapping states.
3. `Импорт`:
   - `/catalog/import`;
   - source import pages.
4. `История`:
   - отдельный audit/activity screen позже;
   - не блокирует clean catalog.
5. `Качество / Валидация`:
   - отдельная страница очереди исправления.

Implementation checklist:

1. удалить `CatalogTab` из основного clean catalog UI или оставить только hidden route-state для будущего — done, основной UI больше не рендерит tabs;
2. убрать `catalogProductsTabs` — done;
3. убрать `catalogWorkHeader` / `catalogTabBarCard` из products mode окончательно, не через CSS-hide — partially done, UI больше не виден пользователю, cleanup оставшегося hidden CSS/class debt нужен отдельным cleanup;
4. убрать tree badges `Поля` / `Выгрузка` — done;
5. заменить tree filters на:
   - `Все`;
   - `С товарами`;
   - `Пустые` — done;
6. убрать right inspector readiness blocks — done;
7. оставить right action panel только с действиями категории — done;
8. проверить, что product table начинается выше и является главным объектом страницы — done через `@browser-use` DOM/screenshot;
9. проверить drag/move SKU или добавить отдельный sub-slice, если move flow еще не реализован — done first-pass: добавлен modal `Перемещение SKU`, финальное сохранение не прожималось на prod, чтобы не менять реальные данные без отдельного подтверждения;
10. пройти `@browser-use`:
    - category tree;
    - search;
    - product table;
    - category actions;
    - empty category;
    - long category names;
    - light/dark;
    - console errors — partially done, проверены DOM/screenshot на default category; расширенная matrix QA остается обязательной.

### 27.3.4 Clean Catalog Implementation

Дата: 2026-04-26.

Статус: first-pass implemented and deployed.

Что изменено:

1. `/catalog` теперь показывает чистый рабочий сценарий:
   - дерево категорий;
   - selected-category product table;
   - actions для категории;
   - counts и category path.
2. Убрано из visible main catalog UI:
   - `Поля товара`;
   - `Выгрузка`;
   - `Импорт Excel`;
   - `История`;
   - `Мастер-файл`;
   - `Я.Маркет`;
   - `Ozon`;
   - `Контекст категории`;
   - `Каналы`;
   - `Модель`.
3. `ProductRegistry` получил reusable variant `catalogClean`, чтобы clean catalog не дублировал таблицу локально.
4. `catalogClean` table оставляет только:
   - `SKU GT`;
   - товар;
   - группу;
   - действие `Открыть`.
5. `catalogClean` filters оставляют только:
   - все товары;
   - без фото;
   - без группы;
   - group select.
6. Backend `view_filter` расширен на:
   - `no_photo`;
   - `no_group`.
7. Tree filters стали:
   - `Все`;
   - `С товарами`;
   - `Пустые`.
8. `catalogClean` получил SKU move action:
   - `Переместить` в строке товара;
   - modal выбора target category;
   - сохранение через `PATCH /products/{id}`;
   - refresh product table и category counts после успеха.

Проверка:

1. `CI=1 npm run build` в `frontend` прошел;
2. production deploy прошел;
3. `https://pim.id-smart.ru/api/health` вернул `{"ok":true}`;
4. `@browser-use` DOM snapshot на `https://pim.id-smart.ru/catalog` подтвердил:
   - required labels присутствуют;
   - forbidden old labels в main clean catalog не найдены;
   - таблица и category actions видны;
   - `Переместить` присутствует в строках;
   - move modal открывается.

Оставшиеся задачи:

1. пройти расширенную visual QA matrix:
   - root category;
   - leaf category;
   - empty category;
   - long names;
   - dark/light;
   - create/rename/delete category;
   - category search;
   - tree sort mode;
   - product open action;
   - финальное сохранение move-flow на тестовом SKU;
2. убрать оставшийся CSS/class debt от старых tabs/header, если после QA не нужен fallback.

### 27.4 Heavy Pages To Rework

После каталога нужно пройти тяжелые страницы отдельными slices.

Обязательный порядок:

1. `Catalog Workspace`;
2. `Navigation Shell / Menu`;
3. `Info Model Workspace`;
4. `Parameter Values Workspace`;
5. `Channel Mapping Workspace`;
6. `Sources / Import`;
7. `Organizations / Admin`;
8. финальная зачистка `Product Workspace` мелочей.

Для каждой страницы:

1. сначала определить рабочий сценарий пользователя;
2. затем определить source/result;
3. затем разделить элементы на universal / feature-level / individual;
4. затем переделать layout;
5. затем проверить в `@browser-use`;
6. затем обновить этот документ.

### 27.4.1 Execution status: Channel Mapping Workspace Rework

Дата: 2026-04-26.

Статус: first rework pass completed, browser-verified.

Что сделано:

1. общий `sources-mapping` topbar уплотнен и переведен из hero-подачи в рабочий command-bar;
2. заголовок `Маппинг каналов` заменен на более широкий рабочий контур `Каналы и источники`;
3. декоративные `sourcesMappingCanvasIntro` скрыты из above-the-fold;
4. tabs оставлены как основной способ навигации между:
   - `Категории и источники`;
   - `Сопоставление параметров`;
   - `Значения`;
   - `Конкуренты`;
5. production deploy выполнен;
6. `@browser-use` проверка на `https://pim.id-smart.ru/sources-mapping?tab=values&category=b2f026d9-a3e2-4821-9034-d17ac1b65065` прошла:
   - новый title отображается;
   - старый `Маппинг каналов` больше не найден;
   - value workspace остается рабочим;
   - контур `Наушники` гидратируется;
   - console errors отсутствуют.

Ограничение:

1. это общий shell-level pass для `sources-mapping`;
2. внутренние тяжелые состояния `Категории и источники` и `Сопоставление параметров` все еще требуют последующих точечных проходов по tables/lists/modals.

### 27.4.2 Execution status: Sources / Import Rework

Дата: 2026-04-26.

Статус: first rework pass completed, browser-verified.

Что сделано:

1. `/catalog/import` и `/catalog/export` сохранены на shared `WorkspaceFrame`, без локального дубля layout;
2. добавлен modern style layer для `cx-pageModern`;
3. page header стал компактнее и ближе к рабочему command-bar;
4. sidebar и inspector закреплены через sticky в desktop shell;
5. длинные tables получили:
   - horizontal scroll;
   - sticky header;
   - theme-safe colors;
6. hardcoded light colors перекрыты CSS variables для dark/light;
7. production deploy выполнен;
8. `@browser-use` проверка прошла:
   - `/catalog/import` показывает picker, action `Запустить`, inspector `Область/Источники`;
   - `/catalog/export` показывает picker, action `Подготовить`, inspector `Область/Каналы`;
   - console errors отсутствуют.

Ограничение:

1. это first-pass visual/system layer;
2. внутренний `CatalogExchangePicker` нужно позже отдельно привести к единому catalog tree design, если он начнет отличаться от `/catalog`.

### 27.4.3 Execution status: Organizations / Admin Rework

Дата: 2026-04-26.

Статус: second layout pass completed, production-deployed, browser-verified.

Что сделано:

1. `OrganizationsAdminFeature` оставлен на shared `WorkspaceFrame`;
2. `orgAdminPage` получил compact command-header вместо высокого page-header;
3. `orgAdminWorkspace` получил плотную трехколоночную сетку и sticky sidebar/inspector;
4. `AdminAccessFeature` пока оставлен на локальной логике, но его shell приведен к тому же compact/sticky contract;
5. production deploy выполнен;
6. `@browser-use` проверка прошла:
   - `/admin/organizations`;
   - `/admin/members`;
   - `/admin/invites`;
   - `/admin/access`;
   - console errors отсутствуют.

Ограничение:

1. `AdminAccessFeature` все еще использует специализированную `accessWorkspace`, но она приведена к compact two-column admin contract;
2. следующий pass по админке должен быть функциональным, а не cosmetic: роли, инвайты, provisioning и audit нужно разделить по понятным рабочим сценариям.

Second pass, 2026-04-28:

1. shell navigation упрощена до реальной информационной архитектуры:
   - `Организации`;
   - `Команда`;
   - `Инвайты`;
   - `Роли и права`;
   - `Platform` скрыт для non-developer пользователей;
2. `/admin/organizations`, `/admin/members`, `/admin/invites` больше не используют внешний трехколоночный layout с зажатым центром:
   - top-level `WorkspaceFrame` теперь `sidebar + main`;
   - context/inspector живет внутри рабочей поверхности как inline inspector;
   - при нехватке ширины inspector уходит ниже, а не ломает таблицу;
3. `WorkspaceFrame` исправлен: режим `sidebar + main` больше не определяется как `workspaceFrameSingle`;
4. admin tables приведены к universal behavior:
   - компактные grid templates для desktop;
   - `min-width: 0` на ячейках;
   - на узких состояниях таблица превращается в читаемый one-column row list, а не обрезает колонки;
5. `/admin/access` переименован в `Роли и права`, чтобы пользователь не путал его с составом команды;
6. `/admin/invites` добавлен в shell-nav, чтобы прямой route не подсвечивал `Рабочее пространство`;
7. verification:
   - `npm --prefix frontend run build` OK;
   - production deploy OK, `/api/health` returns `{"ok":true}`;
   - `@browser-use` checked `/admin/organizations`, `/admin/members`, `/admin/invites`, `/admin/access`;
   - console errors absent on checked admin routes;
   - admin shell is active on all checked admin routes.

Third pass, 2026-04-28:

1. `/admin/members` simplified from table + duplicate inspector into one clear team list:
   - left sidebar remains organization picker;
   - center shows compact employee rows through shared `DataList`;
   - right inspector is hidden for the team mode because it duplicated selected-row information;
   - row content is identity, role, status, last login only;
2. `Default organization` renamed at source level to `Global Trade`:
   - `DEFAULT_ORGANIZATION_NAME` changed in backend control-plane seed;
   - production `org_default` updated to `Global Trade`;
3. production account cleanup completed after explicit user confirmation:
   - kept only `owner` / `owner@local.invalid`;
   - removed test `platform_users` and their memberships through cascade;
   - removed pending organization invites;
   - cleaned legacy auth users to one user;
   - control-plane backup tables created with tag `20260428_102824`;
   - auth JSON backups created under `backend/data/auth/*.cleanup_backup_20260428_102824.json` in `json_documents`;
4. verification:
   - `npm --prefix frontend run build` OK;
   - `PYTHONPATH=backend python3 -m py_compile backend/app/core/control_plane.py` OK;
   - production deploy OK, `/api/health` returns `{"ok":true}`;
   - database check shows:
     - `org_default` = `Global Trade`;
     - `platform_users` = 1;
     - `organization_members` = 1;
     - `organization_invites` = 0;
     - auth users = 1;
   - browser session was expectedly redirected to `/login?expired=1` because the current QA test user was deleted.

Fourth pass, 2026-04-28:

1. after explicit user confirmation one technical Codex QA user was created in `Global Trade`:
   - no extra test users should be created without a new explicit request;
   - current expected production users are `Owner` and `Codex QA`;
   - `org_default` remains `Global Trade`;
2. `/admin/members` spacing and search field were fixed:
   - admin page header now has a larger rhythm gap before tabs;
   - tabs have a stable lower margin before the workspace;
   - member search uses the same SaaS input styling as the rest of the admin surface;
   - placeholder is contextual: organization, employee, invite;
3. verification:
   - `npm --prefix frontend run build` OK;
   - production deploy OK, `/api/health` returns `{"ok":true}`;
   - direct API login as `Codex QA` OK;
   - `/api/platform/workspace/bootstrap?organization_id=org_default` returns `Global Trade` with two members: `Owner` and `Codex QA`;
   - `@browser-use` connection was attempted, but the plugin reported no active Codex browser pane, so visual verification must be repeated when browser-pane is available.

### 27.5 Parameter Values Workspace

Статус: first rework pass completed, browser-verified.

Проблема:

1. значения параметров сейчас нужно отдельно проверить, потому что визуально и логически там вероятен крах;
2. это критичный блок PIM, потому что товарные значения, источники, canonical values и marketplace alternatives должны быть понятны контент-менеджеру.

Будущая структура:

1. слева список параметров / групп параметров;
2. центр:
   - canonical value;
   - source values;
   - confidence / source evidence;
   - manual override;
3. справа:
   - marketplace display values;
   - альтернативные написания;
   - validation warnings;
4. обязательны:
   - origin tracking;
   - source badge;
   - manual value marker;
   - marketplace-specific output preview.

Acceptance:

1. контент-менеджер видит, откуда пришло значение;
2. контент-менеджер видит, какое значение станет PIM canonical;
3. контент-менеджер видит, как значение будет написано на каждой площадке;
4. длинные значения и dictionary values не ломают layout;
5. browser-check через `@browser-use`.

Execution status 2026-04-26:

1. `SourcesValueMappingSection` подключен в `SourcesMappingFeature` как отдельный tab `Значения`, а не как скрытый/неиспользуемый компонент;
2. URL contract: `/sources-mapping?tab=values&category=<category_id>`;
3. category name гидратируется из values API, поэтому верхний `Текущий контур` больше не остается в placeholder-state при direct URL;
4. values workspace уплотнен:
   - category tree;
   - field/dictionary list;
   - embedded dictionary editor;
   - sticky compact header;
5. embedded `DictionaryEditorFeature` получил compact value-header вместо общего page-header;
6. отключен mobile-collapse shell для рабочего desktop-продукта, чтобы в узком browser viewport меню не выталкивало рабочую область вниз;
7. production deploy выполнен;
8. `@browser-use` проверка на `https://pim.id-smart.ru/sources-mapping?tab=values&category=b2f026d9-a3e2-4821-9034-d17ac1b65065` прошла:
   - `Наушники` отображается как текущий контур;
   - `21 полей` загружается;
   - editor открывает `Value dictionary` для `SKU GT`;
   - действия `Добавить значение` и `Импорт значений` доступны;
   - console errors отсутствуют.

Ограничение:

1. это first-pass layout, не финальный high-end дизайн всего channel mapping;
2. следующий дизайнерский проход должен убрать старый hero/topbar `Маппинг каналов` и привести весь screen contract к рабочей плотности без декоративного intro.

### 27.6 Product Workspace Polish

Статус: base accepted, polish remains.

Что не ломать:

1. e-commerce-like карточка товара;
2. media/gallery;
3. workflow tabs;
4. readiness block;
5. общую структуру Product Workspace.

Что доделать позже:

1. мелкие визуальные выравнивания;
2. редактирование параметров;
3. сохранение manual override;
4. variants/cross-sell/analogs UX;
5. marketplace alternative values;
6. source evidence in parameters.

### 27.6.1 Product Creation Wizard

Дата: 2026-04-26.

Статус: first rework pass completed, browser-verified.

Роль страницы:

1. быстрый старт создания одного SKU или variant-family;
2. не заменяет полную карточку товара;
3. после создания пользователь должен перейти в `Product Workspace` и довести параметры, медиа, каналы, аналоги и валидацию.

Source / result:

1. source:
   - catalog category;
   - inherited info-model/template;
   - optional competitor/source links;
   - optional relations;
2. result:
   - один или несколько SKU;
   - product family для variants;
   - минимальный content payload;
   - transition в `/products/:id`.

States:

1. loading bootstrap;
2. bootstrap error;
3. base step empty;
4. base step with title/category;
5. single SKU mode;
6. multi SKU mode;
7. variants absent;
8. variants generated;
9. optional source links empty/filled;
10. content preview empty/filled;
11. relations empty/filled;
12. final review;
13. save error;
14. created success.

Tabs / steps:

1. `База`;
2. `Варианты`;
3. `Источники`;
4. `Контент`;
5. `Связи`;
6. `Проверка`.

Drawers / modals:

1. category picker modal;
2. variant parameter picker modal;
3. catalog product picker modal for analogs;
4. catalog product picker modal for related/cross-sell.

Universal blocks:

1. buttons use shared `.btn` visual contract;
2. inputs/selects use the existing product form contract;
3. modal contract remains feature-local for now, but must be replaced by shared `Modal` in a later cleanup;
4. product picker/category picker should later converge with shared catalog tree components.

Feature-level blocks:

1. `ProductCreationWizard`;
2. `VariantParamPicker`;
3. `CatalogProductPicker`;
4. `ProductCreationReview`.

Individual blocks:

1. orchestration of create/save flow only.

Что сделано:

1. `/products/new` оставлен на новом wizard-flow вместо длинной формы;
2. rail получил live summary:
   - category selected/not selected;
   - SKU count;
   - source links count;
3. topbar и card-density уплотнены под desktop workspace;
4. created-state получил правильный transition на `/products/:id`;
5. production deploy выполнен;
6. `@browser-use` проверка на `https://pim.id-smart.ru/products/new` прошла:
   - wizard загружается;
   - все 6 steps отображаются;
   - category modal открывается;
   - переход на step `Варианты` работает;
   - console errors отсутствуют.

Ограничения:

1. feature file still contains legacy local picker/modal primitives;
2. next cleanup should move picker/modal/forms to shared universal components;
3. desktop visual check был выполнен в доступном in-app browser viewport; полноценную широкую визуальную оценку нужно повторить после стабилизации browser viewport tooling.

### 27.7 Immediate Tasks Checklist

Ближайшие задачи:

1. перепроектировать `/catalog` по секции `20.12`;
2. реализовать новый компактный category workspace;
3. проверить `/catalog` через `@browser-use`;
4. обновить статус `20.12`;
5. затем перейти к `Navigation Shell / Menu`;
6. затем к `Parameter Values Workspace`.

## 28. E2E Product Flow: No Info-Model, Variants, Enrichment, Export Prep

Дата: 2026-04-27.

Статус: production e2e pass completed for test data.

Тестовый сценарий:

1. категория: `Дополненная реальность`;
2. marketplace category mappings уже были заданы:
   - `yandex_market`: `10972670`;
   - `ozon`: `type:17028915:97239`;
3. исходное состояние:
   - у категории не было собственной инфо-модели;
   - у категории не было attribute mapping rows;
   - товаров `Oculus / Meta Quest` не было;
4. создана draft-инфо-модель и attribute mapping на основе требований площадок;
5. создана variant-family `TEST Meta Quest 3`;
6. созданы два SKU:
   - `product_1089`: `TEST Meta Quest 3 128 ГБ`, `sku_gt=53423`;
   - `product_1090`: `TEST Meta Quest 3 256 ГБ`, `sku_gt=53424`;
7. оба SKU заполнены контентом:
   - title;
   - brand;
   - description;
   - S3 media URL через `/api/uploads/...`;
   - category attributes;
   - marketplace export values;
8. создан export-run:
   - `export_de4962061d`;
   - Я.Маркет: 3 stores, все `2/2 ready`;
   - Ozon: 1 store, `2/2 ready`;
9. проверка в браузере:
   - `/products/product_1089`;
   - карточка открывается;
   - бренд отображается как `Meta`;
   - сообщение `Бренд не задан` устранено.

### 28.1 Correct No-Info-Model Behavior

Если пользователь создает или импортирует товар в категорию без инфо-модели, система не должна блокировать создание товара.

Правильный порядок:

1. товар можно создать или импортировать сразу;
2. система проверяет категорию;
3. если у категории есть marketplace category mapping, но нет инфо-модели:
   - создается draft-инфо-модель;
   - draft строится из base fields, marketplace required fields, imported/source fields и variant dimensions;
   - все поля маркируются source-aware;
4. если marketplace category mapping отсутствует:
   - товар создается;
   - экспорт получает явный blocker `Нет сопоставления категории`;
   - пользователь переводится в mapping workflow;
5. если инфо-модель есть, но нет attribute mapping:
   - параметры товара заполняются;
   - export preview показывает blocker по несопоставленным обязательным параметрам;
6. если нет ни модели, ни mapping:
   - импорт/создание товара не падают;
   - система создает минимальный content payload;
   - workflow показывает следующий обязательный шаг: `Создать модель / сопоставить параметры`.

Важно:

1. инфо-модель является contract для параметров и экспорта, но не должна быть hard-blocker для создания SKU;
2. товары остаются главной сущностью;
3. варианты являются отдельными SKU, объединенными через product group;
4. одна запись товара равна одному SKU;
5. `storage`, `color`, `sim`, `region` и похожие признаки должны быть variant dimensions, если по ним меняется SKU.

### 28.2 Test Draft Info-Model

Для `Дополненная реальность` создана модель:

1. `Наименование товара`;
2. `Бренд`;
3. `Описание товара`;
4. `Картинки`;
5. `Тип`;
6. `Название модели`;
7. `Встроенная память`;
8. `Цвет`;
9. `Назначение`;
10. `Общее разрешение`;
11. `Разрешение для каждого глаза`;
12. `Частота обновления`;
13. `Беспроводные интерфейсы`;
14. `Разъемы и интерфейсы`;
15. `Комплектация`;
16. `Вес устройства, г`;
17. `Гарантийный срок`;
18. `Страна производства`.

Variant dimension:

1. `Встроенная память`;
2. test values:
   - `128 ГБ`;
   - `256 ГБ`.

### 28.3 Export Prep Rules

Я.Маркет:

1. preview endpoint: `/api/yandex-market/export/preview`;
2. общий export-run: `/api/catalog/exchange/export/run`;
3. readiness проверяет:
   - offer id / SKU GT;
   - title;
   - vendor;
   - market category id;
   - pictures;
   - description;
   - required marketplace parameters;
4. для тестовых Quest SKU результат: `ready_count=2`, `missing=[]`.

Ozon:

1. добавлен backend preview внутри `/api/catalog/exchange/export/run`;
2. preview пока не отправляет товар на Ozon;
3. readiness проверяет:
   - offer id / SKU GT;
   - Ozon category id;
   - title;
   - images;
   - обязательный `Тип`;
   - обязательный `Бренд`;
   - обязательный `Название модели`;
4. для тестовых Quest SKU результат: `ready_count=2`, `missing=[]`.

Что еще нужно довести:

1. выделить Ozon preview в отдельный публичный route, аналогичный Я.Маркет;
2. добавить UI просмотра Ozon payload;
3. добавить validation для абсолютных публичных media URLs;
4. добавить value mapping UI для альтернативных значений:
   - `128 ГБ` -> marketplace-specific value;
   - `256 ГБ` -> marketplace-specific value;
   - `шлем VR` -> `VR-очки` для Ozon, если такая нормализация нужна;
5. показывать source evidence:
   - manual;
   - XLS import;
   - marketplace import;
   - competitor parser;
6. не смешивать source value и export value в одном поле UI.

### 28.4 Code Changes From E2E

Backend:

1. `backend/app/api/routes/catalog_exchange.py`
   - добавлен Ozon export preview;
   - Ozon batch больше не возвращает `not_implemented`;
   - общий export-run теперь может показать Ozon readiness and payload preview;
2. `backend/app/api/routes/product_groups.py`
   - исправлен missing import `write_doc`, из-за которого создание группы товаров падало.

Frontend:

1. `frontend/src/features/products/ProductWorkspaceFeature.tsx`
   - бренд в карточке товара теперь берется из feature `brand/Бренд`;
   - fallback по title оставлен только если параметр бренда отсутствует;
   - добавлены fallback brands `Meta`, `Oculus`.

### 28.5 UX Implications

Карточка товара должна показывать не просто список параметров, а рабочий pipeline content manager:

1. `Сводка`: что заполнено и что мешает экспорту;
2. `Параметры`: canonical values, source values, conflicts;
3. `Источники`: XLS, marketplace import, competitor parser;
4. `Площадки`: как canonical values превратятся в значения Я.Маркет/Ozon;
5. `Конкуренты`: candidates, accepted/rejected/manual links;
6. `Медиа`: S3 assets and readiness;
7. `Валидация`: blockers per marketplace;
8. `Варианты`: SKU-family and variant dimensions.

Для `catalog`:

1. каталог должен оставаться чистым экраном структуры и финального списка SKU;
2. черновые и грязные операции должны уходить в:
   - imports;
   - mappings;
   - parameter values;
   - product workspace;
   - export validation;
3. каталог не должен показывать пользователю низкоуровневый technical context без действия.

## 29. Operating Workflows And Connector Readiness

Дата: 2026-04-27.

Статус: in progress; first connector readiness pass deployed and browser-checked on production; 2026-04-28 начат second pass по упрощению `/connectors/status`.

Проблема:

1. система содержит функциональные куски, но пользователь не видит три главных пути работы;
2. `/connectors/status` показывает технический health-log, а не готовность источников для PIM;
3. ошибки API выводятся как raw backend text;
4. тесты пока не покрывают реальные операционные сценарии end-to-end.

### 29.1 Required User Journeys

#### Journey A: New Category / No Info-Model / No Products

Цель: завести новый контур с нуля.

Acceptance flow:

1. пользователь создает или выбирает категорию;
2. система показывает readiness:
   - нет инфо-модели;
   - есть/нет category mapping;
   - есть/нет marketplace parameter cache;
   - есть/нет источники competitors;
3. пользователь запускает `Создать draft-модель`;
4. draft-модель создается из:
   - base fields;
   - marketplace required fields;
   - imported/source fields;
   - variant dimensions;
5. пользователь подтверждает модель;
6. пользователь создает SKU или импортирует XLS;
7. система подбирает competitor candidates;
8. пользователь принимает/отклоняет candidates;
9. система насыщает товар;
10. пользователь проверяет channel output values;
11. export preview показывает ready/blockers по Я.Маркет и Ozon.

Required tests:

1. category has no template -> create draft model -> template exists;
2. category has marketplace mapping -> generated attributes include required marketplace fields;
3. product can be created before model approval;
4. export preview blocks until mapping/content is ready;
5. after fill, export preview returns ready.

#### Journey B: Approved Info-Model Exists

Цель: быстро завести новый товар по готовому контракту.

Acceptance flow:

1. пользователь выбирает категорию;
2. UI показывает `Модель утверждена`;
3. product creation wizard получает skeleton параметров;
4. пользователь создает один SKU или variant-family;
5. карточка товара показывает:
   - required fields;
   - optional fields;
   - source evidence;
   - marketplace output values;
6. export preview показывает blockers only for real missing values.

Required tests:

1. approved template -> wizard shows required fields;
2. variant dimensions create separate SKU records in one group;
3. canonical value and marketplace output value stay separate;
4. product card shows source evidence without duplicating rows.

#### Journey C: Existing Catalog Enrichment

Цель: насытить уже загруженные товары.

Acceptance flow:

1. пользователь выбирает ветку или список SKU;
2. запускает enrichment:
   - marketplace import;
   - XLS import;
   - competitor parser;
3. система показывает result queue:
   - filled;
   - conflicts;
   - no source found;
   - needs manual link;
4. content manager подтверждает или исправляет значения;
5. карточка товара обновляет canonical values;
6. export preview пересчитывается.

Required tests:

1. enrichment run on selected product ids;
2. conflict is created when two sources disagree;
3. conflict resolution updates canonical value;
4. rejected competitor candidates do not overwrite product values;
5. export preview sees resolved canonical values.

### 29.2 Connector Page Redesign

Новая роль `/connectors/status`:

1. не технический лог;
2. operational readiness for PIM sources;
3. показывает, что готово для трех journeys.

Above-the-fold:

1. `Подключения`: магазины и credentials;
2. `Категории`: category tree import;
3. `Параметры и модели`: marketplace attribute import;
4. `Товары и экспорт`: product content/status/export readiness.

Issue model:

1. raw backend error должен быть свернут;
2. пользователь видит human-readable blocker;
3. рядом показывается impact:
   - блокирует draft-модель;
   - блокирует attribute mapping;
   - блокирует enrichment;
   - блокирует media generation;
   - не блокирует export.

Provider section:

1. карточка провайдера показывает статус и магазины;
2. методы синхронизации идут компактным списком;
3. расписание остается доступным, но не доминирует экран;
4. destructive actions remain explicit.

### 29.3 Immediate Implementation Order

1. First pass `/connectors/status` layout. Status: done.
2. Add connector readiness helpers in frontend only. Status: done.
3. Browser-check `/connectors/status`. Status: done on production, 2026-04-27.
4. Then create backend/frontend tests for:
   - no-model draft path. Status: backend acceptance test added.
   - product creation with approved model. Status: backend acceptance test added.
   - existing catalog enrichment. Status: backend acceptance test added.
   - connector error normalization. Status: frontend helper extracted and covered by Vitest unit tests.

### 29.4 Connector Status Second Pass

Дата: 2026-04-28.

Причина: production browser-check showed `/connectors/status` still looked like a technical log: readiness cards collapsed, page had too many competing blocks, raw connector details dominated the first screen.

UX target:

1. above-the-fold is a clean SaaS command center, not a diagnostics dump;
2. user sees only four readiness groups first:
   - `Доступы`;
   - `Категории`;
   - `Параметры`;
   - `Товары`;
3. right inspector shows next action/blockers;
4. provider sections stay below and are compact;
5. store credentials are cards inside the provider;
6. method schedule/raw errors are hidden in expandable details;
7. layout must not collapse in narrow in-app browser widths;
8. animation is subtle: panel reveal, hover lift, status pulse.

Implementation status:

1. `ConnectorsStatusFeature` rebuilt as command-center layout. Status: done.
2. `connectors-status.css` replaced with responsive provider/readiness styles. Status: done.
3. Build verification. Status: done locally, `npm --prefix frontend run build`.
4. Production deploy. Status: done, health `{"ok":true}`.
5. Browser-use verification on `https://pim.id-smart.ru/connectors/status`. Status: done for DOM/content and console errors; screenshot capture in in-app browser timed out twice.
6. Commit/push after verification. Status: pending.

Verification:

1. `python3 backend/tests/test_operating_workflows.py` - 5 tests OK.
2. `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_*.py'` - 59 tests OK.
3. `npm --prefix frontend run build` - OK after extracting connector readiness helpers.
4. `npm --prefix frontend test` - 1 file / 4 tests OK for connector readiness helper.

### 30. Sources Mapping: Competitor Category Context

Problem found on `https://pim.id-smart.ru/sources-mapping?category=b6e03b97-a484-4f79-8d44-27e856fc2c41`:

1. screen title says `Каналы и источники`, but category tab explains only marketplace category mapping;
2. `re-store` and `store77` are hidden behind a separate competitors tab and are not visible in the category binding context;
3. user cannot understand which competitor sections/searches feed enrichment for the selected PIM branch;
4. current UI makes marketplace category binding, parameter mapping, value mapping, and competitor discovery feel like unrelated tools.

Decision:

1. keep `Категории и источники` as the category binding workspace;
2. left side remains PIM category tree;
3. center remains marketplace category binding for `Я.Маркет` and `Ozon`;
4. right side must show competitor source context for the selected category:
   - `re-store`;
   - `store77`;
   - products in selected category subtree;
   - confirmed competitor links;
   - candidates waiting for moderation;
   - observed competitor section/search URL suggestions;
5. no live external crawl on page open: category page must be fast and deterministic;
6. live crawling stays in discovery runs; category context uses persisted candidates/links plus safe fallback search URLs.

Implementation status:

1. backend read endpoint added:
   - `GET /api/competitor-mapping/discovery/categories/{category_id}`;
   - returns selected category, SKU count, source summaries, observed suggestions, fallback search suggestions;
2. frontend category mapping side panel added through existing `SourcesMarketplaceSection.renderCategoryDetailExtra`;
3. no duplicate standalone local competitor UI introduced;
4. frontend build verified;
5. backend py-compile verified;
6. targeted backend test added for category competitor source summary.
7. compact layout fix added after browser/screenshot review:
   - competitor context is a right inspector, not a full-width block below marketplace cards;
   - legacy `height: 100%` and `display: contents` provider-card rules are overridden inside `sourcesMappingPage`;
   - marketplace cards stay compact and competitor cards do not stretch the page.

Next page-pass requirements:

1. browser-check full-width desktop layout for `/sources-mapping`;
2. make page explicitly say:
   - `Маркетплейсы` = куда выгружаем;
   - `Конкуренты` = откуда берем enrichment evidence;
3. move competitor discovery queue into its own operational tab, not into category binding center;
4. ensure category context works for empty categories:
   - shows `0 SKU`;
   - shows fallback search;
   - does not imply data has already been parsed;
5. add run action scoped to selected category subtree:
   - start discovery for products in this category;
   - after run, update right-side context.
