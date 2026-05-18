# SmartPim Active Tasks

This is the only active task/backlog document.

Do not create separate `.md` plans, specs, notes, or task lists. Add every new task here by priority.

## Current Baseline

1. Production is deployed at `https://pim.id-smart.ru`.
2. Active organization is `org_default / Global Trade`.
3. Auth/admin schema is consolidated into relational tables: `users`, `roles`, `organizations`, `organization_members`, `organization_invites`.
   - active auth state must not be overwritten by legacy `backend/data/auth/access.json` during bootstrap/migration;
   - legacy auth JSON is migration fallback only, not runtime source of truth.
4. Competitor workflow no longer uses JSON as active source of truth:
   - product candidates, confirmed links, rejected links, stale links, moderation evidence, and category/template competitor mappings live in `pim_channel_links`;
   - discovery run polling/state lives in `pim_workflow_runs`;
   - production cleanup verified on 2026-05-12: `competitor_mapping.json` and `competitor_mapping_org_default.json` have `categories=0`, `templates=0`, `candidates=0`, `links=0`, `runs=0`.
5. Current production competitor rows:
   - `pim_channel_links`, scope `competitor_product`: `candidate=67`, `stale=17`, `rejected=2`, `confirmed=1`;
   - `pim_channel_links`, scope `competitor_mapping`: `category=3`, `template=9`;
   - `pim_workflow_runs`, workflow `competitor_discovery`: `completed=40`, `queued=7`, `running=7`.
6. Marketplace/model data exists for `Смартфоны`:
   - category has 431 SKU in branch;
   - info-model/editor shows 84 fields;
   - current source counts: `Ozon 49`, `Я.Маркет 69`.
7. Known product workflow issue: competitor matching quality still needs iteration; interface is closer but not final.

## Non-Negotiable Work Rules

1. Work by vertical user path, not isolated technical pages.
2. Every page/tab touched must have one clear user job.
3. Universal components and layouts must be reused; no local duplicate catalog/tree/table/button implementations unless explicitly justified.
4. Browser QA is required for frontend changes. Prefer Browser/in-app browser. If bridge is unavailable, record the blocker and run available HTTP/build checks.
5. After Playwright/browser automation work, close browser/processes.
6. For backend/DB changes, verify frontend contract, backend contract, and actual production DB state when production data is involved.
7. After meaningful work: run checks, deploy when needed, commit, and push.

## Current P0 Goal

Complete the `Смартфоны` pipeline until the product data can be prepared for real export without explanation from the developer.

Target path:

1. Open `Сводка` and see blocking tasks for the category.
2. Open `Инфо-модели`.
3. Select category `Смартфоны`.
4. Confirm the info-model fields are understandable and complete.
5. Open category/source mapping.
6. Confirm marketplace categories for `Я.Маркет` and `Ozon`.
7. Confirm competitor category context for `re-store` and `store77`.
8. Open parameter mapping.
9. Match PIM fields to marketplace fields.
10. Open value mapping.
11. Normalize marketplace output values.
12. Pick SKU in `Смартфоны`.
13. Scan competitor product cards.
14. Confirm/reject competitor candidates.
15. Enrich SKU parameters/media/evidence from confirmed partner/competitor product cards.
16. Open product card and verify the content-manager view is readable.
17. Open export.
18. Validate readiness for `Я.Маркет` and `Ozon`.
19. Export or clearly show remaining blockers.

Success criteria:

1. User can understand the next action on every screen without developer explanation.
2. No duplicated headers, duplicated counters, duplicated action blocks, or unexplained technical labels.
3. Category context persists across info-model, mapping, products, import, and export routes.
4. Tables with many columns have fixed horizontal scroll behavior.
5. Long names do not overlap counters, badges, buttons, or adjacent columns.
6. Competitor workflow clearly separates:
   - competitor category/branch context;
   - exact competitor product-card links per SKU;
   - parameter/value evidence extracted from confirmed product-card links.
7. Export readiness says what is ready, what blocks export, and where to fix it.

## Active Tasks

### P0.1 Pipeline Audit For `Смартфоны`

Status: active.

Current category:

1. `Смартфоны`: `bb40de87-254b-4170-84d7-8e5d3925b251`.
2. Browser audit started on 2026-05-12 after auth migration fix.
3. First blocker found and fixed: legacy `backend/data/auth/access.json` could overwrite relational user password hashes during bootstrap. Runtime auth state must stay relational.

Routes to check:

1. `/`
2. `/templates`
3. `/templates/<smartphones-template-or-category-id>`
4. `/sources?tab=sources&category=<smartphones-category-id>`
5. `/sources?tab=params&category=<smartphones-category-id>`
6. `/sources?tab=values&category=<smartphones-category-id>`
7. `/catalog?category=<smartphones-category-id>`
8. `/products?category=<smartphones-category-id>`
9. `/products/<sample-smartphone-product-id>`
10. `/catalog/import?category=<smartphones-category-id>`
11. `/catalog/export?category=<smartphones-category-id>`

Checklist:

1. Record UX score from 1 to 10 for each route.
2. Record buttons used and unused.
3. Record duplicated blocks and labels.
4. Record broken layout, overlap, excessive empty space, and unreadable text.
5. Record missing backend/DB state if the UI shows impossible or contradictory data.
6. Fix critical blockers immediately.
7. Add non-critical findings back into this document under the right priority.

Audit findings to verify/fix:

