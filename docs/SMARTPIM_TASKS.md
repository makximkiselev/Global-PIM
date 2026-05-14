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

Verified:

```bash
PYTHONPATH=backend python3 -m pytest backend/tests/test_auth_flow.py -k "competitor or store77 or restore or sim_profile or variant"
PYTHONPATH=backend python3 -m pytest backend/tests/test_auth_flow.py -k "store77 or competitor or restore"
PYTHONPATH=backend python3 -m pytest backend/tests/test_operating_workflows.py -k "store77"
PYTHONPATH=backend python3 -m pytest backend/tests/test_products_service.py backend/tests/test_operating_workflows.py -k "product_normalizer or loads_variants or store77"
PYTHONPATH=backend python3 -m pytest backend/tests/test_auth_flow.py -k "store77_product_html_extracts_gallery_images or competitor_product_discovery_endpoint_returns_candidates_and_links"
PYTHONPATH=backend python3 -m pytest backend/tests/test_operating_workflows.py -k "existing_catalog_enrichment_uses_confirmed_competitor_links or catalog_import_uses_confirmed_partner_links_before_export"
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
