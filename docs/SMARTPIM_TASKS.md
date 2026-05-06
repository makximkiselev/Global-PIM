# SmartPim Active Tasks

This is the only active task/backlog document.

Do not create separate `.md` plans, specs, notes, or task lists. Add every new task here by priority.

## Current Production Baseline

1. Authentication and organization registration work.
2. Main SaaS shell exists with compact left navigation.
3. Product list and product card are substantially improved.
4. Catalog is simplified but still needs visual/workflow QA.
5. Info-model catalog/editor are improved but still need polish.
6. Category/parameter/value mapping is improved but still needs full user-path validation.
7. Connector/admin pages were improved once but still need cleanup and consistency checks.
8. Competitor discovery exists conceptually and partially in product/category workflows, but matching quality still needs iteration.

## Current Execution Priority

Status: active / user-path order accepted on 2026-05-06.

Work must follow the real first-run user path, not isolated technical pages:

1. `P0 Auth + Registration`
   - login;
   - organization registration;
   - expired session;
   - first owner creation;
   - no technical text or broken transitions.
2. `P0 Administration`
   - organization profile;
   - team;
   - invites;
   - rights and roles;
   - password change and logout.
3. `P0 Catalog Workflow`
   - catalog tree;
   - products;
   - create product;
   - product groups;
   - product media;
   - infographics;
   - import/export.
4. `P0 Data Sources`
   - marketplace/source connections;
   - stores;
   - competitors;
   - access checks and source errors.
5. `P0 Info Models + Mapping`
   - model creation;
   - category mapping;
   - parameter mapping;
   - value mapping;
   - competitor/platform evidence;
   - readiness checks.
6. `P1 Product Card Polish`.
7. `P1 Import/Export Polish`.
8. `P1 DB ownership maps and schema cleanup`.

Rule:

1. For each block, complete a vertical slice: scenario, data/API needs, UI, browser QA, build, deploy, commit.
2. Do not jump to later product workflows until auth/admin baseline is usable.
3. Browser Use/in-app browser is preferred for QA; if the bridge cannot see the pane, record the blocker and run available build/HTTP checks.

## Completed Recent Slices

1. User profile page
   - added protected `/profile` page for the current user;
   - clicking the user avatar in the left rail now opens the profile page;
   - profile shows first name, last name, email, login, organization, organization role, and access roles;
   - profile actions include password change and logout;
   - local `frontend/node_modules` was reinstalled with `npm ci` after `postcss`/`fsevents` optional dependency hang; frontend build passed.
1. Admin first-run cleanup
   - left navigation now keeps administration to two user-facing entries: `Организация` and `Права и роли`;
   - team and invitations are internal tabs of the organization page instead of separate left-menu destinations;
   - developer/service platform panel was removed from the visible administration UI;
   - English shell label and technical authorization copy were replaced with Russian user-facing text;
   - Browser Use QA is currently blocked because the in-app bridge does not see an active pane; build verification passed.
1. `/sources` competitor/channel separation
   - added dedicated `/data-prep/competitors` page under `Инфо-модели`;
   - moved competitor discovery/mapping UI code to `frontend/src/domains/data-prep`;
   - removed competitor tab from `Каналы`;
   - removed competitor context from marketplace category binding screen;
   - legacy `/competitor-mapping` redirects to `/data-prep/competitors`;
   - legacy `/sources?tab=competitors` redirects inside the feature to `/data-prep/competitors`.
1. Product navigation collapse first pass
   - accepted four top-level zones: `Сводка`, `Каталог`, `Инфо-модели`, `Администрирование`;
   - removed separate top-level `Модели`, `Насыщение`, `Экспорт`, `Медиа`, `Каналы`, and `Подготовка данных`;
   - changed menu labels toward user actions instead of internal entities;
   - kept existing routes as subpages/tabs inside the new product zones.
2. Frontend domain folder first pass
   - moved product/catalog features to `frontend/src/domains/products`;
   - moved dashboard to `frontend/src/domains/overview`;
   - moved templates, dictionaries, competitors, and infographics to `frontend/src/domains/data-prep`;
   - moved sources/mapping/connectors to `frontend/src/domains/channels`;
   - moved organization/access admin features to `frontend/src/domains/admin`;
   - removed old empty `frontend/src/features/*` folders.
3. Backend API router registry first pass
   - added `backend/app/api/router_registry.py`;
   - grouped existing flat API route modules by product zones without changing URLs;
   - changed `backend/app/main.py` to include routers through the registry;
   - kept flat route modules in place until compatibility shims or module moves are safe.
