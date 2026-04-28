# Info Model Draft Real Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first real-data implementation of draft-first info models: category sources produce draft field candidates, the user moderates them, approves a model, and `/sources` only works as mapping after the model exists.

**Architecture:** Add an `info_models` adapter layer on top of the current `templates` storage instead of introducing a new database table immediately. Draft metadata is stored in `template.meta.info_model`, while accepted fields continue to use the existing `templates.attributes` array so current product and mapping flows keep working.

**Tech Stack:** FastAPI backend, existing JSON/relational document storage through `json_store`, React 19 frontend, Vite 8, Vitest, Python `unittest`, in-app browser verification through `@browser-use`.

---

## Current Constraints

1. Current persisted source of truth for models is still `templates.json` through `load_templates_db()` and `save_templates_db()`.
2. Current category model creation lives in `backend/app/api/routes/templates.py::create_for_category`.
3. Current model editor lives in `frontend/src/features/templates/TemplateEditorFeature.tsx`.
4. Current channel/category/attribute mapping lives in `frontend/src/features/sources/SourcesMarketplaceSection.tsx`.
5. Current production data must not be overwritten by synthetic fixtures.
6. The first implementation must be an adapter over current storage, not a storage rewrite.

## Target Data Shape

Store draft metadata inside a template record:

```json
{
  "id": "tpl_...",
  "category_id": "b2f026d9-a3e2-4821-9034-d17ac1b65065",
  "name": "Draft: Аксессуары",
  "meta": {
    "info_model": {
      "status": "draft",
      "draft_sources": ["marketplaces", "products", "competitors"],
      "draft_generated_at": "2026-04-27T00:00:00+00:00",
      "approved_at": null,
      "candidates": [
        {
          "id": "cand_memory",
          "name": "Встроенная память",
          "code": "vstroennaya_pamyat",
          "type": "select",
          "group": "Характеристики",
          "required": false,
          "confidence": 0.86,
          "status": "accepted",
          "examples": ["128 GB", "256 GB"],
          "sources": [
            {
              "kind": "product",
              "provider": "existing_products",
              "source_name": "Товары категории",
              "field_name": "memory",
              "examples": ["128 GB", "256 GB"],
              "count": 2
            }
          ]
        }
      ]
    }
  }
}
```

Accepted candidates become normal template attributes:

```json
{
  "id": "attr_memory",
  "name": "Встроенная память",
  "code": "vstroennaya_pamyat",
  "type": "select",
  "required": false,
  "scope": "feature",
  "position": 10,
  "options": {
    "param_group": "Характеристики",
    "source_candidates": ["cand_memory"]
  }
}
```

---

## File Structure

### Backend

- Create: `backend/app/core/info_models/__init__.py`
  - Package marker for the new adapter layer.
- Create: `backend/app/core/info_models/draft_service.py`
  - Builds candidates from real sources, creates draft templates, updates candidate statuses, approves draft into attributes.
- Create: `backend/app/api/routes/info_models.py`
  - Thin FastAPI endpoints for draft-first info model actions.
- Modify: `backend/app/main.py`
  - Include the new router under `/api`.
- Modify: `backend/app/api/routes/templates.py`
  - Add `info_model` summary to existing editor bootstrap response.
- Modify: `backend/tests/test_operating_workflows.py`
  - Add service-level tests for draft generation, moderation and approval.
- Modify: `backend/tests/test_api_read_smoke.py`
  - Add API smoke checks for new endpoints.

### Frontend

- Create: `frontend/src/features/templates/infoModelDraft.ts`
  - Shared TypeScript types and helper functions for model state.
- Modify: `frontend/src/features/templates/TemplateEditorFeature.tsx`
  - Replace no-model empty state with draft-first flow.
  - Render draft candidate moderation.
  - Render approved model state.
- Modify: `frontend/src/features/sources/SourcesMarketplaceSection.tsx`
  - Show clear empty state when parameter/value mapping is opened before a model exists.
- Modify: `frontend/src/features/sources/SourcesMappingFeature.tsx`
  - Keep copy aligned with draft-first workflow.
- Modify: `frontend/src/styles/templates.css`
  - Add compact draft moderation layout styles.

### Docs

- Modify: `docs/smartpim-full-rebuild-master-plan.md`
  - Mark this plan as the active implementation plan.
  - Add status updates after each browser-verified slice.

---

## Task 1: Backend Draft Service Tests

**Files:**
- Modify: `backend/tests/test_operating_workflows.py`

- [ ] **Step 1: Add failing service tests**

Append these tests to `OperatingWorkflowTests`:

