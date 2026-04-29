# SmartPim Rebuild Master Plan

## 1. Status

This is the only active working document for the SmartPim rebuild.

All older redesign notes, intermediate decisions, and historical execution logs are no longer active instructions.

Current active phase:

1. continue full product visual QA page by page;
2. remove duplicate/local UI decisions;
3. keep making heavy workflow screens simpler, cleaner, and more action-oriented;
4. verify every changed page in the in-app browser before marking it done.

Current production baseline:

1. authentication and organization registration are working;
2. main SaaS shell exists with compact left navigation;
3. product list and product card are substantially improved;
4. catalog was simplified but still needs more visual and workflow QA;
5. info-model editor is improved but still under active polishing;
6. category/parameter/value mapping is improved but still needs a full user-path pass;
7. connector/admin pages were improved once but still need cleanup and consistency checks;
8. competitor discovery exists conceptually and partially in product/category workflows, but matching quality still needs iteration.

## 2. Product Decisions

### 2.1 Core Product

SmartPim is a PIM control center for:

1. organization setup;
2. user and access management;
3. channel/import/export setup;
4. catalog category structure;
5. info-model generation;
6. marketplace category and parameter mapping;
7. product creation/import/enrichment;
8. media, relations, analogs, variants, and competitor evidence;
9. marketplace validation and export.

### 2.2 Primary Entity

The main entity is the product SKU.

Rules:

1. one product record equals one SKU;
2. variants also have their own SKU;
3. variants are grouped through variant/product groups;
4. product enrichment is the most frequent working task;
5. catalog, info-models, channels, and mappings are setup contexts around products.

### 2.3 Product Data Model Direction

Use a mixed model:

1. stable product identity fields live on the product record;
2. category/channel-specific values live in normalized value tables;
3. channel readiness/export state is stored per product and channel;
4. media is stored through S3-backed assets;
5. analogs, related products, accessories, and variants are stored as product relations/groups.

### 2.4 Marketplace Rules

Every marketplace/channel can have:

1. its own category tree;
2. its own required parameters;
3. its own accepted values;
4. its own spelling/formatting for values;
5. its own validation/export rules.

Therefore PIM values must be normalized internally and mapped to each channel output.

## 3. Target User Workflow

### 3.1 Organization Setup

1. register organization;
2. create users;
3. assign roles and access;
4. connect channels/import/export sources.

### 3.2 Catalog And Info-Model Setup

1. create or import catalog categories;
2. select category;
3. collect fields from marketplaces, products, imports, and sources;
4. normalize equal fields into one PIM field;
5. review proposed fields;
6. approve info-model;
7. map PIM fields to marketplace fields;
8. map PIM values to marketplace values.

### 3.3 Product Creation And Enrichment

Entry A: manual product creation.

1. user creates SKU;
2. system suggests competitor/source candidates;
3. user confirms the correct source links;
4. parameters are imported from all confirmed sources;
5. product values are normalized into PIM fields;
6. marketplace output values are prepared.

Entry B: XLS/product import.

1. user imports products;
2. SKUs appear in category;
3. source/competitor candidates are generated;
4. content manager moderates links;
5. parameters are imported and normalized;
6. products move through validation/export readiness.

Entry C: enrichment of existing products.

1. user opens product/category;
2. missing fields and problematic mappings are highlighted;
3. competitor and marketplace evidence is shown per field;
4. user confirms or edits values;
5. product is validated and prepared for export.

### 3.4 Marketplace Export

1. select category or products;
2. validate required fields and values per marketplace;
3. show missing/problem rows;
4. prepare export payload;
5. send/export when ready.

## 4. UX Direction

Reference direction:

1. modern desktop SaaS;
2. closer to Attio / Brandquad / PIM cloud patterns;
3. dense but readable;
4. working pages first, dashboards only where useful;
5. no large hero blocks above real work;
6. no decorative panels that duplicate state;
7. clear action hierarchy;
8. compact navigation;
9. light and dark themes must both remain readable.

Hard UX rules:

1. every screen should answer: what is this page for, what should I do now, what is blocking me;
2. every page must perform one primary task;
3. secondary navigation must be low-emphasis;
4. repeated data must be removed or merged;
5. no English labels in visible UI unless they are real marketplace/source names;
6. no unexplained internal terms like `draft`, `confidence`, `context`, `readiness`;
7. no dashboard blocks above working content unless the page is actually a dashboard;
8. every long table must have sticky headers and safe horizontal scroll;
9. sticky sidebars/inspectors are allowed only if they reduce work, not for decoration;
10. browser visual QA is required after frontend changes.

## 5. Universal UI Rules

Universal blocks must be shared or follow one shared contract:

1. buttons;
2. badges;
3. tabs;
4. metric/status strips;
5. empty states;
6. drawers/modals;
7. tables;
8. tree/category navigation;
9. inspectors;
10. import/export pickers;
11. search/filter bars;
12. product/source evidence cards.

Do not create one-off local versions of these unless the block appears only once and cannot become generic.

Page-level logic can stay feature-specific, but visual and interaction patterns must be reused.

## 6. Current Page Status

### 6.1 Login / Registration

Status: accepted enough for now.

Current rules:

1. login and registration use one visual structure;
2. registration should not scroll on standard desktop;
3. animated transition between login/register stays slower and directional;
4. no top `PIM / Workspace` badge.

### 6.2 Navigation Shell

Status: active redesign.

Current rules:

1. compact left rail is the default;
2. expanded menu should be full-height and stable on hover;
3. user, organization, role, and theme toggle must be visible in shell/account area;
4. no oversized icons or random floating dropdowns;
5. menu is grouped by PIM workflow, not by technical page names;
6. expanded panel must explain the current working contour with a short process sequence;
7. route links may point directly to tabbed work modes via `?tab=...`;
8. labels must be user-facing and Russian, not technical.

Accepted navigation contours:

1. `Рабочий стол`
   - tasks, errors, latest actions;
   - current route: `/`;
2. `Каталог`
   - category structure, all SKU, product creation, groups/variants, content quality;
   - routes: `/catalog`, `/products`, `/products/new`, `/catalog/groups`, `/catalog/content-index`;
3. `Модели`
   - info-model catalog, marketplace fields, dictionaries, value normalization;
   - routes: `/templates`, `/sources-mapping?tab=params`, `/dictionaries`, `/sources-mapping?tab=values`;
4. `Насыщение`
   - product import, competitor matching, enrichment proposals, moderation queue;
   - routes: `/catalog/import`, `/sources-mapping?tab=competitors`, `/sources?tab=competitors`;
5. `Каналы`
   - category mapping, parameter mapping, value rules, connector/API status;
   - routes: `/sources?tab=sources`, `/sources?tab=params`, `/sources?tab=values`, `/connectors/status`;
6. `Экспорт`
   - export preparation, validation, channel readiness;
   - routes: `/catalog/export`, `/sources?tab=values`, `/connectors/status`;
7. `Медиа`
   - media files, S3, product bindings, infographics;
8. `Администрирование`
   - organization, team, roles, invites, platform settings.

Open tasks:

1. verify hover stability and full-height panel on production after every shell change;
2. verify active state for tabbed links;
3. add real counters later from backend when queues/errors are ready;
4. keep this shell as the only global navigation source.

### 6.2.1 Category Workspace Unification

Status: active / mandatory.

Problem:

Pages that work with the same category tree were built independently and now look and behave differently. This is not acceptable for the PIM workflow.

Pages that must be edited and visually aligned:

1. `/catalog`
   - final category structure;
   - product list in selected category;
   - product movement between categories;
   - no mapping/import/enrichment dashboards inside the main catalog screen;
2. `/catalog/import`
   - category tree must use the same density, search wording, expand/collapse behavior, active state, and counters as `/catalog`;
   - import-only controls are allowed, but they must be visually expressed as workspace filters, not a different catalog implementation;
   - exact SKU selection can exist as a secondary import tool, but must not replace or visually redefine the catalog tree;