0. 2026-05-17 async/layout audit, routes `/catalog`, `/sources?tab=sources`, `/sources?tab=params`:
   - Browser visual proof: in-app Browser opened the current production `params` route, and the page collapsed into a narrow column although the product is desktop-only;
   - root cause: sources mapping CSS used viewport breakpoints that stacked the command/header/cards at narrow browser-pane widths instead of preserving a desktop workspace with horizontal scroll;
   - fixed: `sourcesMappingPage` now has a desktop minimum width and horizontal scroll through shell content; `params` layout no longer collapses to one column at `1180px`;
   - fixed: `catalogWorkspacePage` uses the same desktop-min-width policy, so the catalog tree/table workspace no longer collapses into a narrow mobile-like column;
   - fixed: product registry no longer shows `Товары не найдены` while a request/search is still loading;
   - fixed: competitor scan counter no longer says `нет SKU для скана` while branch SKU are loading;
   - fixed: parameter mapping no longer shows `нет полей инфо-модели` / zero tabs / empty queue while the category attribute request is still loading;
   - verified on production via in-app Browser at `485x837` browser pane:
     - `/sources?tab=params&category=bb40de87-254b-4170-84d7-8e5d3925b251`: page width `1180`, hero width `1124`, params grid `752px 360px`, no false `нет полей`;
     - `/sources?tab=sources&category=bb40de87-254b-4170-84d7-8e5d3925b251`: page width `1180`, hero width `1124`, no false `нет SKU для скана`;
     - `/catalog?category=bb40de87-254b-4170-84d7-8e5d3925b251`: page width `1180`, frame grid `390px 720px`, no false `Товары не найдены` with `431`.

0. 2026-05-17 catalog cleanup, route `/catalog?category=bb40de87-254b-4170-84d7-8e5d3925b251`:
   - problem: selected-category header and SKU table header duplicated the same category context and counters, pushing the real product table down;
   - fixed: category title, status, branch counters, primary category actions, and product registry now live in one `catalogProductsWorkspace` card;
   - removed stale CSS for the deleted duplicated category summary card;
   - verified on production via in-app Browser:
     - old repeated text `Выбранная категория` is gone;
     - category context is a single line `Каталог / Смартфоны`;
     - the SKU list starts immediately under the compact category header.
   - fixed: group filter no longer receives global project groups from `/catalog/products-page-data`; backend now returns group facets for the current category/filter scope with SKU counts;
   - verified on production via in-app Browser for `Смартфоны`: filter options reduced to `29`, scoped to smartphone groups, with counts, and irrelevant global groups such as `MacBook` are absent.

0. 2026-05-17 cross-functional team audit, production Browser routes `/catalog`, `/sources?tab=sources`, `/sources?tab=params`, `/sources?tab=values`, `/products/product_1091`, `/catalog/exchange?tab=export`:
   - Overall verdict: the project is no longer visually broken on the critical screens, but it is still not yet a self-explanatory SaaS workflow for a new team. The biggest remaining problem is not one page; it is the missing cross-screen state of “what is the next action for this category/SKU”.
   - Product owner finding:
     - P0: add a persistent category/SKU work queue that follows the user from catalog to info-model, sources, parameters, values, product card, and export;
     - the queue must show one current blocker and one next action, for example `сопоставить категорию Ozon`, `подтвердить 5 карточек конкурентов`, `закрыть 3 обязательных поля`, `добавить медиа`, `проверить выгрузку`;
     - pages must stop behaving as independent tools and start behaving as one conveyor for `импортировать товары -> сгруппировать -> сопоставить категории -> собрать модель -> сопоставить параметры/значения -> насытить -> выгрузить`.
   - Designer finding:
     - P0: unify the workspace primitives across catalog, sources, params, values, product card, and export: one header pattern, one tab strip pattern, one tree pattern, one toolbar/search/filter pattern, one table/list pattern, one inspector pattern;
     - current screenshots still show different density and button hierarchy between catalog, sources, values, and export;
     - destructive/secondary actions such as delete/rename/subcategory should move behind quieter controls or an overflow menu when they are not the primary job.
   - Content-manager finding:
     - P0: replace explanatory text blocks with actionable states and evidence;
     - product card and mapping screens must show `PIM field -> selected value -> source evidence -> marketplace output value -> status` without forcing the user to infer it from separate tabs;
     - values screen needs `fix next` mode: show only fields that block export first, then ready fields by request.
   - Frontend developer finding:
     - P0: split large page components before adding more behavior. `ProductRegistry`, `SourcesMarketplaceSection`, params/value mapping sections, and product workspace should be decomposed into reusable containers and shared primitives;
     - current CSS still has many page-specific files for similar layout jobs, so every page cleanup risks creating another local solution;
     - route-level loading/empty/error states must be standardized to avoid false empty states returning in new screens.
   - Backend developer finding:
     - P0: introduce explicit page contract objects for pipeline screens instead of assembling UI state from many independent endpoints;
     - `products-page-data`, sources mapping, parameter mapping, value mapping, and export readiness should return workflow state, warnings, and next actions consistently;
     - fallbacks that hide backend errors must also return a visible warning/metric, otherwise UI can silently show plausible but wrong data.
   - DB architect finding:
     - P0: formalize read models and source-of-truth ownership per route;
     - `catalog_product_page_tenant_rel` is now a real read model used by catalog/product filters and should have documented refresh semantics, source tables, and invalidation rules;
     - canonical attributes must stay global across categories, with uniqueness/merge rules for memory, RAM, SIM type, color, model, dimensions, OS, and marketplace dictionaries;
     - source evidence needs a clearly owned relational path: competitor category mapping -> competitor product link -> extracted raw values/media -> canonical product values -> marketplace value mapping -> export payload.
   - New implementation priority from this audit:
     - P0.1: create shared `WorkspaceHeader`, `WorkspaceTabs`, `WorkspaceTreePanel`, `WorkspaceToolbar`, `WorkspaceInspector`, and `TaskQueue/NextAction` primitives, then retrofit current heavy screens to them;
     - P0.2: add category/SKU pipeline state API and show it in catalog, sources, product card, and export;
     - P0.3: make `/sources?tab=sources` a competitor-card confirmation workspace, not a mixed explanation/source page;
     - P0.4: make `/sources?tab=params` and `/sources?tab=values` operate from blocker queues by default;
     - P0.5: add route-to-table map and response-contract tests for catalog, sources, product card, and export before continuing broad UI changes.
   - P0.1 progress on 2026-05-18:
     - added shared frontend primitive `WorkspaceHeader` for title/context/badges/actions/tabs;
     - added shared frontend primitive `WorkspaceTaskQueue` for a visible next-action lane;
     - `/catalog` now uses `WorkspaceHeader` with the same header density as other workspaces;
     - `/catalog` now shows a compact route from selected category to SKU creation/import, source mapping, and export;
     - `/sources?tab=sources|params|values` now uses the same `WorkspaceHeader` and tab primitive instead of its own local hero/tab implementation;
     - `/sources?tab=sources|params|values` now shows one route: categories/competitors -> params -> values -> export;
     - deployed and Browser-verified on production:
       - `/catalog?category=bb40de87-254b-4170-84d7-8e5d3925b251`: no old `.page-header`, product table remains visible, no horizontal overflow;
       - `/sources?tab=sources|params|values&category=bb40de87-254b-4170-84d7-8e5d3925b251`: no old `.sourcesMappingHero`, shared tabs render through `WorkspaceHeader`, no horizontal overflow;
       - `WorkspaceTaskQueue` was compacted after Browser QA: height is `76-84px`, not a tall dashboard block, and work areas start at `y=233` for catalog and `y=291` for sources routes at the current browser pane;
     - next: move catalog/source tree, toolbar/search/filter, inspector, and next-action queue into shared primitives.

