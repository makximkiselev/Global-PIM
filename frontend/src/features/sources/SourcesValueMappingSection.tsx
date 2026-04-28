import { useEffect, useMemo, useState } from "react";
import CategorySidebar from "../../components/CategorySidebar";
import DictionaryEditorFeature from "../dictionary/DictionaryEditorFeature";
import { api } from "../../lib/api";
import "../../styles/marketplace-mapping.css";

type CatalogNode = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
};

type ValueItemProvider = {
  code: string;
  title: string;
  mapped_count: number;
  allowed_count: number;
  param_name?: string | null;
  required?: boolean;
};

type ValueItem = {
  dict_id: string;
  title: string;
  catalog_name: string;
  group: string;
  scope: "group" | "product" | "shared";
  scope_label: string;
  type: string;
  confirmed: boolean;
  attribute_id?: string | null;
  value_count: number;
  providers: ValueItemProvider[];
  providers_count: number;
  mapped_total: number;
};

type ValuesResp = {
  ok: boolean;
  category: { id: string; name: string; path: string };
  items: ValueItem[];
  count: number;
};

type Props = {
  selectedCategoryId?: string;
  onSelectedCategoryChange?: (categoryId: string, categoryName: string) => void;
};

type ScopeFilter = "all" | "group" | "product" | "shared";

const SERVICE_VALUE_GROUPS = new Set(["артикулы"]);
const SERVICE_VALUE_FIELDS = ["sku", "артикул", "штрихкод", "партномер", "barcode", "offerid", "offer id"];

function isDictionaryLike(item: ValueItem) {
  const type = String(item.type || "").toLowerCase();
  return ["select", "multiselect", "enum", "dictionary", "list"].some((part) => type.includes(part));
}

function isServiceValueField(item: ValueItem) {
  const title = `${item.title || ""} ${item.catalog_name || ""}`.toLowerCase();
  const group = String(item.group || "").trim().toLowerCase();
  return SERVICE_VALUE_GROUPS.has(group) || SERVICE_VALUE_FIELDS.some((part) => title.includes(part));
}

function needsValueMapping(item: ValueItem) {
  const hasProviderValues = item.providers.some((provider) => Number(provider.allowed_count || 0) > 0);
  const hasCanonicalValues = Number(item.value_count || 0) > 0;
  if (isServiceValueField(item)) return false;
  return hasProviderValues || (isDictionaryLike(item) && hasCanonicalValues);
}

function buildChildren(nodes: CatalogNode[]) {
  const map = new Map<string, CatalogNode[]>();
  for (const node of nodes) {
    const parent = String(node.parent_id || "");
    if (!map.has(parent)) map.set(parent, []);
    map.get(parent)!.push(node);
  }
  for (const entry of map.values()) {
    entry.sort((a, b) => {
      const pa = Number(a.position || 0);
      const pb = Number(b.position || 0);
      if (pa !== pb) return pa - pb;
      return String(a.name || "").localeCompare(String(b.name || ""), "ru");
    });
  }
  return map;
}

function buildParents(nodes: CatalogNode[]) {
  const map = new Map<string, string>();
  for (const node of nodes) {
    const id = String(node.id || "");
    const parent = String(node.parent_id || "");
    if (id && parent) map.set(id, parent);
  }
  return map;
}

function collectParents(categoryId: string, parentById: Map<string, string>) {
  const out: string[] = [];
  let cur = String(categoryId || "");
  const seen = new Set<string>();
  while (cur && parentById.has(cur) && !seen.has(cur)) {
    seen.add(cur);
    const parent = String(parentById.get(cur) || "");
    if (!parent) break;
    out.push(parent);
    cur = parent;
  }
  return out;
}

function searchMatch(node: CatalogNode, q: string) {
  if (!q) return true;
  return String(node.name || "").toLowerCase().includes(q);
}