```python
    def test_info_model_draft_from_products_creates_candidates_with_provenance(self) -> None:
        from app.core.info_models import draft_service

        templates_db = {"templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}}
        products = [
            {
                "id": "product_quest_128",
                "category_id": "cat-vr",
                "title": "Meta Quest 3 128GB",
                "content": {
                    "features": [
                        {"name": "Бренд", "value": "Meta"},
                        {"name": "Встроенная память", "value": "128 GB"},
                    ]
                },
            },
            {
                "id": "product_quest_256",
                "category_id": "cat-vr",
                "title": "Meta Quest 3 256GB",
                "content": {
                    "features": [
                        {"name": "Бренд", "value": "Meta"},
                        {"name": "Встроенная память", "value": "256 GB"},
                    ]
                },
            },
        ]
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        with (
            patch.object(draft_service, "load_templates_db", return_value=deepcopy(templates_db)),
            patch.object(draft_service, "save_templates_db", side_effect=save),
            patch.object(draft_service, "query_products_full", return_value=deepcopy(products)),
            patch.object(draft_service, "new_id", side_effect=["tpl-draft-vr", "cand-brand", "cand-memory"]),
            patch.object(draft_service, "now_iso", return_value="2026-04-27T00:00:00+00:00"),
        ):
            response = draft_service.create_draft_from_sources("cat-vr", {"sources": ["products"]})

        self.assertEqual(response["template"]["id"], "tpl-draft-vr")
        self.assertEqual(response["info_model"]["status"], "draft")
        names = {candidate["name"] for candidate in response["candidates"]}
        self.assertIn("Бренд", names)
        self.assertIn("Встроенная память", names)
        memory = next(candidate for candidate in response["candidates"] if candidate["name"] == "Встроенная память")
        self.assertEqual(memory["examples"], ["128 GB", "256 GB"])
        self.assertEqual(memory["sources"][0]["kind"], "product")
        self.assertEqual(saved["templates"]["tpl-draft-vr"]["meta"]["info_model"]["status"], "draft")

    def test_info_model_approve_draft_writes_accepted_candidates_to_attributes(self) -> None:
        from app.core.info_models import draft_service

        templates_db = {
            "templates": {
                "tpl-draft-vr": {
                    "id": "tpl-draft-vr",
                    "category_id": "cat-vr",
                    "name": "Draft: VR",
                    "meta": {
                        "info_model": {
                            "status": "draft",
                            "candidates": [
                                {
                                    "id": "cand-memory",
                                    "name": "Встроенная память",
                                    "code": "vstroennaya_pamyat",
                                    "type": "select",
                                    "group": "Характеристики",
                                    "required": True,
                                    "confidence": 0.9,
                                    "status": "accepted",
                                    "examples": ["128 GB", "256 GB"],
                                    "sources": [],
                                },
                                {
                                    "id": "cand-weight",
                                    "name": "Вес",
                                    "code": "ves",
                                    "type": "number",
                                    "group": "Габариты",
                                    "required": False,
                                    "confidence": 0.4,
                                    "status": "rejected",
                                    "examples": ["515 г"],
                                    "sources": [],
                                },
                            ],
                        }
                    },
                }
            },
            "attributes": {"tpl-draft-vr": []},
            "category_to_template": {"cat-vr": "tpl-draft-vr"},
            "category_to_templates": {"cat-vr": ["tpl-draft-vr"]},
        }
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        with (
            patch.object(draft_service, "load_templates_db", return_value=deepcopy(templates_db)),
            patch.object(draft_service, "save_templates_db", side_effect=save),
            patch.object(draft_service, "new_id", return_value="attr-memory"),
            patch.object(draft_service, "now_iso", return_value="2026-04-27T01:00:00+00:00"),
        ):
            response = draft_service.approve_draft("tpl-draft-vr")

        self.assertEqual(response["info_model"]["status"], "approved")
        attrs = saved["attributes"]["tpl-draft-vr"]
        self.assertEqual(len(attrs), 1)
        self.assertEqual(attrs[0]["name"], "Встроенная память")
        self.assertEqual(attrs[0]["options"]["source_candidates"], ["cand-memory"])
        self.assertEqual(saved["templates"]["tpl-draft-vr"]["meta"]["info_model"]["approved_at"], "2026-04-27T01:00:00+00:00")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_operating_workflows.OperatingWorkflowTests.test_info_model_draft_from_products_creates_candidates_with_provenance backend.tests.test_operating_workflows.OperatingWorkflowTests.test_info_model_approve_draft_writes_accepted_candidates_to_attributes
```

Expected: failure with `ModuleNotFoundError: No module named 'app.core.info_models'`.

---

## Task 2: Backend Draft Service Implementation

