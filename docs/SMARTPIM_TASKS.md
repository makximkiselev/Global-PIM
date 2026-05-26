# SmartPim Active Tasks

This is the only active task/backlog document.

Do not create separate `.md` plans, specs, notes, or task lists. Add every new task here by priority.

## Current Baseline

1. Production is deployed at `https://pim.id-smart.ru`.
2. Active organization is `org_default / Global Trade`.
3. Main production category for vertical QA: `Смартфоны`, id `bb40de87-254b-4170-84d7-8e5d3925b251`.
4. Auth/admin schema is relational: `users`, `roles`, `organizations`, `organization_members`, `organization_invites`.
5. Competitor workflow source of truth is relational:
   - product candidates, confirmed/rejected/stale links, moderation evidence, and category/template competitor mappings live in `pim_channel_links`;
   - discovery run polling/state lives in `pim_workflow_runs`;
   - legacy competitor JSON is not runtime source of truth.
6. Media storage is S3/object storage; product DB stores metadata and internal `/api/uploads/...` references.
7. Product remains the main entity: one product row equals one SKU.
8. Product variants are separate SKU rows grouped by `group_id`.
9. Export tests must use only allowed safe targets:
   - GT USD may be used for marketplace export testing;
   - Ozon may be tested;
   - other stores must not be selected for export testing unless explicitly approved.
10. Info-model layer was reset on production on 2026-05-21:
    - all template/category-template/attribute-mapping/value-ref tables were cleared for tenant and legacy scopes;
    - legacy bootstrap JSON for templates and attribute mappings was cleared so old models do not rehydrate;
    - backup before deletion: `/opt/projects/global-pim/backups/info-model-reset-20260521-144859.json`;
    - products, catalog, category mappings, dictionaries/global attributes, media, users, and connector settings were preserved.
11. Info-model layer was reset again on production on 2026-05-22 after the unified parameter-first flow was agreed:
    - tenant and legacy template/category-template/attribute-mapping/value-ref tables were cleared;
    - legacy bootstrap JSON files for templates, attribute mappings, and value refs were cleared;
    - backup before deletion: `/opt/projects/global-pim/backups/info-model-reset-20260522-123325.json`;
    - service health after restart: `{"ok": true}`;
    - products, catalog, category marketplace bindings, competitor links/evidence, dictionaries/global attributes, media, users, and connector settings were preserved.
12. Manual walkthrough reset on production on 2026-05-25:
    - deleted walkthrough SKU `product_1052 / GT 52420`;
    - cleared templates, marketplace attribute mappings, and attribute value refs;
    - backup before deletion: `/opt/projects/global-pim/backups/manual-flow-reset-20260525-111539.json`;
    - service health after restart: `{"ok": true}`;
    - catalog, category marketplace bindings, competitor links/evidence, dictionaries/global attributes, media, users, and connector settings were preserved.

## Work Rules

1. Work by vertical user path, not isolated technical pages.
2. Every page/tab touched must have one clear user job.
3. Reuse shared components/layouts; do not add local duplicate catalog/tree/table/button implementations unless there is a documented reason.
4. Browser QA is required for frontend changes. Prefer Browser/in-app browser.
5. After Playwright/browser automation work, close browser/processes.
6. For backend/DB changes, verify frontend contract, backend contract, and actual DB state when production data is involved.
7. After meaningful work: run checks, deploy when needed, commit, and push.

## Current P0 Goal

Complete the `Смартфоны` pipeline until a content manager can prepare product data for real export without developer explanation.

## Current Unified Work Block: Parameter-First Marketplace Export

Goal: rebuild the info-model and mapping flow around a single practical outcome: one product SKU can be exported to marketplaces with clear readiness, while product families reduce repeated manual filling.

Canonical flow:

1. Link the selected PIM category or an ancestor to marketplace categories:
   - this imports marketplace category parameters as provider evidence;
   - this does not create a final info-model by itself.
2. Link competitor context and exact competitor product cards for products in the selected branch:
   - raw parameter name;
   - raw value;
   - source marketplace/site and URL;
   - source product/SKU evidence;
   - confidence and parser diagnostics.
3. Build the info-model draft from the combined evidence pool:
   - marketplace fields;
   - competitor fields and values;
   - existing product fields;
   - SKU title/parser facts;
   - learned global attributes and dictionaries.
4. Approve one canonical PIM parameter layer:
   - marketplace fields and competitor fields are evidence for one PIM parameter;
   - parameters reuse global attributes when the meaning is shared across categories;
   - the same canonical parameter can fill different provider roles per channel.
5. Map values after parameters:
   - marketplace allowed values and competitor raw values are compared together;
   - one canonical PIM value is selected for the PIM dictionary;
   - provider-specific output values are stored separately per marketplace.
6. Prepare SKU export readiness:
   - `ready`;
   - `needs parameter mapping`;
   - `needs value mapping`;
   - `missing product value`;
   - `required by provider`;
   - `not exported intentionally`.
7. Enrich products and product groups:
   - product group/family holds shared facts for a line;
   - SKU-level values override group values only for variant axes or exceptions;
   - title/parser/competitor scripts may fill values like memory, color, SIM/eSIM, region, and bundle with evidence.

Marketplace parameter import must capture:
   - provider field id/name;
   - field type (`text`, `number`, `boolean`, `enum`, `multi`);
   - required/optional flag;
   - allowed provider values where available;
   - provider role when known: characteristic, base-card field, media/content field, identifier/export payload field.

Field role rule:

1. `Бренд` is a canonical product parameter, not a purely service field.
2. Channel export decides how `Бренд` is used:
   - Ozon/Я.Маркет base-card field such as `vendor`/`brand`;
   - provider dictionary value if the provider requires a controlled brand list;
   - category characteristic only where that provider category actually exposes it as a characteristic.
3. Similar fields (`Модель`, `Линейка`, `Цвет`, title parts) must be modeled as canonical facts first, then routed to provider output fields.
4. Service/export-only fields are limited to identifiers/media/content payload fields that are not business characteristics by themselves, such as `SKU GT`, offer id, image payloads, and description payload. Even these may depend on canonical product facts.

Immediate implementation sequence:

1. Reset production info-model/mapping layer with backup, preserving products, catalog, users, media, connectors, global attributes/dictionaries unless explicitly stated otherwise.
2. Fix UI wording and backend classification so fields are described by `canonical parameter + provider role`, not the binary `service vs characteristic`.
3. Rebuild `Смартфоны` from marketplace, competitor, product, and title/parser evidence.
4. Add a mapping audit that flags wrong-looking parameter links before approval.
5. Add value readiness audit for a single SKU export.
6. Add product-family enrichment view/action for shared line facts and variant overrides.

Target path:

1. Open `Сводка` and see blocking tasks for the category.
2. Open `Инфо-модели`.
3. Select category `Смартфоны`.
4. Confirm marketplace categories for `Я.Маркет` and `Ozon`.
5. Pick SKU or SKU subset in the selected branch.
6. Scan competitor product cards.
7. Confirm/reject exact competitor candidates.
8. Build info-model draft from marketplace, competitor, product, and title/parser evidence.
9. Approve canonical PIM parameters and variant axes.
10. Map PIM parameters to marketplace fields.
11. Map/normalize values for marketplace output.
12. Enrich SKU/group parameters, media, and evidence from confirmed competitor cards.
13. Review product card readability.
14. Validate readiness for `Я.Маркет` and `Ozon`.
15. Export or clearly show remaining blockers.

Success criteria:

1. User can understand the next action on every screen without developer explanation.
2. No duplicated headers, counters, action blocks, or unexplained technical labels.
3. Category context persists across info-model, mapping, products, import, and export routes.
4. Tables with many columns have fixed horizontal scroll behavior.
5. Long names do not overlap counters, badges, buttons, or adjacent columns.
6. Competitor workflow clearly separates category context, exact product-card links per SKU, extracted evidence, canonical PIM values, marketplace output values, and export payload.
7. Export readiness says what is ready, what blocks export, and where to fix it.

## Active Tasks

### P0.1 Product Card Competitor Workspace

Status: done, keep for regression checks.

Current state:

1. Product card `Конкуренты` tab supports grouped SKU context.
2. Active route is `ProductWorkspaceFeature`.
3. If `/products/{id}` does not return variants, the route uses catalog summary `group_id` and falls back to `/product-groups/{id}`.
4. Group workspace shows SKU rows, source statuses, search, status filters, and current filtered bulk discovery action.
5. Group workspace now supports explicit row checkboxes and “select visible” bulk selection.
6. Bulk discovery runs only for selected visible SKU rows, not for all category products.
7. Group discovery shows a run/status drawer with run id, status, processed count, created count, and updated count.
8. SKU rows show visual source chips for `re-store` and `store77` where source summary data exists.
9. Production Browser verification on 2026-05-20:
   - `/products/product_1052?tab=competitors` shows group workspace for `iPhone 17 Pro Max`;
   - 36 SKU rows are visible behind a scrollable table;
   - one active SKU is selected;
   - status summaries load per SKU;
   - filtering by `Sim+eSim` reduces visible rows to 12;
   - bulk button shows `Найти по видимым 12` without triggering scan during QA.

Regression checks:

1. Browser-verify row checkboxes, select-visible, disabled run button, and the run drawer without launching production scan unless explicitly needed.
2. After a controlled single/SKU run, verify the polling refreshes per-SKU statuses automatically from run state.

### P0.2 Competitor Matching Quality

Status: active.

Current state:

1. Competitor discovery supports `re-store` and `store77`.
2. Candidate matching respects model, memory, color, SIM/eSIM, region/global differences, and variant names better than before.
3. `eSIM` and `SIM + eSIM` must not collapse into one match.
4. Manual URL remains fallback only after candidates are absent or rejected.
5. Confirmed links persist to `pim_channel_links`.
6. Product enrichment writes competitor evidence, canonical values, and media references.
7. `iPhone 17e` is now a separate model profile from `iPhone 17 eSIM`.
8. re-store direct URL generation now supports `iPhone 17e 256Gb Pink` as `https://re-store.ru/catalog/10117E256PNKN/`.
9. re-store search parsing now reads product fields from the product object before the current link, so neighboring products in the same payload do not overwrite the current candidate.
10. Explicit SIM conflicts remain blockers; only missing SIM details on a re-store card can be sent to manual review.
11. Store77 deterministic candidate generation now understands `iPhone 17e`, `Pink`, and `SIM+eSIM`, and returns the exact review candidate before slow browser/category scans.
12. Store77 category scan now runs before deterministic fallback, so real Store77 product pages are preferred over synthetic URLs.
13. Store77 product-title fallback extracts basic specs (`Память`, `SIM-карта`, `Цвет`, `Модель`) when the page has no old specs table.
14. Competitor enrichment now trims noisy donor descriptions before they can become product/export descriptions.
15. Category competitor discovery selector now lists the full selected branch SKU set, not only the first sample rows; production check on `iPhone 17 Pro Max` showed all 36 SKU selectable.
16. Product channel summary reads confirmed/candidate competitor links from `pim_channel_links`, so `Площадки` reflects Re:Store/Store77 links after restart and not only legacy product JSON.
17. Product-level `Загрузить параметры и медиа` keeps competitor media when storage import fails as `needs_review`, and imports Re:Store images to S3 when available.
18. Production check on 2026-05-24: GT 52432 (`256Gb Sim+eSim Silver`) confirmed Re:Store, imported 9 ready media images, and left Store77 candidates unconfirmed because the UI detected SIM mismatch (`nano SIM + eSIM` vs `eSIM only`).

Known problems:

1. Some near matches are still too noisy and must remain manual-review, not auto-confirm.
2. Store77 may intermittently timeout from production; exact seeded candidates reduce the UX impact, but enrichment still depends on fetching the confirmed page.
3. Many donor specs remain unmatched because the current info-model does not yet contain every canonical field.
4. UI still does not show enough source-specific scan evidence when a source returns no candidates.
5. Product-level competitor matching still needs more visible evidence for exact Store77 misses and re-store blocked/partial responses.

Next tasks:

1. Add parser/audit evidence for why an exact SKU was missed.
2. Show retry timing and source-specific failure reason in UI.
3. Add controlled production check for one `17e 256Gb Pink SIM+eSIM` SKU after candidate scan is safe.
4. Continue tests for exact matching around `256Gb`, `1Tb`, `eSIM`, `SIM+eSIM`, and color variants as new variants appear.

### P0.2a Export Readiness Loop

