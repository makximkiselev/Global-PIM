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

Target path:

1. Open `Сводка` and see blocking tasks for the category.
2. Open `Инфо-модели`.
3. Select category `Смартфоны`.
4. Confirm/rebuild info-model fields from marketplace and competitor evidence.
5. Confirm marketplace categories for `Я.Маркет` and `Ozon`.
6. Confirm competitor category context for `re-store` and `store77`.
7. Map PIM fields to marketplace fields.
8. Map/normalize values for marketplace output.
9. Create or import SKU.
10. If SKU has variants, generate SKU matrix from selected axes and create separate SKU rows.
11. Pick SKU or SKU subset in product card.
12. Scan competitor product cards.
13. Confirm/reject competitor candidates.
14. Enrich SKU parameters/media/evidence from confirmed competitor cards.
15. Review product card readability.
16. Validate readiness for `Я.Маркет` and `Ozon`.
17. Export or clearly show remaining blockers.

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

Known problems:

1. Some near matches are still too noisy and must remain manual-review, not auto-confirm.
2. Store77 may intermittently timeout from production.
3. Many donor specs remain unmatched because the current info-model does not yet contain every canonical field.
4. UI still does not show enough source-specific scan evidence when a source returns no candidates.

Next tasks:

1. Add parser/audit evidence for why an exact SKU was missed.
2. Show retry timing and source-specific failure reason in UI.
3. Add controlled production check for one `17e 256Gb Pink SIM+eSIM` SKU after candidate scan is safe.
4. Continue tests for exact matching around `256Gb`, `1Tb`, `eSIM`, `SIM+eSIM`, and color variants as new variants appear.

### P0.3 Info-Model Builder And Global Attributes

Status: active.

Current state:

1. Info-model fields must reference global attributes, not category-local duplicates.
2. Shared parameters such as `Встроенная память`, `Оперативная память`, `SIM`, `Цвет`, `Модель`, dimensions, OS, and dictionaries must be reused across categories.
3. `draft_service.approve_draft` already calls `ensure_global_attribute` and collapses accepted synonyms into template attributes.
4. Smartphone category model currently has marketplace/provider data and enough fields for initial workflow, but unmatched competitor specs still expose model gaps.
5. Draft collection now includes competitor unmatched specs when the UI calls `sources: ["products", "marketplaces", "competitors"]`.
6. Competitor unmatched specs are review-only candidates with source provenance (`restore`/`store77`) and do not auto-approve.
7. Synonyms such as `Объем встроенной памяти` continue to collapse into the global `Встроенная память` attribute during approval.
8. Draft candidates now include `global_match` and `suggested_action`, so UI can show whether the field should reuse an existing global attribute or create a new one.
9. Draft rows show duplicate prevention directly: `Уже есть в PIM` changes the action label to `Использовать поле`; new fields are labelled `Новое поле`.

Known problems:

1. The template/model screen is still heavy for a new user.
2. Product fields can outnumber approved model fields after resets/rebuilds.
3. There is not enough UI clarity around “add field”, “reuse global field”, “ignore source field”, and “map to marketplace field”.
4. Competitor review candidates are present in the draft list, but the UI still needs clearer source grouping and “reuse existing global field” actions.

Next tasks:

1. Re-run smartphone/tablet model rebuild comparison and verify no duplicate memory/RAM attributes are created.
2. Improve draft source grouping so competitor-only fields can be reviewed separately from marketplace-required fields.
3. Add a direct edit path for wrong `global_match` suggestions before approval.

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

Known problems:

1. Value mapping still needs a `fix next blockers` mode.
2. Canonical PIM value, raw source value, marketplace output value, and allowed marketplace values are not compact enough in one row.
3. Marketplace dictionary data quality still needs verification.
4. Actual export payload must consistently read provider-specific output values, not raw competitor text.

Next tasks:

1. Add actions: accept suggestion, edit mapping, mark not needed, reset.
2. Add route tests for complex mappings and provider-specific export values.
3. Add direct source-evidence snippets to value rows where competitor/raw source values differ from canonical PIM values.

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

Known problems:

1. Variant generation still needs more realistic UX around first/base product and variant axes.
2. Need clearer transition from created group to group-level competitor matching.
3. Product creation must not expose technical fields too early.

Next tasks:

1. Re-test full path for a real product family: base data -> axes -> matrix -> create -> group competitor scan -> enrichment -> validation.
2. Improve group workspace after creation with immediate selected-SKU guidance.
3. Add stronger preview of generated group title and variant axes before final create.

### P0.6 Catalog / Products / Export UX

Status: active.

Current state:

1. Catalog was simplified and no longer behaves like a dashboard at the top.
2. Product table is more usable and category context is retained.
3. Export page must keep GT USD and Ozon as safe selected targets during tests.
4. Product media deduplication was cleaned; S3-backed media renders for checked products.
5. Export page now requires a confirmation dialog before batch preparation and explicitly lists selected scope, SKU estimate, target count, and store labels.

Known problems:

1. Catalog/source/tree components are still not fully unified.
2. Some screens still have local layout implementations.
3. Export readiness needs stronger protection against accidental broad category exports.
4. Product card description/source evidence can still be too noisy.

Next tasks:

1. Continue replacing page-specific workspace fragments with shared primitives.
2. Add one persistent category/SKU next-action state across catalog, sources, product card, and export.
3. Move long source descriptions into evidence/details panels, not visible canonical fields.
4. Browser-check export confirmation on GT USD/Ozon with one SKU before real batch usage.

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