export default function SourcesValueMappingSection({ selectedCategoryId = "", onSelectedCategoryChange }: Props) {
  const [nodes, setNodes] = useState<CatalogNode[]>([]);
  const [loadingTree, setLoadingTree] = useState(true);
  const [treeQuery, setTreeQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>("all");
  const [fieldQuery, setFieldQuery] = useState("");
  const [data, setData] = useState<ValuesResp | null>(null);
  const [loadingValues, setLoadingValues] = useState(false);
  const [activeDictId, setActiveDictId] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoadingTree(true);
    void api<CatalogNode[]>("/catalog/nodes")
      .then((resp) => {
        if (cancelled) return;
        setNodes(Array.isArray(resp) ? resp : []);
      })
      .finally(() => {
        if (!cancelled) setLoadingTree(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const childrenByParent = useMemo(() => buildChildren(nodes), [nodes]);
  const parentById = useMemo(() => buildParents(nodes), [nodes]);
  const rootNodes = childrenByParent.get("") || [];

  useEffect(() => {
    if (!selectedCategoryId) return;
    const chain = collectParents(selectedCategoryId, parentById);
    if (!chain.length) return;
    setExpanded((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const id of chain) {
        if (!next[id]) {
          next[id] = true;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [selectedCategoryId, parentById]);

  useEffect(() => {
    if (!selectedCategoryId) {
      setData(null);
      setActiveDictId("");
      return;
    }
    let cancelled = false;
    setLoadingValues(true);
    void api<ValuesResp>(`/marketplaces/mapping/import/values/${encodeURIComponent(selectedCategoryId)}`)
      .then((resp) => {
        if (cancelled) return;
        setData(resp);
        const first = Array.isArray(resp.items) ? resp.items[0] : null;
        setActiveDictId((prev) => {
          if (prev && resp.items.some((item) => item.dict_id === prev)) return prev;
          return first?.dict_id || "";
        });
      })
      .finally(() => {
        if (!cancelled) setLoadingValues(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedCategoryId]);

  const filteredItems = useMemo(() => {
    const q = String(fieldQuery || "").trim().toLowerCase();
    const list = Array.isArray(data?.items) ? data!.items : [];
    return list
      .filter((item) => needsValueMapping(item))
      .filter((item) => {
        if (scopeFilter !== "all" && item.scope !== scopeFilter) return false;
        if (!q) return true;
        const hay = `${item.catalog_name} ${item.group} ${item.providers.map((p) => p.title).join(" ")}`.toLowerCase();
        return hay.includes(q);
      })
      .sort((a, b) => {
        const aReady = a.providers.some((provider) => Number(provider.allowed_count || 0) > 0);
        const bReady = b.providers.some((provider) => Number(provider.allowed_count || 0) > 0);
        if (aReady !== bReady) return aReady ? -1 : 1;
        return String(a.catalog_name || a.title || "").localeCompare(String(b.catalog_name || b.title || ""), "ru");
      });
  }, [data, fieldQuery, scopeFilter]);

  const rawItemsCount = Array.isArray(data?.items) ? data!.items.length : 0;
  const mappingItemsCount = useMemo(() => {
    const list = Array.isArray(data?.items) ? data!.items : [];
    return list.filter((item) => needsValueMapping(item)).length;
  }, [data]);

  useEffect(() => {
    if (!filteredItems.length) {
      setActiveDictId("");
      return;
    }
    if (!activeDictId || !filteredItems.some((item) => item.dict_id === activeDictId)) {
      setActiveDictId(filteredItems[0].dict_id);
    }
  }, [filteredItems, activeDictId]);

  function toggleAll() {
    const expandableIds = nodes
      .filter((node) => (childrenByParent.get(String(node.id || "")) || []).length > 0)
      .map((node) => String(node.id || ""));
    const hasExpanded = expandableIds.some((id) => expanded[id]);
    if (hasExpanded) {
      setExpanded({});
      return;
    }
    const next: Record<string, boolean> = {};
    for (const id of expandableIds) next[id] = true;
    setExpanded(next);
  }

  function renderTreeRow(node: CatalogNode, depth = 0): JSX.Element | null {
    const id = String(node.id || "");
    const children = childrenByParent.get(id) || [];
    const isExpanded = !!expanded[id];
    const q = String(treeQuery || "").trim().toLowerCase();
    const childMatches = children
      .map((child) => renderTreeRow(child, depth + 1))
      .filter(Boolean) as JSX.Element[];
    const selfMatch = searchMatch(node, q);
    if (q && !selfMatch && childMatches.length === 0) return null;

    return (
      <div key={id} className="csb-treeRow" style={{ ["--depth" as any]: depth }}>
        <div className={`csb-treeNode ${selectedCategoryId === id ? "is-active" : ""}`} onClick={() => onSelectedCategoryChange?.(id, node.name)}>
          {children.length ? (
            <button
              type="button"
              className="csb-caretBtn"
              onClick={(e) => {
                e.stopPropagation();
                setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
              }}
            >
              {isExpanded ? "▾" : "▸"}
            </button>
          ) : (
            <span className="csb-caretSpacer" />
          )}
          <span className="csb-treeName" title={node.name}>{node.name}</span>
        </div>
        {children.length && isExpanded ? childMatches : null}
      </div>
    );
  }

  const activeItem = filteredItems.find((item) => item.dict_id === activeDictId) || null;

  useEffect(() => {
    if (!data?.category?.id || !data.category.name) return;
    onSelectedCategoryChange?.(data.category.id, data.category.name);
  }, [data?.category?.id, data?.category?.name]);

  return (
    <div className="sm-valuesPage">
      <div className="sm-valuesLayout">
        <CategorySidebar
          title="Каталог"
          hint="Выберите ветку, где нужно проверить значения для выгрузки"
          searchValue={treeQuery}
          onSearchChange={setTreeQuery}
          searchPlaceholder="Быстрый поиск"
          controls={(
            <button className="btn sm" type="button" onClick={toggleAll}>
              {Object.values(expanded).some(Boolean) ? "Свернуть" : "Развернуть"}
            </button>
          )}
        >
          <div className="csb-tree">
            {loadingTree ? <div className="muted">Загружаю каталог…</div> : rootNodes.map((node) => renderTreeRow(node, 0))}
          </div>
        </CategorySidebar>

        <div className="sm-valuesMain">
          <div className="sm-valuesHead">
            <div>
              <div className="sm-shellTitle">Сопоставление значений</div>
              <div className="sm-shellSub">
                Нормализованные значения PIM остаются внутри системы. Здесь выбирается, как эти значения будут называться на Я.Маркете, Ozon и других площадках.
              </div>
            </div>
            {data?.category ? (
              <div className="sm-valuesMeta">
                <span>{data.category.path}</span>
                <span>{mappingItemsCount} из {rawItemsCount} полей требуют сопоставления</span>
              </div>
            ) : null}
          </div>

          <div className="sm-valuesWorkbench">
            <div className="sm-valuesFields">
              <div className="sm-valuesToolbar">
                <input
                  value={fieldQuery}
                  onChange={(e) => setFieldQuery(e.target.value)}
                  placeholder="Память, цвет, тип SIM…"
                />
                <div className="sm-valuesScopeTabs">
                  {[
                    ["all", "Все"],
                    ["group", "Группа"],
                    ["product", "Товар"],
                    ["shared", "Общее"],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      className={`mm-tab ${scopeFilter === value ? "active" : ""}`}
                      onClick={() => setScopeFilter(value as ScopeFilter)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="sm-valuesFieldList">
                {!selectedCategoryId ? (
                  <div className="sm-valuesEmpty">Выбери категорию слева.</div>
                ) : loadingValues ? (
                  <div className="sm-valuesEmpty">Загружаю поля со значениями…</div>
                ) : filteredItems.length === 0 ? (
                  <div className="sm-valuesEmpty">Для этой категории пока нет полей, где нужно сопоставлять значения площадок.</div>
                ) : (
                  filteredItems.map((item) => (
                    <button
                      key={item.dict_id}
                      type="button"
                      className={`sm-valuesFieldItem ${activeDictId === item.dict_id ? "is-active" : ""}`}
                      onClick={() => setActiveDictId(item.dict_id)}
                    >
                      <div className="sm-valuesFieldTop">
                        <strong>{item.catalog_name}</strong>
                        <span className="sm-valuesPill">{item.scope_label}</span>
                      </div>
                      <div className="sm-valuesFieldMeta">
                        <span>{item.group}</span>
                        <span>{item.value_count} знач.</span>
                        <span>{item.mapped_total ? `${item.mapped_total} сопоставлено` : "сопоставление не настроено"}</span>
                      </div>
                      <div className="sm-valuesProviderRow">
                        {item.providers.map((provider) => (
                          <span key={provider.code} className="sm-valuesProviderPill">
                            {provider.title}: {provider.mapped_count}/{provider.allowed_count}
                          </span>
                        ))}
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>

            <div className="sm-valuesEditor">
              {activeItem ? (
                <DictionaryEditorFeature embedded dictIdOverride={activeItem.dict_id} />
              ) : (
                <div className="sm-valuesEmpty">Выбери поле слева, чтобы открыть сопоставление значений.</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