**Files:**
- Create: `backend/app/core/info_models/__init__.py`
- Create: `backend/app/core/info_models/draft_service.py`

- [ ] **Step 1: Create package marker**

Create `backend/app/core/info_models/__init__.py`:

```python
"""Info model adapter layer built on top of the current templates storage."""
```

- [ ] **Step 2: Implement draft service**

Create `backend/app/core/info_models/draft_service.py`:

```python
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Tuple

from app.core.ids import new_id
from app.core.products.service import query_products_full
from app.core.time import now_iso
from app.storage.json_store import load_templates_db, save_templates_db


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slugify(value: str) -> str:
    out: List[str] = []
    prev_sep = False
    for ch in _text(value).lower():
        if "a" <= ch <= "z" or "0" <= ch <= "9":
            out.append(ch)
            prev_sep = False
        elif "а" <= ch <= "я" or ch == "ё":
            table = {
                "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
                "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
                "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
                "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
            }
            out.append(table.get(ch, ""))
            prev_sep = False
        elif not prev_sep:
            out.append("_")
            prev_sep = True
    return "".join(out).strip("_") or "field"


def _infer_type(values: Iterable[str]) -> str:
    clean = [_text(value) for value in values if _text(value)]
    if not clean:
        return "text"
    numeric = 0
    for value in clean:
        normalized = value.replace(",", ".").replace(" ", "")
        if normalized.replace(".", "", 1).isdigit():
            numeric += 1
    if numeric == len(clean):
        return "number"
    unique_count = len(set(clean))
    if unique_count <= 24:
        return "select"
    return "text"


def _feature_items(product: Dict[str, Any]) -> Iterable[Tuple[str, str]]:
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    features = content.get("features") if isinstance(content.get("features"), list) else []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        name = _text(feature.get("name") or feature.get("code"))
        value = _text(feature.get("value"))
        if name:
            yield name, value


def _product_candidates(category_id: str) -> List[Dict[str, Any]]:
    products = [p for p in query_products_full() if isinstance(p, dict) and _text(p.get("category_id")) == category_id]
    by_code: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for product in products:
        for name, value in _feature_items(product):
            code = _slugify(name)
            row = by_code.setdefault(
                code,
                {
                    "id": new_id(),
                    "name": name,
                    "code": code,
                    "group": "Характеристики",
                    "required": False,
                    "examples": [],
                    "sources": [],
                    "_count": 0,
                },
            )
            row["_count"] += 1
            if value and value not in row["examples"]:
                row["examples"].append(value)
            if not row["sources"]:
                row["sources"].append(
                    {
                        "kind": "product",
                        "provider": "existing_products",
                        "source_name": "Товары категории",
                        "field_name": code,
                        "examples": [],
                        "count": 0,
                    }
                )
            source = row["sources"][0]
            source["count"] = int(source.get("count") or 0) + 1
            if value and value not in source["examples"]:
                source["examples"].append(value)

    out: List[Dict[str, Any]] = []
    product_count = max(len(products), 1)
    for row in by_code.values():
        examples = row.get("examples") if isinstance(row.get("examples"), list) else []
        row["type"] = _infer_type(examples)
        row["confidence"] = min(0.95, round(0.45 + (float(row.get("_count") or 0) / product_count) * 0.45, 2))
        row["status"] = "accepted" if row["confidence"] >= 0.65 else "needs_review"
        row.pop("_count", None)
        out.append(row)
    return out


def _template_for_category(db: Dict[str, Any], category_id: str) -> Tuple[str, Dict[str, Any] | None]:
    templates = db.get("templates") if isinstance(db.get("templates"), dict) else {}
    category_to_templates = db.get("category_to_templates") if isinstance(db.get("category_to_templates"), dict) else {}
    ids = category_to_templates.get(category_id) if isinstance(category_to_templates.get(category_id), list) else []
    template_id = _text((ids or [""])[0])
    template = templates.get(template_id) if template_id else None
    return template_id, template if isinstance(template, dict) else None


def _ensure_template(db: Dict[str, Any], category_id: str, name: str) -> Dict[str, Any]:
    template_id, template = _template_for_category(db, category_id)
    if template:
        return template
    template_id = new_id()
    template = {
        "id": template_id,
        "category_id": category_id,
        "name": name,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "meta": {"sources": {}},
    }
    db.setdefault("templates", {})[template_id] = template
    db.setdefault("attributes", {})[template_id] = []
    db.setdefault("category_to_template", {})[category_id] = template_id
    db.setdefault("category_to_templates", {}).setdefault(category_id, [])
    if template_id not in db["category_to_templates"][category_id]:
        db["category_to_templates"][category_id].append(template_id)
    return template


def _info_model_meta(template: Dict[str, Any]) -> Dict[str, Any]:
    meta = template.get("meta") if isinstance(template.get("meta"), dict) else {}
    info_model = meta.get("info_model") if isinstance(meta.get("info_model"), dict) else {}
    meta["info_model"] = info_model
    template["meta"] = meta
    return info_model


def create_draft_from_sources(category_id: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cid = _text(category_id)
    if not cid:
        raise ValueError("CATEGORY_REQUIRED")
    selected_sources = payload.get("sources") if isinstance(payload, dict) and isinstance(payload.get("sources"), list) else ["products"]
    db = load_templates_db()
    template = _ensure_template(db, cid, f"Draft: {cid}")
    info_model = _info_model_meta(template)
    candidates: List[Dict[str, Any]] = []
    if "products" in selected_sources:
        candidates.extend(_product_candidates(cid))
    info_model.update(
        {
            "status": "draft",
            "draft_sources": selected_sources,
            "draft_generated_at": now_iso(),
            "approved_at": None,
            "candidates": candidates,
        }
    )
    template["updated_at"] = now_iso()
    db["templates"][template["id"]] = template
    save_templates_db(db)
    return {"ok": True, "template": template, "info_model": info_model, "candidates": candidates}


def update_draft_candidate(template_id: str, candidate_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    db = load_templates_db()
    template = (db.get("templates") or {}).get(template_id)
    if not isinstance(template, dict):
        raise ValueError("TEMPLATE_NOT_FOUND")
    info_model = _info_model_meta(template)
    candidates = info_model.get("candidates") if isinstance(info_model.get("candidates"), list) else []
    for candidate in candidates:
        if isinstance(candidate, dict) and _text(candidate.get("id")) == candidate_id:
            for key in ("name", "code", "type", "group", "required", "status"):
                if key in patch:
                    candidate[key] = patch[key]
            template["updated_at"] = now_iso()
            db["templates"][template_id] = template
            save_templates_db(db)
            return {"ok": True, "candidate": candidate, "info_model": info_model}
    raise ValueError("CANDIDATE_NOT_FOUND")


def approve_draft(template_id: str) -> Dict[str, Any]:
    db = load_templates_db()
    template = (db.get("templates") or {}).get(template_id)
    if not isinstance(template, dict):
        raise ValueError("TEMPLATE_NOT_FOUND")
    info_model = _info_model_meta(template)
    candidates = info_model.get("candidates") if isinstance(info_model.get("candidates"), list) else []
    attrs: List[Dict[str, Any]] = []
    for position, candidate in enumerate(c for c in candidates if isinstance(c, dict) and c.get("status") == "accepted"):
        attrs.append(
            {
                "id": new_id(),
                "name": _text(candidate.get("name")),
                "code": _text(candidate.get("code")) or _slugify(_text(candidate.get("name"))),
                "type": _text(candidate.get("type")) or "text",
                "required": bool(candidate.get("required")),
                "scope": "feature",
                "position": position,
                "options": {
                    "param_group": _text(candidate.get("group")) or "Характеристики",
                    "source_candidates": [_text(candidate.get("id"))],
                },
            }
        )
    db.setdefault("attributes", {})[template_id] = attrs
    info_model["status"] = "approved"
    info_model["approved_at"] = now_iso()
    template["updated_at"] = now_iso()
    db["templates"][template_id] = template
    save_templates_db(db)
    return {"ok": True, "template": template, "info_model": info_model, "attributes": attrs}
```