0. 2026-05-17 product-manager UX audit, route `создать товар -> наполнить -> проверить -> выгрузить`:
   - Browser status: in-app Browser pane was unavailable (`No active Codex browser pane available`), so visual QA was done through authenticated Playwright fallback against production as owner in `Global Trade`.
   - Overall clarity for a new product manager: `6/10`.
   - The interface is readable screen-by-screen, but it still does not behave like one guided workflow for the job “заведи новый товар и выложи его на площадку”.
   - `/` score `6.5/10`: useful metrics and quick actions exist, but the dashboard mixes summary, queues, readiness, operations, and source problems without one primary “continue work” lane for the manager.
   - `/products/new` score `7/10`: the creation wizard is the clearest part; still needs stronger post-create promise: after SKU creation user must land in a product card checklist with exact next actions.
   - `/products` score `6.5/10`: good product table and inspector, but too many filters are visible before the user understands the job; inspector actions are useful but not framed as a pipeline.
   - `/catalog` score `6/10`: structure is cleaner, but selected category `Аксессуары` shows contradictory `63 SKU` while table says `0`; this destroys trust and must be fixed before real filling.
   - `/templates` score `5.5/10`: category tree is still too dominant and shows many `ПУСТО`; new user cannot tell whether they should create a model here or first go through marketplace/category sources.
   - `/sources?tab=sources` score `5.5/10`: the competitor block is more understandable than before, but for `Смартфоны` it says no SKU in category because it checks direct category products rather than branch products; user cannot proceed.
   - `/sources?tab=params` score `7/10`: the “attention / ready / all” layout is close to usable; still too technical around `0/2 источников`, `параметр`, and field cards.
   - `/sources?tab=values` score `6.5/10`: concept is understandable, but the amount of rows/statuses is high and there is no compressed “fix next 10 blockers” queue.
   - `/catalog/exchange?tab=export` score `7/10`: export target selection is now much clearer; keep `GT USD` and `Ozon` selected-only behavior and avoid accidental broad exports.
   - Required product-manager workflow change:
     - 2026-05-17 fixed: after creating SKU/family, the user now lands in the product card on `tab=competitors&created=1`, and the persistent checklist explains that the next step is competitor-card confirmation before parameters/media/export;
     - product card checklist must stay persistent and continue to cover: `Конкуренты`, `Параметры`, `Медиа`, `Экспорт`;
     - each checklist item must have one action and one state, for example `Открыть сопоставление`, `Подобрать карточки`, `Заполнить медиа`, `Проверить выгрузку`;
     - dashboard should show one primary work lane: `Продолжить товар`, `Создать товар`, `Импортировать товары`, `Проверить экспорт`;
     - 2026-05-17 fixed in UI copy: source/competitor matching now says it uses SKU from the selected branch, not only direct category SKU; the scan counter is labeled as a scan sample (`до 250 SKU`), not the full category total;
     - 2026-05-17 fixed in catalog copy: product workspace title is `SKU в выбранной ветке`, with `прямо здесь` shown only as a secondary counter;
     - remaining verification: re-run Browser QA and confirm backend response for parent categories always returns branch `sample_products`.