Status: active.

Current state:

1. Export page restores the latest batch for the selected category/product after reload via `/catalog/exchange/export/latest-run`.
2. Export batch preparation is now a fast readiness check over current product data. It no longer auto-parses competitor candidate links during export; competitor enrichment must happen earlier from confirmed product links.
3. Export media auto-enrichment, when explicitly enabled by env, uses only confirmed competitor links and skips unconfirmed candidates.
4. Store77 browser image fetch is lazy fallback only after direct storage import fails, not a prefetch for every export image.
5. Production check on 2026-05-24 for `iPhone 17 Pro Max`: after enriching GT 52432, export readiness moved from 24 ready / 48 blockers to 26 ready / 46 blockers.

Known problems:

1. Remaining blockers are mostly SKU without media in the Sim+eSim/2Sim branch and some 2Sim rows also need brand/description completion.
2. Frontend build is currently blocked locally by macOS dataless placeholder files in `frontend/package.json`, `frontend/dist/*`, and related metadata files; backend patches were deployed directly to production after tests.

### P0.3 Info-Model Builder And Global Attributes

Status: active.

Current state:

1. All old info-models and parameter/value mappings were deleted on production on 2026-05-22 after the unified parameter-first flow was agreed. Backup: `/opt/projects/global-pim/backups/info-model-reset-20260522-123325.json`.
2. Existing dictionaries/global attributes were intentionally preserved as normalization memory so AI can reuse canonical fields instead of creating duplicates.
3. Info-model fields must reference global attributes, not category-local duplicates.
4. Shared parameters such as `Встроенная память`, `Оперативная память`, `SIM`, `Цвет`, `Модель`, dimensions, OS, and dictionaries must be reused across categories.
5. `draft_service.approve_draft` already calls `ensure_global_attribute` and collapses accepted synonyms into template attributes.
6. Draft collection includes competitor unmatched specs when the UI calls `sources: ["products", "marketplaces", "competitors"]`.
7. Competitor unmatched specs are review-only candidates with source provenance (`restore`/`store77`) and do not auto-approve.
8. Synonyms such as `Объем встроенной памяти` must collapse into the global `Встроенная память` attribute during approval.
9. Draft candidates include `global_match` and `suggested_action`, so UI can show whether the field should reuse an existing global attribute or create a new one.
10. Draft rows show duplicate prevention directly: `Уже есть в PIM` changes the action label to `Переиспользовать PIM-поле`; new fields are labelled `Новое поле` and use `Добавить новое PIM-поле`.
11. Draft candidates now include `source_summary` and `review_flags`:
   - UI separates product, marketplace, and competitor evidence in every row;
   - competitor-only fields are explicitly marked as review-only;
   - marketplace-only fields tell the user to verify how product values will be filled;
   - weak global matches show reason and score before approval.
12. Wrong global attribute reuse can be corrected before approval: draft candidate update accepts `global_match: null`, switches the candidate to `create_attribute`, and UI exposes this as `Не переиспользовать, создать новое`.
13. Draft screen has a compact model-quality audit panel for competitor-only, marketplace-only, weak global-match, low-confidence, select-without-values, and duplicate-code candidates.
14. Draft list has quick filters for `Только конкуренты`, `Только площадки`, and `Слабая связь PIM`, using the same evidence metadata as the audit panel.
15. Production audit on 2026-05-21 for weak/empty headphone model before full reset:
   - root category `Наушники` had no direct template resolution before rebuild;
   - product `product_648 / 50998 / Беспроводные наушники Apple AirPods 4` had only `Бренд` before model/enrichment;
   - a draft model for the child headphone category was created from product, marketplace, and competitor evidence;
   - product feature seeding now merges missing template fields into existing product content instead of returning early when at least one field already exists;
   - feature seeding now deduplicates fields by both `code` and `name`, preventing `brand` / `Бренд` duplicates.
16. `Смартфоны` was rebuilt from zero on production after the reset:
   - template id: `68b339e3-0bf4-4e29-84b5-d5d96d3c7f40`;
   - draft created from `products + marketplaces + competitors`;
   - 66 safe accepted candidates were approved first, with review-only competitor/noisy candidates left out;
   - the old marketplace mapping/template upsert path produced 86 working rows, but this is now treated as provider evidence/draft material rather than a final info-model;
   - duplicate audit showed no duplicate `code` or `attribute_id` during approval;
   - `Встроенная память`, `Оперативная память`, `Количество SIM-карт`, and color fields reuse global attributes instead of category-local duplicates.

Known problems:

1. The template/model screen is still heavy for a new user.
2. Product fields can outnumber approved model fields after resets/rebuilds because marketplace mapping upsert also includes protected export/core rows.
4. Marketplace field mapping from the model builder is still a separate workspace step; draft decisions are clearer, but the transition needs browser QA during the manual walkthrough.
5. Draft collection for categories with weak models can still pull noisy marketplace dictionaries/examples into candidate fields. These must stay review-only and should be visually separated from clean marketplace-required fields and competitor evidence.

Next tasks:

1. Repeat the empty-model workflow for at least one more category before considering the model builder stable.
2. Decide whether protected export/core rows should remain visible inside the template structure or only inside export/product workspaces.

### P0.4 Parameter And Value Mapping

Status: active.

Current state:

1. `/sources?tab=params` has grouped parameter queues.
2. Complex mapping exists for one PIM field to multiple marketplace fields.
3. Example already handled: Ozon `Оперативная память` can map to multiple Ozon fields.
4. `Встроенная память` and `Оперативная память` were separated after previous incorrect Ozon mapping.
5. `/sources?tab=values` has a value mapping workspace, but it is still dense.
6. Values workspace now opens in blocker mode by default and separates `Блокеры`, `Все`, and `Готово`.
7. Selected value field now shows compact route `PIM поле -> Канон -> Я.Маркет -> Ozon -> Статус` above the dictionary editor.
8. Backend value details now return provider `allowed_sample` and `mapped_sample` for compact evidence UI.
9. Competitor parameter mapping now uses the local LLM path as a controlled suggestion layer after deterministic matching.
10. LLM suggestions are validated against real model fields and cannot map competitor specs into protected core fields (`Наименование товара`, `Описание товара`).
11. Explicit/manual competitor mappings into protected core fields are ignored by import/export enrichment.
12. Production Ollama is configured for `qwen2.5:7b-instruct`; the same model is used by both the new competitor matching path and the legacy marketplace AI path.
13. Confirmed category/template competitor mappings are now stored as AI learning examples in `pim_channel_links` with scope `ai_mapping_memory`.
14. AI prompt context now includes confirmed mapping examples, and confirmed memory overrides later LLM/rule suggestions for the same source field.
15. Production LLM check after server upgrade on 2026-05-21:
   - server resources are now enough for `qwen2.5:7b-instruct` single-product mapping runs;
   - `product_648 / AirPods 4` AI suggestions completed in LLM mode without warnings;
   - deterministic enrichment filled 16/20 headphone fields from confirmed `store77` and `re-store` links;
   - remaining AI suggestions are mostly `create_attribute`, which exposes model gaps rather than silently writing wrong fields.