- [ ] **Step 3: Run service tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_operating_workflows.OperatingWorkflowTests.test_info_model_draft_from_products_creates_candidates_with_provenance backend.tests.test_operating_workflows.OperatingWorkflowTests.test_info_model_approve_draft_writes_accepted_candidates_to_attributes
```

Expected: both tests pass.

- [ ] **Step 4: Commit backend service**

Run:

```bash
git add backend/app/core/info_models/__init__.py backend/app/core/info_models/draft_service.py backend/tests/test_operating_workflows.py
git commit -m "Add info model draft service"
```

---

## Task 3: Info Model API Adapter

**Files:**
- Create: `backend/app/api/routes/info_models.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api_read_smoke.py`

- [ ] **Step 1: Add failing API smoke tests**

Append to `backend/tests/test_api_read_smoke.py` inside the existing API smoke test class:

```python
    def test_info_model_draft_endpoint(self) -> None:
        from app.api.routes import info_models

        with patch.object(
            info_models.draft_service,
            "create_draft_from_sources",
            return_value={
                "ok": True,
                "template": {"id": "tpl-draft-vr", "category_id": "cat-vr", "name": "Draft: VR"},
                "info_model": {"status": "draft"},
                "candidates": [{"id": "cand-memory", "name": "Встроенная память"}],
            },
        ):
            response = self.client.post("/api/info-models/draft-from-sources", json={"category_id": "cat-vr", "sources": ["products"]})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["template"]["id"], "tpl-draft-vr")
        self.assertEqual(body["info_model"]["status"], "draft")

    def test_info_model_approve_endpoint(self) -> None:
        from app.api.routes import info_models

        with patch.object(
            info_models.draft_service,
            "approve_draft",
            return_value={
                "ok": True,
                "template": {"id": "tpl-draft-vr"},
                "info_model": {"status": "approved"},
                "attributes": [{"id": "attr-memory", "name": "Встроенная память"}],
            },
        ):
            response = self.client.post("/api/info-models/tpl-draft-vr/approve")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info_model"]["status"], "approved")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_api_read_smoke.ApiReadSmokeTests.test_info_model_draft_endpoint backend.tests.test_api_read_smoke.ApiReadSmokeTests.test_info_model_approve_endpoint
