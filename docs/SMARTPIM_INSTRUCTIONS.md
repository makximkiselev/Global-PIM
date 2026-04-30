# SmartPim Agent Instructions

This is the only active instruction document for working in this repository.

Do not create new `.md` documents for plans, notes, specs, or task tracking. If a new instruction is needed, update this file. If a new task is needed, add it to `docs/SMARTPIM_TASKS.md` by priority.

## Project

SmartPim is a desktop-first PIM control center.

Core workflow:

1. register organization;
2. add users and access rights;
3. connect import/export channels;
4. create catalog categories;
5. collect and approve info-model fields;
6. map categories, parameters, and values to marketplaces;
7. create/import/enrich products;
8. manage media, relations, analogs, variants, competitor evidence;
9. validate and export products.

Main entity rule:

1. one product record equals one SKU;
2. variants also have their own SKU;
3. variants are grouped through product groups;
4. products are the most frequent operational entity;
5. catalog, info-models, channels, and mappings are setup contexts around products.

Media rule:

1. binary media lives in S3/object storage;
2. product DB stores media references in product content fields such as `media_images`, `media_videos`, and `media_cover`;
3. do not move binary media into Postgres.

## Repository

Root:

```bash
/Users/maksimkiselev/Desktop/Global PIM
```

Production:

```bash
https://pim.id-smart.ru
```

Backend service:

```bash
global-pim.service
```

Server:

```bash
root@5.129.199.228
```

App path on server:

```bash
/opt/projects/global-pim
```

Local backend health:

```bash
http://127.0.0.1:18010/api/health
```

Public health:

```bash
https://pim.id-smart.ru/api/health
```

## Secrets And Access

Do not write passwords, tokens, API keys, or private credentials into repository files or chat answers.

Local production environment is stored outside the repo:

```bash
/Users/maksimkiselev/.config/global-pim/production.env
```

Use it like this:

```bash
set -a
source /Users/maksimkiselev/.config/global-pim/production.env
set +a
```

The deploy script reads:

1. `APP_SERVER_PASSWORD`;
2. `APP_SERVER_HOST`;
3. `APP_SERVER_USER`;
4. `APP_SERVER_PORT`;
5. `APP_SERVER_PATH`;
6. `APP_SERVICE_NAME`;
7. `DB_CA_CERT_PATH`;
8. `APP_PUBLIC_BASE_URL`.

Never print the env file contents.

Do not `source backend/.env` in shell scripts. Some application env values are not shell-escaped. If a script needs backend env values, parse key/value lines deliberately and never print secrets.

## Local Commands

Install backend dependencies:

```bash
make backend-install
```

Install frontend dependencies:

```bash
make frontend-install
```

Run backend locally:

```bash
make backend-dev
```

Run frontend locally:

```bash
make frontend-dev
```

Build frontend:

```bash
make frontend-build
```

Run backend tests:

```bash
make test
```

Run API read smoke tests:

```bash
make smoke-api
```

Run backend compile check:

```bash
make check-backend
```

Run full baseline check:

```bash
make check
```

Current expected baseline:

1. `make test` should pass;
2. `make check-backend` should pass;
3. `cd frontend && npm run build` should pass;
4. Vite may warn about large chunks; this warning is not a blocker for current UI work.

## Production Deploy

Deploy current backend app and frontend dist:

```bash
CI=1 ./scripts/deploy_production.sh
```

The deploy script loads `/Users/maksimkiselev/.config/global-pim/production.env` automatically. Use `APP_ENV_FILE=/path/to/file` only if another env file is required.

Fast deploy when `frontend/dist` is already built and only backend/scripts need to be shipped:

```bash
CI=1 ./scripts/deploy_production.sh --skip-build
```

The deploy script waits for backend health after restart. If it still reports a transient local health failure, wait 20 seconds and verify manually. The service can take roughly 15-20 seconds to finish startup after restart.

Manual post-deploy checks:

```bash
curl -sS https://pim.id-smart.ru/api/health
curl -sS https://pim.id-smart.ru/ | grep -o 'assets/index-[^" ]*' | head -2
```

Server operations use the same local env file automatically:

```bash
scripts/server_ops.sh health
scripts/server_ops.sh public-health
scripts/server_ops.sh status
scripts/server_ops.sh logs
scripts/server_ops.sh restart
```

Server config backup:

```bash
scripts/backup_server_config.sh
```

Production deploy/backup scripts must not interpolate `APP_SERVER_PASSWORD` into command strings. Pass it through environment variables into `expect` and use `send -- "$env(APP_SERVER_PASSWORD)\r"`.

## Browser QA