4. `807e815 Align import export scope controls`
   - added shared `CategoryScopeSelector`;
   - replaced technical `С подкатегориями` with `Весь каталог`, `Вся ветка`, `Только категория`;
   - cleaned active import/export inspector labels.
2. `93cb4b7 Align templates catalog sidebar`
   - `/templates` tree sidebar now uses shared `CategorySidebar`;
   - reduced local search/header duplication.
3. `6832828 Simplify template editor command actions`
   - `/templates/:categoryId` header is context-only;
   - save/build/approve actions live in the model command card;
   - technical summaries were renamed.
4. Production scripts cleanup
   - deploy/backup scripts now load production env automatically;
   - `APP_SERVER_PASSWORD` is no longer interpolated into `expect` command strings;
   - added `scripts/server_ops.sh` for health/status/logs/restart;
   - deploy now retries backend/public health and skips `pip install` when requirements did not change.
5. Repository structure cleanup
   - removed obsolete root npm contour (`package.json`, `package-lock.json`, root `node_modules`);
   - removed tracked placeholder `.codex/config.toml`;
   - removed inactive legacy `frontend/src/pages/*` route implementations;
   - cleaned ignored local artifacts: `.playwright-cli`, `.DS_Store`, pycache, generated `frontend/dist`;
   - kept `deploy/` until DB/schema audit is complete.

## P0 - Documentation And Work Hygiene

Status: complete for current phase.

Tasks:

1. keep only two active project documents:
   - `docs/SMARTPIM_INSTRUCTIONS.md`;
   - `docs/SMARTPIM_TASKS.md`;
2. delete old project `.md` documents and old tracked local skill `.md` files after their useful content is merged;
3. do not create new `.md` files;
4. if a new task appears, add it to this file by priority;
5. if a new standing instruction appears, add it to `docs/SMARTPIM_INSTRUCTIONS.md`.

Done when:

1. `git ls-files '*.md'` shows only the two active docs, excluding ignored dependency files;
2. build/test commands still work;
3. changes are committed and pushed.

Current note:

1. this phase is done; keep the section as a standing rule.

## P0 - Product Navigation, Module Ownership, And DB Maps

Status: active / product structure accepted on 2026-05-05, menu-vs-tabs contract updated on 2026-05-06.

Goal:

1. rebuild navigation around product work zones;
2. make every page belong to exactly one zone;
3. move related frontend/backend code into discoverable domain folders;
4. document table ownership for every zone and page before destructive DB changes.

Accepted top-level zones:

1. `Сводка` - operational health, queues, problems, and quick return to active work.
2. `Каталог` - product catalog, products, product groups, product media, infographics, content index, import, and export.
3. `Инфо-модели` - info-models, category matching, parameter matching, dictionaries, competitor sources, and marketplace sources.
4. `Администрирование` - organization, users, rights, roles, invitations, and platform settings.

Primary user path:

1. import products;
2. group SKU variants;
3. map catalog categories and competitor sources;
4. collect and approve the info-model;
5. map marketplace channels, parameters, values, and competitor evidence;
6. enrich products;
7. validate and export.

Menu rule:

1. left rail shows broad work areas only;
2. concrete entities and operations live as submenu items or page tabs;
3. submenu labels must be action-oriented where possible;
4. do not duplicate the same operation in multiple left-menu groups.

Accepted submenu contract:

1. `Сводка`:
   - `Рабочая сводка`.
2. `Каталог`:
   - `Каталог`;
   - `Товары`;
   - `Группы`;
   - `Медиа по товарам`;
   - `Создание инфографики`;
   - `Импорт / Экспорт`.
3. `Инфо-модели`:
   - `Инфо-модели`;
   - `Сопоставления`;
   - `Источники данных`.
4. `Администрирование`:
   - `Организация`;
   - `Права и роли`.

Tab contract:

1. `Импорт / Экспорт` owns tabs `Импорт товаров` and `Экспорт товаров`; old `/catalog/import` and `/catalog/export` URLs must redirect to the matching tab.
2. `Сопоставления` owns tabs for categories, parameters, values, competitors/platform evidence, and checks; these should not be separate menu items.
3. `Источники данных` owns tabs/sections for marketplaces, competitors, stores, and connection status; these should not be separate menu items.
4. `Организация` owns tabs for profile, team, and invites.
5. `Права и роли` owns tabs/sections for roles, access, and developer-only platform settings.

Route ownership:

| Zone | Routes | Primary task |
| --- | --- | --- |
| `Сводка` | `/` | Show what needs attention and where to continue. |
| `Каталог` | `/catalog`, `/products`, `/products/new`, `/products/:productId`, `/catalog/groups`, `/products/media`, `/images/infographics`, `/catalog/content-index`, `/catalog/exchange?tab=import`, `/catalog/exchange?tab=export` | Manage product categories, SKU, product cards, groups, media, import, export, and final catalog state. |
| `Инфо-модели` | `/templates`, `/templates/:categoryId`, `/sources?tab=sources`, `/sources?tab=params`, `/sources?tab=values`, `/dictionaries`, `/dictionaries/:dictId`, `/data-prep/competitors`, `/connectors/status` | Build info-models, match categories and parameters, manage dictionaries, and connect external sources. |
| `Администрирование` | `/admin/organizations`, `/admin/members`, `/admin/invites`, `/admin/access`, `/admin/platform` | Manage organization, team, permissions, and platform context. |

Page/layout rules:

1. every page has one primary job and may use tabs for adjacent jobs;
2. no duplicated headers, summaries, counters, or action buttons on the same screen;
3. catalog/category tree must be the same shared component everywhere;
4. long tables must keep headers and horizontal scroll usable;
5. inspectors must explain action/state, not duplicate the center panel;
6. technical labels must not leak into product UI unless the user needs them for work;
7. Browser Use/in-app browser QA is mandatory for each finished route.

Target frontend folders:

1. `frontend/src/app` - app shell, auth context, routing composition only. Status: current.
2. `frontend/src/shared` - reusable UI primitives, layout components, table/list/tree/selectors, hooks, formatters. Status: started with shared placeholder; UI primitives still live in `frontend/src/components` until component consolidation.
3. `frontend/src/domains/overview` - `Сводка`. Status: moved.
4. `frontend/src/domains/products` - `Каталог`. Status: moved.
5. `frontend/src/domains/data-prep` - `Инфо-модели`. Status: moved for templates/dictionaries/competitors/media prep; folder name remains `data-prep` until a separate import-safe rename is justified.
6. `frontend/src/domains/channels` - mapping/source implementation used by `Инфо-модели`; folder name remains until a safe rename is justified.
7. `frontend/src/domains/admin` - `Администрирование`. Status: moved.

Frontend structure debts:

1. `/sources` competitor tab is split out to `/data-prep/competitors`; remaining debt is that parameter mapping still displays competitor evidence as supporting context.
   Update 2026-05-06: `Источники данных` now owns a single `/connectors/status` workspace with `Площадки и магазины` and `Конкуренты` tabs; legacy `/data-prep/competitors` redirects to `/connectors/status?tab=competitors`.
2. `frontend/src/components` still contains shared UI/layout primitives; move into `frontend/src/shared` only after import paths are stabilized.
3. auth-only pages remain in `frontend/src/pages`; either keep as public auth pages or move to `frontend/src/app/auth/pages` in a separate auth cleanup.

Target backend folders:

1. `backend/app/api/routes/overview` - dashboard/readiness/queue APIs;
2. `backend/app/api/routes/products` - catalog, products, groups, product card APIs;
3. `backend/app/api/routes/data_prep` - import, templates, dictionaries, competitors, media prep APIs;
4. `backend/app/api/routes/channels` - connectors, marketplace mapping, validation, export APIs;
5. `backend/app/api/routes/admin` - organizations, users, access, platform APIs;
6. `backend/app/domain/<zone>` - business services for each zone;
7. `backend/app/storage/<zone>` - query/repository functions when storage logic is too large for shared storage.

Backend structure constraint:

1. `backend/app/api/routes` currently has flat modules such as `products.py`, `catalog.py`, `templates.py`, and direct imports between them.
2. A direct folder move to `backend/app/api/routes/products/` conflicts with the existing `products.py` module name.
3. Backend restructuring must therefore be done through a router registry and compatibility aliases first, then module moves one zone at a time.
4. Do not mechanically move backend route files until direct imports are replaced or compatibility shims are prepared.

DB map requirement per page:

1. page route;
2. frontend domain files;
3. backend route files;
4. backend services/storage functions;
5. source-of-truth tables;
6. derived/read-model tables;
7. cross-zone dependencies;
8. allowed writes;
9. forbidden local duplicate state.

Initial DB ownership map:

| Zone | Source-of-truth tables | Derived/read-model tables | Cross-zone dependencies |
| --- | --- | --- | --- |
| `Сводка` | none directly; reads product/catalog/channel/admin state | `dashboard_stats_rel` | Reads all zones, writes only explicit dashboard snapshots. |
| `Каталог` | `products_rel`, `catalog_nodes_rel`, `product_groups_rel`, `product_group_variant_params_rel` | `catalog_product_registry_rel`, `category_product_counts_rel`, `catalog_product_page_rel`, `catalog_product_page_tenant_rel`, `product_marketplace_status_rel`, `product_marketplace_status_tenant_rel` | Reads info-model/channel readiness; writes product/category/group state. |
| `Инфо-модели` | `templates_tenant_rel`, `template_attributes_tenant_rel`, `category_template_links_tenant_rel`, `dictionaries_tenant_rel`, `dictionary_values_tenant_rel`, `dictionary_value_sources_tenant_rel`, `dictionary_provider_refs_tenant_rel`, `dictionary_export_maps_tenant_rel`, `category_mappings_tenant_rel`, `attribute_mappings_tenant_rel`, `attribute_value_refs_tenant_rel`, connector account/state tables, selected `json_documents` operational docs for import/competitor/marketplace jobs | `category_template_resolution_tenant_rel`, marketplace export/readiness snapshots | Reads products/categories; writes models, dictionaries, enrichment evidence, marketplace bindings, and source state. |
| `Администрирование` | `platform_users`, `organizations`, `organization_members`, `organization_invites`, `tenant_registry`, `tenant_provisioning_jobs` | none by default | Owns access context for every zone. |

Implementation order:

1. collapse menu to the accepted four zones. Status: done.
2. document current route/table ownership before moving code. Status: first zone-level map done; page-level maps still needed.
3. create frontend domain folders and move routes one zone at a time with import-safe commits. Status: first pass done.
4. create backend route/service folder aliases one zone at a time without changing behavior. Status: registry added; physical module moves still pending.
5. replace duplicated page-local components with shared components during each page pass;
6. run build/tests and Browser Use QA after every zone;
7. only after parity is proven, remove old folders/import paths.

## P0 - Category Workspace Unification

Status: active / mandatory.

Problem:

Pages that work with the same category tree were built independently and still look/behave differently.

Routes in scope:

1. `/catalog`;
2. `/catalog/import`;
3. `/catalog/export`;
4. `/templates`;
5. `/templates/:categoryId`;
6. `/sources?tab=sources&category=:id`;
7. `/sources?tab=params&category=:id`;
8. `/sources?tab=values&category=:id`;
9. `/data-prep/competitors?category=:id`.

Rules:

1. one visual language for category tree;
2. one density/search/active/counter behavior;
3. no visible `С подкатегориями`;
4. use `Весь каталог`, `Вся ветка`, `Только категория`, or exact SKU selection;
5. no local category tree implementation unless it becomes the new shared component.

Progress:

1. `/catalog/import`: first pass done with shared `CategoryScopeSelector`.
2. `/catalog/export`: first pass done with shared `CategoryScopeSelector`.
3. `/templates`: first pass done with shared `CategorySidebar`.
4. `/templates/:categoryId`: first pass done for command/header cleanup.

Next tasks:

1. extract/finish shared `CategoryTree` renderer from repeated tree row logic;
2. finish `/templates` summary/action dedupe;
3. align `/catalog` tree header/search/selected state with shared sidebar;
4. align `/sources` category drawers with shared sidebar/tree;
5. verify all listed routes in Browser Use/in-app browser.

## P0 - Info-Model And Mapping User Path

Status: active / most painful product flow.

Target path for `Смартфоны`:

1. user selects category;
2. system collects field candidates from marketplaces, products, imports, competitors;
3. user reviews and approves info-model fields;
4. user maps PIM fields to marketplace fields;
5. user maps internal values to marketplace-specific output values;
6. user enriches products from marketplace/competitor sources;
7. user validates export readiness.

Rules:

1. info-model is created through field proposals first;
2. identical fields are normalized into one PIM field;
3. AI mapping action must stay visible where AI mapping is available;
4. competitor evidence from re-store/store77 must be visible where it helps;
5. SKU GT and other required service fields must not be removed if needed for marketplace export;
6. every screen does one task only.

Next tasks:

1. run full user path for `Смартфоны`;
2. verify marketplace field import for Ozon and Yandex;
3. verify competitor evidence from re-store/store77;
4. remove duplicate counters/tabs in parameter mapping. Status: first pass done for `/sources?tab=params`;
5. make binding edit action obvious;
6. inspect and simplify value mapping.