0. 2026-05-17 pipeline audit scorecard, creation -> category -> card -> export:
   - Browser QA status: blocked by unavailable in-app Browser pane (`No active Codex browser pane available`); current score is based on production API/DB diagnostics and code audit, not visual proof.
   - Product creation UX: `7/10`. Improved because the wizard is now short and variants become real SKU rows. 2026-05-17: family creation was moved behind one backend operation, so the frontend no longer creates group/products/patches as separate user-path steps.
   - Category assignment: `7/10`. Created SKU rows receive `category_id`; existing `product_3` is correctly in a child smartphone category and still reachable through the smartphone branch, but category context between root branch and child leaf must be clearer in UI.
   - Product variant card: `7/10`. `product_3` shows `group_37` with `27` SKU variants, but the variants tab still needs clearer primary actions: open group, add missing SKU, compare variant values.
   - Parameter/enrichment view: `7/10`. `product_3` has `73` features, `120` source values, and parameter-flow summary `34 ready / 22 attention / 17 empty`; this is usable but still needs a focused attention queue.
   - Competitor/source matching: `5.5/10`. The distinction between competitor category context and exact product-card source is still the weakest part of the flow.
   - Media: `7/10`. S3-backed media works for the sample SKU (`4` images), but media role/selection/quality state must be easier to understand directly in the product card.
   - Export readiness: `7.5/10`. Single-SKU export path is technically ready for the verified SKU, but the UI still needs stronger protection against accidental broad category exports.
   - Overall project readiness for real filling: `6.5/10`. The vertical path exists and is improving, but the project is not yet “self-explanatory” for a content manager.
   - Next P0 growth points:
     - make category context explicit everywhere: selected leaf category, parent branch, and why product appears in the parent branch;
     - add an attention queue for `parameter-flow`: only rows with missing marketplace mapping or missing value first;
     - audit suspect marketplace mappings for smartphones, especially Ozon memory/model fields;
     - restore Browser QA and re-score the same path visually before calling this block complete.

0. 2026-05-17 production reset checkpoint for info-model/product recreation:
   - Baseline before reset:
     - active info-model/template count: `6`;
     - selected control product: `product_4`;
     - title: `Смартфон Apple iPhone 17 Pro 512Gb eSIM Silver (Global)`;
     - category: `a29cf263-1bf1-4cb2-b3bb-eeaa7c88b3e4`;
     - SKU GT: `52464`;
     - group: `group_37`;
     - product features: `73`;
     - media images: `0`.
   - Snapshot was written on the production server before destructive changes:
     - `/tmp/smartpim_rebuild_snapshot_product_4_1779017670.json`.
   - Action performed:
     - all active info-model templates were cleared;
     - `product_4` was deleted through backend product deletion;
     - info-model for the selected product category was rebuilt from `products + marketplaces`;
     - rebuilt template id: `9931bac5-8c4d-4b14-bfa3-5112485e01ef`;
     - rebuilt template attributes: `71`;
     - selected product was recreated from captured product content and restored into `group_37`.
   - Result after reset:
     - active info-model/template count: `1`;
     - old product `product_4`: deleted and no longer resolvable;
     - recreated product id: `product_1091`;
     - recreated title: `Смартфон Apple iPhone 17 Pro 512Gb eSIM Silver (Global)`;
     - recreated SKU GT: `52464`;
     - recreated group: `group_37`;
     - recreated product features: `73`;
     - recreated media images: `0`;
     - `group_37` still contains `27` products;
     - `group_37` contains `product_1091` and no longer contains `product_4`.
   - Recreated product parameter-flow summary:
     - `features_total=73`;
     - `features_ready=34`;
     - `features_attention=22`;
     - `features_empty=17`;
     - `source_values=57`;
     - `service_rows=4`.
   - Immediate comparison finding:
     - product data survived recreation when content snapshot was reused, but product id changed from `product_4` to `product_1091`; any old deep links to `product_4` now break;
     - deleting all info-models leaves only the rebuilt leaf-category model, so inherited category/model behavior must be retested before real filling;
     - the recreated model has `71` approved attributes while the recreated product still carries `73` feature rows, so the next audit must compare model fields versus product fields and explain/drop/merge the extra rows.

0. 2026-05-17 global attribute reuse rule:
   - info-model fields must be approved as references to global attributes, not as isolated category-local copies;
   - shared parameters such as `Встроенная память` and `Оперативная память` must have one canonical `attribute_id` and one `dict_id` reused by smartphones, tablets, laptops, VR devices, and any other category;
   - synonyms from products/marketplaces/competitors must normalize before approval, for example `Объем встроенной памяти`, `Внутренняя память`, `storage`, `ROM` -> `Встроенная память`, and `Объем оперативной памяти`, `RAM` -> `Оперативная память`;
   - implemented first backend guardrail in `draft_service.approve_draft`: accepted candidates now call `ensure_global_attribute`, write `attribute_id/options.dict_id`, and collapse accepted synonyms into one template attribute;
   - next validation: run real smartphone/tablet model rebuild comparison and verify no duplicate memory/RAM attributes are created across categories.

0. 2026-05-16 product creation and variants:
   - `/products/new` must be a short SKU creation workflow, not a full product-card editor;
   - single product creation creates one real product row and opens its product card;
   - variant creation creates one real product row per SKU, creates a product group, assigns all variant SKU rows to that group, and opens the first SKU on the `Варианты` tab;
   - 2026-05-17 implemented `/api/products/create-family`: single SKU and variant families are now created through one backend operation; frontend wizard sends one payload and navigates to the first created SKU;
   - backend test coverage exists for the single-operation family creation path;
   - 2026-05-17 product card now has a next-action panel after creation/current load: `подобрать карточки конкурентов`, `проверить параметры`, `проверить медиа`, `подготовить выгрузку`;
   - competitor matching is now a first-class product-card tab, so the next-action card opens the real moderation/enrichment workspace instead of scattered external-link fields;
   - enrichment, media, description, analogs, related products, and export readiness belong in the product card after creation, not in the creation wizard;
   - verify that variant groups are visible from the product card and product groups page after creation.

