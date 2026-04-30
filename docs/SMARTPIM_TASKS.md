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

## Completed Recent Slices

1. `807e815 Align import export scope controls`
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
9. `/sources?tab=competitors&category=:id`.

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
4. remove duplicate counters/tabs in parameter mapping;
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

Target rules:

1. one product row equals one SKU;
2. variants are product rows grouped by `group_id`, not separate variant rows;
3. media binaries stay in S3/object storage; DB stores references only;
4. raw source evidence and final canonical values must be separated;
5. derived tables must be rebuildable and never manually edited;
6. every JSON document that remains in `json_documents` must be classified as cache, run log, external snapshot, or migration backlog item.

Next tasks:

1. create a safe DB cleanup script with dry-run mode for backup tables and stale test organizations;
2. add a parity check between `products_rel` and legacy `json_documents.products.json`;
3. add a parity check between `catalog_nodes_rel` and legacy `json_documents.catalog_nodes.json`;
4. decide whether `deploy/sql/*` becomes official migrations or is removed;
5. migrate `product_variants_rel` final row into `products_rel`/group model or drop after confirmation;
6. classify all `json_documents` keys and move active operational docs to explicit tables where needed;
7. define final minimal schema proposal before destructive DB cleanup.

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

Status: active redesign.

Rules:

1. compact left rail default;
2. expanded menu full-height and stable on hover;
3. user, organization, role, and theme toggle visible in shell/account area;
4. no oversized icons or random floating dropdowns;
5. menu grouped by PIM workflow, not technical page names;
6. active state works for tabbed links.

Next tasks:

1. verify hover stability and full-height panel on production;
2. verify active state for tabbed links;
3. add real counters later from backend queues/errors.

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
