import asyncio
import json
import os
import sys
import unittest
from copy import deepcopy
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException


sys.path.insert(0, os.path.abspath("backend"))

from app.api.routes import catalog_exchange, competitor_catalog_import, competitor_mapping, marketplace_mapping, ozon_market, product_groups, products, templates, yandex_market
from app.api.routes.catalog_exchange import CatalogExportRunReq, CatalogImportRunReq
from app.core.competitors.store77 import infer_store77_specs_from_title_or_url
from app.core.products import parameter_flow
from app.core.products import service as products_service
from app.core import value_mapping


class OperatingWorkflowTests(unittest.TestCase):
    def test_product_parameter_flow_connects_sources_pim_and_marketplace_outputs(self) -> None:
        product = {
            "id": "product_phone",
            "category_id": "cat_phones",
            "sku_gt": "52462",
            "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Blue",
            "content": {
                "features": [
                    {
                        "code": "memory",
                        "name": "Встроенная память",
                        "value": "256 ГБ",
                        "source_values": {
                            "competitor": {
                                "store77": {"raw_value": "256Gb", "resolved_value": "256 ГБ"},
                                "restore": {"raw_value": "256GB", "resolved_value": "256 ГБ"},
                            }
                        },
                    }
                ],
                "description": "Описание",
                "media_images": [{"url": "/api/uploads/p.jpg"}],
            },
        }

        with (
            patch.object(parameter_flow, "load_catalog_nodes", return_value=[{"id": "cat_phones", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(
                parameter_flow,
                "load_attribute_mapping_doc",
                return_value={
                    "items": {
                        "cat_phones": {
                            "rows": [
                                {
                                    "catalog_name": "Встроенная память",
                                    "provider_map": {
                                        "yandex_market": {"id": "ym_memory", "name": "Объем встроенной памяти", "export": True},
                                        "ozon": {"id": "oz_memory", "name": "Встроенная память", "export": True},
                                    },
                                }
                            ]
                        }
                    }
                },
            ),
            patch.object(
                parameter_flow,
                "load_attribute_value_refs_doc",
                return_value={
                    "items": {
                        "cat_phones": {
                            "catalog_params": {
                                "memory": {"catalog_name": "Встроенная память", "dict_id": "dict_memory"}
                            }
                        }
                    }
                },
            ),
            patch.object(
                parameter_flow,
                "provider_export_value_details",
                side_effect=lambda dict_id, provider, value: {
                    "value": "256" if provider == "ozon" else str(value),
                    "mapped": True,
                    "reason": "test",
                },
            ),
        ):
            payload = parameter_flow.build_product_parameter_flow(product)

        self.assertEqual(payload["summary"]["features_total"], 1)
        self.assertEqual(payload["summary"]["source_values"], 2)
        self.assertEqual(payload["service_rows"][0]["name"], "SKU GT")
        self.assertEqual(payload["service_rows"][0]["marketplaces"][0]["output_value"], "52462")
        row = payload["items"][0]
        self.assertEqual(row["value"], "256 ГБ")
        self.assertEqual({source["source_id"] for source in row["sources"]}, {"store77", "restore"})
        outputs = {item["provider"]: item for item in row["marketplaces"]}
        self.assertEqual(outputs["yandex_market"]["output_value"], "256 ГБ")
        self.assertEqual(outputs["ozon"]["output_value"], "256")
        self.assertEqual(outputs["ozon"]["status"], "ready")

    def test_product_parameter_flow_keeps_multiple_provider_bindings_for_one_pim_parameter(self) -> None:
        product = {
            "id": "product_phone",
            "category_id": "cat_phones",
            "sku_gt": "52462",
            "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Blue",
            "content": {
                "features": [
                    {"code": "brand", "name": "Бренд", "value": "Apple"},
                ],
            },
        }

        with (
            patch.object(parameter_flow, "load_catalog_nodes", return_value=[{"id": "cat_phones", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(
                parameter_flow,
                "load_attribute_mapping_doc",
                return_value={
                    "items": {
                        "cat_phones": {
                            "rows": [
                                {
                                    "catalog_name": "Бренд",
                                    "provider_map": {
                                        "yandex_market": {
                                            "id": "vendor",
                                            "name": "Производитель",
                                            "export": True,
                                            "bindings": [
                                                {"id": "brand", "name": "Бренд товара", "export": True},
                                            ],
                                        },
                                    },
                                }
                            ]
                        }
                    }
                },
            ),
            patch.object(
                parameter_flow,
                "load_attribute_value_refs_doc",
                return_value={
                    "items": {
                        "cat_phones": {
                            "catalog_params": {
                                "brand": {"catalog_name": "Бренд", "dict_id": "dict_brand"}
                            }
                        }
                    }
                },
            ),
            patch.object(
                parameter_flow,
                "provider_export_value_details",
                return_value={"value": "Apple", "mapped": True, "reason": "allowed_exact"},
            ),
        ):
            payload = parameter_flow.build_product_parameter_flow(product)

        row = payload["items"][0]
        outputs = [item for item in row["marketplaces"] if item["provider"] == "yandex_market"]
        self.assertEqual([item["target_id"] for item in outputs], ["vendor", "brand"])
        self.assertEqual([item["binding_index"] for item in outputs], [0, 1])
        self.assertEqual([item["primary"] for item in outputs], [True, False])

    def test_product_parameter_flow_uses_provider_specific_export_map_fixture(self) -> None:
        product = {
            "id": "product_phone",
            "category_id": "cat_phones",
            "sku_gt": "52462",
            "title": "Смартфон Apple iPhone 17 Pro Max 1 ТБ",
            "content": {
                "features": [
                    {"code": "memory", "name": "Встроенная память", "value": "1 ТБ"},
                ],
            },
        }
        dictionary = {
            "id": "dict_memory",
            "items": [{"value": "1 ТБ"}],
            "aliases": {},
            "meta": {
                "export_map": {
                    "ozon": {"1 тб": "1024"},
                    "yandex_market": {"1 тб": "1 ТБ"},
                },
                "source_reference": {
                    "ozon": {"allowed_values": ["512", "1024"]},
                    "yandex_market": {"allowed_values": ["512 ГБ", "1 ТБ"]},
                },
            },
        }

        with (
            patch.object(parameter_flow, "load_catalog_nodes", return_value=[{"id": "cat_phones", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(
                parameter_flow,
                "load_attribute_mapping_doc",
                return_value={
                    "items": {
                        "cat_phones": {
                            "rows": [
                                {
                                    "catalog_name": "Встроенная память",
                                    "provider_map": {
                                        "yandex_market": {"id": "ym_memory", "name": "Объем встроенной памяти", "export": True},
                                        "ozon": {"id": "oz_memory", "name": "Встроенная память", "export": True},
                                    },
                                }
                            ]
                        }
                    }
                },
            ),
            patch.object(
                parameter_flow,
                "load_attribute_value_refs_doc",
                return_value={
                    "items": {
                        "cat_phones": {
                            "catalog_params": {
                                "memory": {"catalog_name": "Встроенная память", "dict_id": "dict_memory"}
                            }
                        }
                    }
                },
            ),
            patch.object(value_mapping, "load_dict", return_value=deepcopy(dictionary)),
            patch.object(parameter_flow, "provider_export_value_details", side_effect=value_mapping.provider_export_value_details),
        ):
            payload = parameter_flow.build_product_parameter_flow(product)

        outputs = {item["provider"]: item for item in payload["items"][0]["marketplaces"]}
        self.assertEqual(outputs["ozon"]["output_value"], "1024")
        self.assertEqual(outputs["ozon"]["mapping_reason"], "export_map")
        self.assertEqual(outputs["yandex_market"]["output_value"], "1 ТБ")

    def test_dictionary_canonicalizes_competitor_explanatory_value(self) -> None:
        dictionary = {
            "id": "dict_степень_защиты",
            "items": [{"value": "IP48"}, {"value": "IP67"}, {"value": "IP68"}],
            "aliases": {},
            "meta": {
                "source_reference": {
                    "yandex_market": {
                        "allowed_values": ["IP48", "IP67", "IP68", "погружение в воду"],
                    },
                    "ozon": {"allowed_values": []},
                },
                "export_map": {},
            },
        }
        saved: dict[str, object] = {}

        with (
            patch.object(value_mapping, "load_dict", return_value=deepcopy(dictionary)),
            patch.object(value_mapping, "save_dict", side_effect=lambda doc: saved.update(deepcopy(doc))),
        ):
            canonical = value_mapping.canonicalize_dictionary_value(
                "dict_степень_защиты",
                "IP68 допускается погружение в воду на глубину до 6 метров",
            )
            details = value_mapping.provider_export_value_details("dict_степень_защиты", "yandex_market", canonical)

        self.assertEqual(canonical, "IP68")
        self.assertEqual(details["value"], "IP68")
        self.assertEqual(details["mapped"], True)
        self.assertEqual(saved["aliases"]["ip68 допускается погружение в воду на глубину до 6 метров"], "IP68")

    def test_value_details_blocks_only_uncovered_pim_values(self) -> None:
        dictionaries = {
            "items": [
                {
                    "id": "dict_memory",
                    "title": "Встроенная память",
                    "type": "select",
                    "items": [{"value": "256 ГБ"}, {"value": "512 ГБ"}],
                    "meta": {
                        "source_reference": {
                            "yandex_market": {
                                "kind": "ENUM",
                                "allowed_values": ["128 ГБ", "256 ГБ", "512 ГБ", "1 ТБ"],
                            }
                        },
                        "export_map": {},
                    },
                },
                {
                    "id": "dict_version",
                    "title": "Версия",
                    "type": "select",
                    "items": [{"value": "Global"}],
                    "meta": {
                        "source_reference": {
                            "yandex_market": {
                                "kind": "ENUM",
                                "allowed_values": ["EU", "RU"],
                            }
                        },
                        "export_map": {},
                    },
                },
                {
                    "id": "dict_empty",
                    "title": "Линейка",
                    "type": "select",
                    "items": [],
                    "meta": {
                        "source_reference": {
                            "yandex_market": {
                                "kind": "ENUM",
                                "allowed_values": ["iPad Air", "iPhone"],
                            }
                        },
                        "export_map": {},
                    },
                },
            ]
        }
        values_doc = {
            "items": {
                "cat-phone": {
                    "catalog_params": {
                        "memory": {
                            "catalog_name": "Встроенная память",
                            "dict_id": "dict_memory",
                        },
                        "version": {
                            "catalog_name": "Версия",
                            "dict_id": "dict_version",
                        },
                        "line": {
                            "catalog_name": "Линейка",
                            "dict_id": "dict_empty",
                        },
                    }
                }
            }
        }
        products = [
            {
                "id": "product_phone_1",
                "sku_gt": "52420",
                "title": "iPhone 17 Pro Max 256",
                "category_id": "cat-phone",
                "content": {
                    "features": [
                        {
                            "code": "memory",
                            "name": "Встроенная память",
                            "value": "256 ГБ",
                            "source_values": {
                                "competitor": {
                                    "store77": {
                                        "raw_value": "256Gb",
                                        "resolved_value": "256 ГБ",
                                        "canonical_value": "256 ГБ",
                                    }
                                },
                                "yandex_market": {
                                    "ym": {
                                        "raw_value": "256 ГБ",
                                        "resolved_value": "256 ГБ",
                                    }
                                },
                            },
                        }
                    ]
                },
            }
        ]

        with (
            patch.object(marketplace_mapping, "_value_details_cache_bucket", return_value={}),
            patch.object(marketplace_mapping, "_load_catalog_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(marketplace_mapping, "_catalog_rows", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(marketplace_mapping, "_catalog_parent_map", return_value={}),
            patch.object(marketplace_mapping, "_tree_maps", return_value=({}, {})),
            patch.object(marketplace_mapping, "_load_attr_values_dict_doc", return_value=deepcopy(values_doc)),
            patch.object(marketplace_mapping, "load_dictionaries_db", return_value=deepcopy(dictionaries)),
            patch.object(marketplace_mapping, "load_dict", side_effect=lambda dict_id: next(d for d in dictionaries["items"] if d["id"] == dict_id)),
            patch.object(marketplace_mapping, "query_products_full", return_value=deepcopy(products)),
            patch.object(
                marketplace_mapping,
                "provider_export_value_details",
                side_effect=lambda dict_id, provider, value: {
                    "value": str(value),
                    "mapped": dict_id == "dict_memory",
                    "reason": "allowed_exact" if dict_id == "dict_memory" else "value_missing",
                },
            ),
        ):
            response = marketplace_mapping.mapping_value_details("cat-phone")

        by_title = {item["title"]: item for item in response["items"]}
        self.assertFalse(by_title["Встроенная память"]["needs_value_mapping"])
        memory_provider = by_title["Встроенная память"]["providers"][0]
        self.assertEqual(memory_provider["covered_count"], 2)
        self.assertEqual(memory_provider["missing_count"], 0)
        self.assertEqual(by_title["Встроенная память"]["pim_values"], ["256 ГБ", "512 ГБ"])
        self.assertEqual(by_title["Встроенная память"]["source_evidence"][0]["raw_value"], "256Gb")
        self.assertEqual(by_title["Встроенная память"]["source_evidence"][0]["source_id"], "store77")
        self.assertEqual(by_title["Встроенная память"]["source_evidence"][0]["sku_gt"], "52420")
        self.assertEqual(memory_provider["allowed_values"], ["128 ГБ", "256 ГБ", "512 ГБ", "1 ТБ"])
        self.assertEqual(memory_provider["missing_values"], [])
        self.assertTrue(by_title["Версия"]["needs_value_mapping"])
        version_provider = by_title["Версия"]["providers"][0]
        self.assertEqual(version_provider["missing_sample"], ["Global"])
        self.assertEqual(version_provider["missing_values"], ["Global"])
        self.assertFalse(by_title["Линейка"]["needs_value_mapping"])

    def test_value_details_treats_provider_numeric_kind_as_unit_check_not_dictionary_mapping(self) -> None:
        dictionaries = {
            "items": [
                {
                    "id": "dict_weight",
                    "title": "Вес упаковки, г",
                    "type": "select",
                    "items": [{"value": "240"}],
                    "meta": {
                        "source_reference": {
                            "ozon": {
                                "kind": "Decimal",
                                "allowed_values": ["100", "200", "240"],
                            }
                        },
                        "export_map": {},
                    },
                }
            ]
        }
        values_doc = {
            "items": {
                "cat-phone": {
                    "catalog_params": {
                        "weight": {
                            "catalog_name": "Вес упаковки, г",
                            "dict_id": "dict_weight",
                        }
                    }
                }
            }
        }

        with (
            patch.object(marketplace_mapping, "_value_details_cache_bucket", return_value={}),
            patch.object(marketplace_mapping, "_load_catalog_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(marketplace_mapping, "_catalog_rows", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(marketplace_mapping, "_catalog_parent_map", return_value={}),
            patch.object(marketplace_mapping, "_tree_maps", return_value=({}, {})),
            patch.object(marketplace_mapping, "_load_attr_values_dict_doc", return_value=deepcopy(values_doc)),
            patch.object(marketplace_mapping, "load_dictionaries_db", return_value=deepcopy(dictionaries)),
            patch.object(marketplace_mapping, "load_dict", side_effect=lambda dict_id: next(d for d in dictionaries["items"] if d["id"] == dict_id)),
            patch.object(marketplace_mapping, "query_products_full", return_value=[]),
        ):
            response = marketplace_mapping.mapping_value_details("cat-phone")

        item = response["items"][0]
        provider = item["providers"][0]
        self.assertEqual(item["value_mode"], "number")
        self.assertFalse(item["needs_value_mapping"])
        self.assertTrue(item["needs_unit_check"])
        self.assertEqual(provider["mode"], "number")
        self.assertFalse(provider["needs_mapping"])
        self.assertTrue(provider["needs_unit_check"])

    def test_value_ai_suggest_applies_valid_allowed_pairs(self) -> None:
        dictionary = {
            "id": "dict_version",
            "title": "Версия",
            "type": "select",
            "items": [{"value": "Global"}, {"value": "EU"}],
            "meta": {"export_map": {}},
        }
        values_doc = {
            "items": {
                "cat-phone": {
                    "catalog_params": {
                        "version": {
                            "catalog_name": "Версия",
                            "dict_id": "dict_version",
                            "bindings": {
                                "yandex_market": {
                                    "kind": "ENUM",
                                    "values": ["EU", "GLOBAL"],
                                }
                            },
                        }
                    }
                }
            }
        }
        saved: dict[str, object] = {}

        async def suggest(**_kwargs):
            return [
                {"canonical": "Global", "output": "GLOBAL", "confidence": 0.96, "reason": "same region"},
                {"canonical": "EU", "output": "NOT_ALLOWED", "confidence": 0.99, "reason": "invalid output"},
            ]

        with (
            patch.dict(os.environ, {"PIM_ENABLE_AI": "1"}),
            patch.object(marketplace_mapping, "_value_details_cache_bucket", return_value={}),
            patch.object(marketplace_mapping, "_load_catalog_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(marketplace_mapping, "_catalog_rows", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(marketplace_mapping, "load_dict", return_value=deepcopy(dictionary)),
            patch.object(marketplace_mapping, "save_dict", side_effect=lambda doc: saved.update(deepcopy(doc))),
            patch.object(marketplace_mapping, "_load_attr_values_dict_doc", return_value=deepcopy(values_doc)),
            patch.object(marketplace_mapping, "provider_export_value_details", return_value={"value": "", "mapped": False, "reason": "value_missing"}),
            patch.object(marketplace_mapping, "_ollama_suggest_value_pairs", side_effect=suggest),
        ):
            response = asyncio.run(
                marketplace_mapping.mapping_value_ai_suggest(
                    "cat-phone",
                    "dict_version",
                    marketplace_mapping.ValueAiSuggestReq(provider="yandex_market", apply=True),
                )
            )

        self.assertEqual(response["summary"]["engine"], "ollama")
        self.assertEqual(response["summary"]["ai_suggestions"], 1)
        self.assertEqual(response["suggestions"][0]["canonical"], "Global")
        self.assertEqual(saved["meta"]["export_map"]["yandex_market"]["global"], "GLOBAL")
        self.assertEqual(saved["meta"]["export_map"]["yandex_market"]["eu"], "EU")

    def test_value_ai_suggest_uses_category_allowed_values_when_dictionary_has_no_reference(self) -> None:
        dictionary = {
            "id": "dict_version",
            "title": "Версия",
            "type": "select",
            "items": [{"value": "Global"}],
            "meta": {"export_map": {}},
        }
        values_doc = {
            "items": {
                "cat-phone": {
                    "catalog_params": {
                        "version": {
                            "catalog_name": "Версия",
                            "dict_id": "dict_version",
                            "bindings": {
                                "yandex_market": {
                                    "kind": "ENUM",
                                    "values": ["GLOBAL", "RU"],
                                }
                            },
                        }
                    }
                }
            }
        }
        saved: dict[str, object] = {}

        async def suggest(**_kwargs):
            return [{"canonical": "Global", "output": "GLOBAL", "confidence": 0.96, "reason": "same region"}]

        with (
            patch.dict(os.environ, {"PIM_ENABLE_AI": "1"}),
            patch.object(marketplace_mapping, "_value_details_cache_bucket", return_value={}),
            patch.object(marketplace_mapping, "_load_catalog_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(marketplace_mapping, "_catalog_rows", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(marketplace_mapping, "load_dict", return_value=deepcopy(dictionary)),
            patch.object(marketplace_mapping, "save_dict", side_effect=lambda doc: saved.update(deepcopy(doc))),
            patch.object(marketplace_mapping, "_load_attr_values_dict_doc", return_value=deepcopy(values_doc)),
            patch.object(marketplace_mapping, "provider_export_value_details", return_value={"value": "Global", "mapped": True, "reason": "free_text"}),
            patch.object(marketplace_mapping, "_ollama_suggest_value_pairs", side_effect=suggest),
        ):
            response = asyncio.run(
                marketplace_mapping.mapping_value_ai_suggest(
                    "cat-phone",
                    "dict_version",
                    marketplace_mapping.ValueAiSuggestReq(provider="yandex_market", apply=True),
                )
            )

        self.assertEqual(response["summary"]["engine"], "ollama")
        self.assertEqual(response["summary"]["missing_values"], 1)
        self.assertEqual(saved["meta"]["export_map"]["yandex_market"]["global"], "GLOBAL")

    def test_value_export_map_patch_invalidates_category_value_cache(self) -> None:
        dictionary = {
            "id": "dict_version",
            "title": "Версия",
            "type": "select",
            "items": [{"value": "Global"}],
            "meta": {"export_map": {}},
        }
        saved: dict[str, object] = {}
        cache: dict[str, object] = {"cat-phone": {"stale": True}}

        with (
            patch.object(marketplace_mapping, "load_dict", return_value=deepcopy(dictionary)),
            patch.object(marketplace_mapping, "save_dict", side_effect=lambda doc: saved.update(deepcopy(doc))),
            patch.object(marketplace_mapping, "_value_details_cache_bucket", return_value=cache),
        ):
            response = marketplace_mapping.mapping_value_export_map_patch(
                "cat-phone",
                "dict_version",
                marketplace_mapping.ValueExportMapPatchReq(
                    provider="yandex_market",
                    canonical_value="Global",
                    output_value="GLOBAL",
                ),
            )

        self.assertTrue(response["ok"])
        self.assertEqual(saved["meta"]["export_map"]["yandex_market"]["global"], "GLOBAL")
        self.assertNotIn("cat-phone", cache)

    def test_new_category_without_model_can_create_draft_template(self) -> None:
        db = {"templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}}
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        with (
            patch.object(templates, "load_templates_db", return_value=deepcopy(db)),
            patch.object(templates, "save_templates_db", side_effect=save),
            patch.object(templates, "ensure_global_attribute", side_effect=lambda title, type_, code, scope: {"id": f"attr-{code}", "dict_id": f"dict-{code}"}),
            patch.object(templates, "new_id", return_value="tpl-draft-quest"),
            patch.object(templates, "now_iso", return_value="2026-04-27T00:00:00+00:00"),
        ):
            response = templates.create_for_category("cat-vr", {"name": "Draft: VR headsets"})

        self.assertEqual(response["template"]["id"], "tpl-draft-quest")
        self.assertEqual(response["template"]["category_id"], "cat-vr")
        self.assertIn("tpl-draft-quest", saved["templates"])
        self.assertEqual(saved["category_to_template"]["cat-vr"], "tpl-draft-quest")
        self.assertEqual(saved["category_to_templates"]["cat-vr"], ["tpl-draft-quest"])
        self.assertGreater(len(saved["attributes"]["tpl-draft-quest"]), 0)

    def test_approved_model_product_creation_preserves_skeleton_and_variant_group(self) -> None:
        existing_products: list[dict[str, object]] = []
        saved_products: list[dict[str, object]] = []

        def save_product(product):
            saved = deepcopy(product)
            saved_products.append(saved)
            existing_products.append(saved)
            return saved

        with (
            patch.object(products_service, "query_products_full", side_effect=lambda: deepcopy(existing_products)),
            patch.object(products_service, "allocate_sku_pairs_service", side_effect=[
                {"items": [{"sku_pim": "1001", "sku_gt": "51001"}]},
                {"items": [{"sku_pim": "1002", "sku_gt": "51002"}]},
            ]),
            patch.object(products_service, "upsert_product_item", side_effect=save_product),
        ):
            first = products_service.create_product_service(
                {
                    "category_id": "cat-vr",
                    "type": "multi",
                    "title": "Meta Quest 3 128GB",
                    "group_id": "group-quest-3",
                    "selected_params": ["brand", "memory", "color"],
                    "feature_params": ["memory", "resolution"],
                    "exports_enabled": {"yandex_market": True, "ozon": True},
                }
            )
            second = products_service.create_product_service(
                {
                    "category_id": "cat-vr",
                    "type": "multi",
                    "title": "Meta Quest 3 256GB",
                    "group_id": "group-quest-3",
                    "selected_params": ["brand", "memory", "color"],
                    "feature_params": ["memory", "resolution"],
                    "exports_enabled": {"yandex_market": True, "ozon": True},
                }
            )

        self.assertEqual(first["group_id"], "group-quest-3")
        self.assertEqual(second["group_id"], "group-quest-3")
        self.assertEqual(first["selected_params"], ["brand", "memory", "color"])
        self.assertEqual(first["feature_params"], ["memory", "resolution"])
        self.assertEqual(first["exports_enabled"], {"yandex_market": True, "ozon": True})
        self.assertNotEqual(first["sku_gt"], second["sku_gt"])
        self.assertEqual(len(saved_products), 2)

    def test_product_family_creation_is_single_backend_operation(self) -> None:
        saved_groups: list[dict[str, object]] = []
        saved_products: list[dict[str, object]] = []

        def save_groups(doc):
            saved_groups.append(deepcopy(doc))

        def save_products(items):
            saved_products.extend(deepcopy(items))
            return deepcopy(items)

        with (
            patch.object(products_service, "query_products_full", return_value=[]),
            patch.object(products_service, "allocate_next_product_identity", return_value={"product_id": "product_10", "next_sku_pim": "100", "next_sku_gt": "50100"}),
            patch.object(products_service, "load_product_groups_doc", return_value={"version": 1, "items": []}),
            patch.object(products_service, "save_product_groups_doc", side_effect=save_groups),
            patch.object(products_service, "bulk_upsert_product_items", side_effect=save_products),
        ):
            response = products_service.create_product_family_service(
                {
                    "category_id": "cat-smartphones",
                    "type": "multi",
                    "title": "Apple iPhone 17 Pro",
                    "selected_params": ["memory", "color"],
                    "variants": [
                        {
                            "title": "Apple iPhone 17 Pro 256GB Blue",
                            "sku_pim": "100",
                            "sku_gt": "50100",
                            "content": {"features": [{"code": "memory", "name": "Память", "value": "256 ГБ"}]},
                        },
                        {
                            "title": "Apple iPhone 17 Pro 512GB Blue",
                            "sku_pim": "101",
                            "sku_gt": "50101",
                            "content": {"features": [{"code": "memory", "name": "Память", "value": "512 ГБ"}]},
                        },
                    ],
                }
            )

        self.assertTrue(response["ok"])
        self.assertEqual(response["group"]["id"], "group_1")
        self.assertEqual(response["count"], 2)
        self.assertEqual([item["id"] for item in saved_products], ["product_10", "product_11"])
        self.assertEqual({item["group_id"] for item in saved_products}, {"group_1"})
        self.assertEqual(saved_products[0]["content"]["features"][0]["value"], "256 ГБ")
        self.assertEqual(saved_groups[-1]["items"][0]["variant_param_ids"], ["memory", "color"])

    def test_product_group_family_facts_separates_shared_values_and_variant_overrides(self) -> None:
        products_payload = [
            {
                "id": "p1",
                "title": "iPhone 17 Pro Max 256 Orange eSIM",
                "sku_gt": "52420",
                "group_id": "group-phone",
                "content": {
                    "features": [
                        {"code": "brand", "name": "Бренд", "value": "Apple"},
                        {"code": "memory", "name": "Встроенная память", "value": "256 ГБ"},
                        {"code": "color", "name": "Цвет", "value": "Оранжевый"},
                    ]
                },
            },
            {
                "id": "p2",
                "title": "iPhone 17 Pro Max 512 Orange eSIM",
                "sku_gt": "52421",
                "group_id": "group-phone",
                "content": {
                    "features": [
                        {"code": "brand", "name": "Бренд", "value": "Apple"},
                        {"code": "memory", "name": "Встроенная память", "value": "512 ГБ"},
                        {"code": "color", "name": "Цвет", "value": "Оранжевый"},
                    ]
                },
            },
        ]

        with (
            patch.object(product_groups, "load_product_groups_doc", return_value={"items": [{"id": "group-phone", "name": "iPhone 17 Pro Max", "variant_param_ids": ["memory"]}]}),
            patch.object(product_groups, "query_products_full", return_value=deepcopy(products_payload)),
        ):
            response = product_groups.group_family_facts("group-phone")

        self.assertEqual(response["summary"]["products_count"], 2)
        shared_by_code = {item["code"]: item for item in response["shared_facts"]}
        override_by_code = {item["code"]: item for item in response["variant_overrides"]}
        self.assertEqual(shared_by_code["brand"]["value"], "Apple")
        self.assertEqual(shared_by_code["color"]["value"], "Оранжевый")
        self.assertEqual([item["value"] for item in override_by_code["memory"]["values"]], ["256 ГБ", "512 ГБ"])
        self.assertTrue(override_by_code["memory"]["selected_variant_axis"])

    def test_competitor_candidate_approval_confirms_one_and_rejects_siblings(self) -> None:
        db = {
            "version": 2,
            "templates": {},
            "categories": {},
            "discovery": {
                "candidates": {
                    "candidate-a": {
                        "id": "candidate-a",
                        "product_id": "product_1",
                        "source_id": "store77",
                        "url": "https://store77.net/a",
                        "status": "needs_review",
                        "match_group_key": "iphone-16-pro-128-natural",
                        "last_seen_at": "2026-04-27T00:00:00+00:00",
                    },
                    "candidate-b": {
                        "id": "candidate-b",
                        "product_id": "product_1",
                        "source_id": "store77",
                        "url": "https://store77.net/b",
                        "status": "needs_review",
                        "match_group_key": "iphone-16-pro-128-natural",
                        "last_seen_at": "2026-04-27T00:00:00+00:00",
                    },
                },
                "links": {},
                "runs": {},
            },
        }
        saved: dict[str, object] = {}
        saved_channel_links: list[dict[str, object]] = []

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        with (
            patch.object(competitor_mapping, "load_competitor_mapping_db", return_value=deepcopy(db)),
            patch.object(competitor_mapping, "save_competitor_mapping_db", side_effect=save),
            patch.object(competitor_mapping, "upsert_pim_channel_link", side_effect=lambda row: saved_channel_links.append(deepcopy(row)) or row),
            patch.object(competitor_mapping, "now_iso", return_value="2026-04-27T12:00:00+00:00"),
        ):
            response = competitor_mapping.moderate_candidate("candidate-a", {"action": "approve"})

        candidates = saved["discovery"]["candidates"]
        self.assertEqual(response["candidate"]["status"], "approved")
        self.assertEqual(candidates, {})
        by_id = {row["link_id"]: row for row in saved_channel_links}
        self.assertEqual(by_id["candidate-a"]["status"], "confirmed")
        self.assertEqual(by_id["candidate-b"]["status"], "rejected")
        self.assertEqual(by_id["candidate-b"]["payload"]["rejection_reason"], "sibling_not_selected")
        self.assertEqual(by_id["product_1:store77"]["url"], "https://store77.net/a")

    def test_existing_catalog_enrichment_uses_confirmed_competitor_links(self) -> None:
        db = {
            "version": 2,
            "templates": {},
            "categories": {},
            "discovery": {
                "candidates": {},
                "links": {
                    "product_1:store77": {
                        "id": "product_1:store77",
                        "product_id": "product_1",
                        "source_id": "store77",
                        "url": "https://store77.net/meta-quest-3-128",
                        "status": "confirmed",
                    }
                },
                "runs": {},
            },
        }
        product = {
            "id": "product_1",
            "title": "Meta Quest 3 128GB",
            "content": {"features": [], "description": "", "links": []},
        }
        saved_db: dict[str, object] = {}
        saved_channel_links: list[dict[str, object]] = []

        async def fake_extract(url):
            self.assertEqual(url, "https://store77.net/meta-quest-3-128")
            return {
                "ok": True,
                "source_id": "store77",
                "title": "Meta Quest 3 128GB",
                "description": "VR headset with 128GB storage",
                "images": ["https://store77.net/images/meta-quest-3-128.jpg"],
                "specs": {"memory": "128GB", "brand": "Meta"},
            }

        def save(next_db):
            saved_db.clear()
            saved_db.update(deepcopy(next_db))

        with (
            patch.object(competitor_mapping, "load_competitor_mapping_db", return_value=deepcopy(db)),
            patch.object(competitor_mapping, "save_competitor_mapping_db", side_effect=save),
            patch.object(competitor_mapping, "query_products_full", return_value=[deepcopy(product)]),
            patch.object(competitor_mapping, "upsert_product_item", side_effect=lambda p: deepcopy(p)),
            patch.object(competitor_mapping, "upsert_pim_channel_link", side_effect=lambda row: saved_channel_links.append(deepcopy(row)) or row),
            patch.object(competitor_mapping, "extract_competitor_content", side_effect=fake_extract),
            patch.object(competitor_mapping, "_import_competitor_image_to_storage", return_value={
                "url": "/api/uploads/media_images/product_1/competitors/store77/meta-quest-3-128.jpg",
                "external_url": "https://store77.net/images/meta-quest-3-128.jpg",
                "content_type": "image/jpeg",
                "size": 123,
                "storage": "s3",
            }),
            patch.object(competitor_mapping, "now_iso", return_value="2026-04-27T12:00:00+00:00"),
        ):
            response = asyncio.run(competitor_mapping.enrich_product_from_confirmed_competitors("product_1"))

        self.assertEqual(response["ok"], True)
        self.assertEqual(response["enriched_sources"], ["store77"])
        self.assertIn("product", response)
        content = response["product"]["content"]
        self.assertEqual(content["description"], "VR headset with 128GB storage")
        self.assertEqual(content["media_images"][0]["url"], "/api/uploads/media_images/product_1/competitors/store77/meta-quest-3-128.jpg")
        self.assertEqual(content["media_images"][0]["external_url"], "https://store77.net/images/meta-quest-3-128.jpg")
        self.assertEqual(content["media_images"][0]["storage"], "s3")
        self.assertEqual(content["media_images"][0]["role"], "gallery")
        self.assertEqual(content["media_images"][0]["selected"], True)
        self.assertEqual(content["media_images"][0]["status"], "ready")
        self.assertEqual(content["competitor_links"]["store77"]["url"], "https://store77.net/meta-quest-3-128")
        self.assertEqual(content["competitor_links"]["store77"]["status"], "confirmed")
        self.assertEqual(content["source_values"]["media_images"]["store77"]["count"], 1)
        self.assertTrue(
            any((row.get("payload") or {}).get("last_enriched_at") == "2026-04-27T12:00:00+00:00" for row in saved_channel_links)
        )
        self.assertEqual(saved_db["discovery"]["links"], {})

    def test_product_competitor_enrichment_keeps_external_media_for_review_when_import_fails(self) -> None:
        product = {
            "id": "product_1",
            "title": "Meta Quest 3 128GB",
            "content": {"features": [], "description": ""},
        }

        with (
            patch.object(competitor_mapping, "_import_competitor_image_to_storage", return_value=None),
            patch.object(competitor_mapping, "now_iso", return_value="2026-04-27T12:00:00+00:00"),
        ):
            result = asyncio.run(
                competitor_mapping._merge_competitor_content_into_product(
                    product,
                    extracted={
                        "restore": {
                            "ok": True,
                            "specs": {},
                            "description": "",
                            "images": ["https://re-store.ru/images/meta-quest-3-128.jpg"],
                        }
                    },
                    links={"restore": {"url": "https://re-store.ru/catalog/meta-quest-3-128/"}},
                )
            )

        media = result["product"]["content"]["media_images"]
        self.assertEqual(media[0]["url"], "https://re-store.ru/images/meta-quest-3-128.jpg")
        self.assertEqual(media[0]["external_url"], "https://re-store.ru/images/meta-quest-3-128.jpg")
        self.assertEqual(media[0]["source"], "restore")
        self.assertEqual(media[0]["source_type"], "external_hotlink")
        self.assertEqual(media[0]["status"], "needs_review")
        self.assertEqual(media[0]["selected"], True)
        self.assertEqual(result["product"]["content"]["source_values"]["media_images"]["restore"]["count"], 1)

    def test_product_enrich_job_runs_even_when_media_already_exists(self) -> None:
        saved_jobs: list[dict] = []
        called: list[str] = []

        async def fake_enrich(product_id: str):
            called.append(product_id)
            return {
                "ok": True,
                "product_id": product_id,
                "product": {"id": product_id, "content": {"media_images": [{"url": "https://cdn.example.test/old.jpg"}]}},
                "enriched_sources": ["store77"],
                "matched_count": 3,
                "unmatched_count": 1,
                "errors": [],
            }

        with (
            patch.object(competitor_mapping, "get_pim_workflow_run", return_value={"id": "job_1", "job_id": "job_1", "product_id": "product_1"}),
            patch.object(competitor_mapping, "upsert_pim_workflow_run", side_effect=lambda row, workflow=None: saved_jobs.append(deepcopy(row)) or row),
            patch.object(competitor_mapping, "enrich_product_from_confirmed_competitors", side_effect=fake_enrich),
            patch.object(competitor_mapping, "now_iso", return_value="2026-05-27T10:00:00+00:00"),
        ):
            asyncio.run(competitor_mapping._run_product_enrich_job("job_1", "product_1"))

        self.assertEqual(called, ["product_1"])
        self.assertEqual(saved_jobs[-1]["status"], "completed")
        self.assertEqual(saved_jobs[-1]["matched_count"], 3)
        self.assertEqual(saved_jobs[-1]["media_images_count"], 1)

    def test_product_enrich_job_queue_reuses_active_job(self) -> None:
        tasks = BackgroundTasks()
        active_job = {
            "id": "job_existing",
            "job_id": "job_existing",
            "run_id": "job_existing",
            "product_id": "product_1",
            "status": "running",
        }

        with (
            patch.object(competitor_mapping, "list_pim_workflow_runs", return_value=[active_job]),
            patch.object(competitor_mapping, "upsert_pim_workflow_run") as upsert,
        ):
            job = competitor_mapping._queue_product_enrich_job("product_1", tasks)

        self.assertEqual(job["job_id"], "job_existing")
        self.assertEqual(len(tasks.tasks), 0)
        upsert.assert_not_called()

    def test_catalog_import_uses_confirmed_partner_links_before_export(self) -> None:
        req = CatalogImportRunReq.model_validate(
            {
                "selection": {"node_ids": [], "product_ids": ["product_1"], "include_descendants": False},
                "use_yandex_market": False,
                "use_competitors": True,
                "limit": 10,
            }
        )
        product = {
            "id": "product_1",
            "title": "Meta Quest 3 128GB",
            "category_id": "cat-vr",
            "content": {"features": [], "description": "", "links": []},
        }
        competitor_db = {
            "version": 2,
            "templates": {},
            "categories": {},
            "discovery": {
                "candidates": {},
                "links": {
                    "product_1:store77": {
                        "id": "product_1:store77",
                        "product_id": "product_1",
                        "source_id": "store77",
                        "url": "https://store77.net/meta-quest-3-128",
                        "status": "confirmed",
                    }
                },
                "runs": {},
            },
        }
        saved_products: list[dict[str, object]] = []

        async def fake_extract(url, **_kwargs):
            self.assertEqual(url, "https://store77.net/meta-quest-3-128")
            return {
                "description": "Partner description",
                "images": ["https://store77.net/images/meta-quest-3-128.jpg"],
                "specs": {},
            }

        with (
            patch.object(catalog_exchange, "_resolve_products", return_value=[deepcopy(product)]),
            patch.object(catalog_exchange, "_load_products", return_value=[deepcopy(product)]),
            patch.object(catalog_exchange, "_load_nodes", return_value=[]),
            patch.object(catalog_exchange, "_resolve_template_id", return_value="tpl-vr"),
            patch.object(catalog_exchange, "load_competitor_mapping_db", return_value=deepcopy(competitor_db)),
            patch.object(catalog_exchange, "_extract_competitor_content_with_retry", side_effect=fake_extract),
            patch.object(catalog_exchange, "_fetch_store77_images_with_browser", return_value={}),
            patch.object(catalog_exchange, "_import_competitor_image_to_storage", return_value={
                "url": "/api/uploads/media_images/product_1/competitors/store77/meta-quest-3-128.jpg",
                "external_url": "https://store77.net/images/meta-quest-3-128.jpg",
                "content_type": "image/jpeg",
                "size": 123,
                "storage": "s3",
            }),
            patch.object(catalog_exchange, "_fetch_store77_images_with_browser", return_value={}),
            patch.object(catalog_exchange, "_save_products", side_effect=lambda items: saved_products.extend(deepcopy(items))),
            patch.object(catalog_exchange, "_load_runs", return_value={"runs": {}}),
            patch.object(catalog_exchange, "_save_runs", side_effect=lambda _path, _doc: None),
            patch.object(catalog_exchange, "_now_iso", return_value="2026-04-27T12:00:00+00:00"),
        ):
            response = asyncio.run(catalog_exchange.run_catalog_import(req))

        self.assertEqual(response["ok"], True)
        self.assertEqual(response["import_overview"]["images_ready"], 1)
        self.assertEqual(response["import_overview"]["with_competitor_media"], 1)
        self.assertEqual(saved_products[0]["content"]["media_images"][0]["url"], "/api/uploads/media_images/product_1/competitors/store77/meta-quest-3-128.jpg")
        self.assertEqual(saved_products[0]["content"]["media_images"][0]["external_url"], "https://store77.net/images/meta-quest-3-128.jpg")
        self.assertEqual(saved_products[0]["content"]["media_images"][0]["source"], "store77")
        self.assertEqual(saved_products[0]["content"]["media_images"][0]["storage"], "s3")

    def test_export_preparation_enriches_media_from_high_confidence_competitor_link(self) -> None:
        product = {
            "id": "product_1",
            "title": "iPhone 17 Pro Max 256Gb Orange",
            "category_id": "cat-phone",
            "content": {"features": [], "description": ""},
        }
        saved_products: list[dict[str, object]] = []

        async def fake_extract(url, **_kwargs):
            self.assertEqual(url, "https://store77.net/iphone-orange")
            return {
                "description": "",
                "images": ["https://store77.net/images/iphone-orange.jpg"],
                "specs": {},
            }

        with (
            patch.dict(os.environ, {"EXPORT_CANDIDATE_MEDIA_ENRICH_LIMIT": "50"}),
            patch.object(catalog_exchange, "_load_nodes", return_value=[]),
            patch.object(catalog_exchange, "_resolve_template_id", return_value="tpl-phone"),
            patch.object(catalog_exchange, "_template_attr_defs", return_value={}),
            patch.object(catalog_exchange, "list_pim_channel_links", return_value=[
                {
                    "scope": "competitor_product",
                    "entity_type": "product",
                    "entity_id": "product_1",
                    "provider": "store77",
                    "status": "confirmed",
                    "url": "https://store77.net/iphone-orange",
                    "score": 0.94,
                }
            ]),
            patch.object(catalog_exchange, "_extract_competitor_content_with_retry", side_effect=fake_extract),
            patch.object(catalog_exchange, "_import_competitor_image_to_storage", return_value={
                "url": "/api/uploads/media_images/product_1/competitors/store77/iphone-orange.jpg",
                "external_url": "https://store77.net/images/iphone-orange.jpg",
                "content_type": "image/jpeg",
                "size": 123,
                "storage": "s3",
            }),
            patch.object(catalog_exchange, "_save_products", side_effect=lambda items: saved_products.extend(deepcopy(items))),
            patch.object(catalog_exchange, "_now_iso", return_value="2026-05-23T12:00:00+00:00"),
        ):
            changed = asyncio.run(catalog_exchange._enrich_export_products_from_candidate_media([product]))

        self.assertEqual(changed, {"product_1"})
        self.assertEqual(saved_products[0]["content"]["media_images"][0]["url"], "/api/uploads/media_images/product_1/competitors/store77/iphone-orange.jpg")
        self.assertEqual(saved_products[0]["content"]["media_images"][0]["source"], "store77")
        self.assertEqual(saved_products[0]["content"]["source_values"]["media_images"]["store77"]["count"], 1)

    def test_export_preparation_limits_competitor_media_from_one_source_card(self) -> None:
        product = {
            "id": "product_1",
            "title": "iPhone 17 Pro Max 256Gb Orange",
            "category_id": "cat-phone",
            "content": {"features": [], "description": ""},
        }
        saved_products: list[dict[str, object]] = []

        async def fake_extract(url, **_kwargs):
            return {
                "description": "",
                "images": [f"https://store77.net/images/iphone-orange-{idx}.jpg" for idx in range(15)],
                "specs": {},
            }

        with (
            patch.dict(os.environ, {"EXPORT_CANDIDATE_MEDIA_ENRICH_LIMIT": "50", "COMPETITOR_MEDIA_PER_SOURCE_LIMIT": "4"}),
            patch.object(catalog_exchange, "_load_nodes", return_value=[]),
            patch.object(catalog_exchange, "_resolve_template_id", return_value="tpl-phone"),
            patch.object(catalog_exchange, "_template_attr_defs", return_value={}),
            patch.object(catalog_exchange, "list_pim_channel_links", return_value=[
                {
                    "scope": "competitor_product",
                    "entity_type": "product",
                    "entity_id": "product_1",
                    "provider": "store77",
                    "status": "confirmed",
                    "url": "https://store77.net/iphone-orange",
                    "score": 0.94,
                }
            ]),
            patch.object(catalog_exchange, "_extract_competitor_content_with_retry", side_effect=fake_extract),
            patch.object(catalog_exchange, "_import_competitor_image_to_storage", side_effect=lambda image_url, **_kwargs: {
                "url": image_url,
                "external_url": image_url,
                "content_type": "image/jpeg",
                "size": 123,
                "storage": "s3",
            }),
            patch.object(catalog_exchange, "_save_products", side_effect=lambda items: saved_products.extend(deepcopy(items))),
            patch.object(catalog_exchange, "_now_iso", return_value="2026-05-23T12:00:00+00:00"),
        ):
            changed = asyncio.run(catalog_exchange._enrich_export_products_from_candidate_media([product]))

        self.assertEqual(changed, {"product_1"})
        self.assertEqual(len(saved_products[0]["content"]["media_images"]), 4)

    def test_export_preparation_does_not_enrich_media_from_unconfirmed_candidate_link(self) -> None:
        product = {
            "id": "product_1",
            "title": "iPhone 17 Pro Max 256Gb Orange",
            "category_id": "cat-phone",
            "content": {"features": [], "description": ""},
        }

        with (
            patch.dict(os.environ, {"EXPORT_CANDIDATE_MEDIA_ENRICH_LIMIT": "50"}),
            patch.object(catalog_exchange, "_load_nodes", return_value=[]),
            patch.object(catalog_exchange, "_resolve_template_id", return_value="tpl-phone"),
            patch.object(catalog_exchange, "_template_attr_defs", return_value={}),
            patch.object(catalog_exchange, "list_pim_channel_links", return_value=[
                {
                    "scope": "competitor_product",
                    "entity_type": "product",
                    "entity_id": "product_1",
                    "provider": "store77",
                    "status": "candidate",
                    "url": "https://store77.net/iphone-orange",
                    "score": 0.94,
                }
            ]),
            patch.object(catalog_exchange, "_extract_competitor_content_with_retry") as extract_mock,
            patch.object(catalog_exchange, "_save_products") as save_mock,
        ):
            changed = asyncio.run(catalog_exchange._enrich_export_products_from_candidate_media([product]))

        self.assertEqual(changed, set())
        extract_mock.assert_not_called()
        save_mock.assert_not_called()

    def test_export_preparation_keeps_competitor_media_url_when_storage_import_fails(self) -> None:
        product = {
            "id": "product_1",
            "title": "iPhone 17 Pro Max 1Tb Silver",
            "category_id": "cat-phone",
            "content": {"features": [], "description": ""},
        }
        saved_products: list[dict[str, object]] = []

        async def fake_extract(url, **_kwargs):
            return {
                "description": "",
                "images": ["https://store77.net/images/iphone-silver.png"],
                "specs": {},
            }

        with (
            patch.dict(os.environ, {"EXPORT_CANDIDATE_MEDIA_ENRICH_LIMIT": "50"}),
            patch.object(catalog_exchange, "_load_nodes", return_value=[]),
            patch.object(catalog_exchange, "_resolve_template_id", return_value="tpl-phone"),
            patch.object(catalog_exchange, "_template_attr_defs", return_value={}),
            patch.object(catalog_exchange, "list_pim_channel_links", return_value=[
                {
                    "scope": "competitor_product",
                    "entity_type": "product",
                    "entity_id": "product_1",
                    "provider": "store77",
                    "status": "confirmed",
                    "url": "https://store77.net/iphone-silver",
                    "score": 0.94,
                }
            ]),
            patch.object(catalog_exchange, "_extract_competitor_content_with_retry", side_effect=fake_extract),
            patch.object(catalog_exchange, "_fetch_store77_images_with_browser", return_value={}),
            patch.object(catalog_exchange, "_import_competitor_image_to_storage", return_value=None),
            patch.object(catalog_exchange, "_save_products", side_effect=lambda items: saved_products.extend(deepcopy(items))),
            patch.object(catalog_exchange, "_now_iso", return_value="2026-05-23T12:00:00+00:00"),
        ):
            changed = asyncio.run(catalog_exchange._enrich_export_products_from_candidate_media([product]))

        self.assertEqual(changed, {"product_1"})
        image = saved_products[0]["content"]["media_images"][0]
        self.assertEqual(image["url"], "https://store77.net/images/iphone-silver.png")
        self.assertEqual(image["status"], "needs_review")
        self.assertEqual(image["source"], "store77")

    def test_product_channels_summary_reads_competitor_links_from_relational_store(self) -> None:
        product = {
            "id": "product_1",
            "title": "iPhone 17 Pro Max",
            "category_id": "cat-phone",
            "content": {},
        }

        class FakeConnectors:
            def import_stores(self, provider):
                return []

        with (
            patch.object(products, "get_product_service", return_value={"product": product}),
            patch.object(products, "ConnectorsStateReadAdapter", return_value=FakeConnectors()),
            patch.object(products, "read_doc", return_value={"items": {}}),
            patch.object(products, "_load_ozon_summary", return_value={
                "title": "OZON",
                "status": "Нет данных",
                "content_rating": "Нет данных",
                "stores_count": 0,
                "stores": [],
            }),
            patch.object(products, "list_pim_channel_links", return_value=[
                {
                    "provider": "restore",
                    "status": "confirmed",
                    "url": "https://re-store.ru/catalog/iphone/",
                    "score": 0.95,
                },
                {
                    "provider": "store77",
                    "status": "candidate",
                    "url": "https://store77.net/iphone/",
                    "score": 0.94,
                },
            ]),
        ):
            result = products.product_channels_summary("product_1")

        by_key = {item["key"]: item for item in result["competitors"]}
        self.assertEqual(by_key["restore"]["status"], "Подключен")
        self.assertEqual(by_key["restore"]["url"], "https://re-store.ru/catalog/iphone/")
        self.assertEqual(by_key["store77"]["status"], "На проверке")
        self.assertEqual(by_key["store77"]["url"], "https://store77.net/iphone/")

    def test_competitor_discovery_category_lists_all_branch_sku_for_manual_scan(self) -> None:
        products_in_branch = [
            {
                "id": f"product_{idx}",
                "title": f"iPhone Variant {idx:02d}",
                "sku_gt": f"GT{idx:02d}",
            }
            for idx in range(12)
        ]
        product_ids = {str(item["id"]) for item in products_in_branch}

        async def no_suggestions(*_args, **_kwargs):
            return []

        with (
            patch.object(competitor_mapping, "_catalog_node_by_id", return_value={"id": "cat-phone", "name": "iPhone"}),
            patch.object(competitor_mapping, "_product_ids_for_category_scope", return_value=(deepcopy(products_in_branch), product_ids)),
            patch.object(competitor_mapping, "load_competitor_mapping_db", return_value={"discovery": {"candidates": {}, "links": {}}}),
            patch.object(competitor_mapping, "_merge_relational_discovery_items", return_value=None),
            patch.object(competitor_mapping, "_scan_competitor_catalog_suggestions", side_effect=no_suggestions),
        ):
            result = asyncio.run(competitor_mapping.discovery_category_context("cat-phone"))

        self.assertEqual(result["category"]["products_count"], 12)
        self.assertEqual(len(result["category"]["sample_products"]), 12)
        self.assertEqual(result["category"]["sample_products"][-1]["sku_gt"], "GT11")

    def test_latest_catalog_export_run_filters_by_category(self) -> None:
        runs_doc = {
            "runs": {
                "export_old": {
                    "id": "export_old",
                    "created_at": "2026-05-23T10:00:00+00:00",
                    "selection": {"node_ids": ["cat-phone"], "product_ids": []},
                    "count": 1,
                    "summary": {"product_count": 1},
                    "batches": [],
                },
                "export_new": {
                    "id": "export_new",
                    "created_at": "2026-05-23T11:00:00+00:00",
                    "selection": {"node_ids": ["cat-phone"], "product_ids": []},
                    "count": 2,
                    "summary": {"product_count": 2},
                    "batches": [{"provider": "ozon"}],
                },
                "export_other": {
                    "id": "export_other",
                    "created_at": "2026-05-23T12:00:00+00:00",
                    "selection": {"node_ids": ["cat-tablet"], "product_ids": []},
                    "count": 3,
                    "summary": {"product_count": 3},
                    "batches": [],
                },
            }
        }

        with patch.object(catalog_exchange, "_load_runs", return_value=runs_doc):
            result = catalog_exchange.get_latest_catalog_export_run(category_id="cat-phone")

        self.assertEqual(result["run"]["id"], "export_new")
        self.assertEqual(result["run"]["count"], 2)

    def test_catalog_exchange_run_history_is_bounded_before_save(self) -> None:
        runs_doc = {
            "runs": {
                f"run_{idx}": {"id": f"run_{idx}", "created_at": f"2026-05-23T10:{idx:02d}:00+00:00"}
                for idx in range(5)
            }
        }

        with patch.dict(os.environ, {"CATALOG_EXCHANGE_RUN_HISTORY_LIMIT": "2"}):
            pruned = catalog_exchange._prune_runs_doc(catalog_exchange.EXPORT_RUNS_PATH, runs_doc)

        self.assertEqual(list(pruned["runs"].keys()), ["run_4", "run_3"])

    def test_competitor_specs_auto_map_without_saved_template_mapping(self) -> None:
        attrs = {
            "встроенная_память": {"code": "встроенная_память", "name": "Встроенная память"},
            "название_цвета_от_производителя": {
                "code": "название_цвета_от_производителя",
                "name": "Название цвета от производителя",
            },
            "количество_sim_карт": {"code": "количество_sim_карт", "name": "Количество SIM-карт"},
            "подробная_комплектация": {"code": "подробная_комплектация", "name": "Подробная комплектация"},
        }
        specs = {
            "Память": "256 ГБ",
            "Цвет": "песчаный титановый",
            "SIM-карта": "SIM + eSIM",
            "В комплекте": "кабель USB-C",
        }

        with patch.object(catalog_exchange, "_template_attr_defs", return_value=attrs):
            mapped = catalog_exchange._auto_map_competitor_specs("tpl-phone", specs, {})

        self.assertEqual(mapped["встроенная_память"], "256 ГБ")
        self.assertEqual(mapped["название_цвета_от_производителя"], "песчаный титановый")
        self.assertEqual(mapped["количество_sim_карт"], "SIM + eSIM")
        self.assertEqual(mapped["подробная_комплектация"], "кабель USB-C")

    def test_competitor_specs_auto_map_never_maps_core_text_fields(self) -> None:
        attrs = {
            "title": {"code": "title", "name": "Наименование товара"},
            "description": {"code": "description", "name": "Описание товара"},
            "встроенная_память": {"code": "встроенная_память", "name": "Встроенная память"},
        }
        specs = {
            "Память": "256 ГБ",
            "Описание товара": "Длинный рекламный текст конкурента",
        }

        with patch.object(catalog_exchange, "_template_attr_defs", return_value=attrs):
            mapped = catalog_exchange._auto_map_competitor_specs(
                "tpl-phone",
                specs,
                {"title": "Память", "description": "Описание товара"},
            )

        self.assertNotIn("title", mapped)
        self.assertNotIn("description", mapped)
        self.assertEqual(mapped["встроенная_память"], "256 ГБ")

    def test_competitor_specs_auto_map_normalizes_restore_device_specs(self) -> None:
        attrs = {
            "тип_разъема": {"code": "тип_разъема", "name": "Тип разъема для зарядки"},
            "вес": {"code": "вес", "name": "Вес устройства, г"},
            "материал": {"code": "материал", "name": "Материал корпуса"},
            "яркость": {"code": "яркость", "name": "Максимальная яркость"},
            "навигация": {"code": "навигация", "name": "Навигационная система"},
            "крепление": {"code": "крепление", "name": "Крепление аккумулятора"},
            "видео": {"code": "видео", "name": "Время в режиме воспроизведения видео"},
        }
        specs = {
            "Разъём": "USB Type-C",
            "Вес, г": "227",
            "Материал": "титан",
            "Яркость": "2000 кд/м²",
            "Навигация": "GPS; ГЛОНАСС",
            "Аккумулятор": "Несъемный",
            "Воспроизведение видео": "до 33 часов",
        }

        with patch.object(catalog_exchange, "_template_attr_defs", return_value=attrs):
            mapped = catalog_exchange._auto_map_competitor_specs("tpl-phone", specs, {})

        self.assertEqual(mapped["тип_разъема"], "USB Type-C")
        self.assertEqual(mapped["вес"], "227")
        self.assertEqual(mapped["материал"], "титан")
        self.assertEqual(mapped["яркость"], "2000 кд/м²")
        self.assertEqual(mapped["навигация"], "GPS; ГЛОНАСС")
        self.assertEqual(mapped["крепление"], "Несъемный")
        self.assertEqual(mapped["видео"], "до 33 часов")

    def test_product_competitor_enrichment_maps_restore_device_specs(self) -> None:
        product = {
            "id": "product_1",
            "content": {
                "features": [
                    {"code": "connector", "name": "Тип разъема для зарядки", "value": ""},
                    {"code": "device_weight", "name": "Вес устройства, г", "value": ""},
                    {"code": "material", "name": "Материал корпуса", "value": ""},
                    {"code": "brightness", "name": "Максимальная яркость", "value": ""},
                    {"code": "nav", "name": "Навигационная система", "value": ""},
                    {"code": "height", "name": "Высота устройства, мм", "value": ""},
                    {"code": "width", "name": "Ширина устройства, мм", "value": ""},
                    {"code": "thickness", "name": "Толщина", "value": ""},
                    {
                        "code": "battery_capacity",
                        "name": "Емкость аккумулятора (точно)",
                        "value": "Несъемный",
                        "source_values": {
                            "competitor": {
                                "store77": {
                                    "raw_value": "Несъемный",
                                    "resolved_value": "Несъемный",
                                    "canonical_value": "Несъемный",
                                }
                            }
                        },
                    },
                    {"code": "battery_mount", "name": "Крепление аккумулятора", "value": ""},
                    {"code": "video_time", "name": "Время в режиме воспроизведения видео", "value": ""},
                ],
            },
        }

        result = asyncio.run(
            competitor_mapping._merge_competitor_content_into_product(
                product,
                extracted={
                    "restore": {
                        "ok": True,
                        "specs": {
                            "Разъём": "USB Type-C",
                            "Вес, г": "227",
                            "Материал": "титан",
                            "Яркость": "2000 кд/м²",
                            "Навигация": "GPS; ГЛОНАСС",
                            "Размеры": "163x77.6x8.25 мм",
                            "Аккумулятор": "Несъемный",
                            "Воспроизведение видео": "до 33 часов",
                        },
                        "images": [],
                    }
                },
                links={"restore": {"url": "https://re-store.ru/catalog/test/"}},
            )
        )

        features = {item["code"]: item for item in result["product"]["content"]["features"]}
        self.assertEqual(features["connector"]["value"], "USB Type-C")
        self.assertEqual(features["device_weight"]["value"], "227")
        self.assertEqual(features["material"]["value"], "титан")
        self.assertEqual(features["brightness"]["value"], "2000 кд/м²")
        self.assertEqual(features["nav"]["value"], "GPS; ГЛОНАСС")
        self.assertEqual(features["height"]["value"], "163")
        self.assertEqual(features["width"]["value"], "77.6")
        self.assertEqual(features["thickness"]["value"], "8.25")
        self.assertEqual(features["battery_capacity"]["value"], "")
        self.assertEqual(features["battery_mount"]["value"], "Несъемный")
        self.assertEqual(features["video_time"]["value"], "до 33 часов")

    def test_product_competitor_enrichment_keeps_core_text_fields_out_of_specs(self) -> None:
        product = {
            "id": "product_1",
            "title": "Смартфон Apple iPhone 17e 256Gb Pink SIM+eSIM",
            "content": {
                "features": [
                    {"code": "title", "name": "Наименование товара", "value": "Исходное имя"},
                    {"code": "description", "name": "Описание товара", "value": ""},
                    {"code": "storage", "name": "Встроенная память", "value": ""},
                ]
            },
        }
        noisy_description = (
            "Короткое описание товара для карточки. Похожие товары Apple iPhone 17e 512GB "
            "В корзину С этим товаром покупают чехлы."
        )

        result = asyncio.run(
            competitor_mapping._merge_competitor_content_into_product(
                product,
                extracted={
                    "restore": {
                        "ok": True,
                        "specs": {
                            "Память": "256 ГБ",
                            "Наименование товара": "256 ГБ",
                            "Описание товара": noisy_description,
                        },
                        "description": noisy_description,
                        "images": [],
                    }
                },
                links={"restore": {"url": "https://re-store.ru/catalog/test/"}},
            )
        )

        features = {item["code"]: item for item in result["product"]["content"]["features"]}
        self.assertEqual(features["title"]["value"], "Исходное имя")
        self.assertEqual(features["description"]["value"], "")
        self.assertEqual(features["storage"]["value"], "256 ГБ")
        self.assertEqual(result["product"]["content"]["description"], "Короткое описание товара для карточки.")
        self.assertEqual(
            result["product"]["content"]["source_values"]["descriptions"]["restore"]["value"],
            "Короткое описание товара для карточки.",
        )

    def test_competitor_ai_suggestions_fallback_sorts_unmatched_specs(self) -> None:
        product = {
            "id": "product_1",
            "title": "Смартфон Apple iPhone 16 Pro 256GB",
            "content": {
                "features": [
                    {"code": "material", "name": "Материал корпуса", "value": ""},
                    {"code": "brightness", "name": "Максимальная яркость", "value": ""},
                    {"code": "battery_mount", "name": "Крепление аккумулятора", "value": ""},
                ],
                "source_evidence": {
                    "competitors": {
                        "restore": {
                            "unmatched_specs": {
                                "Материал": "титан",
                                "Яркость": "2000 кд/м²",
                                "Отзывы": "123",
                            }
                        },
                        "store77": {
                            "unmatched_specs": {
                                "Страна производства": "Китай",
                            }
                        },
                    }
                },
            },
        }

        async def failing_llm_chat_text(**kwargs):
            raise RuntimeError("llm unavailable")

        with (
            patch.dict(os.environ, {"PIM_ENABLE_AI": "0"}),
            patch.object(competitor_mapping, "list_pim_channel_links", return_value=[]),
            patch.object(competitor_mapping, "llm_chat_text", side_effect=failing_llm_chat_text),
        ):
            response = asyncio.run(competitor_mapping._competitor_ai_suggestion_items(product))
        items = response["items"]
        by_name = {item["source_name"]: item for item in items}

        self.assertEqual(response["mode"], "rules")
        self.assertEqual(by_name["Материал"]["action"], "map_existing")
        self.assertEqual(by_name["Материал"]["target_code"], "material")
        self.assertEqual(by_name["Яркость"]["action"], "map_existing")
        self.assertEqual(by_name["Яркость"]["target_code"], "brightness")
        self.assertEqual(by_name["Отзывы"]["action"], "ignore")
        self.assertEqual(by_name["Страна производства"]["action"], "create_attribute")

    def test_competitor_ai_suggestions_validates_llm_targets(self) -> None:
        product = {
            "id": "product_1",
            "title": "Смартфон Apple iPhone 16 Pro 256GB",
            "content": {
                "features": [{"code": "brightness", "name": "Максимальная яркость", "value": ""}],
                "source_evidence": {
                    "competitors": {
                        "restore": {
                            "unmatched_specs": {
                                "Яркость": "2000 кд/м²",
                                "Гарантия": "1 год",
                            }
                        }
                    }
                },
            },
        }

        async def fake_llm_chat_text(**kwargs):
            return {
                "model": "test-model",
                "content": json.dumps(
                    {
                        "items": [
                            {
                                "source_id": "restore",
                                "source_name": "Яркость",
                                "raw_value": "2000 кд/м²",
                                "action": "map_existing",
                                "target_code": "brightness",
                                "target_name": "Максимальная яркость",
                                "confidence": 0.91,
                                "reason": "это яркость дисплея",
                            },
                            {
                                "source_id": "restore",
                                "source_name": "Гарантия",
                                "raw_value": "1 год",
                                "action": "map_existing",
                                "target_code": "unknown",
                                "target_name": "Несуществующее поле",
                                "confidence": 0.8,
                                "reason": "ошибочная цель",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
            }

        with (
            patch.dict(os.environ, {"PIM_ENABLE_AI": "1"}),
            patch.object(competitor_mapping, "list_pim_channel_links", return_value=[]),
            patch.object(competitor_mapping, "llm_chat_text", side_effect=fake_llm_chat_text),
        ):
            response = asyncio.run(competitor_mapping._competitor_ai_suggestion_items(product))

        items = {item["source_name"]: item for item in response["items"]}
        self.assertEqual(response["mode"], "llm")
        self.assertEqual(items["Яркость"]["action"], "map_existing")
        self.assertEqual(items["Яркость"]["target_code"], "brightness")
        self.assertEqual(items["Гарантия"]["action"], "create_attribute")
        self.assertEqual(items["Гарантия"]["target_code"], "гарантия")

    def test_competitor_ai_suggestions_use_confirmed_mapping_memory(self) -> None:
        product = {
            "id": "product_1",
            "title": "Смартфон Apple iPhone 16 Pro 256GB",
            "content": {
                "features": [
                    {"code": "storage", "name": "Встроенная память", "value": ""},
                    {"code": "ram", "name": "Оперативная память", "value": ""},
                ],
                "source_evidence": {
                    "competitors": {
                        "store77": {
                            "unmatched_specs": {
                                "Память": "256 ГБ",
                            }
                        }
                    }
                },
            },
        }
        memory_rows = [
            {
                "provider": "store77",
                "title": "Память",
                "external_id": "storage",
                "status": "confirmed",
                "payload": {
                    "source_name": "Память",
                    "target_code": "storage",
                    "target_name": "Встроенная память",
                },
            }
        ]

        async def bad_llm_chat_text(**kwargs):
            return {
                "model": "test-model",
                "content": json.dumps(
                    {
                        "items": [
                            {
                                "source_id": "store77",
                                "source_name": "Память",
                                "raw_value": "256 ГБ",
                                "action": "map_existing",
                                "target_code": "ram",
                                "target_name": "Оперативная память",
                                "confidence": 0.99,
                                "reason": "ошибка модели",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            }

        with (
            patch.dict(os.environ, {"PIM_ENABLE_AI": "1"}),
            patch.object(competitor_mapping, "list_pim_channel_links", return_value=memory_rows),
            patch.object(competitor_mapping, "llm_chat_text", side_effect=bad_llm_chat_text),
        ):
            response = asyncio.run(competitor_mapping._competitor_ai_suggestion_items(product))

        item = response["items"][0]
        self.assertEqual(response["mode"], "llm")
        self.assertEqual(item["target_code"], "storage")
        self.assertEqual(item["target_name"], "Встроенная память")
        self.assertEqual(item["source"], "memory")
        self.assertIn("подтвержден", item["reason"])

    def test_save_category_mapping_persists_ai_mapping_memory(self) -> None:
        saved_links: list[dict] = []
        with (
            patch.object(competitor_mapping, "_resolve_template_for_category", return_value=("tpl-phone", "cat-phone")),
            patch.object(competitor_mapping, "_get_category_row_with_fallback", return_value=({}, "tpl-phone", "cat-phone")),
            patch.object(competitor_mapping, "_valid_master_codes", return_value={"storage", "ram"}),
            patch.object(
                competitor_mapping,
                "_master_fields",
                return_value=[
                    {"code": "storage", "name": "Встроенная память"},
                    {"code": "ram", "name": "Оперативная память"},
                ],
            ),
            patch.object(competitor_mapping, "_persist_competitor_mapping_row"),
            patch.object(competitor_mapping, "_remove_legacy_competitor_mapping_row"),
            patch.object(competitor_mapping, "upsert_pim_channel_link", side_effect=lambda row: saved_links.append(deepcopy(row)) or row),
        ):
            response = competitor_mapping.save_category_mapping(
                "cat-phone",
                {"mapping_by_site": {"store77": {"storage": "Память"}}},
            )

        self.assertTrue(response["ok"])
        self.assertEqual(len(saved_links), 1)
        row = saved_links[0]
        self.assertEqual(row["scope"], "ai_mapping_memory")
        self.assertEqual(row["entity_type"], "template")
        self.assertEqual(row["entity_id"], "tpl-phone")
        self.assertEqual(row["provider"], "store77")
        self.assertEqual(row["external_id"], "storage")
        self.assertEqual(row["title"], "Память")
        self.assertEqual(row["payload"]["target_name"], "Встроенная память")

    def test_competitor_template_ai_mapping_uses_llm_but_rejects_core_fields(self) -> None:
        fields = [
            {"code": "title", "name": "Наименование товара"},
            {"code": "description", "name": "Описание товара"},
            {"code": "storage", "name": "Встроенная память"},
            {"code": "color", "name": "Цвет"},
        ]
        specs = {
            "Память": "256 ГБ",
            "Описание товара": "Длинный текст конкурента",
            "Цвет": "розовый",
        }

        async def fake_llm_chat_text(**kwargs):
            return {
                "model": "test-model",
                "content": json.dumps(
                    {
                        "items": [
                            {
                                "source_id": "store77",
                                "source_name": "Память",
                                "raw_value": "256 ГБ",
                                "action": "map_existing",
                                "target_code": "title",
                                "target_name": "Наименование товара",
                                "confidence": 0.99,
                                "reason": "ошибочная цель",
                            },
                            {
                                "source_id": "store77",
                                "source_name": "Цвет",
                                "raw_value": "розовый",
                                "action": "map_existing",
                                "target_code": "color",
                                "target_name": "Цвет",
                                "confidence": 0.92,
                                "reason": "цвет товара",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
            }

        with (
            patch.dict(os.environ, {"PIM_ENABLE_AI": "1"}),
            patch.object(competitor_mapping, "list_pim_channel_links", return_value=[]),
            patch.object(competitor_mapping, "_master_fields", return_value=fields),
            patch.object(competitor_mapping, "llm_chat_text", side_effect=fake_llm_chat_text),
        ):
            mapped = asyncio.run(competitor_mapping._ai_map_competitor_specs_to_template("tpl-phone", "store77", specs))

        self.assertNotIn("title", mapped)
        self.assertNotIn("description", mapped)
        self.assertEqual(mapped["storage"], "256 ГБ")
        self.assertEqual(mapped["color"], "розовый")

    def test_content_source_summary_detects_competitor_media_after_storage_import(self) -> None:
        product = {
            "id": "product_1",
            "content": {
                "media_images": [
                    {
                        "url": "/api/uploads/media_images/product_1/competitors/store77/image.jpg",
                        "external_url": "https://store77.net/images/image.jpg",
                        "source": "store77",
                        "storage": "s3",
                    }
                ],
                "source_values": {"media_images": {"store77": {"count": 1}}},
            },
        }

        summary = catalog_exchange._content_source_summary(product)

        self.assertEqual(summary["media"]["images_count"], 1)
        self.assertTrue(summary["media"]["from_competitors"])

    def test_export_media_url_expands_local_uploads_to_public_urls(self) -> None:
        with (
            patch.dict(os.environ, {"APP_PUBLIC_BASE_URL": "https://pim.id-smart.ru"}),
            patch.object(yandex_market, "_env_file_value", return_value=""),
        ):
            self.assertEqual(
                yandex_market._export_media_url("/api/uploads/media_images/product_1/image.jpg"),
                "https://pim.id-smart.ru/api/uploads/media_images/product_1/image.jpg",
            )
            self.assertEqual(
                yandex_market._export_media_url("https://cdn.example.test/image.jpg"),
                "https://cdn.example.test/image.jpg",
            )

    def test_store77_discovery_scans_real_category_before_seed_fallback(self) -> None:
        product = {
            "id": "product_1",
            "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)",
            "sku_gt": "52460",
            "category_id": "phones",
        }
        html = """
        <a href="/apple_iphone_17_pro_1/telefon_apple_iphone_17_pro_256gb_esim_silver/">
          Телефон Apple iPhone 17 Pro 256 ГБ, eSim (электронная SIM-карта), цвет: серебристый (Silver)
        </a>
        """
        fetched_urls: list[str] = []

        async def fake_fetch(url):
            fetched_urls.append(url)
            return html

        with patch.object(competitor_mapping, "_fetch_store77_category_html", side_effect=fake_fetch):
            candidates = asyncio.run(competitor_mapping._discover_store77_candidates(product))

        self.assertEqual(candidates[0]["url"], "https://store77.net/apple_iphone_17_pro_1/telefon_apple_iphone_17_pro_256gb_esim_silver/")
        self.assertIn("apple_iphone_17_pro_1", fetched_urls[0])
        self.assertEqual(len(fetched_urls), 1)
        self.assertTrue(all("/product/product_" not in item["url"] for item in candidates))

    def test_store77_discovery_uses_imported_competitor_catalog_index(self) -> None:
        product = {
            "id": "product_huawei",
            "title": "Смартфон Huawei Mate X7 512Gb Black",
            "sku_gt": "70001",
            "category_id": "phones",
        }
        imported_store = {
            "products": {
                "store77_huawei_black": {
                    "url": "https://store77.net/huawei_mate_x7/telefon_huawei_mate_x7_16_512gb_black",
                    "title": "Телефон Huawei Mate X7 16/512 ГБ цвет: черный (Black)",
                    "brand": "Huawei",
                    "sku": "",
                    "price": "107360",
                    "images": ["https://store77.net/upload/huawei-black.jpg"],
                },
                "store77_wrong": {
                    "url": "https://store77.net/apple_iphone_17/telefon_apple_iphone_17_256gb_black",
                    "title": "Телефон Apple iPhone 17 256Gb Black",
                    "brand": "Apple",
                    "images": [],
                },
            }
        }

        with (
            patch.object(competitor_catalog_import, "_load_store", return_value=imported_store),
            patch.object(competitor_mapping, "_discover_store77_candidates", return_value=[]),
        ):
            candidates = asyncio.run(
                competitor_mapping._discover_product_candidates_for_source(product, {"id": "store77", "name": "store77"})
            )

        self.assertEqual(candidates[0]["url"], "https://store77.net/huawei_mate_x7/telefon_huawei_mate_x7_16_512gb_black")
        self.assertEqual(candidates[0]["discovery_strategy"], "competitor_catalog_index")
        self.assertGreaterEqual(candidates[0]["confidence_score"], 0.82)

    def test_store77_seed_candidate_supports_iphone_17e_pink(self) -> None:
        product = {
            "id": "product_1092",
            "title": "Смартфон Apple iPhone 17e 256Gb Pink SIM+eSIM",
            "sku_gt": "53425",
            "category_id": "phones",
        }

        candidates = competitor_mapping._store77_seed_candidates_for_product(product)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]["url"],
            "https://store77.net/apple_iphone_17e/telefon_apple_iphone_17e_256_gb_esim_elektronnaya_sim_karta_tsvet_rozovyy_soft_pink/",
        )
        self.assertEqual(candidates[0]["product_sim_profile"], "nano_sim_esim")
        self.assertEqual(candidates[0]["candidate_sim_profile"], "esim_only")

    def test_store77_title_fallback_extracts_specs_from_product_title(self) -> None:
        specs = infer_store77_specs_from_title_or_url(
            "Телефон Apple iPhone 17e 256 ГБ, eSim (электронная SIM-карта), цвет: розовый (Soft pink)",
            "https://store77.net/apple_iphone_17e/telefon_apple_iphone_17e_256_gb_esim_elektronnaya_sim_karta_tsvet_rozovyy_soft_pink/",
        )

        self.assertEqual(specs["Память"], "256 ГБ")
        self.assertEqual(specs["SIM-карта"], "eSIM")
        self.assertEqual(specs["Цвет"], "розовый (Soft pink)")
        self.assertEqual(specs["Модель"], "iPhone 17e")

    def test_store77_seed_candidate_requires_matching_product_page(self) -> None:
        candidate = {
            "title": "Телефон Apple iPhone 17 Pro 256Gb eSim (Silver)",
            "url": "https://store77.net/apple_iphone_17_pro_1/telefon_apple_iphone_17_pro_256gb_esim_silver/",
        }
        self.assertTrue(
            competitor_mapping._store77_seed_candidate_matches_page(
                candidate,
                "Телефон Apple iPhone 17 Pro 256 ГБ eSim цвет серебристый Silver",
            )
        )
        self.assertFalse(
            competitor_mapping._store77_seed_candidate_matches_page(
                candidate,
                "Чехол Gurdini Super Slim для iPhone 17 Pro",
            )
        )

    def test_variant_profile_treats_deep_blue_as_blue_even_with_dark_blue_specs(self) -> None:
        profile = competitor_mapping._variant_profile(
            "Apple iPhone 17 Pro Max 256GB, Deep Blue Темно-синий nano SIM + eSIM"
        )

        self.assertEqual(profile["color"], "blue")
        self.assertEqual(profile["sim"], "nano_sim_esim")

    def test_competitor_variant_profile_handles_watch_band_axes(self) -> None:
        product = {"title": "Часы Apple Watch Ultra 3 Black Titanium Black Trail Loop S/M"}
        candidate = "Умные часы Apple Watch Ultra 3, 49 мм, Black Titanium Bl/Charcoal Trail Loop M/L"

        score, reasons = competitor_mapping._confidence_for_candidate(product, candidate, "")

        self.assertEqual(score, 0.0)
        self.assertIn("конфликт размера ремешка", reasons[0])

    def test_competitor_variant_profile_handles_oura_size_and_dyson_model(self) -> None:
        oura_product = {"title": "Умное кольцо Oura Ring 4 Серебристый (Silver) 4 US"}
        oura_score, oura_reasons = competitor_mapping._confidence_for_candidate(
            oura_product,
            "Oura Ring 4 Silver Size 4",
            "",
        )
        self.assertGreaterEqual(oura_score, 0.78)
        self.assertIn("вариантные признаки совпали", oura_reasons)

        dyson_product = {
            "title": "Стайлер Dyson Airwrap i.d. Long HS08 Straight+Wavy, розовый/розовое золото (Ceramic pink/Rose gold)"
        }
        dyson_score, dyson_reasons = competitor_mapping._confidence_for_candidate(
            dyson_product,
            "Dyson Airwrap HS08 Ceramic Pink Rose Gold",
            "",
        )
        self.assertGreaterEqual(dyson_score, 0.78)
        self.assertIn("вариантные признаки совпали", dyson_reasons)

    def test_competitor_variant_profile_keeps_samsung_fold_without_sim_as_review(self) -> None:
        product = {"title": "Смартфон Samsung Galaxy Z Fold7 256Gb Dual nano SIM+eSIM Blue Shadow"}

        score, reasons = competitor_mapping._near_miss_confidence_for_candidate(
            product,
            "Samsung Galaxy Z Fold 7 256GB Blue Shadow",
            "",
        )

        self.assertGreaterEqual(score, 0.78)
        self.assertIn("проверь SIM", reasons[0])

    def test_store77_seed_candidate_supports_samsung_fold7(self) -> None:
        product = {
            "id": "product_684",
            "title": "Смартфон Samsung Galaxy Z Fold7 256Gb Dual nano SIM+eSIM Blue Shadow",
            "sku_gt": "52394",
        }

        candidates = competitor_mapping._store77_seed_candidates_for_product(product)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]["url"],
            "https://store77.net/telefony_samsung/telefon_samsung_galaxy_z_fold7_12_256gb_blue_shadow/",
        )
        self.assertGreaterEqual(candidates[0]["confidence_score"], 0.78)
        self.assertIn("store77 URL собран из модели, памяти и цвета Samsung", candidates[0]["confidence_reasons"])

    def test_restore_seed_candidate_supports_oura_ring4_size_and_color(self) -> None:
        silver = {
            "id": "product_928",
            "title": "Умное кольцо Oura Ring 4 Серебристый (Silver) 4 US",
            "sku_gt": "53292",
        }
        brushed = {
            "id": "product_933",
            "title": "Умное кольцо Oura Ring 4 Матовое серебро (Brushed Silver) 9 US",
            "sku_gt": "53321",
        }

        silver_candidate = competitor_mapping._restore_oura_seed_candidate_for_product(silver)
        brushed_candidate = competitor_mapping._restore_oura_seed_candidate_for_product(brushed)

        self.assertIsNotNone(silver_candidate)
        self.assertEqual(silver_candidate["url"], "https://re-store.ru/catalog/RING4SL4/")
        self.assertGreaterEqual(silver_candidate["confidence_score"], 0.78)
        self.assertIsNotNone(brushed_candidate)
        self.assertEqual(brushed_candidate["url"], "https://re-store.ru/catalog/RING4BR9/")

    def test_ai_competitor_examples_use_only_confirmed_source_links(self) -> None:
        rows = [
            {
                "entity_id": "product_seed",
                "provider": "store77",
                "url": "https://store77.net/apple_iphone_17_pro/telefon_apple_iphone_17_pro_256gb_silver/",
                "title": "Телефон Apple iPhone 17 Pro 256GB Silver",
                "status": "confirmed",
            },
            {
                "entity_id": "product_candidate",
                "provider": "store77",
                "url": "https://store77.net/apple_iphone_17_pro/telefon_wrong/",
                "title": "Wrong",
                "status": "candidate",
            },
            {
                "entity_id": "product_restore",
                "provider": "restore",
                "url": "https://re-store.ru/catalog/iphone-test/",
                "title": "Restore",
                "status": "confirmed",
            },
        ]
        products_by_id = {
            "product_seed": {
                "id": "product_seed",
                "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)",
                "sku_gt": "seed",
            },
            "product_candidate": {
                "id": "product_candidate",
                "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Black (Global)",
            },
            "product_restore": {
                "id": "product_restore",
                "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)",
            },
        }

        with (
            patch.object(competitor_mapping, "list_pim_channel_links", return_value=rows),
            patch.object(
                competitor_mapping,
                "query_products_full",
                side_effect=lambda ids=None, **_: [products_by_id[item] for item in (ids or []) if item in products_by_id],
            ),
        ):
            examples = competitor_mapping._confirmed_competitor_candidate_examples(
                {"id": "product_target", "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)"},
                "store77",
            )

        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0]["product_id"], "product_seed")
        self.assertIn("store77.net", examples[0]["url"])

    def test_legacy_ai_competitor_candidate_discovery_is_disabled(self) -> None:
        product = {
            "id": "product_target",
            "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)",
            "sku_gt": "50001",
        }
        source = {"id": "store77", "domain": "store77.net", "base_url": "https://store77.net", "name": "store77"}

        with patch.dict(os.environ, {"PIM_ENABLE_AI": "0", "ENABLE_AI_COMPETITOR_DISCOVERY": "0"}):
            candidates = asyncio.run(competitor_mapping._discover_ai_competitor_candidates(product, source))

        self.assertEqual(candidates, [])

    def test_legacy_ai_competitor_candidate_discovery_ignores_confirmed_links_when_disabled(self) -> None:
        product = {
            "id": "product_target",
            "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)",
            "sku_gt": "50001",
        }
        source = {"id": "store77", "domain": "store77.net", "base_url": "https://store77.net", "name": "store77"}

        with patch.dict(os.environ, {"PIM_ENABLE_AI": "0", "ENABLE_AI_COMPETITOR_DISCOVERY": "0"}):
            candidates = asyncio.run(competitor_mapping._discover_ai_competitor_candidates(product, source))

        self.assertEqual(candidates, [])

    def test_discovery_run_request_ignores_legacy_ai_candidate_flag(self) -> None:
        sources, product_ids, limit, use_ai = competitor_mapping._parse_discovery_run_request(
            {"sources": ["store77"], "product_ids": ["product_1"], "limit": 1, "use_ai": True}
        )

        self.assertEqual([item["id"] for item in sources], ["store77"])
        self.assertEqual(product_ids, ["product_1"])
        self.assertEqual(limit, 1)
        self.assertFalse(use_ai)

    def test_product_discovery_does_not_append_ai_candidates_in_active_flow(self) -> None:
        product = {
            "id": "product_target",
            "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)",
            "sku_gt": "50001",
        }
        source = {"id": "store77", "domain": "store77.net", "base_url": "https://store77.net", "name": "store77"}
        low_candidate = {
            "url": "https://store77.net/apple_iphone_17_pro/telefon_wrong/",
            "title": "Чехол для Apple iPhone 17 Pro",
            "confidence_score": 0.2,
        }
        ai_candidate = {
            "url": "https://store77.net/apple_iphone_17_pro/telefon_apple_iphone_17_pro_256gb_esim_silver/",
            "title": "Телефон Apple iPhone 17 Pro 256 ГБ eSIM Silver",
            "confidence_score": 0.8,
            "discovery_strategy": "ai_confirmed_link_memory",
        }

        with (
            patch.object(competitor_mapping, "_discover_store77_candidates", return_value=[low_candidate]),
            patch.object(competitor_mapping, "_discover_ai_competitor_candidates", return_value=[ai_candidate]),
        ):
            candidates = asyncio.run(competitor_mapping._discover_product_candidates_for_source(product, source, use_ai=True))

        self.assertEqual(candidates, [low_candidate])

    def test_export_preview_keeps_ready_and_blockers_per_marketplace(self) -> None:
        saved_runs: dict[str, object] = {}
        req = CatalogExportRunReq.model_validate(
            {
                "selection": {"node_ids": [], "product_ids": ["product_1"], "include_descendants": False},
                "targets": [{"provider": "yandex_market", "store_ids": ["ym-1"]}, {"provider": "ozon", "store_ids": ["oz-1"]}],
                "limit": 20,
            }
        )

        with (
            patch.object(catalog_exchange, "_resolve_products", return_value=[{"id": "product_1", "title": "Meta Quest 3 128GB"}]),
            patch.object(catalog_exchange.ConnectorsStateReadAdapter, "import_stores", side_effect=lambda provider: {
                "yandex_market": [{"id": "ym-1", "title": "YM", "enabled": True}],
                "ozon": [{"id": "oz-1", "title": "Ozon", "enabled": True}],
            }.get(provider, [])),
            patch.object(catalog_exchange, "yandex_export_preview", return_value={
                "ready_count": 1,
                "count": 1,
                "items": [{"product_id": "product_1", "ready": True, "missing": []}],
            }),
            patch.object(catalog_exchange, "_ozon_export_preview", return_value={
                "ready_count": 0,
                "count": 1,
                "items": [{"product_id": "product_1", "product_title": "Meta Quest 3 128GB", "category_id": "cat-vr", "ready": False, "missing": ["description"]}],
            }),
            patch.object(catalog_exchange, "_enrich_export_products_from_candidate_media", return_value=set()),
            patch.object(catalog_exchange, "_hydrate_marketplace_product_content", return_value=[]),
            patch.object(catalog_exchange, "_hydrate_missing_content_from_variant_siblings", return_value=[]),
            patch.object(catalog_exchange, "query_products_full", return_value=[{"id": "product_1", "title": "Meta Quest 3 128GB"}]),
            patch.object(catalog_exchange, "_load_runs", return_value={"runs": {}}),
            patch.object(catalog_exchange, "_save_runs", side_effect=lambda _path, doc: saved_runs.update(deepcopy(doc))),
            patch.object(catalog_exchange, "uuid4", return_value=type("FakeUuid", (), {"hex": "abcdef1234567890"})()),
        ):
            response = catalog_exchange.run_catalog_export(req)

        self.assertEqual(response["ok"], True)
        self.assertEqual(response["count"], 1)
        self.assertEqual(
            response["summary"],
            {
                "product_count": 1,
                "target_count": 2,
                "batch_count": 2,
                "ready_batches": 1,
                "blocked_batches": 1,
                "ready_target_items": 1,
                "blocked_target_items": 1,
                "blockers_count": 1,
                "status": "blocked",
            },
        )
        self.assertEqual(len(response["batches"]), 2)
        self.assertEqual(response["batches"][0]["provider"], "yandex_market")
        self.assertEqual(response["batches"][0]["status"], "ready")
        self.assertEqual(response["batches"][0]["ready_count"], 1)
        self.assertEqual(response["batches"][1]["provider"], "ozon")
        self.assertEqual(response["batches"][1]["status"], "blocked")
        self.assertEqual(response["batches"][1]["ready_count"], 0)
        self.assertEqual(response["batches"][1]["not_ready_count"], 1)
        self.assertEqual(response["batches"][1]["blockers_count"], 1)
        self.assertEqual(response["batches"][1]["items"][0]["missing"], ["description"])
        self.assertEqual(response["batches"][1]["blockers"][0]["missing"], ["description"])
        self.assertEqual(response["batches"][1]["blockers"][0]["product_title"], "Meta Quest 3 128GB")
        self.assertEqual(response["batches"][1]["blockers"][0]["category_id"], "cat-vr")
        self.assertIn("export_abcdef1234", saved_runs["runs"])
        self.assertEqual(saved_runs["runs"]["export_abcdef1234"]["summary"]["blocked_target_items"], 1)

    def test_export_run_rejects_unknown_selected_store_id(self) -> None:
        req = CatalogExportRunReq.model_validate(
            {
                "selection": {"node_ids": [], "product_ids": ["product_1"], "include_descendants": False},
                "targets": [{"provider": "yandex_market", "store_ids": ["gt_usd"]}],
                "limit": 20,
            }
        )

        with (
            patch.object(catalog_exchange, "_resolve_products", return_value=[{"id": "product_1", "title": "Meta Quest 3 128GB"}]),
            patch.object(
                catalog_exchange.ConnectorsStateReadAdapter,
                "import_stores",
                return_value=[{"id": "ym-store-real", "title": "GT USD", "enabled": True}],
            ),
            patch.object(catalog_exchange, "yandex_export_preview", return_value={"ready_count": 1, "count": 1, "items": []}),
            patch.object(catalog_exchange, "_enrich_export_products_from_candidate_media", return_value=set()),
            patch.object(catalog_exchange, "_hydrate_marketplace_product_content", return_value=[]),
            patch.object(catalog_exchange, "_hydrate_missing_content_from_variant_siblings", return_value=[]),
            patch.object(catalog_exchange, "query_products_full", return_value=[{"id": "product_1", "title": "Meta Quest 3 128GB"}]),
        ):
            with self.assertRaises(HTTPException) as ctx:
                catalog_exchange.run_catalog_export(req)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("No matching stores selected", str(ctx.exception.detail))

    def test_export_run_accepts_explicit_store_not_preselected_for_export(self) -> None:
        req = CatalogExportRunReq.model_validate(
            {
                "selection": {"node_ids": [], "product_ids": ["product_1"], "include_descendants": False},
                "targets": [{"provider": "ozon", "store_ids": ["ozon-ae"]}],
                "limit": 20,
            }
        )

        with (
            patch.object(catalog_exchange, "_resolve_products", return_value=[{"id": "product_1", "title": "Meta Quest 3 128GB"}]),
            patch.object(
                catalog_exchange.ConnectorsStateReadAdapter,
                "import_stores",
                return_value=[{"id": "ozon-ae", "title": "Ozon AE", "enabled": True, "export_enabled": False}],
            ),
            patch.object(catalog_exchange, "_ozon_export_preview", return_value={
                "ready_count": 1,
                "count": 1,
                "items": [{"product_id": "product_1", "ready": True, "missing": []}],
            }),
            patch.object(catalog_exchange, "_enrich_export_products_from_candidate_media", return_value=set()),
            patch.object(catalog_exchange, "_hydrate_marketplace_product_content", return_value=[]),
            patch.object(catalog_exchange, "_hydrate_missing_content_from_variant_siblings", return_value=[]),
            patch.object(catalog_exchange, "query_products_full", return_value=[{"id": "product_1", "title": "Meta Quest 3 128GB"}]),
            patch.object(catalog_exchange, "_load_runs", return_value={"runs": {}}),
            patch.object(catalog_exchange, "_save_runs", return_value=None),
        ):
            response = catalog_exchange.run_catalog_export(req)

        self.assertEqual(response["ok"], True)
        self.assertEqual(response["summary"]["target_count"], 1)
        self.assertEqual(response["batches"][0]["store_id"], "ozon-ae")

    def test_export_package_contains_only_ready_payload_items(self) -> None:
        run = {
            "id": "export_test",
            "selection": {"product_ids": ["product_1"]},
            "targets": [{"provider": "yandex_market", "store_ids": ["ym-1"]}],
            "batches": [
                {
                    "provider": "yandex_market",
                    "store_id": "ym-1",
                    "store_title": "GT USD",
                    "items": [
                        {
                            "product_id": "product_1",
                            "ready": True,
                            "payload_item": {"offerId": "GT-1", "name": "Ready item", "manuals": [], "barcodes": [], "parameterValues": []},
                        },
                        {
                            "product_id": "product_2",
                            "ready": False,
                            "missing": ["Нет изображений"],
                            "payload_item": {"offerId": "GT-2", "name": "Blocked item"},
                        },
                    ],
                }
            ],
        }

        package = catalog_exchange._build_export_package(run)

        self.assertEqual(package["run_id"], "export_test")
        self.assertEqual(package["status"], "partial")
        self.assertEqual(package["summary"]["ready_items"], 1)
        self.assertEqual(package["summary"]["blocked_items"], 1)
        self.assertEqual(package["warnings"][0]["blocked_items"], 1)
        batch = package["batches"][0]
        self.assertEqual(batch["status"], "partial")
        self.assertEqual(batch["ready_count"], 1)
        self.assertEqual(batch["items"][0]["offer_id"], "GT-1")
        self.assertEqual(batch["items"][0]["payload"]["name"], "Ready item")
        self.assertNotIn("manuals", batch["items"][0]["payload"])
        self.assertNotIn("barcodes", batch["items"][0]["payload"])
        self.assertNotIn("parameterValues", batch["items"][0]["payload"])

    def test_ozon_export_preview_derives_required_type_and_model_name(self) -> None:
        product = {
            "id": "product_iphone",
            "sku_gt": "52460",
            "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)",
            "category_id": "cat-iphone",
            "content": {
                "media_images": [{"url": "/api/uploads/media_images/iphone.webp"}],
                "description": "Apple iPhone 17 Pro",
                "features": [
                    {"code": "brand", "name": "Бренд", "value": "Apple"},
                    {"code": "camera_type", "name": "Тип основных камер", "value": "телефото"},
                ],
            },
        }

        rows = [
            {
                "catalog_name": "Тип основных камер",
                "provider_map": {
                    "ozon": {"id": "8229", "name": "Тип", "required": True, "export": True}
                },
            },
            {
                "catalog_name": "Бренд",
                "provider_map": {
                    "ozon": {"id": "85", "name": "Бренд", "required": True, "export": True}
                },
            },
        ]

        with (
            patch.object(catalog_exchange, "query_products_full", return_value=[product]),
            patch.object(catalog_exchange, "_load_nodes", return_value=[{"id": "cat-iphone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(catalog_exchange, "_load_category_mapping", return_value={"cat-iphone": {"ozon": "17028922"}}),
            patch.object(catalog_exchange, "_load_attr_mapping_rows", return_value={"cat-iphone": rows}),
            patch.object(catalog_exchange, "dict_id_for_product_feature", return_value=""),
        ):
            response = catalog_exchange._ozon_export_preview(["product_iphone"], 10)

        self.assertEqual(response["ready_count"], 1)
        item = response["items"][0]
        self.assertEqual(item["missing"], [])
        self.assertEqual(item["payload_item"]["price"], "1000000")
        self.assertEqual(item["payload_item"]["price_source"], "technical_placeholder")
        attrs = {str(attr["id"]): attr["values"][0]["value"] for attr in item["payload_item"]["attributes"]}
        attr_values = {str(attr["id"]): attr["values"][0] for attr in item["payload_item"]["attributes"]}
        self.assertEqual(attrs["8229"], "Смартфон")
        self.assertEqual(attrs["9048"], "iPhone 17 Pro")
        self.assertEqual(attrs["22232"], "8517130000 - Смартфоны")
        self.assertEqual(attr_values["22232"]["dictionary_value_id"], 971400011)

    def test_ozon_export_preview_derives_watch_type_and_brand_from_title(self) -> None:
        product = {
            "id": "product_watch",
            "sku_gt": "53286",
            "title": "Часы Apple Watch Ultra 3 Natural Titanium Black Alpine Loop M",
            "category_id": "cat-watch",
            "content": {
                "media_images": [{"url": "/api/uploads/media_images/watch.webp"}],
                "description": "Apple Watch Ultra 3",
                "features": [],
            },
        }

        with (
            patch.object(catalog_exchange, "query_products_full", return_value=[product]),
            patch.object(catalog_exchange, "_load_nodes", return_value=[{"id": "cat-watch", "parent_id": None, "name": "Умные часы"}]),
            patch.object(catalog_exchange, "_load_category_mapping", return_value={"cat-watch": {"ozon": "watch-ozon"}}),
            patch.object(catalog_exchange, "_load_attr_mapping_rows", return_value={"cat-watch": []}),
            patch.object(catalog_exchange, "load_competitor_mapping_db", return_value={}),
        ):
            response = catalog_exchange._ozon_export_preview(["product_watch"], 10)

        item = response["items"][0]
        self.assertNotIn("Ozon: обязательный параметр 'Тип' не сопоставлен/пуст", item["missing"])
        self.assertNotIn("Ozon: обязательный параметр 'Бренд' не сопоставлен/пуст", item["missing"])
        attrs = {str(attr["id"]): attr["values"][0]["value"] for attr in item["payload_item"]["attributes"]}
        self.assertEqual(attrs["8229"], "Умные часы")
        self.assertEqual(attrs["85"], "Apple")

    def test_ozon_export_preview_blocks_empty_parameter_mapping_even_with_system_attrs(self) -> None:
        product = {
            "id": "product_1",
            "sku_gt": "GT-1",
            "title": "Смартфон Apple iPhone 17 Pro Max 256Gb",
            "category_id": "cat-phone",
            "status": "active",
            "content": {
                "description": "Phone",
                "media_images": [{"url": "https://cdn.example.test/p.jpg"}],
                "features": [{"code": "memory", "name": "Встроенная память", "value": "256 ГБ"}],
            },
        }

        with (
            patch.object(catalog_exchange, "query_products_full", return_value=[deepcopy(product)]),
            patch.object(catalog_exchange, "_load_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(catalog_exchange, "_load_category_mapping", return_value={"cat-phone": {"ozon": "oz-phone"}}),
            patch.object(catalog_exchange, "_load_attr_mapping_rows", return_value={"cat-phone": []}),
            patch.object(catalog_exchange, "load_competitor_mapping_db", return_value={}),
        ):
            response = catalog_exchange._ozon_export_preview(["product_1"], 10)

        item = response["items"][0]
        self.assertEqual(item["ready"], False)
        self.assertIn("Нет сопоставленных PIM-параметров для Ozon: соберите инфо-модель и свяжите параметры площадки", item["missing"])
        attrs = {str(attr["id"]): attr["values"][0]["value"] for attr in item["payload_item"]["attributes"]}
        self.assertEqual(attrs["8229"], "Смартфон")

    def test_variant_sibling_hydration_covers_ipad_storage_variants(self) -> None:
        donor = {
            "id": "product_ipad_donor",
            "sku_gt": "50806",
            "title": "Планшет Apple iPad Air 11 M3 2025 128Gb Wi-Fi + Cellular purple",
            "category_id": "cat-ipad-air-11-m3",
            "content": {
                "description": "iPad Air donor description",
                "media_images": [{"url": "https://cdn.example.test/ipad-purple.jpg", "selected": True}],
                "features": [{"code": "brand", "name": "Бренд", "value": "Apple"}],
            },
        }
        target = {
            "id": "product_ipad_target",
            "sku_gt": "50814",
            "title": "Планшет Apple iPad Air 11 M3 2025 256Gb + Cellular Wi-Fi purple",
            "category_id": "cat-ipad-air-11-m3",
            "content": {"features": []},
        }

        changed = catalog_exchange._hydrate_missing_content_from_variant_siblings([deepcopy(donor), deepcopy(target)])

        self.assertEqual(len(changed), 1)
        content = changed[0]["content"]
        self.assertEqual(content["description"], "iPad Air donor description")
        self.assertEqual(content["media_images"][0]["url"], "https://cdn.example.test/ipad-purple.jpg")
        self.assertEqual(content["features"][0]["value"], "Apple")
        self.assertEqual(content["source_values"]["media_images"]["variant_sibling"]["source_product_id"], "product_ipad_donor")

    def test_yandex_export_preview_filters_products_in_sql_by_selected_ids(self) -> None:
        product = {
            "id": "product_1",
            "title": "Meta Quest 3 128GB",
            "sku_gt": "GT-1",
            "category_id": "cat-vr",
            "status": "active",
            "content": {"features": [{"code": "brand", "name": "Бренд", "value": "Meta"}]},
        }

        with (
            patch.object(yandex_market, "query_products_full", return_value=[deepcopy(product)]) as query_mock,
            patch.object(yandex_market, "_load_products", side_effect=AssertionError("must not load full product table")),
            patch.object(yandex_market, "_load_nodes", return_value=[]),
            patch.object(yandex_market, "_load_category_mapping", return_value={}),
            patch.object(yandex_market, "_load_attr_mapping_rows", return_value={}),
            patch.object(yandex_market, "_load_attr_value_refs", return_value={}),
            patch.object(yandex_market, "_yandex_required_param_ids", return_value=set()),
        ):
            response = yandex_market.yandex_export_preview(
                yandex_market.ExportPreviewReq(product_ids=["product_1"], only_active=False, limit=10)
            )

        query_mock.assert_called_once_with(ids=["product_1"])
        self.assertEqual(response["count"], 1)
        self.assertEqual(response["items"][0]["payload_item"]["offerId"], "GT-1")
        self.assertEqual(response["items"][0]["payload_item"]["price"], "1000000")
        self.assertEqual(response["items"][0]["payload_item"]["price_source"], "technical_placeholder")
        self.assertEqual(response["items"][0]["product_title"], "Meta Quest 3 128GB")
        self.assertEqual(response["items"][0]["category_id"], "cat-vr")

    def test_yandex_export_preview_treats_description_and_media_as_system_content(self) -> None:
        product = {
            "id": "product_1",
            "title": "Meta Quest 3 128GB",
            "sku_gt": "GT-1",
            "category_id": "cat-vr",
            "status": "active",
            "content": {
                "description": "VR headset",
                "media_images": [
                    {"url": "https://cdn.example.test/skip.jpg", "selected": False, "export_order": 1},
                    {"url": "https://cdn.example.test/quest.jpg", "selected": True, "export_order": 2},
                ],
                "features": [{"code": "brand", "name": "Бренд", "value": "Meta"}],
            },
        }

        with (
            patch.object(yandex_market, "query_products_full", return_value=[deepcopy(product)]),
            patch.object(yandex_market, "_load_nodes", return_value=[]),
            patch.object(yandex_market, "_load_category_mapping", return_value={"cat-vr": {"yandex_market": "ym-vr"}}),
            patch.object(yandex_market, "_load_attr_mapping_rows", return_value={}),
            patch.object(yandex_market, "_load_attr_value_refs", return_value={}),
            patch.object(yandex_market, "_yandex_required_param_ids", return_value=set()),
        ):
            response = yandex_market.yandex_export_preview(
                yandex_market.ExportPreviewReq(product_ids=["product_1"], only_active=False, limit=10)
            )

        missing = response["items"][0]["missing"]
        self.assertNotIn("Не настроен блок 'Медиа' для Я.Маркет в маппинге", missing)
        self.assertNotIn("Не настроен блок 'Описание товара' для Я.Маркет в маппинге", missing)
        self.assertNotIn("Нет изображений (pictures)", missing)
        self.assertNotIn("Описание (аннотация) не заполнено", missing)
        self.assertEqual(response["items"][0]["payload_item"]["pictures"], ["https://cdn.example.test/quest.jpg"])
        self.assertEqual(response["items"][0]["payload_item"]["description"], "VR headset")

    def test_yandex_export_preview_blocks_empty_parameter_mapping(self) -> None:
        product = {
            "id": "product_1",
            "title": "Apple iPhone",
            "sku_gt": "GT-1",
            "category_id": "cat-phone",
            "status": "active",
            "content": {
                "description": "Phone",
                "media_images": [{"url": "https://cdn.example.test/p.jpg"}],
                "features": [
                    {"code": "brand", "name": "Бренд", "value": "Apple"},
                    {"code": "memory", "name": "Встроенная память", "value": "256 ГБ"},
                ],
            },
        }

        with (
            patch.object(yandex_market, "query_products_full", return_value=[deepcopy(product)]),
            patch.object(yandex_market, "_load_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(yandex_market, "_load_category_mapping", return_value={"cat-phone": {"yandex_market": "ym-phone"}}),
            patch.object(yandex_market, "_load_attr_mapping_rows", return_value={"cat-phone": []}),
            patch.object(yandex_market, "_load_attr_value_refs", return_value={}),
            patch.object(yandex_market, "_yandex_required_param_ids", return_value=set()),
        ):
            response = yandex_market.yandex_export_preview(
                yandex_market.ExportPreviewReq(product_ids=["product_1"], only_active=False, limit=10)
            )

        item = response["items"][0]
        self.assertEqual(item["ready"], False)
        self.assertEqual(item["payload_item"]["parameterValues"], [])
        self.assertEqual(item["payload_item"]["price"], "1000000")
        self.assertEqual(item["payload_item"]["price_source"], "technical_placeholder")
        self.assertIn("Нет сопоставленных PIM-параметров для Я.Маркет: соберите инфо-модель и свяжите параметры площадки", item["missing"])

    def test_yandex_offer_cards_sync_imports_marketplace_media_without_media_row(self) -> None:
        product = {
            "id": "product_1",
            "title": "Meta Quest 3 128GB",
            "sku_gt": "GT-1",
            "category_id": "cat-vr",
            "status": "active",
            "content": {"features": []},
        }
        saved_products: list[list[dict]] = []

        class FakeResponse:
            is_success = True
            content = b"{}"

            def json(self):
                return {"result": {"offerCards": [{"offerId": "GT-1", "parameterValues": []}]}}

        class FakeAsyncClient:
            def __init__(self, *_args, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            async def post(self, *_args, **_kwargs):
                return FakeResponse()

        async def fake_fetch_offer_mappings_once(**_kwargs):
            return {
                "ok": True,
                "body": {
                    "result": {
                        "offerMappings": [
                            {
                                "offer": {
                                    "offerId": "GT-1",
                                    "pictures": [
                                        {"url": "https://market.example.test/quest-main.jpg"},
                                        {"url": "https://market.example.test/quest-side.jpg"},
                                    ],
                                }
                            }
                        ]
                    }
                },
            }

        with (
            patch.object(yandex_market, "_load_products", return_value=[deepcopy(product)]),
            patch.object(yandex_market, "_load_group_name_by_id", return_value={}),
            patch.object(yandex_market, "_load_nodes", return_value=[]),
            patch.object(yandex_market, "_load_category_mapping", return_value={}),
            patch.object(yandex_market, "_load_attr_mapping_rows", return_value={"cat-vr": []}),
            patch.object(yandex_market, "_load_attr_value_refs", return_value={}),
            patch.object(yandex_market, "_load_offer_cards_doc", return_value={"items": {}}),
            patch.object(yandex_market, "_load_offer_mappings_doc", return_value={"items": {}}),
            patch.object(yandex_market, "_save_offer_cards_doc"),
            patch.object(yandex_market, "_save_offer_mappings_doc"),
            patch.object(yandex_market, "_save_products", side_effect=lambda items: saved_products.append(deepcopy(items))),
            patch.object(yandex_market, "_fetch_offer_mappings_once", side_effect=fake_fetch_offer_mappings_once),
            patch.object(yandex_market.httpx, "AsyncClient", FakeAsyncClient),
        ):
            response = asyncio.run(
                yandex_market.sync_offer_cards(
                    yandex_market.OfferCardsSyncReq(
                        product_ids=["product_1"],
                        token="token",
                        business_id="business_1",
                        store_id="store_1",
                        store_title="GT USD",
                    )
                )
            )

        self.assertEqual(response["updated_products"], 1)
        media = saved_products[0][0]["content"]["media_images"]
        self.assertEqual([x["url"] for x in media], [
            "https://market.example.test/quest-main.jpg",
            "https://market.example.test/quest-side.jpg",
        ])
        self.assertEqual(saved_products[0][0]["content"]["source_values"]["media_images"]["yandex_market"]["count"], 2)

    def test_yandex_marketplace_cache_omits_full_raw_mapping_payload(self) -> None:
        entry = {
            "offer": {
                "offerId": "GT-1",
                "description": "VR headset",
                "pictures": [{"url": "https://market.example.test/quest-main.jpg"}],
                "vendor": "Meta",
                "unused_raw_field": {"nested": ["x"] * 100},
            }
        }

        compact = yandex_market._compact_offer_mapping_for_cache(entry)

        self.assertEqual(compact["offerId"], "GT-1")
        self.assertEqual(compact["description"], "VR headset")
        self.assertEqual(compact["pictures"], ["https://market.example.test/quest-main.jpg"])
        self.assertEqual(compact["vendor"], "Meta")
        self.assertNotIn("unused_raw_field", json.dumps(compact, ensure_ascii=False))

    def test_ozon_attribute_values_cache_stores_raw_summary_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STORE_MARKETPLACE_RAW_PAGES", None)
            raw = ozon_market._attribute_values_raw_payload({"raw_pages": [{"items": list(range(100))}, {"items": [1]}]})

        self.assertEqual(raw, {"pages_count": 2})

    def test_ozon_products_sync_imports_marketplace_images_to_product_content(self) -> None:
        product = {
            "id": "product_1",
            "title": "Meta Quest 3 128GB",
            "sku_gt": "GT-1",
            "category_id": "cat-vr",
            "status": "active",
            "content": {"features": []},
        }
        saved_products: list[list[dict]] = []

        async def fake_post_api_key(path, _payload, _api_key, _client_id):
            if path == "/v3/product/info/list":
                return {
                    "items": [
                        {
                            "offer_id": "GT-1",
                            "sku": 123,
                            "primary_image": "https://ozon.example.test/quest-main.jpg",
                            "images": ["https://ozon.example.test/quest-side.jpg"],
                            "statuses": {"status": "active", "status_name": "Продается"},
                        }
                    ]
                }
            return {"products": []}

        with (
            patch.object(ozon_market, "_load_products", return_value=[deepcopy(product)]),
            patch.object(ozon_market, "_post_api_key", side_effect=fake_post_api_key),
            patch.object(ozon_market, "_save_doc"),
            patch.object(ozon_market, "_save_products", side_effect=lambda items: saved_products.append(deepcopy(items))),
        ):
            response = asyncio.run(
                ozon_market.sync_product_statuses(
                    ozon_market.OzonProductsSyncReq(
                        product_ids=["product_1"],
                        token="token",
                        client_id="client_1",
                        store_id="ozon_store_1",
                        store_title="Ozon",
                    )
                )
            )

        self.assertEqual(response["updated_products"], 1)
        media = saved_products[0][0]["content"]["media_images"]
        self.assertEqual([x["url"] for x in media], [
            "https://ozon.example.test/quest-main.jpg",
            "https://ozon.example.test/quest-side.jpg",
        ])
        self.assertEqual(media[0]["source"], "ozon")
        self.assertEqual(saved_products[0][0]["content"]["source_values"]["media_images"]["ozon"]["count"], 2)

    def test_ozon_media_merge_dedupes_same_image_across_cdn_hosts(self) -> None:
        existing = [
            {
                "url": "https://cdn1.ozone.ru/s3/multimedia-1-7/9127394143.jpg",
                "external_url": "https://cdn1.ozone.ru/s3/multimedia-1-7/9127394143.jpg",
                "source": "ozon",
            }
        ]

        merged = ozon_market._merge_marketplace_media_items(
            existing,
            [
                "https://ir.ozone.ru/s3/multimedia-1-7/9127394143.jpg",
                "https://ir.ozone.ru/s3/multimedia-1-y/9142586890.jpg",
            ],
            source="ozon",
            overwrite_existing=False,
        )

        self.assertEqual([item["url"] for item in merged], [
            "https://cdn1.ozone.ru/s3/multimedia-1-7/9127394143.jpg",
            "https://ir.ozone.ru/s3/multimedia-1-y/9142586890.jpg",
        ])

    def test_yandex_media_merge_dedupes_same_ozon_cdn_alias_when_reused(self) -> None:
        existing = [
            {
                "url": "https://cdn1.ozone.ru/s3/multimedia-1-7/9127394143.jpg",
                "external_url": "https://cdn1.ozone.ru/s3/multimedia-1-7/9127394143.jpg",
            }
        ]

        merged = yandex_market._merge_media_items(
            existing,
            [
                "https://ir.ozone.ru/s3/multimedia-1-7/9127394143.jpg",
                "https://ir.ozone.ru/s3/multimedia-1-y/9142586890.jpg",
            ],
            overwrite_existing=False,
        )

        self.assertEqual([item["url"] for item in merged], [
            "https://cdn1.ozone.ru/s3/multimedia-1-7/9127394143.jpg",
            "https://ir.ozone.ru/s3/multimedia-1-y/9142586890.jpg",
        ])

    def test_yandex_export_preview_blocks_unmapped_controlled_value(self) -> None:
        product = {
            "id": "product_1",
            "title": "Apple iPhone",
            "sku_gt": "GT-1",
            "category_id": "cat-phone",
            "status": "active",
            "content": {
                "description": "Phone",
                "media_images": [{"url": "https://cdn.example.test/p.jpg"}],
                "features": [
                    {"code": "brand", "name": "Бренд", "value": "Apple"},
                    {"code": "protection", "name": "Степень защиты", "value": "IP68 допускается погружение"},
                ],
            },
        }
        rows = [
            {
                "catalog_name": "Степень защиты",
                "provider_map": {
                    "yandex_market": {"id": "14876852", "name": "Степень защиты", "export": True}
                },
            }
        ]

        with (
            patch.object(yandex_market, "query_products_full", return_value=[deepcopy(product)]),
            patch.object(yandex_market, "_load_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(yandex_market, "_load_category_mapping", return_value={"cat-phone": {"yandex_market": "ym-phone"}}),
            patch.object(yandex_market, "_load_attr_mapping_rows", return_value={"cat-phone": rows}),
            patch.object(
                yandex_market,
                "_load_attr_value_refs",
                return_value={
                    "cat-phone": {
                        "catalog_params": {
                            "protection": {"catalog_name": "Степень защиты", "dict_id": "dict_protection"}
                        }
                    }
                },
            ),
            patch.object(yandex_market, "_yandex_required_param_ids", return_value=set()),
            patch.object(
                yandex_market,
                "provider_export_value_details",
                return_value={"value": "", "mapped": False, "reason": "value_missing"},
            ),
        ):
            response = yandex_market.yandex_export_preview(
                yandex_market.ExportPreviewReq(product_ids=["product_1"], only_active=False, limit=10)
            )

        item = response["items"][0]
        self.assertEqual(item["ready"], False)
        self.assertIn("Степень защиты: значение не сопоставлено с Я.Маркет", item["missing"])
        self.assertIn(
            {
                "code": "value_mapping_required",
                "message": "Степень защиты: значение не сопоставлено с Я.Маркет",
                "target": "values",
                "parameter": "Степень защиты",
            },
            item["missing_details"],
        )

    def test_yandex_export_preview_uses_provider_specific_output_value(self) -> None:
        product = {
            "id": "product_1",
            "title": "Apple iPhone",
            "sku_gt": "GT-1",
            "category_id": "cat-phone",
            "status": "active",
            "content": {
                "description": "Phone",
                "media_images": [{"url": "https://cdn.example.test/p.jpg"}],
                "features": [
                    {"code": "brand", "name": "Бренд", "value": "Apple"},
                    {"code": "protection", "name": "Степень защиты", "value": "IP68 допускается погружение"},
                ],
            },
        }
        rows = [
            {
                "catalog_name": "Степень защиты",
                "provider_map": {
                    "yandex_market": {"id": "14876852", "name": "Степень защиты", "export": True}
                },
            }
        ]
        calls: list[tuple[str, str, str]] = []

        def export_value(dict_id, provider, value):
            calls.append((dict_id, provider, value))
            if dict_id == "dict_protection":
                return {"value": "IP68", "mapped": True, "reason": "export_map"}
            return {"value": str(value), "mapped": True, "reason": "free_text"}

        with (
            patch.object(yandex_market, "query_products_full", return_value=[deepcopy(product)]),
            patch.object(yandex_market, "_load_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(yandex_market, "_load_category_mapping", return_value={"cat-phone": {"yandex_market": "ym-phone"}}),
            patch.object(yandex_market, "_load_attr_mapping_rows", return_value={"cat-phone": rows}),
            patch.object(
                yandex_market,
                "_load_attr_value_refs",
                return_value={
                    "cat-phone": {
                        "catalog_params": {
                            "protection": {"catalog_name": "Степень защиты", "dict_id": "dict_protection"}
                        }
                    }
                },
            ),
            patch.object(yandex_market, "_yandex_required_param_ids", return_value=set()),
            patch.object(yandex_market, "provider_export_value_details", side_effect=export_value),
        ):
            response = yandex_market.yandex_export_preview(
                yandex_market.ExportPreviewReq(product_ids=["product_1"], only_active=False, limit=10)
            )

        item = response["items"][0]
        values = {
            str(param["parameterId"]): param["values"][0]["value"]
            for param in item["payload_item"]["parameterValues"]
        }
        self.assertEqual(values["14876852"], "IP68")
        self.assertNotEqual(values["14876852"], "IP68 допускается погружение")
        self.assertIn(("dict_protection", "yandex_market", "IP68 допускается погружение"), calls)
        self.assertNotIn("Степень защиты: значение не сопоставлено с Я.Маркет", item["missing"])

    def test_ozon_export_preview_blocks_unmapped_controlled_value(self) -> None:
        product = {
            "id": "product_1",
            "sku_gt": "GT-1",
            "title": "Смартфон Apple iPhone 17 Pro 256Gb",
            "category_id": "cat-phone",
            "status": "active",
            "content": {
                "media_images": [{"url": "https://cdn.example.test/p.jpg"}],
                "description": "Phone",
                "features": [
                    {"code": "brand", "name": "Бренд", "value": "Apple"},
                    {"code": "protection", "name": "Степень защиты", "value": "IP68 допускается погружение"},
                ],
            },
        }
        rows = [
            {"catalog_name": "Бренд", "provider_map": {"ozon": {"id": "85", "name": "Бренд", "export": True}}},
            {"catalog_name": "Степень защиты", "provider_map": {"ozon": {"id": "5269", "name": "Степень защиты", "export": True}}},
        ]

        with (
            patch.object(catalog_exchange, "query_products_full", return_value=[deepcopy(product)]),
            patch.object(catalog_exchange, "_load_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(catalog_exchange, "_load_category_mapping", return_value={"cat-phone": {"ozon": "oz-phone"}}),
            patch.object(catalog_exchange, "_load_attr_mapping_rows", return_value={"cat-phone": rows}),
            patch.object(catalog_exchange, "dict_id_for_product_feature", side_effect=lambda product, name: "dict_protection" if name == "Степень защиты" else ""),
            patch.object(
                catalog_exchange,
                "provider_export_value_details",
                side_effect=lambda dict_id, provider, value: {"value": "", "mapped": False} if dict_id == "dict_protection" else {"value": str(value), "mapped": True},
            ),
        ):
            response = catalog_exchange._ozon_export_preview(["product_1"], 10)

        item = response["items"][0]
        self.assertEqual(item["ready"], False)
        self.assertIn("Степень защиты: значение не сопоставлено с Ozon", item["missing"])

    def test_ozon_export_preview_points_missing_media_to_marketplace_import_first(self) -> None:
        product = {
            "id": "product_1",
            "sku_gt": "GT-1",
            "title": "Смартфон Apple iPhone 17 Pro 256Gb",
            "category_id": "cat-phone",
            "status": "active",
            "content": {
                "description": "Phone",
                "features": [{"code": "brand", "name": "Бренд", "value": "Apple"}],
            },
        }

        with (
            patch.object(catalog_exchange, "query_products_full", return_value=[deepcopy(product)]),
            patch.object(catalog_exchange, "_load_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(catalog_exchange, "_load_category_mapping", return_value={"cat-phone": {"ozon": "oz-phone"}}),
            patch.object(catalog_exchange, "_load_attr_mapping_rows", return_value={"cat-phone": []}),
            patch.object(catalog_exchange, "_confirmed_links_for_product", return_value=[]),
        ):
            response = catalog_exchange._ozon_export_preview(["product_1"], 10)

        detail = response["items"][0]["missing_details"][0]
        self.assertEqual(detail["code"], "marketplace_media_import_required")
        self.assertEqual(detail["target"], "import")
        self.assertIn("импортируйте фото", detail["message"])

    def test_ozon_export_preview_classifies_review_media_as_media_check(self) -> None:
        product = {
            "id": "product_1",
            "sku_gt": "GT-1",
            "title": "Смартфон Apple iPhone 17 Pro 256Gb",
            "category_id": "cat-phone",
            "status": "active",
            "content": {
                "description": "Phone",
                "media_images": [
                    {
                        "url": "https://restore.example.test/iphone.jpg",
                        "status": "needs_review",
                        "selected": True,
                    }
                ],
                "features": [{"code": "brand", "name": "Бренд", "value": "Apple"}],
            },
        }

        with (
            patch.object(catalog_exchange, "query_products_full", return_value=[deepcopy(product)]),
            patch.object(catalog_exchange, "_load_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(catalog_exchange, "_load_category_mapping", return_value={"cat-phone": {"ozon": "oz-phone"}}),
            patch.object(catalog_exchange, "_load_attr_mapping_rows", return_value={"cat-phone": []}),
        ):
            response = catalog_exchange._ozon_export_preview(["product_1"], 10)

        item = response["items"][0]
        self.assertEqual(item["ready"], False)
        detail = item["missing_details"][0]
        self.assertEqual(detail["code"], "media_review_required")
        self.assertEqual(detail["target"], "media")
        self.assertIn("требует проверки", detail["message"])

    def test_ozon_export_preview_uses_provider_specific_output_value(self) -> None:
        product = {
            "id": "product_1",
            "sku_gt": "GT-1",
            "title": "Смартфон Apple iPhone 17 Pro 256Gb",
            "category_id": "cat-phone",
            "status": "active",
            "content": {
                "media_images": [{"url": "https://cdn.example.test/p.jpg"}],
                "description": "Phone",
                "features": [
                    {"code": "brand", "name": "Бренд", "value": "Apple"},
                    {"code": "protection", "name": "Степень защиты", "value": "IP68 допускается погружение"},
                ],
            },
        }
        rows = [
            {"catalog_name": "Бренд", "provider_map": {"ozon": {"id": "85", "name": "Бренд", "export": True}}},
            {"catalog_name": "Степень защиты", "provider_map": {"ozon": {"id": "5269", "name": "Степень защиты", "export": True}}},
        ]
        calls: list[tuple[str, str, str]] = []

        def export_value(dict_id, provider, value):
            calls.append((dict_id, provider, value))
            if dict_id == "dict_protection":
                return {"value": "IP68", "mapped": True, "reason": "export_map"}
            return {"value": str(value), "mapped": True, "reason": "free_text"}

        with (
            patch.object(catalog_exchange, "query_products_full", return_value=[deepcopy(product)]),
            patch.object(catalog_exchange, "_load_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(catalog_exchange, "_load_category_mapping", return_value={"cat-phone": {"ozon": "oz-phone"}}),
            patch.object(catalog_exchange, "_load_attr_mapping_rows", return_value={"cat-phone": rows}),
            patch.object(catalog_exchange, "dict_id_for_product_feature", side_effect=lambda product, name: "dict_protection" if name == "Степень защиты" else ""),
            patch.object(catalog_exchange, "provider_export_value_details", side_effect=export_value),
        ):
            response = catalog_exchange._ozon_export_preview(["product_1"], 10)

        item = response["items"][0]
        attrs = {str(attr["id"]): attr["values"][0]["value"] for attr in item["payload_item"]["attributes"]}
        self.assertEqual(attrs["5269"], "IP68")
        self.assertNotEqual(attrs["5269"], "IP68 допускается погружение")
        self.assertIn(("dict_protection", "ozon", "IP68 допускается погружение"), calls)
        self.assertNotIn("Степень защиты: значение не сопоставлено с Ozon", item["missing"])

    def test_ozon_export_batch_does_not_block_on_tree_source_only(self) -> None:
        preview = {
            "count": 1,
            "ready_count": 1,
            "not_ready_count": 0,
            "items": [
                {
                    "product_id": "product_1",
                    "product_title": "TV Box",
                    "category_id": "cat-tv",
                    "ready": True,
                    "missing": [],
                    "payload_item": {
                        "offer_id": "GT-1",
                        "description_category_id": "17028924",
                    },
                }
            ],
        }

        with patch.object(
            catalog_exchange,
            "_ozon_category_store_sources",
            return_value={"source_store_ids": ["ozon-store-b"], "source_titles": ["Тестовый магазин"]},
        ):
            batch = catalog_exchange._export_batch_from_preview(
                provider="ozon",
                store={"id": "ozon-store-a", "title": "Global Trade AE"},
                preview=preview,
            )

        self.assertEqual(batch["status"], "ready")
        self.assertEqual(batch["ready_count"], 1)
        self.assertEqual(batch["not_ready_count"], 0)
        self.assertEqual(batch["blockers"], [])

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

    def test_info_model_draft_from_marketplaces_creates_channel_candidates(self) -> None:
        from app.core.info_models import draft_service

        templates_db = {"templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}}
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        def read_doc(path, default=None):
            path_text = str(path)
            if path_text.endswith("category_parameters.json"):
                return {
                    "items": {
                        "ym-smart-ring": {
                            "raw": {
                                "result": {
                                    "parameters": [
                                        {"id": "brand", "name": "Бренд", "required": True, "type": "ENUM", "values": [{"name": "Oura"}]},
                                        {"id": "ring_size", "name": "Размер кольца", "required": True, "type": "ENUM", "values": [{"name": "10"}]},
                                        {
                                            "id": "material",
                                            "name": "Материал",
                                            "required": False,
                                            "type": "ENUM",
                                            "values": [{"name": f"Справочное значение материала номер {idx}"} for idx in range(60)],
                                        },
                                        {"id": "thumbnail", "name": "Изображение для миниатюры", "required": False, "type": "String"},
                                        {"id": "rich_content", "name": "Rich-контент JSON", "required": False, "type": "String"},
                                    ]
                                }
                            }
                        }
                    }
                }
            if path_text.endswith("category_attributes.json"):
                return {
                    "items": {
                        "ozon-smart-ring": {
                            "attributes": [
                                {"id": "battery", "name": "Время работы", "is_required": False, "type": "String"},
                                {"id": "ring_size", "name": "Размер кольца", "is_required": True, "type": "String"},
                            ]
                        }
                    }
                }
            return deepcopy(default)

        with (
            patch.object(draft_service, "load_templates_db", return_value=deepcopy(templates_db)),
            patch.object(draft_service, "save_templates_db", side_effect=save),
            patch.object(draft_service, "query_products_full", return_value=[]),
            patch.object(draft_service, "load_catalog_nodes", return_value=[{"id": "cat-rings", "parent_id": None, "name": "Умные кольца"}]),
            patch.object(draft_service, "load_category_mappings", return_value={"cat-rings": {"yandex_market": "ym-smart-ring", "ozon": "ozon-smart-ring"}}),
            patch.object(draft_service, "read_doc", side_effect=read_doc),
            patch.object(
                draft_service,
                "new_id",
                side_effect=[
                    "tpl-draft-rings",
                    "cand-brand",
                    "cand-size-ym",
                    "cand-material",
                    "cand-thumbnail",
                    "cand-rich",
                    "cand-battery",
                    "cand-size-ozon",
                ],
            ),
            patch.object(draft_service, "now_iso", return_value="2026-04-27T00:00:00+00:00"),
        ):
            response = draft_service.create_draft_from_sources("cat-rings", {"sources": ["marketplaces"]})

        names = {candidate["name"] for candidate in response["candidates"]}
        self.assertIn("Бренд", names)
        self.assertIn("Размер кольца", names)
        self.assertIn("Время работы", names)
        self.assertIn("Материал", names)
        self.assertIn("Изображение для миниатюры", names)
        self.assertIn("Rich-контент JSON", names)
        material = next(candidate for candidate in response["candidates"] if candidate["name"] == "Материал")
        self.assertEqual(material["type"], "select")
        self.assertEqual(material["examples"], [])
        self.assertEqual(material["sources"][0]["examples"], [])
        thumbnail = next(candidate for candidate in response["candidates"] if candidate["name"] == "Изображение для миниатюры")
        self.assertEqual(thumbnail["field_layer"], "media")
        rich = next(candidate for candidate in response["candidates"] if candidate["name"] == "Rich-контент JSON")
        self.assertEqual(rich["field_layer"], "rich_content")
        self.assertEqual(rich["group"], "Rich-content")
        ring_size = next(candidate for candidate in response["candidates"] if candidate["name"] == "Размер кольца")
        self.assertEqual(ring_size["status"], "needs_review")
        self.assertEqual({source["provider"] for source in ring_size["sources"]}, {"yandex_market", "ozon"})
        self.assertEqual({source["field_title"] for source in ring_size["sources"]}, {"Размер кольца"})
        self.assertEqual(ring_size["source_summary"]["by_kind"], {"marketplace": 2})
        self.assertTrue(any(flag["code"] == "marketplace_required" for flag in ring_size["review_flags"]))
        self.assertEqual(saved["templates"]["tpl-draft-rings"]["meta"]["info_model"]["draft_sources"], ["marketplaces"])

    def test_info_model_draft_from_competitors_creates_review_candidates(self) -> None:
        from app.core.info_models import draft_service

        templates_db = {"templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}}
        products = [
            {
                "id": "product_iphone_1",
                "category_id": "cat-phones",
                "title": "Apple iPhone 17e 256Gb",
                "content": {
                    "features": [{"name": "Встроенная память", "value": "256 ГБ"}],
                    "source_evidence": {
                        "competitors": {
                            "restore": {
                                "unmatched_specs": {
                                    "Яркость": "1200 нит",
                                    "Объем встроенной памяти": "256 ГБ",
                                }
                            },
                            "store77": {
                                "unmatched_specs": {
                                    "Яркость": "1200 нит",
                                    "Датчики": "акселерометр",
                                }
                            },
                        }
                    },
                },
            }
        ]
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        def suggest_attributes(query, limit=8):
            normalized = str(query or "").strip().lower()
            if normalized in {"встроенная память", "vstroennaya_pamyat"}:
                return [
                    {
                        "id": "attr-global-storage",
                        "title": "Встроенная память",
                        "code": "vstroennaya_pamyat",
                        "type": "select",
                        "scope": "feature",
                        "dict_id": "dict_vstroennaya_pamyat",
                    }
                ]
            return []

        with (
            patch.object(draft_service, "load_templates_db", return_value=deepcopy(templates_db)),
            patch.object(draft_service, "save_templates_db", side_effect=save),
            patch.object(draft_service, "query_products_full", return_value=deepcopy(products)),
            patch.object(draft_service, "new_id", side_effect=["tpl-draft-phones", "cand-product-storage", "cand-brightness", "cand-storage", "cand-sensors"]),
            patch.object(draft_service, "now_iso", return_value="2026-05-20T00:00:00+00:00"),
            patch.object(draft_service, "suggest_attributes", side_effect=suggest_attributes),
        ):
            response = draft_service.create_draft_from_sources("cat-phones", {"sources": ["products", "competitors"]})

        by_name = {candidate["name"]: candidate for candidate in response["candidates"]}
        self.assertIn("Яркость", by_name)
        self.assertIn("Датчики", by_name)
        self.assertIn("Встроенная память", by_name)
        brightness = by_name["Яркость"]
        self.assertEqual(brightness["status"], "needs_review")
        self.assertEqual(brightness["group"], "Данные конкурентов")
        self.assertEqual({source["provider"] for source in brightness["sources"]}, {"restore", "store77"})
        self.assertEqual(brightness["source_summary"]["by_kind"], {"competitor": 2})
        self.assertTrue(any(flag["code"] == "competitor_only" for flag in brightness["review_flags"]))
        storage = by_name["Встроенная память"]
        self.assertEqual(storage["code"], "vstroennaya_pamyat")
        self.assertTrue(any(source["kind"] == "competitor" for source in storage["sources"]))
        self.assertEqual(storage["suggested_action"], "reuse_existing")
        self.assertEqual(storage["global_match"]["id"], "attr-global-storage")
        self.assertEqual(storage["source_summary"]["by_kind"], {"product": 1, "competitor": 1})
        self.assertEqual(brightness["suggested_action"], "create_attribute")
        self.assertNotIn("global_match", brightness)
        self.assertEqual(saved["templates"]["tpl-draft-phones"]["meta"]["info_model"]["draft_sources"], ["products", "competitors"])

    def test_info_model_draft_uses_nearest_ancestor_marketplace_mapping(self) -> None:
        from app.core.info_models import draft_service

        templates_db = {"templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}}
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        def read_doc(path, default=None):
            if str(path).endswith("category_parameters.json"):
                return {
                    "items": {
                        "ym-smart-rings": {
                            "raw": {
                                "result": {
                                    "parameters": [
                                        {"id": "ring_size", "name": "Размер кольца", "required": True, "type": "ENUM", "values": [{"name": "10"}]},
                                    ]
                                }
                            }
                        }
                    }
                }
            if str(path).endswith("category_attributes.json"):
                return {"items": {}}
            return deepcopy(default)

        with (
            patch.object(draft_service, "load_templates_db", return_value=deepcopy(templates_db)),
            patch.object(draft_service, "save_templates_db", side_effect=save),
            patch.object(draft_service, "query_products_full", return_value=[]),
            patch.object(
                draft_service,
                "load_catalog_nodes",
                return_value=[
                    {"id": "cat-rings", "parent_id": None, "name": "Умные кольца"},
                    {"id": "cat-oura", "parent_id": "cat-rings", "name": "Oura Ring 4"},
                ],
            ),
            patch.object(draft_service, "load_category_mappings", return_value={"cat-rings": {"yandex_market": "ym-smart-rings"}}),
            patch.object(draft_service, "read_doc", side_effect=read_doc),
            patch.object(draft_service, "new_id", side_effect=["tpl-draft-oura", "cand-size"]),
            patch.object(draft_service, "now_iso", return_value="2026-04-27T00:00:00+00:00"),
        ):
            response = draft_service.create_draft_from_sources("cat-oura", {"sources": ["marketplaces"]})

        self.assertEqual(response["template"]["id"], "tpl-draft-oura")
        self.assertEqual([candidate["name"] for candidate in response["candidates"]], ["Размер кольца"])
        self.assertEqual(saved["templates"]["tpl-draft-oura"]["meta"]["info_model"]["status"], "draft")

    def test_info_model_draft_merges_ozon_title_into_product_title_field(self) -> None:
        from app.core.info_models import draft_service

        templates_db = {"templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}}
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        def read_doc(path, default=None):
            if str(path).endswith("category_parameters.json"):
                return {
                    "items": {
                        "ym-phone": {
                            "raw": {
                                "result": {
                                    "parameters": [
                                        {"id": "name", "name": "Наименование товара", "required": False, "type": "TEXT"},
                                    ]
                                }
                            }
                        }
                    }
                }
            if str(path).endswith("category_attributes.json"):
                return {
                    "items": {
                        "oz-phone": {
                            "attributes": [
                                {"id": "4180", "name": "Название", "required": False, "type": "String"},
                            ]
                        }
                    }
                }
            return deepcopy(default)

        with (
            patch.object(draft_service, "load_templates_db", return_value=deepcopy(templates_db)),
            patch.object(draft_service, "save_templates_db", side_effect=save),
            patch.object(draft_service, "query_products_full", return_value=[]),
            patch.object(draft_service, "load_catalog_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(draft_service, "load_category_mappings", return_value={"cat-phone": {"yandex_market": "ym-phone", "ozon": "oz-phone"}}),
            patch.object(draft_service, "read_doc", side_effect=read_doc),
            patch.object(draft_service, "new_id", side_effect=["tpl-draft-phone", "cand-name-ym", "cand-name-ozon"]),
            patch.object(draft_service, "now_iso", return_value="2026-05-27T00:00:00+00:00"),
        ):
            response = draft_service.create_draft_from_sources("cat-phone", {"sources": ["marketplaces"]})

        self.assertEqual(len(response["candidates"]), 1)
        candidate = response["candidates"][0]
        self.assertEqual(candidate["name"], "Наименование товара")
        self.assertEqual(candidate["code"], "naimenovanie_tovara")
        self.assertEqual({source["provider"] for source in candidate["sources"]}, {"yandex_market", "ozon"})
        ozon_source = next(source for source in candidate["sources"] if source["provider"] == "ozon")
        self.assertEqual(ozon_source["field_name"], "4180")
        self.assertEqual(ozon_source["field_title"], "Название")

    def test_info_model_draft_merges_only_explicit_semantic_aliases(self) -> None:
        from app.core.info_models import draft_service

        templates_db = {"templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}}
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        def read_doc(path, default=None):
            if str(path).endswith("category_parameters.json"):
                return {
                    "items": {
                        "ym-phone": {
                            "raw": {
                                "result": {
                                    "parameters": [
                                        {"id": "sim_count", "name": "Кол-во SIM", "required": False, "type": "ENUM"},
                                        {"id": "os", "name": "Операционная система", "required": False, "type": "ENUM"},
                                        {"id": "os_version", "name": "Версия ОС", "required": False, "type": "TEXT"},
                                    ]
                                }
                            }
                        }
                    }
                }
            if str(path).endswith("category_attributes.json"):
                return {
                    "items": {
                        "oz-phone": {
                            "attributes": [
                                {"id": "sim_cards_count", "name": "Количество SIM-карт", "required": False, "type": "String"},
                                {"id": "ios_version", "name": "Версия iOS", "required": False, "type": "String"},
                            ]
                        }
                    }
                }
            return deepcopy(default)

        with (
            patch.object(draft_service, "load_templates_db", return_value=deepcopy(templates_db)),
            patch.object(draft_service, "save_templates_db", side_effect=save),
            patch.object(draft_service, "query_products_full", return_value=[]),
            patch.object(draft_service, "load_catalog_nodes", return_value=[{"id": "cat-phone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(draft_service, "load_category_mappings", return_value={"cat-phone": {"yandex_market": "ym-phone", "ozon": "oz-phone"}}),
            patch.object(draft_service, "read_doc", side_effect=read_doc),
            patch.object(
                draft_service,
                "new_id",
                side_effect=["tpl-draft-phone", "cand-sim-ym", "cand-os", "cand-os-version", "cand-sim-ozon", "cand-ios-version"],
            ),
            patch.object(draft_service, "now_iso", return_value="2026-05-27T00:00:00+00:00"),
        ):
            response = draft_service.create_draft_from_sources("cat-phone", {"sources": ["marketplaces"]})

        by_name = {candidate["name"]: candidate for candidate in response["candidates"]}
        self.assertEqual(by_name["Количество SIM-карт"]["code"], "kolichestvo_sim_kart")
        self.assertEqual({source["field_title"] for source in by_name["Количество SIM-карт"]["sources"]}, {"Кол-во SIM", "Количество SIM-карт"})
        self.assertTrue(any(flag["code"] == "merged_alias_sources" for flag in by_name["Количество SIM-карт"]["review_flags"]))
        self.assertIn("Операционная система", by_name)
        self.assertIn("Версия ОС", by_name)
        self.assertIn("Версия iOS", by_name)
        self.assertEqual(len(response["candidates"]), 4)

    def test_info_model_candidate_update_can_clear_wrong_global_match(self) -> None:
        from app.core.info_models import draft_service

        templates_db = {
            "templates": {
                "tpl-draft": {
                    "id": "tpl-draft",
                    "category_id": "cat-test",
                    "name": "Draft",
                    "meta": {
                        "info_model": {
                            "status": "draft",
                            "candidates": [
                                {
                                    "id": "cand-color",
                                    "name": "Цвет",
                                    "code": "color",
                                    "type": "select",
                                    "group": "Характеристики",
                                    "required": False,
                                    "confidence": 0.84,
                                    "status": "needs_review",
                                    "examples": ["Orange"],
                                    "sources": [
                                        {
                                            "kind": "competitor",
                                            "provider": "restore",
                                            "source_name": "restore",
                                            "field_name": "Цвет",
                                            "examples": ["Orange"],
                                            "count": 1,
                                        }
                                    ],
                                    "global_match": {"id": "attr-wrong", "title": "Цвет корпуса", "score": 0.84, "reason": "similar_title"},
                                    "suggested_action": "reuse_existing",
                                }
                            ],
                        }
                    },
                }
            },
            "attributes": {"tpl-draft": []},
            "category_to_template": {"cat-test": "tpl-draft"},
            "category_to_templates": {"cat-test": ["tpl-draft"]},
        }
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        with (
            patch.object(draft_service, "load_templates_db", return_value=deepcopy(templates_db)),
            patch.object(draft_service, "save_templates_db", side_effect=save),
            patch.object(draft_service, "now_iso", return_value="2026-05-24T00:00:00+00:00"),
        ):
            response = draft_service.update_draft_candidate(
                "tpl-draft",
                "cand-color",
                {"global_match": None, "suggested_action": "create_attribute"},
            )

        candidate = response["candidate"]
        self.assertNotIn("global_match", candidate)
        self.assertEqual(candidate["suggested_action"], "create_attribute")
        self.assertTrue(any(flag["code"] == "competitor_only" for flag in candidate["review_flags"]))
        saved_candidate = saved["templates"]["tpl-draft"]["meta"]["info_model"]["candidates"][0]
        self.assertNotIn("global_match", saved_candidate)

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
            patch.object(
                draft_service,
                "ensure_global_attribute",
                return_value={"id": "global-memory", "dict_id": "dict_vstroennaya_pamyat"},
            ),
            patch.object(draft_service, "now_iso", return_value="2026-04-27T01:00:00+00:00"),
        ):
            response = draft_service.approve_draft("tpl-draft-vr")

        self.assertEqual(response["info_model"]["status"], "approved")
        attrs = saved["attributes"]["tpl-draft-vr"]
        self.assertEqual(len(attrs), 1)
        self.assertEqual(attrs[0]["name"], "Встроенная память")
        self.assertEqual(attrs[0]["attribute_id"], "global-memory")
        self.assertEqual(attrs[0]["options"]["dict_id"], "dict_vstroennaya_pamyat")
        self.assertEqual(attrs[0]["options"]["source_candidates"], ["cand-memory"])
        self.assertEqual(saved["templates"]["tpl-draft-vr"]["meta"]["info_model"]["approved_at"], "2026-04-27T01:00:00+00:00")

    def test_info_model_approve_reuses_global_attribute_for_synonymous_fields(self) -> None:
        from app.core.info_models import draft_service

        templates_db = {
            "templates": {
                "tpl-draft-devices": {
                    "id": "tpl-draft-devices",
                    "category_id": "cat-devices",
                    "name": "Draft: Devices",
                    "meta": {
                        "info_model": {
                            "status": "draft",
                            "candidates": [
                                {
                                    "id": "cand-storage-1",
                                    "name": "Встроенная память",
                                    "code": "vstroennaya_pamyat",
                                    "type": "select",
                                    "group": "Характеристики",
                                    "required": True,
                                    "status": "accepted",
                                },
                                {
                                    "id": "cand-storage-2",
                                    "name": "Объем встроенной памяти",
                                    "code": "obem_vstroennoy_pamyati",
                                    "type": "select",
                                    "group": "Требования площадок",
                                    "required": False,
                                    "status": "accepted",
                                },
                                {
                                    "id": "cand-ram",
                                    "name": "Объем оперативной памяти",
                                    "code": "obem_operativnoy_pamyati",
                                    "type": "select",
                                    "group": "Характеристики",
                                    "required": False,
                                    "status": "accepted",
                                },
                            ],
                        }
                    },
                }
            },
            "attributes": {"tpl-draft-devices": []},
            "category_to_template": {"cat-devices": "tpl-draft-devices"},
            "category_to_templates": {"cat-devices": ["tpl-draft-devices"]},
        }
        saved: dict[str, object] = {}
        created_refs: list[tuple[str, str, str]] = []

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        def ensure_global(title: str, type_: str, code: str, scope: str):
            created_refs.append((title, code, scope))
            return {"id": f"global-{code}", "dict_id": f"dict_{code}"}

        with (
            patch.object(draft_service, "load_templates_db", return_value=deepcopy(templates_db)),
            patch.object(draft_service, "save_templates_db", side_effect=save),
            patch.object(draft_service, "new_id", side_effect=["attr-storage", "attr-ram"]),
            patch.object(draft_service, "ensure_global_attribute", side_effect=ensure_global),
            patch.object(draft_service, "now_iso", return_value="2026-04-27T01:00:00+00:00"),
        ):
            response = draft_service.approve_draft("tpl-draft-devices")

        attrs = response["attributes"]
        self.assertEqual([attr["code"] for attr in attrs], ["vstroennaya_pamyat", "operativnaya_pamyat"])
        storage = attrs[0]
        self.assertEqual(storage["name"], "Встроенная память")
        self.assertEqual(storage["attribute_id"], "global-vstroennaya_pamyat")
        self.assertEqual(storage["options"]["dict_id"], "dict_vstroennaya_pamyat")
        self.assertEqual(storage["options"]["source_candidates"], ["cand-storage-1", "cand-storage-2"])
        self.assertEqual(attrs[1]["name"], "Оперативная память")
        self.assertEqual(
            created_refs,
            [
                ("Встроенная память", "vstroennaya_pamyat", "feature"),
                ("Встроенная память", "vstroennaya_pamyat", "feature"),
                ("Оперативная память", "operativnaya_pamyat", "feature"),
            ],
        )
        self.assertEqual(saved["attributes"]["tpl-draft-devices"][0]["attribute_id"], "global-vstroennaya_pamyat")


if __name__ == "__main__":
    unittest.main()