## P0 - Database Ownership Audit

Status: first production audit complete / cleanup not executed.

Runtime schema sources:

1. `backend/app/storage/relational_pim_store.py` creates 44 PIM relational tables.
2. `backend/app/core/control_plane.py` creates 8 control-plane tables.
3. `backend/app/core/json_store.py` creates `json_documents`.
4. `deploy/sql/*` is historical/ops schema reference, not the active runtime migration source.

Production snapshot on 2026-04-30:

1. total public tables: 61;
2. expected runtime tables: 53;
3. extra tables: 8 `backup_20260428_*` control-plane backup tables;
4. active organization: `org_default / Global Trade`;
5. stale provisioning organizations: 16 test/QA organizations;
6. `products_rel`: 1090 rows;
7. `catalog_nodes_rel`: 272 rows;
8. `product_groups_rel`: 105 rows;
9. `product_variants_rel`: 1 row;
10. `json_documents`: 85 rows.

Canonical source-of-truth tables:

1. catalog: `catalog_nodes_rel`;
2. products/SKU: `products_rel`;
3. product groups: `product_groups_rel`, `product_group_variant_params_rel`;
4. organization/users/access: `platform_users`, `organizations`, `organization_members`, `organization_invites`;
5. tenant registry/provisioning: `tenant_registry`, `tenant_provisioning_jobs`.

Config tables:

1. info-models: `templates_tenant_rel`, `template_attributes_tenant_rel`, `category_template_links_tenant_rel`;
2. global fallback/reference info-models: `templates_rel`, `template_attributes_rel`, `category_template_links_rel`;
3. category mappings: `category_mappings_tenant_rel`, `category_mappings_rel`;
4. parameter mappings: `attribute_mappings_tenant_rel`, `attribute_mappings_rel`;
5. source/value refs: `attribute_value_refs_tenant_rel`, `attribute_value_refs_rel`;
6. dictionaries/value mapping: `dictionaries_tenant_rel`, `dictionary_values_tenant_rel`, `dictionary_value_sources_tenant_rel`, `dictionary_provider_refs_tenant_rel`, `dictionary_export_maps_tenant_rel`;
7. global dictionary fallback/reference: non-tenant dictionary tables.

Derived/read-model tables:

1. `catalog_product_registry_rel`;
2. `category_product_counts_rel`;
3. `category_template_resolution_rel`;
4. `category_template_resolution_tenant_rel`;
5. `product_marketplace_status_rel`;
6. `product_marketplace_status_tenant_rel`;
7. `catalog_product_page_rel`;
8. `catalog_product_page_tenant_rel`;
9. `dashboard_stats_rel`.

Legacy/migration candidates:

1. `product_variants_rel` conflicts with the accepted model where every variant is also a row in `products_rel` with its own SKU and shared `group_id`;
2. `json_documents` contains many legacy snapshots that duplicate relational tables: `products.json`, `catalog_nodes.json`, `templates.json`, `dictionaries.json`, `product_groups.json`, SKU indexes;
3. `json_documents` also stores active non-relational operational docs: import/export runs, marketplace caches, offer cache, competitor mapping, ComfyUI runs if used;
4. `platform_user_roles` has 0 rows and no current product-facing use; keep only if platform-level RBAC is still planned;
5. `deploy/sql/*` duplicates runtime schema and must either become the real migration source or be removed after migration strategy is decided.

Immediate cleanup candidates after backup/confirmation:

1. drop `backup_20260428_102730_*` and `backup_20260428_102824_*` tables;
2. delete 16 stale `provisioning` test organizations and related `tenant_registry` / `tenant_provisioning_jobs` rows;
3. delete derived tenant rows for stale orgs:
   - `catalog_product_page_tenant_rel`;
   - `product_marketplace_status_tenant_rel`;
   - `category_template_resolution_tenant_rel`;
4. delete legacy auth cleanup docs from `json_documents` after confirming current auth tables/sessions are enough;
5. remove legacy duplicate JSON docs only after relational parity checks pass.

Risks found:

1. tenant read models are duplicated across stale test orgs: `catalog_product_page_tenant_rel` and `product_marketplace_status_tenant_rel` have 11960 rows each for roughly 1090 real products;
2. mixed storage remains: core PIM entities are relational, but many workflows still read/write `json_documents`;
3. `backend/.env` is not shell-source-safe because at least one value contains `&`; scripts should not assume `source backend/.env`;
4. global vs tenant tables are not consistently documented, so accidental reads from global fallback can hide missing tenant data;
5. product variant logic still has two models: `products_rel.group_id` and legacy `product_variants_rel`.
6. `/catalog/products` had a dangerous mixed path: product reads were relational, but create/delete used legacy `_save_products()`; fixed on 2026-04-30 by routing create/delete through product services and disabling the local legacy writer;
7. `products_rel` and legacy `json_documents.products.json` are already not equal: 1090 vs 1087 rows;
8. connector state reads are mixed: connector status writes relational tenant state, but product/export/Yandex/Ozon paths still read JSON connector docs.
9. cleanup SQL must stay review-only by default; generated DROP/DELETE statements need an explicit guard and rollback until backup/parity sign-off.
10. consolidated connector accounts must not store raw API keys/tokens in JSONB; store a secret reference plus masked metadata only.

DDL/audit readiness review on 2026-04-30:

1. `backend/scripts/db_consolidation_audit.py` cleanup output is review-only and non-destructive if pasted as-is;
2. stale organization cleanup now discovers tenant-scoped tables dynamically by `organization_id`;
3. `deploy/sql/014_consolidated_pim_schema_draft.sql` has tenant-scoped FKs to `organizations`;
4. consolidated product/model/value tables have tenant-aware FKs and JSONB shape checks;
5. external snapshot expiry indexes include `organization_id`;
6. connector credentials are modeled as `credentials_ref` plus masked `credentials_meta_json`, not raw secret JSON.

Target rules:

1. one product row equals one SKU;
2. variants are product rows grouped by `group_id`, not separate variant rows;
3. media binaries stay in S3/object storage; DB stores references only;
4. raw source evidence and final canonical values must be separated;
5. derived tables must be rebuildable and never manually edited;
6. every JSON document that remains in `json_documents` must be classified as cache, run log, external snapshot, or migration backlog item.

Target consolidated schema direction:

Do not move everything into one physical table. Use a small number of large domain tables so pages share the same source, while keeping high-write and high-cardinality data indexable.

Core tables:

1. `pim_categories`
   - replaces `catalog_nodes_rel`;
   - stores tree, path, position, category state, category-level summary JSON;
   - every category workspace page reads this table.
2. `pim_products`
   - replaces `products_rel`, `catalog_product_registry_rel`, `catalog_product_page_*`, `product_marketplace_status_*`, and legacy `product_variants_rel`;
   - one row equals one SKU;
   - contains stable columns for `id`, `organization_id`, `category_id`, `group_id`, `sku_gt`, `sku_pim`, `title`, `status`;
   - contains JSONB blocks for content, media refs, relations, final channel readiness, export flags, competitor links, and UI-ready summary;
   - product list, catalog product preview, product card, export readiness, and variant grouping read from this table.
3. `pim_product_values`
   - stores one canonical product parameter value per product/field;
   - includes source/evidence pointers, confidence, approval status, and value normalization state;
   - used by product card, enrichment, validation, and export.
4. `pim_models`
   - replaces templates/category template links/resolution tables;
   - stores category model identity, inheritance/source category, status, and model-level JSON summary;
   - model catalog/editor read from this table.
5. `pim_model_fields`
   - replaces template attributes, attribute mappings, attribute value refs, dictionary provider refs, and value maps where possible;
   - one row per canonical PIM field per model/category;
   - stores field type, required state, allowed values, marketplace field mappings, competitor field evidence, and channel output rules as JSONB;
   - info-model builder, parameter mapping, value mapping, and export validation read from this table.
6. `pim_channel_links`
   - one table for category/product/source links to external systems;
   - covers marketplace categories, competitor category links, competitor product URLs, imported offer IDs, and moderation state;
   - sources mapping and competitor discovery read/write this table.
7. `pim_runs`
   - one table for import/export/enrichment/connector run history;
   - replaces JSON run docs like `catalog_import_runs.json`, `catalog_export_runs.json`, connector scheduler docs where possible.
8. `pim_connector_accounts`
   - replaces connector method/settings/import store split;
   - stores masked credentials/config/status per organization/provider/store.
9. `pim_external_snapshots`
   - cache table for heavy external payloads from marketplaces and competitors;
   - replaces most marketplace cache documents in `json_documents`;
   - not a source of truth, rebuildable.

Control-plane tables stay separate:

1. `platform_users`;
2. `organizations`;
3. `organization_members`;
4. `organization_invites`;
5. `tenant_registry` and `tenant_provisioning_jobs` only if real multi-tenant provisioning remains.

Why not one table:

1. product rows are updated frequently by content managers;
2. parameter values are high-cardinality and need filtering/search/validation;
3. marketplace and competitor evidence can grow much faster than product identity;
4. import/export run logs and external snapshots are caches/history, not product truth;
5. separate domain tables allow partial indexes without making every page scan giant JSON.

Accepted denormalization:

1. `pim_products` should be wide and include UI-ready JSON summaries to avoid reassembling catalog/product lists from many joins;
2. `pim_model_fields` should include marketplace/competitor mapping JSON so mapping pages share one source;
3. `pim_channel_links` should include moderation state and link candidates so competitor/category/source pages share one source;
4. derived summaries can live inside JSONB columns if they are explicitly rebuildable.

Migration principle:

1. create new consolidated tables beside old tables;
2. backfill from old tables and `json_documents`;
3. add read adapters that serve existing API from new tables;
4. switch write paths page by page;
5. add parity checks;
6. freeze old writes;
7. remove old tables only after production parity and backup.

Required read adapters before write switching:

1. `ConnectorsStateReadAdapter`
   - one source for connector state;
   - replace direct `read_doc(connectors_scheduler.json)` in product/export/Yandex/Ozon paths.
2. `MarketplaceProviderCacheReadAdapter`
   - one source for Yandex/Ozon category trees, params, offer cards, import info, rating and external snapshots.
3. `ProductCatalogReadAdapter`
   - one source for catalog product list/search/page data;
   - replace mixed `load_catalog_product_items`, `query_catalog_product_items`, `query_products_full` usage where page shape matters.
4. `CompetitorMappingReadAdapter`
   - read-only facade over current competitor JSON first;
   - later backed by `pim_channel_links`.
5. `TemplateReadAdapter`
   - typed methods for `get_template`, `list_by_category`, `resolve_for_category`, `editor_payload`;
   - API should stop depending on legacy whole-doc `category_to_template/category_to_templates`.

Most dangerous write paths:

1. product bulk/upsert/import/Yandex sync because they affect SKU, content, counts, registry and page data;
2. `/catalog/products` legacy JSON write path because it can create phantom divergence;
3. template create/update/delete/apply-to-products because it mutates model fields and product features;
4. marketplace mapping AI/save because it mutates mappings, templates, dictionaries and value refs;
5. connector config because it contains tenant-scoped credentials and legacy readers may miss updates;
6. catalog delete/move because category subtree operations can affect products and templates.

Mandatory UI/API QA after read-model changes:

1. `/catalog`;
2. `/products`;
3. `/products/:productId`;
4. `/products/new?category_id=...`;
5. `/templates`;
6. `/templates/:categoryId`;
7. `/sources?tab=sources`;
8. `/sources?tab=params&category=...`;
9. `/sources?tab=values&category=...`;
10. `/data-prep/competitors`;
11. `/catalog/import`;
12. `/catalog/export`;
13. `/connectors/status`;
14. `/`.

Next tasks:

1. use `backend/scripts/db_consolidation_audit.py` before and after every DB migration step;
2. implement `ProductCatalogReadAdapter`;
3. classify all `json_documents` keys and decide cache/run/snapshot/migrate/delete;
4. create idempotent backfill for `pim_categories`, `pim_products`, `pim_models`, `pim_model_fields`;
5. run parity checks and only then add read adapters over consolidated tables.

Product write audit on 2026-04-30:

1. `catalog.py` local `_save_products()` legacy writer is disabled and create/delete routes use product services;
2. `catalog_exchange.py` and `yandex_market.py` `_save_products()` helpers already route through `bulk_upsert_product_items`;
3. no remaining direct `products.json` write was found in the catalog create/delete path.

Connector state adapter status on 2026-04-30:

1. `backend/app/core/connectors_state.py` is the read adapter seam for connector provider settings/import stores;
2. product channel summary, catalog export, Yandex defaults and Ozon defaults use the adapter instead of direct route-level `connectors_scheduler.json` reads;
3. remaining `connectors_scheduler.json` access is limited to relational storage bootstrap/backfill.

## P1 - Catalog Cleanup

Status: reopened / not final.

Goal:

Catalog should be clean: category structure, product viewing, SKU movement, and category actions only.

Rules:

1. no mapping/import/enrichment dashboards in `/catalog`;
2. no marketplace/channel/mapping terminology in main catalog;
3. selected category actions stay near selected category header;
4. product table shows products from selected branch;
5. branch counter and table count must not contradict after reload.

Next tasks:

