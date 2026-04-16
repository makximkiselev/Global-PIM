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

### Phase 5

Перенести:
- product registry read-model и вспомогательные summary tables
- остаточные вспомогательные JSON-backed слои
- убрать dual-write для уже вынесенных сущностей

## Exit criteria

После переноса всех hot entities:

- `json_documents` остается только как legacy fallback;
- потом legacy dual-write удаляется;
- затем удаляются JSON-backed paths из runtime. 