3. `/templates`
   - same category-tree density, search, expansion behavior, and selected-state logic as catalog;
   - only info-model state and actions;
4. `/templates/:categoryId`
   - model assembly and proposal review for one category;
   - no duplicated category context or summary blocks;
5. `/sources?tab=sources&category=:id`
   - category-to-marketplace binding;
   - same tree component behavior as catalog/templates;
   - no top `Сводка` dashboard above the work area;
6. `/sources?tab=params&category=:id`
   - parameter mapping for selected category;
   - category switch must not take over the whole page;
7. `/sources?tab=values&category=:id`
   - value mapping for selected category;
   - sticky headers and horizontal scroll for long tables;
8. `/sources?tab=competitors&category=:id`
   - competitor category/product evidence for enrichment;
   - must not mix category binding, product matching, and parameter mapping in one visual pile.

Universal category workspace rules:

1. category tree has one shared visual language:
   - same card shape;
   - same search;
   - same active state;
   - same counters/badges density;
   - same expand/collapse behavior;
2. `Свернуть` collapses the tree to the selected category parent chain, not to a random saved state;
3. `Развернуть` expands all visible branches;
4. search temporarily expands matching branches but does not destroy manual expansion state;
5. heavy summaries and KPI dashboards are removed from category work screens unless they directly support the current action;
6. if a page needs metrics, they live inline near the selected object, not as a dashboard above the work area;
7. terminology must be the same everywhere:
   - `Категории`;
   - `Товары`;
   - `Инфо-модель`;
   - `Поля`;
   - `Значения`;
   - `Каналы`;
   - `Конкуренты`;
8. no page should introduce its own local category tree style unless it becomes the new shared component.

Execution order:

1. fix `/templates` collapse behavior;
2. remove `/sources?tab=sources` top summary and align page header with `/templates`;
3. align `/catalog` tree header, search, buttons and selected state with `/templates`;
4. extract shared category tree/workspace component if the third page still duplicates logic;
5. verify all listed pages in in-app browser.

Current implementation note for `/catalog`:

1. `/catalog` is a two-column workspace: category tree + selected category products;
2. the old right inspector is removed from catalog because it duplicated actions and added mapping/status noise;
3. selected-category actions live in the selected category header:
   - add SKU;
   - create subcategory;
   - rename;
   - delete branch;
4. product card keeps only product-table actions, currently `Полный список`;
5. no marketplace/channel/mapping terminology should appear on the catalog screen;
6. product table in catalog must show products from the selected branch, not only direct products of the selected node;
7. branch counter and product table count must not contradict each other after reload.

### 6.3 Catalog

Status: reopened / not final.

Current direction:

1. catalog should be clean;
2. catalog is mainly for final category structure, product viewing, and product movement;
3. intermediate mapping/import/enrichment dirt should live in dedicated pages;
4. no heavy dashboard at the top;
5. category tree, product list, and selected-category actions must be readable without explanation.

Open tasks:

1. review `/catalog` visually again;
2. remove remaining unclear labels;
3. keep only category/product workflow in catalog;
4. move mapping/import/status complexity to mapping/import pages;
5. verify product movement/category structure path.

### 6.4 Info-Model Catalog

Status: active cleanup.

Current accepted structure for `/templates`:

1. page has two columns only:
   - category/model tree;
   - selected category workspace;
2. no separate right `Сводка модели` inspector;
3. page header has no selected-category action buttons;
4. expand/collapse controls belong to the tree, not the page header;
5. selected category workspace owns actions:
   - create model;
   - open editor/source;
   - open category;
   - open products;
   - delete own model;
6. summary metrics are inline and compact, not separate dashboard cards;
7. model usage blocks are supporting context only and must not duplicate the main action panel.

Open tasks:

1. visually verify `/templates` after every layout change;
2. check selected categories with own model, inherited model, locked empty node, and creatable empty node;
3. keep wording focused on user action, not technical status.

### 6.5 Info-Model Editor

Status: active polishing.

Current accepted structure:

