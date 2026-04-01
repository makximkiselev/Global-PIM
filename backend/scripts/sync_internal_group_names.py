from __future__ import annotations

from app.core.json_store import read_doc, write_doc, DATA_DIR

PRODUCTS_PATH = DATA_DIR / "products.json"
GROUPS_PATH = DATA_DIR / "product_groups.json"


def main() -> None:
    groups_doc = read_doc(GROUPS_PATH, default={"items": []})
    group_items = groups_doc.get("items") if isinstance(groups_doc, dict) else []
    group_name_by_id = {
        str(row.get("id") or "").strip(): str(row.get("name") or "").strip()
        for row in (group_items or [])
        if isinstance(row, dict) and str(row.get("id") or "").strip() and str(row.get("name") or "").strip()
    }

    products_doc = read_doc(PRODUCTS_PATH, default={"items": []})
    items = products_doc.get("items") if isinstance(products_doc, dict) else []
    if not isinstance(items, list):
        print("products_changed=0 features_changed=0")
        return

    products_changed = 0
    features_changed = 0
    source_values_changed = 0
    for product in items:
        if not isinstance(product, dict):
            continue
        group_id = str(product.get("group_id") or "").strip()
        if not group_id:
            continue
        internal_name = str(group_name_by_id.get(group_id) or "").strip()
        if not internal_name:
            continue
        content = product.get("content") if isinstance(product.get("content"), dict) else None
        if not isinstance(content, dict):
            continue
        features = content.get("features") if isinstance(content.get("features"), list) else []
        changed_here = False
        for feature in features:
            if not isinstance(feature, dict):
                continue
            code = str(feature.get("code") or "").strip().lower()
            name = str(feature.get("name") or "").strip().lower()
            if code != "group_id" and "группа товара" not in name:
                continue
            if str(feature.get("value") or "").strip() == internal_name:
                pass
            else:
                feature["value"] = internal_name
                changed_here = True
                features_changed += 1
            source_values = feature.get("source_values") if isinstance(feature.get("source_values"), dict) else {}
            yandex_market = source_values.get("yandex_market") if isinstance(source_values.get("yandex_market"), dict) else {}
            if isinstance(yandex_market, dict) and yandex_market:
                for payload in yandex_market.values():
                    if not isinstance(payload, dict):
                        continue
                    changed_payload = False
                    if str(payload.get("canonical_value") or "").strip() != internal_name:
                        payload["canonical_value"] = internal_name
                        changed_payload = True
                    if str(payload.get("resolved_value") or "").strip() != internal_name:
                        payload["resolved_value"] = internal_name
                        changed_payload = True
                    if changed_payload:
                        source_values_changed += 1
                        changed_here = True
                if yandex_market:
                    source_values["yandex_market"] = yandex_market
                    feature["source_values"] = source_values
        if changed_here:
            products_changed += 1

    if products_changed:
        write_doc(PRODUCTS_PATH, {"version": 1, "items": items})
    print(
        f"products_changed={products_changed} "
        f"features_changed={features_changed} "
        f"source_values_changed={source_values_changed}"
    )


if __name__ == "__main__":
    main()
