# JSON to Relational Migration

## Goal

Убрать hot-path сущности из `json_documents` и перевести их на реальные таблицы Postgres без одномоментной остановки продового контура.

## Current state

Сейчас предметные данные в основном читаются через:

- `read_doc(backend/data/catalog_nodes.json)`
- `read_doc(backend/data/marketplaces/category_mapping.json)`
- `read_doc(backend/data/products.json)`
- `read_doc(backend/data/templates.json)`

Физически это хранится в `public.json_documents(path, payload, updated_at)`.

## Phase 1

Переносим первые две самые горячие сущности:

1. `catalog_nodes` -> `catalog_nodes_rel`
2. `category_mappings` -> `category_mappings_rel`

### Runtime strategy

- bootstrap из legacy JSON в таблицы при первом обращении;
- дальнейшее чтение из таблиц;
- запись одновременно:
  - в таблицы
  - в legacy JSON

Это дает совместимость для кода, который еще не переведен.

## Hot paths moved in Phase 1

- `Catalog`
- `Sources / marketplace mapping`
- `Templates`
- `Products bootstrap`
- `Product groups`
- `Catalog exchange`
- `Dictionaries`
- `Yandex/Ozon` category readers

## Next phases

### Phase 2

Перенесено:

- `attribute_mappings` -> `attribute_mappings_rel`
- `attribute_value_dictionary` -> `attribute_value_refs_rel`
- `dictionaries` -> реляционный словарный слой:
  - `dictionaries_rel`
  - `dictionary_values_rel`
  - `dictionary_value_sources_rel`
  - `dictionary_aliases_rel`
  - `dictionary_provider_refs_rel`
  - `dictionary_export_maps_rel`

Все три слоя работают через dual-write:

- чтение идет из таблиц;
- запись идет в таблицы;
- legacy JSON пока сохраняется для совместимости.

### Phase 3

Перенесено:

- `templates` -> реляционный слой:
  - `templates_rel`
  - `template_attributes_rel`
  - `category_template_links_rel`

Runtime strategy та же:

- чтение идет из таблиц;
- запись идет в таблицы;
- legacy `templates.json` сохраняется как dual-write compatibility layer.

### Phase 4

Перенесено:

- `products` -> `products_rel`

Runtime strategy:

- чтение `products` идет из таблицы;
- запись идет в таблицу;
- legacy `products.json` сохраняется как dual-write compatibility layer;
- SKU/category indexes больше не являются source of truth и собираются из реляционного product store.

Hot paths, уже переведенные на новый слой:

- `app.core.products.repo`
- `app.core.products.service`
- `catalog`
- `catalog_exchange`
- `templates` product readers
- `yandex_market`
- `ozon_market`
- registry projection:
  - `catalog_product_registry_rel`
  - `category_product_counts_rel`
- product summaries:
  - `category_template_resolution_rel`
  - `product_marketplace_status_rel`
- `stats` summary теперь считает товары из реляционного product store, не из JSON blob
- `catalog/products-page-data` больше не должен читать полный product blob для шаблонов и marketplace статусов
- `catalog/products` и `catalog/products/search` идут через SQL query path по `catalog_product_registry_rel`
- `stats/summary` теперь может подниматься из persisted summary table:
  - `dashboard_stats_rel`
- `catalog/products-page-data` переводится на page-read-model:
  - `catalog_product_page_rel`

### Phase 5

Перенести:
- остаточные product summary/read models для тяжелых экранов
- остаточные вспомогательные JSON-backed слои
- убрать dual-write для уже вынесенных сущностей

Следующий фокус после этого среза:

- `product_groups`
- `catalog_exchange`
- connector/dashboard summaries

Уже убрано в product-срезе:

- `products.json` больше не является write target для runtime updates;
- `sku_gt_index.json`, `sku_pim_index.json`, `product_category_index.json`, `catalog_products.json`
  больше не являются source of truth и не обновляются как рабочий слой.

Уже убрано для ранее вынесенных storage-сущностей:

- `catalog_nodes.json`
- `marketplaces/category_mapping.json`
- `marketplaces/attribute_master_mapping.json`
- `marketplaces/attribute_value_dictionary.json`
- `dictionaries.json`
- `templates.json`

они больше не являются write target для runtime updates.

## Exit criteria

После переноса всех hot entities:

- `json_documents` остается только как legacy fallback;
- потом legacy dual-write удаляется;
- затем удаляются JSON-backed paths из runtime. 
