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

Перенести:

- `attribute_mappings`
- `attribute_value_dictionary`
- read-model для `sources-mapping`

`attribute_mappings` уже переведены на отдельную таблицу `attribute_mappings_rel` с dual-write.
`attribute_value_dictionary` переведен на отдельную таблицу `attribute_value_refs_rel` с dual-write.

### Phase 3

Перенести:

- `products`
- product indexes
- catalog product registry read-model

### Phase 4

Перенести:

- `templates`
- template attributes
- category-to-template links

## Exit criteria

После переноса всех hot entities:

- `json_documents` остается только как legacy fallback;
- потом legacy dual-write удаляется;
- затем удаляются JSON-backed paths из runtime. 