1. visual QA `/catalog`;
2. remove remaining unclear labels;
3. verify product movement;
4. verify category creation/rename/delete;
5. align tree with shared category workspace.

## P1 - Import / Export Cleanup

Status: first pass done, still active.

Rules:

1. import/export are operational tools, not dashboards;
2. category context must persist from source page to export;
3. import runs and export batches need clear state;
4. category picker should use shared components;
5. long tables need sticky headers.

Next tasks:

1. verify `/catalog/import`;
2. verify `/catalog/export`;
3. verify category query parameter is preserved;
4. verify Excel import path;
5. verify export readiness per marketplace;
6. reduce remaining summary clutter.

## P1 - Product Card And Product Creation

Status: improved, still important.

Product card direction:

1. should feel like an e-commerce product page;
2. content manager sees title, media, SKU, variants, values, sources, channel readiness quickly;
3. parameters show source/evidence and final output;
4. competitor candidate matching supports multiple alternatives;
5. rejected candidates do not reappear as primary suggestions unless restored.

Creation direction:

1. product can be created before full enrichment;
2. candidate discovery runs after manual creation or XLS import;
3. if info-model is missing, product can still exist and be enriched later.

Next tasks:

1. continue product card polish;
2. improve competitor matching quality;
3. handle SIM/eSIM distinctions strictly;
4. add manual competitor URL fallback;
5. verify variants for one SKU group;
6. validate no-info-model product path.

## P1 - Competitor Discovery

Status: partially implemented / quality not accepted.

Supported competitor sources:

1. re-store;
2. store77.

Rules:

1. match strictly on model, memory, color, SIM/eSIM, region, generation;
2. show multiple close candidates as alternatives;
3. user accepts one candidate and rejects others;
4. if all rejected, user can paste manual URL;
5. accepted/rejected decisions should improve future suggestions;
6. competitor category links should feed discovery/enrichment where useful.

Next tasks:

1. improve matching quality;
2. make SIM/eSIM parser strict;
3. add candidate carousel UX where needed;
4. add manual URL fallback;
5. show competitor evidence in enrichment/mapping.

## P2 - Connectors

Status: not final.

Goal:

Connector status page must be simple and operational.

Rules:

1. show channel readiness;
2. show credential status;
3. show last sync and errors;
4. show manual actions;
5. hide technical implementation details from normal users;
6. credentials/tokens must stay masked.

Next tasks:

1. redesign `/connectors/status`;
2. simplify connector cards;
3. clarify channel setup path;
4. verify no exposed secrets.

## P2 - Administration

Status: first cleanup done, not final.

Rules:

1. admin pages must be Russian-language only;
2. organization, team, invites, and access need distinct purpose;
3. no technical tenant/default labels unless unavoidable;
4. organization name is `Global Trade`;
5. keep only intended users, no test clutter.

Next tasks:

1. inspect all admin tabs;
2. remove confusing duplicate tables;
3. simplify search;
4. clarify organization/team/invite/access differences;
5. verify layout at desktop widths.

## P2 - Navigation Shell

Status: active redesign / responsive menu bug found on 2026-05-05.

Rules:

1. compact left rail default;
2. expanded menu must open by click and remain pinned until link click, outside click, close button, or Escape;
3. hover may preview a section, but cannot be the only way to open the menu;
4. expanded menu must stay inside viewport on smaller desktop widths;
5. user and theme controls stay in the rail/account entry, not as a heavy duplicated block inside every menu panel;
6. no oversized icons or random floating dropdowns;
7. menu grouped by PIM workflow, not technical page names;
8. active state works for tabbed links.

Next tasks:

1. verify click-pinned menu and smaller-width behavior in Browser Use/in-app browser;
2. verify active state for tabbed links;
3. reduce remaining dashboard/menu English labels (`Control Center`, `Sources / Mapping`, `Channels`). Status: done for `/` dashboard on 2026-05-06;
4. add real counters later from backend queues/errors.

## P3 - Testing And Deploy Hardening

Status: needed.

Tasks:

1. add smoke coverage for catalog/templates/sources critical read endpoints;
2. consider frontend route smoke once Browser Use is stable;
3. consider code splitting to reduce Vite large chunk warning;
4. later consider SSH key auth to remove password-based deploy entirely.

## Definition Of Done For Current Phase

1. Every core page has one obvious primary job.
2. No major page starts with decorative dashboard clutter.
3. Repeated blocks are removed or shared.
4. All visible UI text is understandable to a content manager.
5. Key user path for `Смартфоны` can be completed without explanation.
6. Production browser checks pass without console errors.