0. 2026-05-16 end-to-end check:
   - production data exists: `272` catalog categories, `121` category product counters, `6` info-models;
   - `Смартфоны` info-model has `84` fields and no duplicate field names/codes in backend data;
   - `product_3 / SKU GT 52462` has a confirmed Store77 product-card link and 4 S3-backed Store77 images;
   - product media lacked explicit `role/selected/status` metadata, and product content lacked normalized `competitor_links`;
   - fixed in backend enrichment path: confirmed donor links are written to `content.competitor_links`, imported media is marked as selected ready gallery media, and approved candidate rows are no longer persisted as canonical confirmed links.
   - export page readiness check for one SKU passes for `GT USD` and `Ozon` with `2` ready target rows and `0` blockers;
   - fixed export initial loading state so the UI no longer briefly shows false `0 узлов / нет каналов` before async data arrives.

1. `/catalog?category=bb40de87-254b-4170-84d7-8e5d3925b251`
   - opens authenticated;
   - selected category context works;
   - shows `431 SKU в ветке` and `4 подкатегорий`;
   - category tree no longer overlaps counters at 1920px;
   - left menu overlay can still consume workspace and must be checked collapsed/pinned.
2. `/templates/bb40de87-254b-4170-84d7-8e5d3925b251`
   - opens authenticated;
   - model has `84` fields and source summary `Я.Маркет 69`;
   - field list is very long and needs continued visual confirmation for readability, labels, action density, and duplicate controls.
   - Browser audit on 2026-05-14 found duplicated context across `PageHeader`, command card, `Поля модели`, and `Источник структуры`; first useful field rows started too low.
   - Fixed on 2026-05-14: removed duplicate `PageHeader`, compressed the model command block, moved source status into an inline strip, and aligned field tabs/actions in one toolbar.
   - Second pass on 2026-05-14: field rows were changed from heavy form-like cards to denser table rows with quieter borders, compact controls, and focus/hover emphasis.
   - Remaining issue: verify whether editing a field, dictionary binding, drag ordering, and deletion are understandable without extra explanation.
3. `/sources?tab=sources&category=bb40de87-254b-4170-84d7-8e5d3925b251`
   - Browser-verified on 2026-05-12 after compact layout pass;
   - no accidental horizontal overflow;
   - selected SKU and Store77 candidate are visible;
   - candidate row actions no longer wrap into a tall broken card;
   - 2026-05-15 competitor block wording/layout pass: source matching now explains the real job as `SKU -> competitor product card -> enrichment`, and the primary action reads `Подобрать карточки` instead of the misleading `Сканировать каталог`;
   - remaining issue: category tree and top hero are still visually heavy, but usable.
4. `/sources?tab=params&category=bb40de87-254b-4170-84d7-8e5d3925b251`
   - Browser-verified on 2026-05-13 after provider binding cleanup;
   - no accidental horizontal overflow;
   - right-side provider binding no longer uses a huge native dropdown;
   - each provider now has search, current state, a short candidate list, and count `shown/total`;
   - remaining issue: candidate quality still depends on backend AI/category source data, not layout.
5. `/sources?tab=values&category=bb40de87-254b-4170-84d7-8e5d3925b251`
   - Browser-verified on 2026-05-13 after value list cleanup;
   - no accidental horizontal overflow;
   - left field list no longer repeats useless provider `0/0` states;
   - rows show task status: `нужно сопоставить`, `готово`, or `нет справочника`;
   - dictionary editor now opens the first provider with real allowed values instead of an empty provider tab;
   - remaining issue: actual value normalization and suggested mappings still need data-quality work for marketplace dictionaries.
6. Continue audit with screenshots/DOM checks before changing layout again.

### P0.2 Value Mapping Cleanup

Status: active after pipeline audit exposes exact blockers.

Goal: make `/sources?tab=values` readable and task-focused.

Required behavior:

1. Show only fields that need value work by default.
2. Make canonical PIM value, marketplace output value, allowed marketplace values, and source evidence visible in one compact row/card.
3. Hide raw metadata unless opened in details.
4. Provide clear actions: accept suggestion, edit mapping, mark not needed, reset.
5. Preserve category context and return route.

Progress:

1. 2026-05-15 audit of `/sources?tab=values&category=bb40de87-254b-4170-84d7-8e5d3925b251` found the value editor working but too tall before actual rows:
   - duplicated semantic header inside the embedded dictionary editor;
   - separate provider/supplier dictionary card consumed too much vertical space;
   - search/actions card pushed value rows below the first viewport;
   - no backend change needed for this pass.
2. Compact embedded dictionary editor pass:
   - inner header now reads as field context, not a second page title;
   - provider dictionary block uses denser cards and a shorter allowed-value cloud;
   - search/filter/actions block is laid out as one compact control strip;
   - target is to make actual value rows visible immediately after opening a field.

### P0.3 Competitor Matching Quality

Status: active after pipeline audit; backend variant matching tightened on 2026-05-13 and Store77 category scan corrected on 2026-05-14.

Goal: improve `re-store` and `store77` exact product-card discovery for SKU enrichment.

