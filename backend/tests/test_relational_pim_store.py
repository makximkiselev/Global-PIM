import os
import json
import sys
import threading
import time
import unittest
from unittest.mock import patch


sys.path.insert(0, os.path.abspath("backend"))

from app.storage import relational_pim_store
from app.storage import json_store


class RelationalPimStoreTests(unittest.TestCase):
    def test_replace_templates_tenant_tables_persists_template_meta(self) -> None:
        inserted_templates: list[tuple[object, ...]] = []

        class _Cursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def execute(self, query, params=None) -> None:
                return None

            def executemany(self, query, rows) -> None:
                if "INSERT INTO templates_tenant_rel" in str(query):
                    inserted_templates.extend(list(rows))

        class _Conn:
            def cursor(self) -> _Cursor:
                return _Cursor()

        doc = {
            "version": 2,
            "templates": {
                "tpl-draft": {
                    "id": "tpl-draft",
                    "name": "Draft",
                    "category_id": "cat-vr",
                    "created_at": "2026-04-27T00:00:00+00:00",
                    "updated_at": "2026-04-27T00:01:00+00:00",
                    "meta": {"info_model": {"status": "draft", "candidates": [{"id": "cand-memory"}]}},
                }
            },
            "attributes": {"tpl-draft": []},
            "category_to_templates": {"cat-vr": ["tpl-draft"]},
        }

        with (
            patch.object(relational_pim_store, "_with_pg_retry", side_effect=lambda fn: fn()),
            patch.object(relational_pim_store, "_pg_connect", return_value=(_Conn(), None, None)),
            patch.object(relational_pim_store, "_resolve_organization_id", return_value="org_default"),
        ):
            relational_pim_store._replace_templates_tenant_tables(doc, organization_id="org_default")

        self.assertEqual(len(inserted_templates), 1)
        self.assertEqual(inserted_templates[0][1], "tpl-draft")
        self.assertEqual(json.loads(inserted_templates[0][6])["info_model"]["status"], "draft")

    def test_load_competitor_mapping_does_not_overwrite_non_empty_tenant_doc_with_legacy(self) -> None:
        tenant_doc = {
            "version": 2,
            "categories": {},
            "templates": {},
            "discovery": {
                "runs": {"run_1": {"id": "run_1", "status": "completed"}},
                "candidates": {"cand_1": {"id": "cand_1"}},
                "links": {},
            },
        }
        legacy_doc = {
            "version": 2,
            "categories": {},
            "templates": {"legacy": {"id": "legacy"}},
        }
        writes = []

        def fake_read(path, default):
            if str(path).endswith("competitor_mapping_org_default.json"):
                return tenant_doc.copy()
            if str(path).endswith("competitor_mapping.json"):
                return legacy_doc.copy()
            return default

        with (
            patch.object(json_store, "current_tenant_organization_id", return_value="org_default"),
            patch.object(json_store, "_read_json", side_effect=fake_read),
            patch.object(json_store, "_write_json_atomic", side_effect=lambda path, data: writes.append((path, data))),
        ):
            loaded = json_store.load_competitor_mapping_db()

        self.assertEqual(loaded["discovery"]["runs"]["run_1"]["status"], "completed")
        self.assertEqual(loaded["discovery"]["candidates"]["cand_1"]["id"], "cand_1")
        self.assertEqual(writes, [])

    def test_normalize_dictionary_doc_merges_duplicate_dictionary_ids(self) -> None:
        doc = {
            "version": 2,
            "items": [
                {
                    "id": "dict_sim_karta",
                    "title": "SIM-карта",
                    "code": "sim_karta",
                    "attr_id": "attr_sim_a",
                    "type": "select",
                    "scope": "both",
                    "items": [{"value": "nano", "count": 1}],
                    "aliases": {"nano sim": "nano"},
                    "meta": {"service": True},
                },
                {
                    "id": "dict_sim_karta",
                    "title": "SIM-карта",
                    "code": "sim_karta",
                    "attr_id": "attr_sim_b",
                    "type": "select",
                    "scope": "both",
                    "items": [{"value": "micro", "count": 2}],
                    "aliases": {"micro sim": "micro"},
                    "meta": {"required": True},
                },
            ],
        }

        normalized = relational_pim_store._normalize_dictionary_doc(doc)
        items = normalized["items"]

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "dict_sim_karta")
        self.assertEqual(items[0]["code"], "sim_karta")
        self.assertEqual(items[0]["meta"]["service"], True)
        self.assertEqual(items[0]["meta"]["required"], True)
        self.assertEqual(items[0]["aliases"]["nano sim"], "nano")
        self.assertEqual(items[0]["aliases"]["micro sim"], "micro")
        self.assertEqual(
            [row["value"] for row in items[0]["items"]],
            ["nano", "micro"],
        )

    def test_ensure_tables_skips_full_bootstrap_when_schema_marker_exists(self) -> None:
        original_ready = relational_pim_store._TABLES_READY
        relational_pim_store._TABLES_READY = False
        try:
            with (
                patch.object(relational_pim_store, "_schema_bootstrap_marker_exists", return_value=True, create=True),
                patch.object(
                    relational_pim_store,
                    "_ensure_tables_impl",
                    side_effect=AssertionError("full bootstrap should be skipped"),
                ),
            ):
                relational_pim_store._ensure_tables()
            self.assertTrue(relational_pim_store._TABLES_READY)
        finally:
            relational_pim_store._TABLES_READY = original_ready

    def test_save_dictionaries_db_doc_is_safe_under_parallel_writes(self) -> None:
        doc = {
            "version": 2,
            "items": [
                {
                    "id": "dict_sku_gt",
                    "title": "SKU GT",
                    "code": "sku_gt",
                    "attr_id": "attr_sku_gt",
                    "type": "select",
                    "scope": "both",
                    "items": [{"value": "50001", "count": 1}],
                    "aliases": {},
                    "meta": {"service": True},
                }
            ],
        }

        class _State:
            def __init__(self) -> None:
                self.dictionary_values: set[tuple[str, str, str]] = set()
                self.lock = threading.Lock()

        class _Cursor:
            def __init__(self, state: _State) -> None:
                self._state = state

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def execute(self, query, params=None) -> None:
                sql = " ".join(str(query).split())
                if "DELETE FROM dictionary_values_tenant_rel" in sql:
                    with self._state.lock:
                        self._state.dictionary_values.clear()
                    time.sleep(0.02)

            def executemany(self, query, rows) -> None:
                sql = " ".join(str(query).split())
                if "INSERT INTO dictionary_values_tenant_rel" not in sql:
                    return
                time.sleep(0.02)
                for row in rows:
                    key = (str(row[0]), str(row[1]), str(row[2]))
                    with self._state.lock:
                        if key in self._state.dictionary_values:
                            raise RuntimeError(f"duplicate value row: {key}")
                        self._state.dictionary_values.add(key)

        class _Conn:
            def __init__(self, state: _State) -> None:
                self._state = state

            def cursor(self) -> _Cursor:
                return _Cursor(self._state)

        state = _State()
        errors: list[Exception] = []
        write_lock = threading.Lock()

        def _worker() -> None:
            try:
                relational_pim_store.save_dictionaries_db_doc(doc, organization_id="org_default")
            except Exception as exc:  # pragma: no cover - captured for assertion
                errors.append(exc)

        with (
            patch.object(relational_pim_store, "_ensure_tables", return_value=None),
            patch.object(relational_pim_store, "_with_pg_retry", side_effect=lambda fn: fn()),
            patch.object(relational_pim_store, "_pg_connect", side_effect=lambda: (_Conn(state), None, None)),
            patch.object(relational_pim_store, "with_lock", side_effect=lambda *_args, **_kwargs: write_lock),
        ):
            threads = [threading.Thread(target=_worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(errors, [])

    def test_replace_attribute_value_refs_tenant_table_dedupes_duplicate_catalog_name_keys(self) -> None:
        inserted_rows: list[tuple[object, ...]] = []

        class _Cursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def execute(self, query, params=None) -> None:
                return None

            def executemany(self, query, rows) -> None:
                inserted_rows.extend(list(rows))

        class _Conn:
            def cursor(self) -> _Cursor:
                return _Cursor()

        with (
            patch.object(relational_pim_store, "_with_pg_retry", side_effect=lambda fn: fn()),
            patch.object(relational_pim_store, "_pg_connect", return_value=(_Conn(), None, None)),
            patch.object(
                relational_pim_store,
                "_collect_attribute_value_ref_rows",
                return_value=[
                    (
                        "cat_a",
                        "SKU GT",
                        "SKU GT",
                        "Артикулы",
                        "attr_one",
                        "dict_one",
                        "text",
                        True,
                        "ym_a",
                        "p1",
                        "Param 1",
                        "ENUM",
                        None,
                        False,
                        True,
                        None,
                        None,
                        None,
                        None,
                        None,
                        False,
                        False,
                        1,
                    ),
                    (
                        "cat_a",
                        "SKU GT",
                        "SKU GT",
                        "Артикулы",
                        "attr_two",
                        "dict_two",
                        "text",
                        False,
                        "ym_a",
                        "p2",
                        "Param 2",
                        "ENUM",
                        None,
                        False,
                        True,
                        None,
                        None,
                        None,
                        None,
                        None,
                        False,
                        False,
                        2,
                    ),
                ],
            ),
        ):
            relational_pim_store._replace_attribute_value_refs_tenant_table({}, organization_id="org_default")

        self.assertEqual(len(inserted_rows), 1)
        self.assertEqual(inserted_rows[0][0], "org_default")
        self.assertEqual(inserted_rows[0][1], "cat_a")
        self.assertEqual(inserted_rows[0][2], "SKU GT")
        self.assertEqual(inserted_rows[0][5], "attr_two")

    def test_replace_attribute_value_refs_tenant_table_dedupes_canonical_name_collisions(self) -> None:
        inserted_rows: list[tuple[object, ...]] = []

        class _Cursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def execute(self, query, params=None) -> None:
                return None

            def executemany(self, query, rows) -> None:
                inserted_rows.extend(list(rows))

        class _Conn:
            def cursor(self) -> _Cursor:
                return _Cursor()

        with (
            patch.object(relational_pim_store, "_with_pg_retry", side_effect=lambda fn: fn()),
            patch.object(relational_pim_store, "_pg_connect", return_value=(_Conn(), None, None)),
            patch.object(
                relational_pim_store,
                "_collect_attribute_value_ref_rows",
                return_value=[
                    (
                        "cat_a",
                        "sku gt",
                        "sku gt",
                        "Артикулы",
                        "attr_one",
                        "dict_one",
                        "text",
                        True,
                        "ym_a",
                        "p1",
                        "Param 1",
                        "ENUM",
                        None,
                        False,
                        True,
                        None,
                        None,
                        None,
                        None,
                        None,
                        False,
                        False,
                        1,
                    ),
                    (
                        "cat_a",
                        "SKU GT",
                        "SKU GT",
                        "Артикулы",
                        "attr_two",
                        "dict_two",
                        "text",
                        False,
                        "ym_a",
                        "p2",
                        "Param 2",
                        "ENUM",
                        None,
                        False,
                        True,
                        None,
                        None,
                        None,
                        None,
                        None,
                        False,
                        False,
                        2,
                    ),
                ],
            ),
        ):
            relational_pim_store._replace_attribute_value_refs_tenant_table({}, organization_id="org_default")

        self.assertEqual(len(inserted_rows), 1)
        self.assertEqual(inserted_rows[0][0], "org_default")
        self.assertEqual(inserted_rows[0][1], "cat_a")
        self.assertEqual(inserted_rows[0][2], "SKU GT")
        self.assertEqual(inserted_rows[0][5], "attr_two")


if __name__ == "__main__":
    unittest.main()
