from __future__ import annotations

from app.core.ai_contracts import json_object_from_text, parse_value_pair_suggestions


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