1. no permanent left duplicate navigation;
2. no separate right `Сводка модели` panel;
3. main workspace uses full width;
4. top assembly block is compact;
5. page header contains only global page actions:
   - `Создать модель` only when the category has no own model;
   - `Сохранить` when an own model exists;
   - import/export and delete are secondary actions inside the model workspace;
6. visible terms are user-facing:
   - `Сборка инфо-модели`;
   - `Поля карточки товара`;
   - `Поля из площадок и товаров`;
   - `совпадение`, not `уверенность`;
   - `Добавить в модель`, not `Принять`;
   - `Не использовать`, not `Отклонить`;
7. top status bar must not look like tabs and must keep only high-level counters:
   - found fields;
   - fields already in model;
   - source counts;
8. review count belongs to the proposal review block, not the top assembly status;
9. proposal review block must not duplicate the top approve action;
10. proposal review block appears immediately after the assembly block;
11. model name, import/export, delete, and navigation links are hidden under `Настройки и переходы`;
12. proposal review uses status filters:
   - `На проверке`;
   - `В модели`;
   - `Не используется`;
   - `Все`;
13. related navigation is secondary and must not compete with the main review workflow.

Open tasks:

1. continue visual QA on `/templates/:categoryId`;
2. make field proposal review easier to scan;
3. make accepted/rejected/review states visually clearer;
4. ensure model creation from marketplace fields is understandable without explanation;
5. verify category with no info-model and category with approved model.

### 6.6 Parameter Mapping

Status: improved, still active.

Current direction:

1. one selected category at a time;
2. no permanent catalog tree on primary work screen;
3. category switch through drawer/button;
4. main work is parameter queue and selected-field inspector;
5. marketplace bindings editable in inspector;
6. competitor evidence must be visible where it helps fill/verify fields;
7. `Сопоставить с AI` must remain visible where AI mapping is available;
8. SKU GT and other service fields must not be removed if needed for marketplace export.

Open tasks:

1. run full user path for `Смартфоны`;
2. verify marketplace field import for Ozon/Yandex;
3. verify competitor evidence from re-store/store77;
4. remove duplicate counters and confusing tabs;
5. decide if category tree is hidden by default and opens only when needed;
6. make editing current binding obvious.

### 6.6 Value Mapping

Status: first pass done, needs deeper QA.

Current direction:

1. PIM value must map to marketplace output value;
2. user must see alternatives per marketplace;
3. value spelling differences must be explicit;
4. examples: internal `256 GB`, marketplace can need `256ГБ`, `256 GB`, or dictionary ID;
5. long value tables need sticky headers and horizontal scroll.

Open tasks:

1. inspect parameter values pages again;
2. verify value alternatives and marketplace output;
3. verify validation errors per marketplace;
4. simplify any overwhelming blocks.

### 6.7 Product List

Status: mostly accepted, keep checking during flows.

Current direction:

1. product list is product-first, not dashboard-first;
2. category context and filters should not hide the product rows;
3. product cards/rows must show enough data to pick the correct SKU;
4. missing enrichment/export problems should be visible.

### 6.8 Product Card

Status: much improved, still important.

Current direction:

1. product card should feel like an e-commerce product page;
2. content manager must quickly see title, media, SKU, variants, values, sources, and channel readiness;
3. parameters show source/evidence and final output;
4. competitor candidate matching should support carousel/multiple candidates;
5. rejected candidates should not reappear as primary suggestions unless manually restored.

Open tasks:

1. continue card polish;
2. improve competitor matching quality;
3. handle SIM/eSIM distinctions strictly;
4. support manual competitor URL when all candidates are rejected;
5. verify variants for one SKU group.

### 6.9 Product Creation

Status: first pass done, needs path validation.

Current direction:

1. creation must be compact;
2. product can be created before full enrichment;
3. candidate discovery should run after creation or import;
4. if info-model is missing, product can still exist and later be enriched.

Open tasks:

1. create test product flow again;
2. verify variants;
3. verify no-info-model behavior;
4. verify transition to enrichment.

### 6.10 Sources / Import / Export

Status: improved, still active.

