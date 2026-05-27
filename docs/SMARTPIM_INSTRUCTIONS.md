# SmartPim Agent Instructions

This is the only active instruction document for working in this repository.

Do not create new `.md` documents for plans, notes, specs, or task tracking. If a new instruction is needed, update this file. If a new task is needed, add it to `docs/SMARTPIM_TASKS.md` by priority.

## Project

SmartPim is a desktop-first PIM control center.

Core workflow:

1. register organization;
2. add users and access rights;
3. connect marketplaces, stores, competitor sources, and source health checks;
4. import products;
5. group SKU variants;
6. map catalog categories and competitor sources;
7. collect and approve info-model fields;
8. map channels, parameters, values, and competitor evidence;
9. enrich products and media;
10. validate and export products.

## Product Navigation Contract

Top-level menu is fixed to four product zones and should be organized around user work, not internal database entities:

1. `Сводка` - operational health, queues, problems, and quick return to active work.
2. `Каталог` - product catalog, products, product groups, product media, infographics, content index, import, and export.
3. `Инфо-модели` - info-models, category matching, parameter matching, dictionaries, competitor sources, and marketplace sources.
4. `Администрирование` - organization, users, rights, roles, invitations, and platform settings.

Do not add new top-level menu groups without explicit approval. New workflows must be added as tabs, sections, or local actions inside one of these four zones.

Menu labels must describe the user's task. Prefer `Импортировать товары`, `Собрать модель`, `Сопоставить параметры`, `Настроить значения`, and `Выгрузить товары` over technical nouns.

Current submenu contract:

1. `Сводка` contains `Рабочая сводка`.
2. `Каталог` contains `Каталог`, `Товары`, `Группы`, `Медиа по товарам`, `Создание инфографики`, and `Импорт / Экспорт`.
3. `Инфо-модели` contains `Инфо-модели`, `Сопоставления`, and `Источники данных`.
4. `Администрирование` contains `Организация` and `Права и роли`.

Use tabs inside a page for close variants of the same work:

1. `Импорт / Экспорт` owns import/export tabs.
2. `Сопоставления` owns category, parameter, value, competitor/platform evidence, and check tabs.
3. `Источники данных` owns marketplace, competitor, store, and connection-status tabs/sections.

`Сопоставить параметры` and `Сопоставление категорий` belong to the info-model workflow. Export belongs to the product catalog workflow.

Media is not a separate top-level zone. Product media lives in the product card and product workflows; infographics and bulk media preparation live under `Каталог`.

Every substantial page must have:

1. one primary user task;
2. clear tab structure for secondary tasks;
3. no duplicated summary/action blocks;
4. shared UI components for repeated buttons, lists, tables, category trees, tabs, selectors, and inspectors;
5. a documented data ownership map in `docs/SMARTPIM_TASKS.md` before backend/schema changes.

Main entity rule:

1. one product record equals one SKU;
2. variants also have their own SKU;
3. variants are grouped through product groups;
4. products are the most frequent operational entity;
5. catalog, info-models, channels, and mappings are setup contexts around products.

Info-model attribute rule:

1. info-models are compositions of global attributes, not isolated local fields per category;
2. if the same business parameter appears in different categories, it must reuse one global `attribute_id` and one dictionary/reference where applicable;
3. examples: `Встроенная память` and `Оперативная память` are shared parameters for smartphones, tablets, laptops, VR devices, and other categories that need them;
4. source/provider names such as `Объем встроенной памяти`, `Внутренняя память`, `storage`, `ROM`, `RAM`, and `Объем оперативной памяти` must be normalized to canonical global attributes before approving an info-model;
5. local template attributes may keep category-specific source evidence and required flags, but must point to the canonical global `attribute_id` and `options.dict_id`;
6. do not create category-local duplicates for parameters that already exist globally.

Unified parameter flow:

1. the operational target is one sellable SKU exported to one or more marketplaces;
2. a product group/family is a helper for shared enrichment and variants, not a replacement for SKU-level facts;
3. marketplace category parameters must be imported first with type, required flag, dictionary values, and export role when the provider exposes it;
4. marketplace category parameters create provider evidence and a skeleton only; they must not be treated as a final info-model without competitor/product evidence;
5. competitor parameters must be imported from matched competitor product URLs with raw name, raw value, source URL, product/SKU evidence, and confidence;
6. existing product fields and SKU title/parser facts are part of the same evidence pool;
7. the canonical info-model draft is created only after marketplace, competitor, product, and title/parser evidence are available or explicitly marked unavailable;
8. marketplace parameters and competitor parameters are evidence for one canonical PIM parameter, not separate isolated maps;
9. a canonical PIM parameter may be exported as a marketplace characteristic, a marketplace base-card field, an export payload field, or several of those at once depending on channel;
10. `Бренд` is a canonical product parameter. It must not be hardcoded as only service/export or only characteristic: per channel it can fill `vendor/brand`, a dictionary value, and/or a category characteristic;
11. canonical PIM values are normalized once, then converted into provider-specific output values per marketplace;
12. value mapping must compare marketplace allowed values, competitor raw values, existing product values, and learned memory before marking export readiness;
13. readiness is SKU-specific and must clearly separate `ready`, `needs parameter mapping`, `needs value mapping`, `missing product value`, `required by provider`, and `not exported intentionally`;
14. family enrichment should copy common facts across a line and isolate variant axes such as memory, color, SIM/eSIM, region, and bundle;
15. scripts may use product titles and competitor evidence to fill variant differences, but every derived value must keep source evidence and be reviewable.
16. competitor discovery status must separate selected SKU state from branch totals. UI labels should explicitly say `для SKU` for the selected product and `в ветке` for aggregate evidence.
17. a queued/running discovery job must block duplicate launches for the same category/product scope and must not coexist with a `not started` message if candidates or links already exist.
18. `Бренд` must remain a canonical parameter in the draft. Do not reintroduce it into service-only export lists or automatic system-row detection; channel-specific `brand/vendor` fields are mappings/evidence for that canonical parameter.
19. when `product_ids` are explicitly provided to competitor discovery, scan only those SKU IDs. Do not silently expand the run to the whole category branch.
20. selected SKU must stay selected after a discovery run, including empty results. Automatic jumps to another SKU are only allowed through an explicit queue/next-SKU action.
21. variant parsing must treat colors as blocking axes for exact card matching. Known Apple colors include `starlight`, `space grey/space gray`, `purple`, `midnight`, `sky blue`, `silver`, `blue`, `orange`, and titanium variants.
22. source-localized color names must be normalized before confidence filtering. For example, `Silver` and `Серебристый`, `Midnight` and `полуночный/темно-синий`, `Sky Blue` and `небесно-голубой` are the same variant axis, not missing required tokens.
23. deterministic competitor seeds are allowed when they produce review candidates, not automatic approval. Store77 MacBook seeds must include line, size, chip, RAM, SSD, color, and part number in the URL/title evidence.
24. export preparation must not parse unconfirmed competitor candidates. Enrich products from confirmed competitor links before export; export itself is a bounded readiness check over current product data.
25. export preparation may run bounded marketplace product-card hydration for the selected stores/SKUs before readiness checks, because marketplace imports are first-party product data for the final catalog;
26. candidate competitor links may be shown for manual review, but only confirmed links may be used for automatic media/parameter enrichment or export-side fallback.
27. candidate moderation must distinguish proven conflicts from unknown data. If both product and competitor SIM profiles are known and different, approval is blocked. If competitor SIM is not recognized, keep it as manual review and allow an explicit source-labelled approval/reject decision.
28. AI competitor candidate discovery must learn from confirmed product-card links, not from prompt edits:
    - use only `pim_channel_links` rows with `scope = competitor_product`, `entity_type = product`, `status = confirmed`, and the same `provider`;
    - validate every AI URL with `detect_site(url) == provider`;
    - pass the AI title/URL through the same variant confidence checks as deterministic discovery;
    - persist AI suggestions only as review candidates (`needs_review` / channel `candidate`), never as confirmed links.