16. `/sources-mapping?tab=sources` initial catalog load was optimized on 2026-05-21:
   - previous bootstrap returned all marketplace category trees with the catalog: about 3.31 MB and 19,051 provider categories;
   - new bootstrap returns only the PIM catalog, mappings, states, and mapped provider-category labels: about 0.30 MB;
   - full provider trees now load lazily only when the user opens the marketplace category picker.
17. Parent categories with child marketplace bindings now show explicit actions:
   - `Открыть дочернюю` navigates to a concrete child binding for safe editing;
   - `Задать общую` opens the explicit clear/replace flow;
   - the old confusing `Сопоставить -> очистка дочерних связей` path was removed from the primary action.
18. `/sources?tab=params` selected-parameter inspector now explains why a field needs attention and exposes direct actions:
   - `Подобрать AI`;
   - `Подтвердить`;
   - `Не передавать`;
   - `Настроить значения`.
19. Marketplace parameter bindings now carry and display provenance:
   - `AI` for LLM suggestions;
   - `Правило` for deterministic fallback matches;
   - `Память` for learned mappings when present;
   - `Ручное` for user-edited bindings.
20. The selected-parameter inspector shows source, confidence, and reason per marketplace field so a content manager can decide whether to confirm or edit.
21. Core export fields (`SKU GT`, product title, description, media/images) are protected from arbitrary category-attribute bindings. They are exported through the product/export flow, not through marketplace characteristic mapping.
22. Legacy marketplace AI-match now uses the installed production model by default:
   - `qwen2.5:7b-instruct`, not the missing `qwen2.5:14b-instruct`;
   - compact JSON pair prompt instead of a verbose schema prompt;
   - shortlist candidates before sending to Ollama;
   - chunked matching and `ai_error` diagnostics instead of silent fallback.
23. `/sources?tab=params` now starts marketplace AI matching through a background job:
   - `POST /api/marketplaces/mapping/import/attributes/{category_id}/ai-match/jobs` returns immediately with `job_id`;
   - `GET /api/marketplaces/mapping/import/attributes/ai-match/jobs/{job_id}` returns queued/running/completed/failed state;
   - the UI polls job status, shows progress copy, and reloads parameter details when the job completes;
   - duplicate running jobs for the same category are reused instead of starting parallel LLM runs.
24. AI job state is now persistent in `pim_workflow_runs`, workflow `marketplace_attribute_ai_match`:
   - job state survives process restarts and can be inspected from SQL;
   - stale queued/running jobs are marked `failed/stale` after the bounded timeout window;
   - execution is started through a separate `app.workers.marketplace_attribute_ai_match` worker process per job;
   - the same worker also supports `--run-pending` and `--loop` to pick queued jobs from `pim_workflow_runs` after restarts;
   - worker execution claims a job with a conditional `queued -> running` update before running LLM work, so parallel one-job/daemon workers skip already claimed jobs;
   - the previous in-memory-only job map was removed.
25. `Смартфоны` parameter remap after reset:
   - endpoint stayed stable and did not crash;
   - deterministic rule/memory mapping produced 86 rows, 62 ready rows, 18 attention rows, and 5 unmapped Я.Маркет fields;
   - Ollama did not add extra confident marketplace pairs for the remaining rows, so final engine remained fallback without `ai_error`;
   - critical fields are correct: `Встроенная память` -> Я.Маркет `Встроенная память` / Ozon `Встроенная память`; `Оперативная память` -> Я.Маркет `Оперативная память` / Ozon `Оперативная память`; `Количество SIM-карт` -> Я.Маркет `Количество SIM-карт` / Ozon `Число физических SIM-карт`.
26. Protected/core fields intentionally remain without Я.Маркет characteristic binding: `SKU GT`, title, description, images/media, barcode. They must be exported through the product/export payload, not characteristic mapping.
27. `/sources?tab=params` parameter list rows now show compact provenance chips for marketplace bindings:
   - `AI`, `Правило`, `Память`, `Ручное`;
   - confidence percent is shown when available;
   - detailed reason remains in the selected-parameter inspector.
28. `/sources?tab=params` selected-parameter actions now complete the basic decision loop:
   - `Подтвердить` keeps the mapping and marks the row ready;
   - `Не передавать` clears marketplace bindings and marks the row as an intentional non-characteristic field;
   - `Сбросить решение` clears bindings and returns the row to the attention queue.
29. `/sources?tab=params` now exposes marketplace parameter value modes directly in the list and selected-parameter inspector:
   - `Справочник` / `Мультивыбор` fields require value normalization in `/sources?tab=values`;
   - `Да/Нет` fields are treated as value-normalization blockers, not as plain text;
   - `Число` fields call out unit checks instead of dictionary mapping;
   - `Текст` fields are shown as free-text/manual-PIM fields.
30. Service/export fields are now explained as export payload fields, not marketplace characteristics:
   - `SKU GT`, title, description, images, and barcode show whether they are system/export fields or suspiciously linked as characteristics;
   - the inspector copy now tells a content manager not to match these fields to category characteristics when the marketplace accepts them as base card fields.
31. `Бренд` was removed from the service/export-only list:
   - it is a canonical product parameter;
   - each channel decides whether it fills a base-card field, a provider dictionary, and/or a category characteristic.
