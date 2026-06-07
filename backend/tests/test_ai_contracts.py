from __future__ import annotations

from app.core.ai_contracts import json_object_from_text, parse_attribute_row_suggestions, parse_value_pair_suggestions


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