29. long browser-facing operations must not expose raw nginx `504` pages in the UI. Use persisted run/job state and polling when the backend operation can exceed the proxy timeout; show the saved result once the backend finishes.
30. export media selection is separate from media enrichment. Removing media from the export set must not delete the enriched source media, and later enrichment must not automatically re-enable media that the user excluded from export.
31. product media export uses `content.media_images[].selected !== false` and `export_order`/array order. Physical deletion is separate from excluding an image from export.
32. export preparation should use the persisted job path for broad or long-running scopes:
    - `POST /api/catalog/exchange/export/jobs`;
    - `GET /api/catalog/exchange/export/jobs/{job_id}`;
    - worker service: `global-pim-export-worker.service`.
    The synchronous `/catalog/exchange/export/run` endpoint is compatibility/diagnostic path, not the preferred UI path for broad checks.
33. export must not derive price from PIM, marketplace imports, competitor pages, or product parameters. If a marketplace API requires a price for technical card creation, use the explicit placeholder `1000000` and mark the source as `technical_placeholder`.
34. info-model draft review must show why each candidate exists before approval:
    - `source_summary.by_kind` separates product, marketplace, and competitor evidence;
    - `review_flags` must call out competitor-only, marketplace-only, low-confidence, single-source, select-without-values, and weak global-match cases;
    - a candidate that only comes from competitors is evidence, not an automatically approved canonical parameter.
35. if a draft candidate suggests the wrong global parameter, the user must be able to clear `global_match` before approval and create a new canonical parameter instead of silently reusing the wrong one.
36. the draft screen should expose aggregate quality counters before approval, so the user can see risky candidate groups without reading every row first.
37. draft quick filters should let the user isolate competitor-only, marketplace-only, and weak global-match candidates from ordinary status filters.

Media rule:

1. binary media lives in S3/object storage;
2. product DB stores media references in product content fields such as `media_images`, `media_videos`, and `media_cover`;
3. marketplace product imports must also hydrate `content.media_images` when source cards contain images; media is not competitor-only;
4. do not move binary media into Postgres.

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