32. Flow wording was corrected so marketplace fields no longer imply a final info-model:
   - `/sources?tab=sources` now presents the first step as marketplace category links plus exact competitor cards;
   - `/sources?tab=params` is now a `Черновик PIM-параметров` workspace;
   - empty or marketplace-only states tell the user to confirm competitor cards and product evidence before approving the info-model;
   - leaf categories can use inherited marketplace category links from parent branches while keeping competitor/product evidence on the selected product branch.
33. Competitor discovery from `/sources?tab=sources` now runs as a background job:
   - the primary button returns immediately and remains blocked while a queued/running job exists;
   - the status line no longer says `скан еще не запускали` when candidates or confirmed cards already exist;
   - source counters distinguish selected-SKU review state from branch-level totals (`для SKU` vs `в ветке`).
34. Confirming competitor candidates was browser-tested on production for `iPhone 17 Pro Max`:
   - exact re-store/store77 cards were approved for SKU `52430`;
   - after approval the UI moves to the next SKU with candidates and now explains that behavior;
   - confirmed cards stay as branch evidence for the later parameter/value draft.
35. `Бренд` is no longer treated as a service/system export row in the active `/sources` parameter workspace:
   - old `svc:brand` rows are ignored by service-row detection in the UI;
   - `Бренд / vendor` is not injected as an automatic Yandex system binding;
   - provider `brand`/`vendor` fields remain available as marketplace evidence for the canonical `Бренд` parameter.
36. Competitor discovery now scans the selected SKU, not the entire category branch, when `product_ids` are provided:
   - backend no longer expands explicit `product_ids` by `category_id`;
   - UI copy says `скан по одному SKU`;
   - the previous long iPad run `run_1f4c2ffd35a5d886` was stopped and marked `failed/SUPERSEDED_BY_SINGLE_SKU_DISCOVERY`.
37. iPad Air 11 M3 production check:
   - selected SKU `50807 · iPad Air 11 M3 128Gb Wi-Fi + Cellular starlight`;
   - re-store produced the exact `starlight` candidate and it was approved;
   - `space grey` and `purple` false candidates were removed after adding `starlight`, `purple`, and `space grey` to variant color normalization;
   - Store77 did not produce an iPad candidate yet.
38. MacBook Air 13 M4 production check:
   - selected SKU preservation was fixed: after scanning `50956 · ... Silver`, the UI stays on `50956` instead of jumping back to the first SKU;
   - Store77 deterministic seed now builds review URLs from MacBook line, size, chip, RAM, SSD, color, and part number;
   - selected SKU `50956 · MacBook Air 13 M4 16/256 Silver MW0W3` produced a Store77 candidate and it was approved;
   - re-store currently has no exact base `MW0W3/MW123` candidate in the checked HTML, so it remains empty for that SKU.
39. MacBook candidate visibility bug was fixed:
   - candidates with canonical English color in PIM and localized Russian color in the source, such as `Silver` vs `Серебристый`, now remain visible when the variant parser confirms the same color;
   - this prevents category context from hiding a freshly created Store77 candidate during the second confidence pass.
40. Production memory investigation on 2026-05-22:
   - the server had no memory pressure: swap was almost unused, no OOM events were found, and most visible OS growth was Linux page cache;
   - the app service runs 4 uvicorn workers, so large category/import/export payloads and Python caches are duplicated per worker;
   - one worker that handled heavy category/value/media requests retained the largest private heap after the request completed;
   - marketplace attribute/value details caches were shortened and bounded per worker so category payloads are not kept for a full day;
   - catalog import overview cache was bounded so repeated preview runs with different selections do not accumulate indefinitely;
   - competitor discovery run cache was bounded so repeated scans do not grow the in-process cache without limit.
41. Production disk investigation on 2026-05-22:
   - root filesystem was not close to full (`/` used about 23 GB of 96 GB);
   - growth source was disk logs and deploy artifacts, not product text files;
   - `/var/log` used about 2.2 GB, mostly persistent `systemd-journal` files;
   - `/opt/projects/global-pim/backups` used about 596 MB because each deploy kept another `app-*.tgz`;
   - deploy script now keeps only the latest app deploy backups by default, while preserving explicit info-model reset backups.
   - server cleanup reduced journal storage to about 268 MB, `/var/log` to about 636 MB, app backups to about 31 MB, and the app directory to about 253 MB;
   - production journald now has `SystemMaxUse=300M`, `SystemMaxFileSize=50M`, and `MaxRetentionSec=14day`.
42. `/sources?tab=values` value-mode pass:
   - backend now returns value mode per PIM field and provider (`enum`, `multi`, `boolean`, `number`, `text`);
   - boolean and dictionary-like provider fields are value-mapping blockers only when provider allowed values are not covered;
   - numeric provider fields are shown as unit checks, not select-only dictionary blockers;
   - UI now has a direct `Следующий блокер` action and compact source/output samples in the field list and selected-field panel.
   - parent categories without own value rows now read value refs from descendant working categories, so `Смартфоны` no longer shows an empty value step when `iPhone 17 Pro Max` has mappings;
   - production API check for `Смартфоны` returned 148 value rows from 1 descendant source, 38 value blockers, and 26 unit checks.
43. Frontend build command was stabilized for the current Vite 8/Rolldown toolchain:
   - default minified build could hang locally during Rolldown/OXC minify with no CPU progress;
   - `npm run build` now uses `--configLoader runner --minify false`, which completed successfully.
44. Export preview value-output guard:
   - Я.Маркет preview is route-tested so controlled fields write the provider-specific output value into `parameterValues`, not the raw competitor/PIM text;
   - Ozon preview is route-tested so controlled fields write the provider-specific output value into `attributes`, not the raw competitor/PIM text;
   - both tests also keep the existing blocker behavior for unmapped controlled values.
45. `/sources?tab=params` selected-parameter editor grouping:
   - current marketplace bindings stay separated from the manual provider-field picker;
   - close-by-name provider fields are shown as a suggestion group before the full manual list;
   - selected/manual options now show value mode labels, so the user sees whether the next step is dictionary mapping, boolean normalization, numeric unit check, or free text.
46. `/sources?tab=params` browser check after deploy:
   - opening the params tab without a `category` URL no longer gets stuck on `Подбираем рабочую категорию`;
   - production check for `iPhone 17 Pro Max` loaded 142 parameter rows and opened the selected-parameter inspector;
   - inspector showed separated option groups (`Связано сейчас`, manual provider list) with value-mode labels.