Required behavior:

1. Backend scans competitor catalog/search pages and extracts product-card URLs.
2. Matching must respect exact model, memory, color, SIM/eSIM configuration, region/global differences, and variant names.
3. `eSIM` and `SIM + eSIM` must not collapse into the same match.
   - Backend now builds a variant profile from candidate/product title: `model`, `memory`, `color`, `sim`, `region`.
   - Candidate scoring rejects explicit conflicts by color, region, memory, model, or SIM profile.
   - `match_group_key` includes SIM profile, so approving one candidate does not auto-reject another SIM variant.
4. If multiple close candidates exist, UI shows them as selectable variants.
5. If all candidates are rejected, user can add exact competitor URL manually.
6. Approved/rejected decisions persist to `pim_channel_links`.

Progress:

1. Store77 discovery no longer creates unverified synthetic product URLs before scanning the real category.
2. Store77 category route generation now handles iPhone generation differences:
   - iPhone 17+ tries `_1`, `_2`, base route;
   - earlier generations keep `_2`, base, `_1`.
3. Local real-site check for `Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)` finds:
   - `https://store77.net/apple_iphone_17_pro_1/telefon_apple_iphone_17_pro_256gb_esim_silver/`
4. Production cleanup removed old synthetic/test candidates like `/product/product_1` and stale wrong `product_1` restore matches.
5. Product API recursion blocker fixed: legacy `extra.extra.extra...` payloads are collapsed at `products_rel` normalization, and production `products_rel.extra_json` was cleaned for 1090 affected SKU.
6. Store77 category scan now returns after the first valid category candidate set instead of continuing into slower fallback routes until the worker timeout.
7. Product card route now respects `?tab=competitors`, so export blockers and workflow links can open the competitor enrichment step directly.
8. Product competitor moderation text was cleaned up: no user-facing `candidate/link/review` labels, actions now read as `Найти карточки`, `Подтвердить`, `Загрузить параметры и медиа`.
9. `pim_channel_links.payload` now persists `product_sim_profile` and `candidate_sim_profile`, so the UI can show `eSIM only` / `nano SIM + eSIM` instead of `SIM не распознан`.
10. Store77 product-card enrichment now extracts only the real product gallery (`#cardPhoto` and popup gallery), not unrelated modal/promo images.
11. Partner media enrichment no longer stores broken external hotlinks as ready product media:
   - Store77 image bytes are fetched through a Playwright browser context when direct HTTP returns Store77 protection HTML;
   - images are uploaded to S3/object storage through `upload_bytes`;
   - product DB stores `/api/uploads/...` in `content.media_images.url` and keeps the original competitor URL in `external_url`;
   - repeated enrichment prunes stale Store77 media that is not present in the current product gallery.
12. Production `product_1` was cleaned from 24 mixed Store77 images to 6 real product images, all backed by S3 `/api/uploads/...` references. Browser QA verified that the media tab renders images.
13. Product enrichment now retries competitor product-card extraction:
   - Store77 gets 3 attempts because the site can intermittently timeout from the production server;
   - other competitor sources get 2 attempts;
   - failed extraction returns `retryable=true` for transient errors and does not overwrite product content with empty data.
14. Product competitor UI now shows readable enrichment failures such as `store77 — источник долго отвечает, можно повторить` instead of generic `Ошибок: N`.
15. `re-store` discovery parser was hardened:
   - re-store search HTML now parses candidates by scanning `/catalog/...` product links and reading nearby product fields, so it no longer depends on a fragile JSON key order;
   - the old catastrophic fallback regex was removed because it could hang on megabyte search pages when no candidate matched;
   - real-site check for `Apple iPhone 17 Pro 256GB Silver` returns `https://re-store.ru/catalog/10117PRO256SLVN/` in about 2 seconds;
   - `Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)` correctly does not match the available physical-SIM `re-store` SKU, because SIM profile conflicts must not collapse.
   - 2026-05-16: HTTP discovery for re-store is enabled by default, with kill switch `ENABLE_HTTP_COMPETITOR_DISCOVERY=0`; real-site check for `Смартфон Apple iPhone 17 Pro 256Gb eSIM Blue (Global)` returns `https://re-store.ru/catalog/10117PRO256BLUE/` with confidence `0.95`.
   - when exact `eSIM` is absent from the server-side re-store response, the same model/memory/color physical-SIM card is now surfaced as a manual-review near match with `проверь SIM`, not silently discarded and not auto-confirmed.
16. Product competitor moderation must not show historical low-confidence garbage as actionable candidates:
   - production audit on `/products/product_2?tab=competitors` showed `35-39%` candidates for unrelated Apple Watch, Samsung vacuum and organization pages;
   - API context now exposes only approved candidates and `needs_review` candidates with confidence at least `0.78`;
   - frontend keeps the same defensive threshold so stale/low-confidence rows cannot reappear from cached or legacy payloads.
17. Store77 exact fallback must support current iPhone colors:
   - `iPhone 17 Pro 256Gb eSIM Orange` previously had no exact seed because `orange` was absent from the Store77 color URL builder;
   - `orange/оранжевый` is now part of variant color normalization, while Store77 URL generation uses the real site slug `cosmic_orange`;
   - wrong-color Orange/Silver matches are explicitly rejected by the confidence function.

Verified:

```bash
PYTHONPATH=backend python3 -m pytest backend/tests/test_auth_flow.py -k "competitor or store77 or restore or sim_profile or variant"
PYTHONPATH=backend python3 -m pytest backend/tests/test_auth_flow.py -k "store77 or competitor or restore"
PYTHONPATH=backend python3 -m pytest backend/tests/test_operating_workflows.py -k "store77"
PYTHONPATH=backend python3 -m pytest backend/tests/test_products_service.py backend/tests/test_operating_workflows.py -k "product_normalizer or loads_variants or store77"
PYTHONPATH=backend python3 -m pytest backend/tests/test_auth_flow.py -k "store77_product_html_extracts_gallery_images or competitor_product_discovery_endpoint_returns_candidates_and_links"
PYTHONPATH=backend python3 -m pytest backend/tests/test_operating_workflows.py -k "existing_catalog_enrichment_uses_confirmed_competitor_links or catalog_import_uses_confirmed_partner_links_before_export"
PYTHONPATH=backend python3 -m pytest backend/tests/test_auth_flow.py -k "restore_search_parser_extracts_large_escaped_catalog_fast or restore_search_html_candidates"
make check-backend
cd frontend && npm run build
```

### P0.4 Import / Export Contract Check

Status: active.

Goal: verify imported products, partner enrichment, and export readiness use the same category/model/value/media state as the UI.

Required behavior:

1. Import can create/update SKU under selected category.
2. Import preserves category context.
3. Created/imported SKU can be enriched with model fields and competitor evidence.
4. Partner/competitor enrichment must run before final export readiness when marketplace media/content is missing.
5. Confirmed partner product-card links in `pim_channel_links` are the source of truth; import must not depend on legacy/manual `content.links`.
6. Export shows blockers per marketplace.
7. Export uses `SKU GT` as article/offer identifier where required.
8. Export run state must be readable and not hidden in JSON-only operational docs long-term.

Progress:

1. Export batch API now returns `status=ready|blocked`, `not_ready_count`, `blockers_count`, and first blocker rows with `product_id`, `offer_id`, and missing reasons.
2. Export UI shows blocked SKU reasons directly on the export screen instead of hiding them inside raw preview JSON.
3. Contract test added for mixed Я.Маркет/Ozon readiness: Я.Маркет ready, Ozon blocked.
4. Production timeout found and fixed: export preview now filters selected SKU in SQL, applies SQL `LIMIT` for category batches, caches value-dictionary export lookups, and the UI requests a first 50-SKU readiness batch instead of a full synchronous category run.
5. Export blockers now carry SKU title/category context and the UI deduplicates repeated store blockers with direct actions: open SKU, open category mapping, open parameter mapping, open value mapping, media, or description.
6. Я.Маркет export no longer treats product `Описание` and `Медиа` as mandatory manual parameter mappings. These are system content fields: export checks whether product description/images exist and only blocks on missing content.
7. Partner enrichment contract fixed:
   - `POST /competitor-mapping/discovery/products/{product_id}/enrich` now writes extracted partner images into `content.media_images` and extracted description into `content.description` when missing;
   - `POST /catalog/exchange/import/run` now uses confirmed relational partner links from `pim_channel_links`, not only legacy/manual `content.links`;
   - regression tests cover confirmed partner link enrichment and import-before-export media readiness.
8. Import/export media contract fixed:
   - bulk import enrichment uploads competitor images to S3/object storage and skips broken external hotlinks;
   - product media keeps `/api/uploads/...` as the canonical internal reference and the original competitor URL in `external_url`;
   - import overview detects competitor media by source metadata, `source`, and `external_url`, not only by URL hostname;
   - Я.Маркет and Ozon export previews expand `/api/uploads/...` into public `APP_PUBLIC_BASE_URL` URLs before building marketplace payloads.
9. 2026-05-15 export audit for `Смартфоны`:
   - `/catalog/export?category=bb40de87-254b-4170-84d7-8e5d3925b251` redirects to `/catalog/exchange?...&tab=export` and opens without console errors or horizontal overflow;
   - export run API for first 50 SKU returns in about 12 seconds with blocking reasons, for example `Нет изображений (pictures)`;
   - UI previously only changed button text to `Готовлю...` during the synchronous wait, so the user did not understand whether the screen was working;
   - export UI now shows an explicit preparation state with selected scope, channel count, target count, and a short explanation of what is being checked.
10. Export safety rule:
    - all Я.Маркет stores may be visible in the UI;
    - default selected Я.Маркет store must be only `GT USD`;
    - `GT RUB` and `ID Store RUB AE` must stay visible but unchecked unless explicitly selected later;
    - Ozon is allowed for testing and may be selected by default.
    - 2026-05-15 backend safety fix: if a request sends a non-existent `store_id`, export must return `400` instead of silently falling back to `Все магазины`.
    - current pipeline QA must use one selected SKU only, preferably a product missing on one or both marketplaces; do not run export/update across all `Смартфоны` while the pipeline is still being stabilized.
    - current pipeline QA targets are only `GT USD` for Я.Маркет and Ozon test store; other Я.Маркет stores must not be selected or mutated.
11. Parameter enrichment and marketplace mapping contract:
    - competitor/partner extraction writes raw evidence into product feature `source_values`;
    - product card must show `PIM field -> selected value -> source evidence -> marketplace output value` in one screen;
    - export uses canonical PIM values plus marketplace value mapping, never raw competitor values directly;
    - `SKU GT` is a service row and must be visible as the marketplace `offerId/offer_id` source.
12. 2026-05-15 product media blocker audit:
    - first export blocker opens `/products/product_2?tab=media`;
    - media tab previously showed only an empty S3 message and no next action;
    - empty media state now explains that export is blocked and links the user to competitor-card discovery/enrichment or validation.