Production `scripts/server_ops.sh exec '<cmd>'` starts a fresh SSH shell, not the `global-pim.service` process. Direct Python diagnostics run through SSH do not automatically inherit service env values such as S3 settings. Prefer testing through API/service endpoints. If a direct Python diagnostic must use runtime env, load only the required key/value pairs inside Python with a safe parser and never echo env contents.

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
scripts/server_ops.sh exec '<safe diagnostic command>'
```

Server config backup:

```bash
scripts/backup_server_config.sh
```

Production deploy/backup scripts must not interpolate `APP_SERVER_PASSWORD` into command strings. Pass it through environment variables into `expect` and use `send -- "$env(APP_SERVER_PASSWORD)\r"`.

## Production LLM

Local AI matching runs through Ollama on the production server.

Required production service:

```bash
ollama.service
```

Required local model:

```bash
qwen2.5:7b-instruct
```

Backend runtime env must include these non-secret values in `/opt/projects/global-pim/backend/.env`:

```bash
LLM_API_BASE=http://localhost:11434/v1
LLM_MODEL=qwen2.5:7b-instruct
LLM_MODEL_FAST=qwen2.5:7b-instruct
LLM_MODEL_BALANCED=qwen2.5:7b-instruct
LLM_MODEL_QUALITY=qwen2.5:7b-instruct
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
AI_MATCH_OLLAMA_TIMEOUT_SECONDS=90
AI_MATCH_OLLAMA_CHUNK_SIZE=12
```

Use one model across the old marketplace AI path and the newer `app.core.llm` path. Do not point production to `llama3.1:*`, `qwen2.5:14b-instruct`, or `70b` models unless the model is installed and server resources are checked first.

Category-level marketplace AI matching must stay bounded:

1. never send the full marketplace parameter dictionary plus all PIM rows as one prompt;
2. shortlist marketplace candidates by deterministic token score before calling Ollama;
3. send compact pair prompts (`rows: [[pim_name, provider_id_or_null]]`), not verbose schemas;
4. run category rows in chunks and preserve deterministic rule/memory fallback;
5. expose `ai_error` when LLM fails, instead of silently claiming AI matched the data;
6. use a background job/queue for any full-category LLM rematch that can take longer than an interactive request.

Interactive parameter matching should use the background job endpoints:

```text
POST /api/marketplaces/mapping/import/attributes/{category_id}/ai-match/jobs
GET  /api/marketplaces/mapping/import/attributes/ai-match/jobs/{job_id}
```

The old synchronous endpoint may remain for scripts and diagnostics, but frontend buttons should not block on it.

AI matching job state is persisted in `pim_workflow_runs` with workflow:

```text
marketplace_attribute_ai_match
```

Use this table to inspect stuck/completed AI jobs. Queued/running jobs older than the bounded stale window are marked `failed/stale` on the next job start/status check so users can restart matching.

Execution is handled by `app.workers.marketplace_attribute_ai_match` as a separate one-job worker process. The worker can also run queued jobs directly:

```bash
PYTHONPATH=backend python3 -m app.workers.marketplace_attribute_ai_match --run-pending --organization-id org_default
PYTHONPATH=backend python3 -m app.workers.marketplace_attribute_ai_match --loop --poll-interval 5 --organization-id org_default
```

Production deploy installs and restarts the managed loop unit:

```text
global-pim-ai-match-worker.service
```

Use `scripts/server_ops.sh worker-status`, `worker-logs`, or `restart-worker` for operations. The unit runs `--loop --poll-interval 5 --limit 10 --organization-id org_default`, so queued jobs are picked up again after host/process restarts.

The worker must claim jobs before running LLM work. The claim path is a conditional update in `pim_workflow_runs` from `queued` to `running`; if another process already claimed the job, the worker reports it as skipped and does not execute matching again.

Runtime memory rules:

1. production runs multiple uvicorn workers, so every in-process Python cache is duplicated per worker;
2. large text/JSON payloads are not cheap after parsing: provider dictionaries, category trees, mapping rows, and export readiness payloads become Python dict/list objects and can retain heap after a heavy request;
3. long-lived route caches must have both a short TTL and a max item count unless they are tiny by design;
4. do not cache full marketplace/category/value payloads for a day in process memory; prefer persistent rebuildable files/DB rows plus short per-worker hot caches;
5. if RSS keeps growing under real load after bounded caches, prefer reducing worker count or moving to a managed worker model with request recycling before adding more in-process caches.

Production disk rules:

1. repeated deploys must not accumulate unlimited `app-*.tgz` archives under `backups`;
2. keep explicit operational backups such as `info-model-reset-*.json` unless the user asks to remove them;
3. monitor `/var/log/journal` separately from app data because SSH/deploy/test loops can grow system logs even when product files are tiny;
4. journald should have a bounded persistent disk limit on the production server.
5. `json_documents` is for compact rebuildable documents, not full raw marketplace API archives:
   - skip rewrites when the JSON payload is unchanged;
   - store raw API page counts/summaries unless raw pages are explicitly needed for a debugging session;
   - bound import/export run history before saving;
   - after large JSON rewrites, use a planned `VACUUM FULL json_documents` or `pg_repack` window to return old TOAST space to disk.

AI mapping must learn from user confirmations through data, not through ad-hoc prompt edits:

1. confirmed category/template competitor mappings are saved in `pim_channel_links`;
2. AI learning rows use `scope = ai_mapping_memory`, `entity_type = template`, `status = confirmed`;
3. the row `provider` is the competitor source, `title` is the competitor/source field name, and `external_id` is the target PIM field code;
4. `payload_json` must include `source_name`, `source_name_key`, `target_code`, `target_name`, `template_id`, `context_type`, and `context_id`;
5. AI prompts must include recent confirmed examples before unmatched source fields;
6. if a confirmed memory example matches the source field, it overrides later LLM/rule suggestions;
7. protected fields such as product name/title and description must never be target fields for competitor parameter mapping.
8. product-card candidate discovery uses a separate learning path: confirmed competitor product links (`scope = competitor_product`) are few-shot examples for future URL suggestions, but the result is still only a candidate until the user approves it.

Verify LLM without printing secrets:

```bash
scripts/server_ops.sh exec "cd /opt/projects/global-pim && set -a && . /opt/projects/global-pim/backend/.env && set +a && PYTHONPATH=/opt/projects/global-pim/backend /opt/projects/global-pim/.venv/bin/python - <<'PY'
import asyncio
from app.core.llm import llm_chat_text
async def main():
    res = await llm_chat_text(messages=[{'role': 'user', 'content': 'Ответь одним словом: ok'}], profile='fast', timeout_seconds=60)
    print('llm_ok', res.get('model'), str(res.get('content') or '')[:120])