47. Navigation and route audit pass:
   - `/catalog -> products -> sources -> params -> values -> export` keeps the selected category in links that leave the current workspace;
   - product-list quick actions now open category-scoped mapping instead of the generic mapping workspace;
   - template editor quick actions now use canonical `/sources?tab=params&category=...` and `/catalog?category=...` routes;
   - category-scoped data-source header links preserve category context when returning to сопоставления or инфо-модели;
   - media/infographics pages were checked and are still placeholder-level; keep them visible until the product decision is made instead of hiding them during audit;
   - legacy sidebar was confirmed unused by the current shell and later removed after explicit approval.
48. Full category scenario pass after legacy cleanup:
   - unused `frontend/src/app/layout/Sidebar.tsx` was removed after explicit approval; current `Shell.tsx` navigation and media placeholders remain intact;
   - `/sources?tab=sources&category=...` now invalidates stale source-mapping cache when the URL category is missing from cached bootstrap data, so category/marketplace/competitor matching opens directly on the requested category instead of showing `Выберите категорию слева`;
   - export links in products, product card, params, and values now use canonical `/catalog/exchange?tab=export...`; `/catalog/export` remains only as a compatibility redirect;
   - production browser scenario was run for `iPhone 17 Pro Max`: catalog, products, sources, params, values, info-model, media placeholders, export selection, and export batch preparation;
   - export preparation produced run `export_38b3036b74` for 36 SKU and 2 batch rows; 2 ready rows and 70 blockers were shown, mostly missing media/pictures with direct `Открыть SKU` and `Открыть медиа` actions.

Known problems:

1. Value mapping now has a first `Следующий блокер` action and inline PIM -> provider value editing in the selected-field panel, but dictionary data quality still needs real-category QA.
2. Canonical PIM value, marketplace output value, allowed marketplace values, AI result, and manual save/remove are visible in the values panel; raw competitor/source value snippets still need a dedicated pass.
3. Marketplace dictionary data quality still needs verification.
4. Actual export payload now has route-level guard tests for provider-specific output values; remaining risk is the quality/completeness of the dictionaries and export maps.
5. Parameter list provenance and type-mode chips are now visible, but the next pass should verify the density on narrow laptop widths after more real mappings are confirmed.
6. Enrichment for weak models still depends on approved template fields; if a model is missing a field, source values remain unmatched even when competitors have useful specs.
7. re-store MacBook coverage is still partial for base 13-inch M4 configurations: Store77 can provide review candidates, but re-store may be empty when exact SKUs are not present in its current listing.
7. The clear/replace flow for parent categories is now explicit, but the modal copy and visual hierarchy still need final design polish.
8. Marketplace AI matching worker daemon is now managed by `global-pim-ai-match-worker.service`; deploy installs/enables/restarts it and `server_ops.sh` exposes `worker-status`, `worker-logs`, and `restart-worker`.
9. The value workspace can still classify some numeric/logistics fields through the PIM template type, so the next backend pass should verify provider numeric fields are not treated as select-only value dictionaries.

Next tasks:

1. Add more route tests for complex one-PIM-field-to-many-marketplace-field mappings and real dictionary/export-map fixtures.
2. Add direct source-evidence snippets to value rows where competitor/raw source values differ from canonical PIM values.
3. Show AI confidence/reason/memory source next to competitor field mapping suggestions in `/sources?tab=params`.
4. Browser-check inline value editing on a category with real unresolved value blockers, not only already-covered smartphone dictionaries.

## Current Closeout Checklist

These 10 items are being worked as one closeout batch before the category/export flow can be considered stable:

- [x] Values: show raw source/competitor evidence next to each PIM canonical value.
- [x] Params: show AI confidence, reason, and memory/source provenance next to AI mapping suggestions.
- [x] Values: browser-check inline value editing on a category/field with real unresolved blockers. Current production data has 0 unresolved value blockers for `iPhone 17 Pro Max`, `iPad Air 11 M3`, and `MacBook Air 13 M4`; inline editing was browser-checked on live MacBook value rows with raw evidence and save/remove controls.
- [x] Marketplace dictionary QA: identify and mark suspicious/noisy provider dictionaries that can mislead matching.
- [x] Tests: add coverage for complex one-PIM-field-to-many-marketplace-field mappings and provider-specific export-map fixtures.
- [x] Product-family enrichment: expose shared line facts and SKU variant overrides in a usable view/action.
- [x] Competitor diagnostics: show source-specific exact-miss, timeout, and retry evidence for Store77/re-store.
- [x] Export readiness UX: each blocker must point to the exact fixing workspace/action.
- [x] Info-model builder: repeat empty-model workflow on a second category (tablet or notebook) and fix blockers found there. `MacBook Air 13 M4` empty-model state was opened on production and `Собрать предложения` produced a draft with 137 suggestions and 41 fields in model.
- [x] Numeric/logistics fields: verify provider numeric fields prefer unit-check flow over select-only dictionary mapping.

### P0.5 Product Creation And Variants

Status: active.

Current state:

1. `/products/new` is a short SKU creation workflow.
2. Single product creation creates one product row and opens product card.
3. Variant creation creates one product row per SKU and assigns all rows to a product group.
4. Variant axes are curated, not full info-model.
5. Generated variant matrix supports enabled/disabled combinations before create.
6. After create, user lands in product card on competitor workflow.
7. Generated variant rows now allow editing title, SKU GT, and SKU PIM before creation.
8. Creation blocks duplicate manual SKU GT inside the variant matrix before calling backend.
9. Variant-family creation now opens the created product group directly, so the next step is group-level SKU review and enrichment instead of a single product card.
10. Created product groups show a next-step guide with direct actions to competitor matching for the first SKU and export preparation for the selected SKU group.

Known problems:

1. Variant generation still needs more realistic UX around first/base product and variant axes.
2. Need clearer transition from created group to group-level competitor matching.
3. Product creation must not expose technical fields too early.

Next tasks:

1. Re-test full path for a real product family: base data -> axes -> matrix -> create -> group competitor scan -> enrichment -> validation.
2. Browser-check group workspace after creation with a real newly created family and refine selected-SKU guidance if it is still unclear.
3. Add stronger preview of generated group title and variant axes before final create.

### P0.6 Catalog / Products / Export UX

Status: active.

Current state:

1. Catalog was simplified and no longer behaves like a dashboard at the top.
2. Product table is more usable and category context is retained.
3. Export page defaults to safe stores for readiness tests: `GT USD` for Я.Маркет and `Global Trade AE` for Ozon when those stores exist. Other enabled stores remain visible but must be selected explicitly.
4. Product media deduplication was cleaned; S3-backed media renders for checked products.
5. Export page now requires a confirmation dialog before batch preparation and explicitly lists selected scope, SKU estimate, target count, and store labels.
   Broad scopes additionally require an explicit checkbox before preparation can start, and a selected branch can be narrowed to the current category directly from the confirmation dialog.
6. Product card parameter values are now compacted in the queue/source evidence; long text opens through a details panel instead of stretching the workbench.
7. Product media cards now show source and short object name instead of raw internal URLs.
8. Vertical QA baseline for `product_1092 / 53425` on 2026-05-20:
   - features: 34/84 filled, no critical blockers, very long restore description exists and must stay collapsed;
   - media: 4 S3 images from re-store;
   - competitors: re-store confirmed, store77 now shows a deterministic review candidate after single-SKU rescan;
   - export-preview: one SKU only, selected safe targets are GT USD and Ozon.
9. Export picker now has an explicit area switch:
   - `Категория` exports selected category/all branch;
   - `Отдельные SKU` exports only manually selected products;
   - selecting SKU clears category export scope to avoid accidental mixed/broad batches.
10. Legacy `/product-groups` route redirects to `/catalog/groups`, so old links do not land on an empty shell.
11. Product workspace now shows a persistent next-action card above the main workbench. It routes the SKU to parameter mapping, competitor/media work, validation, or safe single-SKU export based on the current product facts.

Known problems:

1. Catalog/source/tree components are still not fully unified.
2. Some screens still have local layout implementations.
3. Export readiness needs stronger protection against accidental broad final submissions after the readiness batch.
4. Product card description/source evidence must be rechecked after deploy to confirm the compact UI is enough for real content work.
5. iPhone 17 Pro Max single-SKU export blocker was closed for `product_1052`; keep media import/enrichment reliable for the rest of the line.

Next tasks:

1. Continue replacing page-specific workspace fragments with shared primitives.
2. Add one persistent category/SKU next-action state across catalog, sources, product card, and export. Product list and product workspace now share the same scenario intent; next pass should surface this state inside `/sources` headers too.
3. Move long source descriptions into evidence/details panels, not visible canonical fields.
4. Add a guardrail that defaults export checks to one SKU or asks for explicit confirmation before broad category batches. The broad-scope confirmation checkbox is implemented; continue nudging users toward selected SKU/category checks in the next-action state.
5. Continue applying the same one-SKU media/enrichment/export check to the next iPhone variants in the line.

### P1 DB Consolidation

Status: pending until the smartphone vertical path is stable.

Goal:

1. Reduce split legacy/read-model state.
2. Keep source-of-truth ownership clear per route.
3. Avoid collapsing everything into huge opaque tables.

Candidate target tables:

1. `pim_products`
2. `pim_model_fields`
3. `pim_external_payloads`

Rules:

1. Do not consolidate DB blindly before the user path is proven.
2. Product remains the main entity: one row equals one SKU.
3. Product groups only group SKU variants; variants still have their own SKU.
4. S3 remains media storage; DB stores metadata and object references.

## Recently Completed

1. Auth/admin consolidation and cleanup.
2. Profile page.
3. Ozon category/type resolution and parameter mapping population.
4. Competitor mappings moved from JSON to `pim_channel_links`.
5. Competitor discovery run state moved from JSON to `pim_workflow_runs`.
6. Product media canonicalization to `content.media_images`.
7. Duplicate media cleanup in production.
8. Product validation workbench.
9. Variant matrix in product creation.
10. Group-level competitor workspace in product card.
11. Per-SKU competitor status rows.
12. SKU search/status filters in group competitor workspace.
13. Bulk discovery action for currently visible SKU rows.
14. Values tab now opens on `Все` instead of an empty `Блокеры` filter and explains empty states per filter.
15. Value refs are lazily restored from saved parameter rows when a category has approved/draft mappings but the value step has no rows yet.
16. Production one-SKU export check: iPad Air 11 M3 and MacBook Air 13 M4 are ready for GT USD and Ozon.
17. iPhone 17 Pro Max `product_1052 / GT 52420` was the previous one-SKU ready proof, then was intentionally deleted during the 2026-05-25 manual walkthrough reset.
18. Competitor product enrichment has a job-based endpoint backed by `pim_workflow_runs`; the product competitor UI now uses job/status polling instead of waiting on long media extraction/upload HTTP requests.
19. Export preparation no longer enriches from unconfirmed competitor `candidate` links. Automatic export/media fallback may use only confirmed `pim_channel_links`; if a confirmed competitor image URL is found but storage import fails, the URL is kept in `content.media_images` as `needs_review` instead of being lost as “Нет изображений”.
20. Export preparation UI handles long backend runs without showing nginx `504`: it aborts the visible request, polls the persisted latest run, and renders the saved batch result.
21. Competitor candidate moderation labels approve/reject buttons by source and blocks approval only for proven SIM conflicts where both sides are known and different. `SIM не распознан` remains a manual-review case, not an automatic reject.
22. Marketplace product imports hydrate canonical product media too: Yandex offer-card pictures and Ozon product images are merged into `content.media_images` so export readiness sees photos collected from marketplaces, not only competitors.
23. Export preparation now runs bounded marketplace hydration for the selected SKU/store set before readiness checks, so first-party marketplace photos/descriptions/brand data are pulled into PIM before batch blockers are calculated.
24. Export preparation also fills missing media/description/brand from sibling variants with the same category, iPhone model, storage, and color. This covers line variants such as `eSIM`, `Sim+eSIM`, and `2Sim` where only the SIM axis differs.
25. After the manual reset, one clean SKU proof is ready again: `product_1065 / GT 52433` produced export run `export_4a7603c091` for safe targets `Я.Маркет GT USD` and `OZON Global Trade AE`; result is 2 ready target rows, 0 blockers.
26. Ozon category/type linking now treats `description-category/tree` and `description-category/attribute` as two separate signals:
   - tree presence means the category is visible in the store's category tree;
   - attributes validation means the store API accepts this `description_category_id` / `type_id` pair even if the tree endpoint does not expose it;
   - UI must show both sources and allow manual Ozon `category/type` validation before linking.

