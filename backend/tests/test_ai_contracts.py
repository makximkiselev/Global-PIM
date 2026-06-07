from __future__ import annotations

from app.core.ai_contracts import (
    json_object_from_text,
    parse_attribute_row_suggestions,
    parse_competitor_candidate_suggestions,
    parse_competitor_spec_mapping_suggestions,
    parse_value_pair_suggestions,
)


def test_json_object_from_text_extracts_fenced_json():
    assert json_object_from_text('```json\n{"ok": true}\n```') == {"ok": True}


def test_parse_value_pair_suggestions_clamps_and_drops_invalid_items():
    payload = """
    {"pairs":[
      {"canonical":" Desert Titanium ","output":"титановый пустынный","confidence":0.82,"reason":"same color"},
      {"canonical":"","output":"missing canonical","confidence":0.9},
      {"canonical":"Black","output":"","confidence":0.9}
    ]}
    """

    assert parse_value_pair_suggestions(payload) == [
        {
            "canonical": "Desert Titanium",
            "output": "титановый пустынный",
            "confidence": 0.82,
            "reason": "same color",
        }
    ]


def test_parse_attribute_row_suggestions_accepts_prompt_list_format():
    payload = '{"rows":[["Операционная система","34812830"],["Название товара",null],["", "bad"]]}'

    assert parse_attribute_row_suggestions(payload) == [
        {"catalog_name": "Операционная система", "group": "", "yandex_id": "34812830", "confirmed": True},
        {"catalog_name": "Название товара", "group": "", "yandex_id": "", "confirmed": True},
    ]


def test_parse_attribute_row_suggestions_accepts_single_dict_aliases():
    payload = '{"pim_name":" Количество SIM-карт ","provider_id":"sim_count","confirmed":false}'

    assert parse_attribute_row_suggestions(payload) == [
        {"catalog_name": "Количество SIM-карт", "group": "", "yandex_id": "sim_count", "confirmed": False}
    ]


def test_parse_competitor_candidate_suggestions_accepts_candidates_and_items_alias():
    payload = """
    ```json
    {"items":[
      {"url":" https://store77.net/item ","title":" iPhone 17 Pro ","brand":"Apple","sku":"A1","reason":"pattern"},
      {"url":"","title":"missing url"}
    ]}
    ```
    """

    assert parse_competitor_candidate_suggestions(payload) == [
        {
            "url": "https://store77.net/item",
            "title": "iPhone 17 Pro",
            "brand": "Apple",
            "sku": "A1",
            "reason": "pattern",
        }
    ]


def test_parse_competitor_spec_mapping_suggestions_accepts_compact_aliases():
    payload = """
    {"items":[
      {"sid":"restore","n":" Операционная система ","v":"iOS","action":"map_existing","c":"os","tn":"OS","confidence":1.2},
      {"sid":"","n":"missing source","v":"bad","action":"ignore","confidence":0.5}
    ]}
    """

    assert parse_competitor_spec_mapping_suggestions(payload) == [
        {
            "source_id": "restore",
            "source_name": "Операционная система",
            "raw_value": "iOS",
            "action": "map_existing",
            "target_code": "os",
            "target_name": "OS",
            "confidence": 1.0,
            "reason": "",
        }
    ]