asyncio.run(main())
PY"
```

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

Current Browser Use diagnostic:

1. `node_repl` / `mcp__node_repl__js` is available;
2. browser-client loads with `backend = "iab"`;
3. if `agent.browser.tabs.selected()` and `agent.browser.tabs.new()` both report no active Codex browser pane, the blocker is the in-app browser pane/bridge, not missing `node_repl`;
4. do not fall back silently to external Playwright for an explicit Browser Use request; record the blocker and continue with non-visual checks only when needed.

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
12. competitor links: accepted/rejected evidence URLs in `pim_channel_links`;
13. workflow runs: operational run polling/state in `pim_workflow_runs`, not JSON documents;
14. connector accounts and runs: credentials/config and sync history;
15. derived tables must be named, documented, rebuildable, and never manually edited.

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

## Latest Production Verification Notes

1. `sources?tab=values` must open on `Все`, not `Блокеры`, because a category can have value fields without unresolved mapping blockers.
2. If value refs are empty but saved parameter rows exist, rebuild value refs from the saved parameter rows before showing the value step.
3. Single-SKU export readiness was checked on production for GT USD and Ozon:
   - iPad Air 11 M3: ready;
   - MacBook Air 13 M4: ready;
   - iPhone 17 Pro Max `product_1052`: ready after confirming exact competitor links and importing 13 media images.
4. Do not treat `0 блокеров` plus empty visible list as “no value work”; check the active filter and `Все` count.
5. Product competitor enrichment must use `/competitor-mapping/discovery/products/{product_id}/enrich/jobs` from UI. The direct `/enrich` endpoint can exceed proxy timeouts when images are fetched and uploaded.
6. Export media blockers must be diagnosed in two layers:
   - if `pim_channel_links` has `candidate` or `confirmed` competitor links, export preparation should enrich `content.media_images` from those links;
   - if no competitor links exist for the SKU, the blocker belongs to the competitor-matching step, not the media-import step.
7. Competitor image URLs that are extracted but cannot be imported into storage should remain visible as `content.media_images[].status = needs_review`; do not collapse them back into “Нет изображений”.
8. Export blocker UI should prefer backend `missing_details[].target` over text matching. `competitors` opens the competitor workspace, `media` opens product media, `params`/`values`/`sources` open the relevant mapping tab.
9. Ozon category availability has two valid sources:
   - `description-category/tree` for visible catalog navigation;
   - `description-category/attribute` for real export/import compatibility.
   If a category/type pair is missing from the tree but the attributes API accepts it, keep it usable, show the validation source in UI, and do not block export solely by tree provenance.
