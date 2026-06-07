from __future__ import annotations

from app.core.export_contracts import export_payload_audit


def test_export_payload_audit_normalizes_missing_sources_and_counts():
    payload = {
        "price_source": "",
        "media_count": 3,
        "attributes_total": 5,
        "attributes_with_source": 2,
        "missing_source": [" Цвет ", "Цвет", "", "Память", *[f"extra_{idx}" for idx in range(20)]],
    }

    audit = export_payload_audit(payload)

    assert audit["price_source"] == "unknown"
    assert audit["media_count"] == 3
    assert audit["attributes_total"] == 5
    assert audit["attributes_with_source"] == 2
    assert audit["attributes_without_source"] == 3
    assert audit["missing_source"][:2] == ["Цвет", "Память"]
    assert len(audit["missing_source"]) == 12