```

Expected: failure because `app.api.routes.info_models` does not exist.

- [ ] **Step 3: Create API route**

Create `backend/app/api/routes/info_models.py`:

```python
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.core.info_models import draft_service

router = APIRouter(prefix="/info-models", tags=["info-models"])


def _bad_request(error: ValueError) -> HTTPException:
    message = str(error)
    status = 404 if message in {"TEMPLATE_NOT_FOUND", "CANDIDATE_NOT_FOUND"} else 400
    return HTTPException(status_code=status, detail=message)


@router.post("/draft-from-sources")
def draft_from_sources(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return draft_service.create_draft_from_sources(str(payload.get("category_id") or ""), payload)
    except ValueError as error:
        raise _bad_request(error)


@router.patch("/{template_id}/draft-candidates/{candidate_id}")
def update_draft_candidate(template_id: str, candidate_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return draft_service.update_draft_candidate(template_id, candidate_id, payload)
    except ValueError as error:
        raise _bad_request(error)


@router.post("/{template_id}/approve")
def approve(template_id: str) -> Dict[str, Any]:
    try:
        return draft_service.approve_draft(template_id)
    except ValueError as error:
        raise _bad_request(error)
```

- [ ] **Step 4: Include router in app**

Modify `backend/app/main.py`:

```python
from app.api.routes import (
    products,
    catalog,
    templates,
    info_models,
    competitor_mapping,
    dictionaries,
)
```

Add near the templates router:

```python
app.include_router(info_models.router, prefix="/api")
```

- [ ] **Step 5: Run API tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_api_read_smoke.ApiReadSmokeTests.test_info_model_draft_endpoint backend.tests.test_api_read_smoke.ApiReadSmokeTests.test_info_model_approve_endpoint
```

Expected: both tests pass.

- [ ] **Step 6: Commit API adapter**

Run:

```bash
git add backend/app/api/routes/info_models.py backend/app/main.py backend/tests/test_api_read_smoke.py
git commit -m "Expose info model draft API"
```

---

## Task 4: Add Info Model State to Editor Bootstrap

**Files:**
- Modify: `backend/app/api/routes/templates.py`
- Modify: `backend/tests/test_api_read_smoke.py`

- [ ] **Step 1: Add assertion to existing bootstrap smoke test**

In `test_templates_editor_bootstrap_endpoint`, add:

```python
        self.assertIn("info_model", body)
        self.assertEqual(body["info_model"]["status"], "approved")
```

Change the mocked template in the test to include:

```python
                "meta": {"info_model": {"status": "approved", "candidates": []}},
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_api_read_smoke.ApiReadSmokeTests.test_templates_editor_bootstrap_endpoint
```

Expected: failure because `info_model` is missing from the response.

- [ ] **Step 3: Add bootstrap summary**

In `backend/app/api/routes/templates.py`, inside `template_editor_bootstrap`, before `return`, compute:

```python
    tpl_meta = owner_tpl.get("meta") if isinstance(owner_tpl, dict) and isinstance(owner_tpl.get("meta"), dict) else {}
    info_model = tpl_meta.get("info_model") if isinstance(tpl_meta.get("info_model"), dict) else {}
    info_model_status = str(info_model.get("status") or ("approved" if owner_tpl else "none")).strip()
```

Add to the returned dict:

```python
        "info_model": {
            **info_model,
            "status": info_model_status,
            "candidates_count": len(info_model.get("candidates") if isinstance(info_model.get("candidates"), list) else []),
        },
```

- [ ] **Step 4: Run backend smoke test**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_api_read_smoke.ApiReadSmokeTests.test_templates_editor_bootstrap_endpoint
```

Expected: pass.

- [ ] **Step 5: Commit bootstrap state**

Run:

```bash
git add backend/app/api/routes/templates.py backend/tests/test_api_read_smoke.py
git commit -m "Add info model state to template bootstrap"
```

---

## Task 5: Frontend Draft Types and API Helpers

**Files:**
- Create: `frontend/src/features/templates/infoModelDraft.ts`

- [ ] **Step 1: Create shared types**

Create `frontend/src/features/templates/infoModelDraft.ts`:

```ts
export type InfoModelStatus = "none" | "collecting" | "draft" | "review" | "approved" | "needs_update";

export type InfoModelCandidateSource = {
  kind: string;
  provider: string;
  source_name: string;
  field_name: string;
  examples?: string[];
  count?: number;
};

export type InfoModelCandidate = {
  id: string;
  name: string;
  code: string;
  type: "text" | "number" | "select" | string;
  group: string;
  required: boolean;
  confidence: number;
  status: "accepted" | "needs_review" | "rejected";
  examples: string[];
  sources: InfoModelCandidateSource[];
};

export type InfoModelSummary = {
  status: InfoModelStatus;
  candidates?: InfoModelCandidate[];
  candidates_count?: number;
  draft_sources?: string[];
  draft_generated_at?: string | null;
  approved_at?: string | null;
};

export function modelStatusLabel(status: InfoModelStatus): string {
  if (status === "none") return "Нет модели";
  if (status === "collecting") return "Сбор источников";
  if (status === "draft") return "Draft на модерации";
  if (status === "review") return "Готова к утверждению";
  if (status === "approved") return "Утверждена";
  return "Требует обновления";
}

export function candidateTone(candidate: InfoModelCandidate): "active" | "pending" | "danger" | "neutral" {
  if (candidate.status === "accepted") return "active";
  if (candidate.status === "needs_review") return "pending";
  if (candidate.status === "rejected") return "danger";
  return "neutral";
}
```

- [ ] **Step 2: Run TypeScript build**

Run:

```bash
npm --prefix frontend run build
```

Expected: pass.

- [ ] **Step 3: Commit frontend types**

Run:

```bash
git add frontend/src/features/templates/infoModelDraft.ts
git commit -m "Add info model draft frontend types"
```

---

## Task 6: Template Editor Draft-First UI

**Files:**
- Modify: `frontend/src/features/templates/TemplateEditorFeature.tsx`
- Modify: `frontend/src/styles/templates.css`

- [ ] **Step 1: Extend editor response types**

In `TemplateEditorFeature.tsx`, import:

```ts
import type { InfoModelCandidate, InfoModelSummary } from "./infoModelDraft";
import { candidateTone, modelStatusLabel } from "./infoModelDraft";
```

Add state:

```ts
const [infoModel, setInfoModel] = useState<InfoModelSummary>({ status: "none" });
const [draftBusy, setDraftBusy] = useState(false);
```

Extend bootstrap response type with:

```ts
info_model?: InfoModelSummary;
```

Inside `load()`, after `setMaster(data.master || null);`, add:

```ts
setInfoModel(data.info_model || { status: data.owner_template?.id ? "approved" : "none" });
```

- [ ] **Step 2: Add draft actions**

Add functions inside `TemplateEditorFeature.tsx`:

```ts
async function collectDraftModel() {
  if (!categoryId || draftBusy) return;
  setDraftBusy(true);
  try {
    const response = await api<{ template: TemplateT; info_model: InfoModelSummary; candidates: InfoModelCandidate[] }>("/info-models/draft-from-sources", {
      method: "POST",
      body: JSON.stringify({ category_id: categoryId, sources: ["products"] }),
    });
    setOwnerTpl(response.template);
    setTpl(response.template);
    setInfoModel({ ...(response.info_model || { status: "draft" }), candidates: response.candidates || [] });
    showToast("Draft-модель собрана");
    await load();
  } finally {
    setDraftBusy(false);
  }
}

async function approveDraftModel() {
  const templateId = ownerTpl?.id || tpl?.id;
  if (!templateId || draftBusy) return;
  setDraftBusy(true);
  try {
    const response = await api<{ info_model: InfoModelSummary; attributes: AttrT[] }>(`/info-models/${encodeURIComponent(templateId)}/approve`, {
      method: "POST",
    });
    setInfoModel(response.info_model || { status: "approved" });
    setAttrs(sortAttrs(response.attributes || []));
    showToast("Инфо-модель утверждена");
    await load();
  } finally {
    setDraftBusy(false);
  }
}
```

- [ ] **Step 3: Replace no-model empty state**

Replace the current no-model `EmptyState` action with:

```tsx
<EmptyState
  title="Инфо-модель еще не собрана"
  body="Сначала соберите draft из реальных источников: товаров категории, импортов и подключенных каналов. После модерации модель можно утвердить и использовать в товарах."
  action={
    <div className="tplEmptyActions">
      <Button variant="primary" onClick={collectDraftModel} disabled={!categoryId || draftBusy}>
        {draftBusy ? "Собираю…" : "Собрать draft-модель"}
      </Button>
      <Button onClick={createTemplateIfMissing} disabled={!categoryId || saving || draftBusy}>
        Создать вручную
      </Button>
      <Button onClick={() => setImportOpen(true)} disabled={!categoryId || saving || draftBusy}>
        Импортировать Excel
      </Button>
    </div>
  }
/>
```

- [ ] **Step 4: Render draft moderation panel**

Before the approved attributes board, add:

```tsx
{infoModel.status === "draft" ? (
  <Card className="tplDraftCard">
    <div className="tplDraftHeader">
      <div>
        <div className="tplSectionEyebrow">Draft из источников</div>
        <h3>Проверьте предложенные параметры</h3>
        <p>Система собрала параметры из реальных данных. Примите полезные поля, отклоните мусор и затем утвердите модель.</p>
      </div>
      <Button variant="primary" onClick={approveDraftModel} disabled={draftBusy}>
        {draftBusy ? "Утверждаю…" : "Утвердить модель"}
      </Button>
    </div>
    <div className="tplDraftList">
      {(infoModel.candidates || []).map((candidate) => (
        <div className="tplDraftRow" key={candidate.id}>
          <div>
            <strong>{candidate.name}</strong>
            <span>{candidate.group} · {candidate.type} · confidence {Math.round(candidate.confidence * 100)}%</span>
          </div>
          <div className="tplDraftExamples">{candidate.examples?.slice(0, 3).join(", ") || "Без примеров"}</div>
          <Badge tone={candidateTone(candidate)}>{candidate.status === "accepted" ? "Принять" : candidate.status === "rejected" ? "Отклонено" : "Проверить"}</Badge>
        </div>
      ))}
    </div>
  </Card>
) : null}
```

- [ ] **Step 5: Add styles**

Append to `frontend/src/styles/templates.css`:

```css
.tplDraftCard {
  display: grid;
  gap: 16px;
}

.tplDraftHeader {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
}

.tplDraftHeader h3 {
  margin: 4px 0 6px;
  font-size: 22px;
}

.tplDraftHeader p {
  margin: 0;
  max-width: 720px;
  color: var(--muted);
}

.tplDraftList {
  display: grid;
  gap: 8px;
}

.tplDraftRow {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(240px, 1fr) auto;
  gap: 14px;
  align-items: center;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--surface-soft);
}

.tplDraftRow strong,
.tplDraftRow span {
  display: block;
}

.tplDraftRow span,
.tplDraftExamples {
  color: var(--muted);
  font-size: 13px;
}
```

- [ ] **Step 6: Run frontend build**

Run:

```bash
npm --prefix frontend run build
```

Expected: pass.

- [ ] **Step 7: Commit editor UI**

Run:

```bash
git add frontend/src/features/templates/TemplateEditorFeature.tsx frontend/src/styles/templates.css
git commit -m "Add draft-first info model editor UI"
```

---

## Task 7: Sources Mapping Guardrail

**Files:**
- Modify: `frontend/src/features/sources/SourcesMarketplaceSection.tsx`
- Modify: `frontend/src/features/sources/SourcesMappingFeature.tsx`

- [ ] **Step 1: Add model-missing guard in parameter mapping**

In `SourcesMarketplaceSection.tsx`, use the existing `template_id` from attribute details. Before rendering the parameter mapping workbench rows, add:

```tsx
{activeAttrCategoryId && !savedTemplateId ? (
  <EmptyState
    title="Сначала соберите инфо-модель"
    body="Сопоставление параметров открывается после draft-модели. Перейдите в поля товара категории, соберите draft из источников и утвердите рабочую структуру."
    action={<Link className="btn primary" to={`/templates/${encodeURIComponent(activeAttrCategoryId)}`}>Открыть инфо-модель</Link>}
  />
) : null}
```

Ensure the existing parameter table is not rendered when `activeAttrCategoryId && !savedTemplateId`.

- [ ] **Step 2: Update tab copy**

In `SourcesMappingFeature.tsx`, keep the sources tab clean:

```ts
? "Категории маркетплейсов и источники. Параметры и значения сопоставляются после появления инфо-модели."
```

- [ ] **Step 3: Run frontend build**

Run:

```bash
npm --prefix frontend run build
```

Expected: pass.

- [ ] **Step 4: Commit mapping guardrail**

Run:

```bash
git add frontend/src/features/sources/SourcesMarketplaceSection.tsx frontend/src/features/sources/SourcesMappingFeature.tsx
git commit -m "Guard source mapping until info model exists"
```

---

## Task 8: Full Verification and Production Deploy

**Files:**
- Modify after verification: `docs/smartpim-full-rebuild-master-plan.md`

- [ ] **Step 1: Run backend tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_*.py'
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend tests**

Run stable local test mode:

```bash
cd frontend && npx vitest run --pool=threads --maxWorkers=1 --no-file-parallelism
```

Expected: all tests pass.

- [ ] **Step 3: Run frontend build**

Run:

```bash
npm --prefix frontend run build
```

Expected: build passes.

- [ ] **Step 4: Deploy production**

Run:

```bash
source /Users/maksimkiselev/.config/global-pim/production.env
sshpass -p "$APP_SERVER_PASSWORD" scp -o StrictHostKeyChecking=no root@5.129.199.228:/opt/projects/global-pim/certs/ca.crt /tmp/global-pim-ca.crt
CI=1 DB_CA_CERT_PATH=/tmp/global-pim-ca.crt APP_SERVER_PASSWORD="$APP_SERVER_PASSWORD" ./scripts/deploy_production.sh
```

Expected:

```text
active
{"ok":true}
==> Deploy complete
```

- [ ] **Step 5: Browser-use verification**

Use the in-app browser.

Verify:

1. `https://pim.id-smart.ru/templates/b2f026d9-a3e2-4821-9034-d17ac1b65065` loads.
2. If no own model exists, the primary action is `Собрать draft-модель`.
3. Clicking `Собрать draft-модель` creates a real template draft from products for the category.
4. Draft candidate rows show source examples and confidence.
5. Approving the draft writes accepted candidates to model attributes.
6. `https://pim.id-smart.ru/sources?category=b2f026d9-a3e2-4821-9034-d17ac1b65065&tab=params` no longer tries to explain model creation; it either shows mapping or a clear guardrail.

- [x] **Step 6: Update master-plan status**

Append under section `21.14 Product correction: Draft-first Info Model Workflow`:

```markdown
Implementation status:

1. backend adapter `/api/info-models/draft-from-sources` added;
2. draft metadata stored under `template.meta.info_model`;
3. `/templates/:categoryId` can collect and approve draft from real product data;
4. `/sources` guarded so mapping does not pretend to create models;
5. browser-use verification completed on production.
```

Production verification notes:

1. `Oura Ring 4` was used as the real-data no-model category.
2. Draft state persists after reload through `template.meta.info_model`.
3. False `approved` fallback was caused by missing relational `meta_json` persistence and is fixed.
4. Initial `Oura Ring 4` check produced `0` candidates because direct category mapping was absent and products did not contain `content.features`.
5. Marketplace source collectors were added for Я.Маркет and Ozon.
6. Draft generation now resolves nearest ancestor category mapping.
7. Rechecked production: `Oura Ring 4` inherits mapping from `Умные кольца` and produces 60 marketplace candidates.
8. Browser-use confirmed the UI shows `Draft из источников`, marketplace parameter rows and enabled `Утвердить модель`.

- [ ] **Step 7: Commit verification status**

Run:

```bash
git add docs/smartpim-full-rebuild-master-plan.md
git commit -m "Mark info model draft workflow verified"
git push origin main
```

- [ ] **Step 8: Close browser/playwright processes**

Run:

```bash
ps -axo pid,command | rg -i "playwright|chromium|chrome.*--remote|vite|node ./node_modules/vite|vitest" | rg -v "rg -i" || true
```

If any task-owned processes are listed, stop them:

```bash
kill -9 <pid>
```

---

## Self-Review

Spec coverage:

1. Draft from sources is covered by Tasks 1-3.
2. Moderation and approval are covered by Tasks 2 and 6.
3. Existing templates storage adapter is covered by Tasks 2 and 4.
4. `/sources` as mapping-layer only is covered by Task 7.
5. Browser verification and production deploy are covered by Task 8.

Placeholder scan:

1. The plan contains no unfinished marker strings.
2. The plan contains no stub implementation steps.
3. Each code task includes exact files, exact commands, and expected results.

Type consistency:

1. Backend uses `info_model.status`, `candidates`, `approved_at`.
2. Frontend uses `InfoModelSummary.status`, `InfoModelCandidate.status`, and the same candidate fields.
3. API endpoint paths match between backend and frontend: `/info-models/draft-from-sources` and `/info-models/{template_id}/approve`.