Use Browser Use / in-app browser when the user asks to inspect, test, or visually verify production/local UI.

Required checks for changed frontend pages:

1. direct URL opens;
2. reload keeps required context;
3. no console errors;
4. primary workflow is visible above the fold;
5. no overlapping text;
6. no clipped buttons;
7. colors are readable;
8. no accidental horizontal overflow except intentional table scroll;
9. sticky elements do not cover content;
10. empty/loading/error states are understandable.

If Browser Use has no active in-app pane, state that clearly and do not pretend visual QA was completed. Use build, curl, DOM/API checks as fallback only.

After browser automation, close any external Playwright/Chromium processes started by the agent. Do not kill unrelated user browser processes.

## Git

Default branch:

```bash
main
```

Commit stable slices frequently.

Before commit:

```bash
git status --short
```

Commit:

```bash
git add <changed-files>
git commit -m "<clear message>"
git push origin main
```

Do not amend commits unless the user explicitly asks.

Do not revert user changes unless the user explicitly asks.

## Autonomous Team Protocol

Default operating model:

1. the main Codex agent is the tech lead and integrator;
2. subagents are domain workers, not final approvers;
3. subagents may inspect and patch only their assigned ownership zone;
4. the integrator reviews every subagent diff before staging;
5. no change is approved until relevant checks pass locally.

Domain ownership:

1. Backend/API owner:
   - `backend/app/api/**`;
   - `backend/app/core/**`;
   - backend route/service tests in `backend/tests/**`.
2. DB/storage owner:
   - `backend/app/storage/**`;
   - `backend/scripts/db_*`;
   - `deploy/sql/**`;
   - DB audit/backfill/parity logic.
3. Frontend/UI owner:
   - `frontend/src/components/**`;
   - `frontend/src/features/**`;
   - `frontend/src/routes/**`;
   - `frontend/src/styles/**`.
4. DevOps/deploy owner:
   - `scripts/**`;
   - `Makefile`;
   - deployment and server operation scripts.
5. Documentation/task owner:
   - `docs/SMARTPIM_INSTRUCTIONS.md`;
   - `docs/SMARTPIM_TASKS.md`.

Integrator-only decisions:

1. schema direction and data ownership changes;
2. route/page structure changes that affect multiple workflows;
3. shared component API changes;
4. production deploys;
5. commits and pushes;
6. destructive DB or filesystem operations;
7. creating/deleting documentation files.

Subagent task rules:

1. every subagent prompt must state the repo path;
2. every subagent prompt must state that other agents may be editing concurrently;
3. every subagent prompt must define file/module ownership;
4. every subagent prompt must forbid reverting unrelated edits;
5. every subagent prompt must require a final report with changed files, checks, and risks;
6. do not assign the same file ownership to two active subagents;
7. do not let agents edit production secrets or print secret values;
8. close finished or stalled subagents before final response.

Parallel work rules:

1. run DB, backend, and frontend work in parallel only when file ownership is disjoint;
2. keep cross-cutting refactors small and staged;
3. if a backend API shape changes, frontend work must wait for the new response contract or use a typed compatibility layer;
4. if a DB storage path changes, route writes must be switched only after parity/read-adapter checks;
5. if frontend shared components change, test at least one route that uses the component and one route that was not edited directly.

Review checklist before accepting subagent changes:

1. inspect `git diff` manually;
2. confirm no secrets were added;
3. confirm no unrelated files were changed;
4. confirm no local duplicate component/style was introduced;
5. confirm no legacy JSON write path was introduced;
6. confirm error/loading/empty states are not broken;
7. confirm tests/build match the changed area.

Required gates by change type:

1. backend route/service change:
   - `python3 -m py_compile <changed python files>`;
   - targeted unittest for touched workflow;
   - `make test` before commit when storage/auth/product/mapping logic changes.
2. DB/storage change:
   - `python3 backend/scripts/db_consolidation_audit.py`;
   - targeted storage tests;
   - no destructive SQL unless explicitly approved;
   - backfill/parity plan documented in `docs/SMARTPIM_TASKS.md`.
3. frontend change:
   - `cd frontend && npm run build`;
   - Browser Use/in-app visual check when a page layout changes and browser tools are available;
   - no page-specific duplicate of shared buttons, tree, tables, tabs, panels, or badges.
4. deploy/script change:
   - shell syntax/readability check where possible;
   - never print passwords/tokens;
   - keep production env outside repository.
5. documentation-only change:
   - `git diff --check`.

Commit rules:

1. one commit should contain one coherent slice;
2. avoid mixing unrelated frontend, backend, DB, and deploy changes;
3. when a mixed commit is necessary, the final answer must explain why;
4. commit only after all relevant gates pass;
5. push only after `git status --short` shows only intended staged/committed changes.

## Frontend Architecture Rules

Active routes are in `frontend/src/app/App.tsx`.

Protected route targets use `frontend/src/routes/*` wrappers and `frontend/src/features/*` implementations. `frontend/src/pages/*` is kept only for active standalone/auth pages that are still imported by `App.tsx`.

Universal UI blocks must be shared or follow one shared contract:

1. buttons;
2. badges;
3. tabs;
4. metric/status strips;
5. empty states;
6. drawers/modals;
7. tables;
8. category tree/navigation;
9. inspectors/action panels;
10. import/export pickers;
11. search/filter bars;
12. product/source evidence cards.

Do not create new local versions of these blocks. Extend shared components first.

Current shared direction:

1. `PageHeader` for page context only;
2. `WorkspaceFrame` for page columns;
3. `CategorySidebar` for category/model tree shells;
4. `CategoryScopeSelector` for `Весь каталог`, `Вся ветка`, `Только категория`;
5. `DataToolbar` for compact work-area title/actions;
6. `DataTable` / future `TableFrame` for long tables.

## Visual Language

SmartPim design direction:

1. modern desktop SaaS;
2. operational PIM, not marketing landing page;
3. warm light base by default;
4. orange accent for active/action states, not constant fill;
5. dense but readable;
6. broad working canvas;
7. no oversized hero blocks above real work;
8. no decorative cards that duplicate state;
9. no purple/default SaaS look;
10. no English UI labels unless they are real source/channel names.

Data-heavy screens:

1. keep one primary work area;
2. supporting panels must support the work, not duplicate the center;
3. use sticky headers and horizontal scroll for long tables;
4. keep primary identifiers visible;
5. reduce button noise;
6. hide secondary/destructive actions behind disclosure when possible;
7. avoid card-inside-card-inside-card layouts.

Category workspace rules:

1. category tree has one shared visual language;
2. search wording, density, active state, counters, expand/collapse must be consistent;
3. `Развернуть` expands all visible branches;
4. `Свернуть` should collapse to the useful parent chain, not random state;
5. `С подкатегориями` is a technical backend flag and must not be user-facing wording;
6. use `Весь каталог`, `Вся ветка`, `Только категория`, or exact SKU selection.

## Database Direction

Do not rewrite the database blindly.

Current table count from `backend/app/storage/relational_pim_store.py`: 44.

Current source-of-truth rules:

1. `products_rel` is canonical for SKU identity, category, group, status, main content JSON, and core SKU identifiers;
2. `catalog_product_registry_rel` is derived/read-model data;
3. `catalog_product_page_rel` and `catalog_product_page_tenant_rel` are derived/read-model data;
4. `product_marketplace_status_rel` and tenant variant are channel readiness/status data and need ownership clarification;
5. `product_variants_rel` is a migration candidate because the accepted model is one SKU equals one product row;
6. template/info-model data currently lives in `templates_*`, `template_attributes_*`, and `category_template_links_*`;
7. category/parameter/value mappings are split across category mappings, attribute mappings, value refs, dictionaries, aliases, provider refs, and export maps;
8. tenant/global duplicate tables must be audited before migration.

Target data direction:

1. products: one row per SKU;
2. product groups: grouping only;
3. product relations: analogs, related, accessories, replacements, variants if needed;
4. product media: metadata and S3 references;
5. product source values: raw imported/enriched evidence;
6. product canonical values: approved PIM values;
7. categories: catalog tree;
8. info models and fields: approved model per category or inherited reference;
9. channel categories: marketplace/competitor category links;
10. channel field mappings: external fields to canonical fields;
11. value mappings: canonical value to channel output value;
12. competitor links: accepted/rejected evidence URLs;
13. connector accounts and runs: credentials/config and sync history;
14. derived tables must be named, documented, rebuildable, and never manually edited.

## Work Protocol

For every page/tab before editing:

1. identify the route;
2. define the page’s one primary job;
3. list universal blocks;
4. list feature-specific blocks;
5. list one-off blocks;
6. remove duplicated data/actions;
7. define source -> user action -> result;
8. check if sticky headers/sidebars are needed;
9. check empty/loading/error/dense-data/long-scroll states.

For every page/tab after editing:

1. run build/tests appropriate to the change;
2. deploy if production verification is required;
3. inspect in Browser Use/in-app browser when available;
4. check console errors and warnings;
5. update `docs/SMARTPIM_TASKS.md`;
6. commit and push stable slices.
