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
15. Enrich SKU parameters/media/evidence from confirmed sources.
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

1. `/catalog?category=bb40de87-254b-4170-84d7-8e5d3925b251`
   - opens authenticated;
   - selected category context works;
   - shows `431 SKU в ветке` and `4 подкатегорий`;
   - category tree no longer overlaps counters at 1920px;
   - left menu overlay can still consume workspace and must be checked collapsed/pinned.
2. `/templates/bb40de87-254b-4170-84d7-8e5d3925b251`
   - opens authenticated;
   - model has `84` fields and source summary `Я.Маркет 69`;
   - field list is very long and needs visual confirmation for readability, labels, action density, and duplicate controls.
3. `/sources?tab=sources&category=bb40de87-254b-4170-84d7-8e5d3925b251`
   - Browser-verified on 2026-05-12 after compact layout pass;
   - no accidental horizontal overflow;
   - selected SKU and Store77 candidate are visible;
   - candidate row actions no longer wrap into a tall broken card;
   - remaining issue: category tree and top hero are still visually heavy, but usable.
4. `/sources?tab=params&category=bb40de87-254b-4170-84d7-8e5d3925b251`
   - Browser-verified on 2026-05-12;
   - no accidental horizontal overflow;
   - remaining issue: the right-side provider field dropdown/list is too long and should become searchable/sectioned instead of dumping all Ozon/Yandex fields.
5. `/sources?tab=values&category=bb40de87-254b-4170-84d7-8e5d3925b251`
   - Browser-verified on 2026-05-12;
   - no accidental horizontal overflow;
   - remaining issue: value rows are still dense and Ozon shows `0/0` for many fields, so data readiness and empty-state copy need cleanup.
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

### P0.3 Competitor Matching Quality

Status: active after pipeline audit.

Goal: improve `re-store` and `store77` exact product-card discovery for SKU enrichment.

Required behavior:

1. Backend scans competitor catalog/search pages and extracts product-card URLs.
2. Matching must respect exact model, memory, color, SIM/eSIM configuration, region/global differences, and variant names.
3. `eSIM` and `SIM + eSIM` must not collapse into the same match.
4. If multiple close candidates exist, UI shows them as selectable variants.
5. If all candidates are rejected, user can add exact competitor URL manually.
6. Approved/rejected decisions persist to `pim_channel_links`.

### P0.4 Import / Export Contract Check

Status: pending after mapping/value blockers.

Goal: verify imported products and export readiness use the same category/model/value state as the UI.

Required behavior:

1. Import can create/update SKU under selected category.
2. Import preserves category context.
3. Created/imported SKU can be enriched with model fields and competitor evidence.
4. Export shows blockers per marketplace.
5. Export uses `SKU GT` as article/offer identifier where required.
6. Export run state must be readable and not hidden in JSON-only operational docs long-term.

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