## Current Production Finding

iPhone 17 Pro Max export pass is ready on production after confirmed competitor matching, marketplace hydration, and sibling enrichment:

Manual-reset follow-up: `product_1052 / GT 52420` is intentionally gone; current one-SKU proof is `product_1065 / GT 52433`, run `export_4a7603c091`, safe targets only, 0 blockers.

1. Fresh production export run `export_928e9a89af` completed for the `iPhone 17 Pro Max` branch without nginx `504`.
2. Result: 36 SKU x 2 safe targets (`Я.Маркет GT USD`, `OZON Global Trade AE`) = 72 ready target rows, 0 blockers.
3. Export preparation hydrated 9 Yandex offer cards, checked 24 Ozon rows, and filled 12 `2Sim` variants from sibling SKU facts.
4. Previously blocked Sim+eSim rows such as GT 52441 now have media available for export.
5. Previously blocked `2Sim` rows now receive brand, description, and media from same-line sibling facts.
6. Store77 eSIM-only candidates for Sim+eSim SKU stay unconfirmed and cannot be accidentally approved from the UI.

Second category export proof:

1. `iPad Air 11 M3` branch export run `export_58a390b9ac` completed after generalizing sibling enrichment beyond iPhone-only titles.
2. Result: 32 SKU x 2 safe targets (`Я.Маркет GT USD`, `OZON Global Trade AE`) = 64 ready target rows, 0 blockers.
3. The pass hydrated 12 Yandex offer cards and filled 20 missing SKU from same-line sibling facts.
4. Sibling enrichment now groups Apple line variants by category, model line, and color for iPhone, iPad Air, MacBook Air, and MacBook Pro titles, instead of only matching iPhone by storage/color.

Next fix in the category flow:

1. Export blockers now carry machine-readable `missing_details` with a target workspace:
   - no confirmed competitor/product source for images -> `competitors`;
   - confirmed source exists but images are not imported -> `media`;
   - selected `needs_review`/external-hotlink media exists -> `media` review blocker, not silent readiness;
   - parameter/category/value blockers route to `sources`, `params`, or `values` without guessing from text.
2. Continue value/dictionary QA on the ready branches, especially provider-specific controlled values.
   - value readiness now checks real PIM dictionary values against provider output coverage, not the full provider allowed-value list;
   - production value check after deploy: `iPhone 17 Pro Max` has 0 value blockers and 26 unit checks; `iPad Air 11 M3` has 0 value blockers and 24 unit checks;
   - `/sources?tab=values` shows provider coverage as covered PIM values (`covered / PIM total`) instead of `mapped / allowed`.
   - value mapping now has an AI suggestion endpoint and UI action for a selected PIM dictionary/provider:
     `POST /api/marketplaces/mapping/import/values/{category_id}/dictionaries/{dict_id}/ai-suggest`;
     the endpoint uses the same allowed-value evidence as the value tab, validates that every suggested output is an actual provider allowed value, writes accepted pairs into dictionary `meta.export_map`, and records AI/rule evidence in `meta.value_ai`.
   - value AI matching also has a persisted job path for long dictionaries/Ollama calls:
     `POST /api/marketplaces/mapping/import/values/{category_id}/dictionaries/{dict_id}/ai-suggest/jobs`,
     `GET /api/marketplaces/mapping/import/values/ai-suggest/jobs/{job_id}`;
     queued/running jobs are saved in `pim_workflow_runs` as `marketplace_value_ai_match`, stale jobs are failed after a bounded window, and `global-pim-value-ai-worker.service` can resume queued work after restart.
   - when provider allowed values come only from category value bindings, value AI now treats missing `export_map` rows as unmapped even if the generic exporter would fall back to free text. This prevents false `already_covered` and forces a real PIM value -> provider allowed value pair.
3. Long full-category export preparation now has a persisted backend job path:
   - `POST /api/catalog/exchange/export/jobs` creates/reuses a queued job;
   - `GET /api/catalog/exchange/export/jobs/{job_id}` returns queued/running/completed/failed status and the saved run result;
   - `global-pim-export-worker.service` runs `app.workers.catalog_export_prepare --loop` and picks queued jobs after process/host restarts;
   - the old synchronous `/export/run` remains for compatibility.
4. Product media export controls are implemented in the active product media tab: each image can be included/excluded from export and moved up/down for export order without deleting enriched media. Export previews for Я.Маркет and Ozon use only images where `selected !== false`, sorted by `export_order`/array order.
5. Product creation now lands on the product workspace with a created-state guide that points the user to SKU/group competitor matching before enrichment/export.
6. Competitor source cards now show hidden-candidate reasons and retry guidance for no-exact-match/source-error states.
7. Value mapping evidence now shows PIM canonical sample values next to provider allowed/mapped samples.
8. Info-model draft rows now show evidence mix and review flags per candidate, including competitor-only fields, marketplace-only fields, low-confidence matches, and weak global attribute reuse.
9. Info-model draft rows with a weak/wrong global reuse suggestion can be switched to a new canonical field before approval with `Создать как новое`.
10. Info-model draft header now summarizes model-quality risks before approval: competitor-only, marketplace-only, weak PIM reuse, low confidence, empty select dictionaries, and duplicate codes.
11. Ozon source mapping can be unblocked manually when the tree is incomplete: enter a `type:<description_category_id>:<type_id>` value, validate it through the Ozon attributes API for enabled stores, then save the category binding only after the API confirms at least one store.

## Verification Commands

Use as applicable:

```bash
make check-backend
PYTHONPATH=backend python3 -m pytest backend/tests/test_auth_flow.py -k "competitor"
PYTHONPATH=backend python3 -m pytest backend/tests/test_products_service.py
cd frontend && npm run build
scripts/server_ops.sh public-health
scripts/server_ops.sh health
```

Deploy when needed:

```bash
cd frontend && npm run build
CI=1 ./scripts/deploy_production.sh --skip-build
```

Close browser/processes after browser automation:

```bash
pkill -9 -f '@playwright/mcp' || true
pkill -9 -f 'playwright-mcp' || true
pkill -9 -f 'mcp-chrome' || true
rm -rf .playwright-mcp
```