13. 2026-05-15 Store77 media import fix:
    - production S3 is enabled and `global-pim.service` reads `/opt/projects/global-pim/backend/.env`;
    - Store77 `/upload/...` image URLs first return an HTML JS challenge, not an image;
    - backend now computes the Store77 challenge cookies and retries the image request before writing media into S3;
    - verified on `/products/product_2?tab=media`: Store77 enrichment now shows S3-backed media cards with `/api/uploads/...` URLs.
14. Next product-pipeline UI cleanup:
    - fixed: product-source confirmed links such as `product_2:store77` are no longer shown as candidate cards with `0%` and `SIM не распознан`;
    - API now returns the real discovery candidate (`cand_6bfd36bda7f3ad62`) as the selectable approved item with `score=0.95` and `candidate_sim_profile=esim_only`;
    - confirmed links remain in the separate ready-link block and include last checked/enriched timing;
    - product media tab now works functionally, but still needs compact product-card layout polish after the pipeline blockers are cleared.
15. re-store vs Store77 source visibility:
    - production audit for `product_2` shows Store77 is the only confirmed exact eSIM source and therefore is the current media/enrichment source;
    - re-store currently returns low-confidence unrelated candidates for this SKU (Apple Watch / unrelated URLs), so they must stay hidden from moderation;
    - product competitor API/UI must still show per-source reason cards, so a user sees `Store77: confirmed` and `re-store: no exact product` instead of assuming the system ignored re-store.
16. 2026-05-15 Ozon required system fields:
    - production export audit found Ozon field `9048 / Название модели` missing from the `Смартфоны` mapping and `8229 / Тип` incorrectly mapped to `Тип основных камер`;
    - export must derive Ozon `Тип` and `Название модели` from the product itself for commodity electronics instead of forcing users to repair broken technical mappings before every test;
    - regression test added for `Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)`: Ozon payload must contain `Тип=Смартфон` and `Название модели=iPhone 17 Pro`.
    - production single-SKU verification used only `product_3 / SKU GT 52462` against `GT USD` and Ozon test store; both exports are now blocked by missing images only, not by Ozon `Название модели`.
17. 2026-05-16 single-SKU pipeline verification:
    - only `product_3 / SKU GT 52462` was used; no category-wide export/update was run;
    - Store77 candidate `https://store77.net/apple_iphone_17_pro_1/telefon_apple_iphone_17_pro_256gb_esim_deep_blue/` was confirmed for this SKU;
    - enrichment wrote 4 Store77 images into S3-backed `/api/uploads/...` media references;
    - export readiness for this one SKU is now `ready` for `GT USD` and Ozon test store.
    - product-list export navigation now supports single-SKU checks through `/catalog/export?product=<product_id>` and selected SKU checks through `/catalog/export?products=<ids>`, so users are not pushed into category-wide export preparation by default.
18. Direct SSH diagnostics gotcha:
    - `server_ops.sh exec` does not inherit `global-pim.service` env; S3 can appear disabled in manual Python diagnostics if runtime env is not loaded safely;
    - prefer API/service verification for S3/media flows, or load required env inside Python without printing secrets.
19. 2026-05-16 stock/archive safety audit:
    - SmartPim code currently does not send Ozon stock, warehouse, price, archive, posting, or visibility mutation requests;
    - Ozon product status sync is read-only from SmartPim side: `/v3/product/info/list` and `/v1/product/rating-by-sku`;
    - if stock changes or marketplace archive happens by itself, compare exact SKU/timestamp with server logs and audit external integrations/cron/systemd/Ozon API keys before blaming the PIM export preview;
    - local product archive status is now normalized to canonical `archived`; legacy `archive` is accepted only for backwards-compatible reads/writes.
20. 2026-05-16 export run readability:
    - export run responses and persisted run rows now include aggregate summary fields: product count, target count, ready/blocked batches, ready/blocked target rows, and blocker count;
    - export UI uses this summary for the visible batch metrics instead of forcing the user to infer run state from nested raw rows.
    - ready export state now shows a separate `Batch готов к выгрузке` panel with a neutral message that SmartPim prepared product-card data for selected marketplaces.

### P1 DB Consolidation

Status: pending.

Goal: reduce split legacy/read-model state after the `Смартфоны` pipeline works.

Target tables still to design/implement:

1. `pim_products`
2. `pim_model_fields`
3. `pim_external_payloads`

Rules:

1. Do not consolidate DB blindly before the user path is proven.
2. Product remains the main entity: one row equals one SKU.
3. Product groups only group SKU variants; variants still have their own SKU.
4. S3 remains the media storage backend; DB stores metadata and object references.

## Recently Completed

1. Auth/admin consolidation and cleanup.
2. Profile page.
3. Data source page first-pass cleanup.
4. Ozon category/type resolution and parameter mapping population for real categories.
5. Template editor counter fix for `Смартфоны`.
6. Competitor candidates/category mappings moved from JSON to `pim_channel_links`.
7. Competitor discovery run state moved from JSON to `pim_workflow_runs`.
8. Production legacy competitor JSON cleanup.

## Verification Commands

Use as applicable:

```bash
make check-backend
PYTHONPATH=backend python3 -m pytest backend/tests/test_auth_flow.py -k "competitor"
cd frontend && npm run build
scripts/server_ops.sh public-health
scripts/server_ops.sh health
```

Deploy backend-only when frontend is unchanged:

```bash
CI=1 ./scripts/deploy_production.sh --skip-build
```