Current direction:

1. import/export pages are operational tools, not dashboards;
2. category context must persist from source page to export;
3. import runs and export batches must have clear state;
4. category picker should be shared;
5. long tables need sticky headers.

Open tasks:

1. verify `/catalog/import`;
2. verify `/catalog/export`;
3. verify category query parameter is preserved;
4. verify Excel import path;
5. verify export readiness by marketplace.

### 6.11 Connectors

Status: not final.

Current direction:

1. connector status page must be simple;
2. show channel readiness, credentials status, last sync, errors, and manual actions;
3. remove oversized summary/dashboard blocks;
4. hide technical implementation details from normal users;
5. credentials/tokens must stay masked.

Open tasks:

1. redesign `/connectors/status`;
2. simplify connector cards;
3. clarify channel setup path;
4. verify no exposed secrets.

### 6.12 Administration

Status: first cleanup done, not final.

Current direction:

1. admin pages should be clear and Russian-language only;
2. organization, team, invites, and access must have distinct purpose;
3. no technical tenant/default labels in user-facing surfaces unless unavoidable;
4. organization name is `Global Trade`;
5. keep only the intended user(s), no test clutter.

Open tasks:

1. inspect all admin tabs again;
2. remove confusing duplicate tables;
3. simplify search;
4. clarify organization/team/invite/access differences;
5. verify layout at desktop widths.

### 6.13 Competitor Discovery

Status: partially implemented / quality not accepted.

Current direction:

1. supported competitor sources: re-store, store77;
2. competitor catalog/category links should be collected and linked to PIM category where possible;
3. product candidate matching should be strict on model, memory, color, SIM/eSIM, region, and generation;
4. multiple close candidates should be shown as alternatives for moderation;
5. user can accept one candidate and reject others;
6. if all rejected, user can paste manual URL;
7. accepted/rejected decisions should improve future suggestions.

Open tasks:

1. improve matching quality;
2. make SIM/eSIM parsing strict;
3. add candidate carousel UX where needed;
4. add manual URL fallback;
5. show competitor evidence inside enrichment/mapping where it helps.

## 7. Page Work Protocol

For every page/tab before editing:

1. identify the route;
2. define the page’s one primary job;
3. list universal blocks;
4. list feature-specific blocks;
5. list one-off blocks;
6. remove duplicated data/actions;
7. define source -> user action -> result;
8. check if sticky headers/sidebars are needed;
9. check empty, loading, error, dense-data, and long-scroll states.

For every page/tab after editing:

1. run build;
2. deploy if production verification is required;
3. inspect in Browser Use/in-app browser;
4. check console errors and warnings;
5. update this document;
6. close external Playwright/Chrome processes if any were started;
7. commit and push when the slice is stable.

## 8. Browser QA Protocol

Use Browser Use / in-app browser for visual checks.

Required checks:

1. page opens directly by URL;
2. page reloads without losing required context;
3. no console errors/warnings;
4. primary workflow is visible above the fold;
5. no overlapping text;
6. no clipped buttons;
7. no unreadable colors in current theme;
8. no hidden horizontal overflow unless it is an intentional table scroll;
9. sticky elements do not cover content;
10. loading and empty states are understandable.

After work, external Playwright/Chrome processes must be closed.

## 9. Immediate Next Work

Recommended order:

1. finish current `Info Model Editor` polish;
2. run full path for `Смартфоны`: collect info-model -> review fields -> map marketplace parameters -> map values -> enrich products -> export readiness;
3. rework `Parameter Mapping` if the path still feels confusing;
4. inspect `Value Mapping`;
5. inspect `Connectors`;
6. inspect `Admin`;
7. return to `Catalog` cleanup;
8. continue product card and competitor discovery improvements.

Definition of done for the current phase:

1. every core page has one obvious primary job;
2. no major page starts with decorative dashboard clutter;
3. repeated blocks are removed or merged;
4. all visible UI text is understandable to a content manager;
5. key user path for `Смартфоны` can be completed without explanation;
6. production browser checks pass without console errors.
