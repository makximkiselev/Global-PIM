import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import CategorySidebar from "../../components/CategorySidebar";
import DictionaryEditorFeature from "../data-prep/DictionaryEditorFeature";
import { api } from "../../lib/api";
import "../../styles/marketplace-mapping.css";

type CatalogNode = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
};
type NodesResp = CatalogNode[] | { nodes?: CatalogNode[] };

type ValueItemProvider = {
  code: string;
  title: string;
  mapped_count: number;
  allowed_count: number;
  covered_count?: number;
  missing_count?: number;
  kind?: string | null;
  mode?: "boolean" | "enum" | "multi" | "number" | "text" | string;
  needs_mapping?: boolean;
  needs_unit_check?: boolean;
  mapped_sample?: Array<{ canonical: string; output: string }>;
  mapped_values?: Record<string, string>;
  allowed_sample?: string[];
  allowed_values?: string[];
  missing_sample?: string[];
  missing_values?: string[];
  dictionary_quality?: {
    status?: "ok" | "warn" | string;
    issues?: Array<{ code?: string; label?: string; text?: string }>;
  };
  param_name?: string | null;
  required?: boolean;
};

type ValueSourceEvidence = {
  product_id?: string;
  sku_gt?: string;
  product_title?: string;
  source_group?: string;
  source_id?: string;
  source_label?: string;
  raw_value?: string;
  resolved_value?: string;
  canonical_value?: string;
};

type ValueItem = {
  dict_id: string;
  title: string;
  catalog_name: string;
  group: string;
  scope: "group" | "product" | "shared";
  scope_label: string;
  type: string;
  value_mode?: "boolean" | "enum" | "multi" | "number" | "text" | string;
  confirmed: boolean;
  attribute_id?: string | null;
  value_count: number;
  pim_sample?: string[];
  pim_values?: string[];
  source_evidence?: ValueSourceEvidence[];
  needs_value_mapping?: boolean;
  needs_unit_check?: boolean;
  source_category?: { id: string; name: string; path?: string } | null;
  providers: ValueItemProvider[];
  providers_count: number;
  mapped_total: number;
};

type ValuesResp = {
  ok: boolean;
  category: { id: string; name: string; path: string };
  branch_sources?: Array<{ id: string; name: string; path?: string }>;
  items: ValueItem[];
  count: number;
};

type ValueAiJobResp = {
  ok?: boolean;
  job_id?: string;
  status?: string;
  phase?: string;
  message?: string;
  error?: string;
  ai_error?: string;
  summary?: {
    suggestions?: number;
    ai_suggestions?: number;
    rule_suggestions?: number;
  };
};

type Props = {
  selectedCategoryId?: string;
  focusParameter?: string;
  onSelectedCategoryChange?: (categoryId: string, categoryName: string) => void;
};

type ScopeFilter = "all" | "group" | "product" | "shared";
type WorkFilter = "blockers" | "all" | "ready";

const SERVICE_VALUE_GROUPS = new Set(["артикулы"]);
const SERVICE_VALUE_FIELDS = ["sku", "артикул", "штрихкод", "партномер", "barcode", "offerid", "offer id"];

function isDictionaryLike(item: ValueItem) {
  const type = String(item.value_mode || item.type || "").toLowerCase();
  return ["select", "multiselect", "enum", "dictionary", "list"].some((part) => type.includes(part));
}

function valueModeLabel(item: ValueItem) {
  const mode = String(item.value_mode || item.type || "").toLowerCase();
  if (mode.includes("bool")) return "Да/Нет";
  if (mode.includes("number")) return "Число";
  if (mode.includes("multi")) return "Мультивыбор";
  if (mode.includes("enum") || isDictionaryLike(item)) return "Справочник";
  return "Текст";
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
  return Boolean(item.needs_value_mapping || item.needs_unit_check) || hasProviderValues || (isDictionaryLike(item) && hasCanonicalValues);
}

function usefulProviders(item: ValueItem) {
  return item.providers.filter((provider) =>
    Number(provider.allowed_count || 0) > 0 ||
    Number(provider.mapped_count || 0) > 0 ||
    Boolean(provider.needs_unit_check),
  );
}

function valueItemStatus(item: ValueItem) {
  const providers = usefulProviders(item);
  if (!providers.length) return { label: "нет справочника", tone: "muted" };
  if (Number(item.value_count || 0) === 0) return { label: "нет PIM знач.", tone: "muted" };
  const hasGap = providers.some((provider) => Boolean(provider.needs_mapping));
  if (hasGap) return { label: "нужно сопоставить", tone: "warn" };
  if (item.needs_unit_check) return { label: "проверить единицы", tone: "muted" };
  return { label: "готово", tone: "ok" };
}

function providerHasGap(provider: ValueItemProvider) {
  const mode = String(provider.mode || "").toLowerCase();
  if (mode === "number") return false;
  return Boolean(provider.needs_mapping);
}

function providerSampleText(provider: ValueItemProvider) {
  const missing = (provider.missing_sample || []).filter(Boolean).slice(0, 3);
  const allowed = (provider.allowed_sample || []).filter(Boolean).slice(0, 3);
  const mapped = (provider.mapped_sample || []).filter((item) => item.canonical || item.output).slice(0, 2);
  if (missing.length) return `не покрыто: ${missing.join(", ")}`;
  if (mapped.length) return mapped.map((item) => `${item.canonical} → ${item.output}`).join("; ");
  if (Number(provider.covered_count || 0) > 0) return `покрыто PIM-значений: ${provider.covered_count}`;
  if (allowed.length) return `значения площадки: ${allowed.join(", ")}`;
  if (provider.needs_unit_check) return "проверь единицы измерения перед экспортом";
  return "";
}

function sourceEvidenceText(evidence: ValueSourceEvidence) {
  const source = evidence.source_label || evidence.source_id || evidence.source_group || "источник";
  const sku = evidence.sku_gt ? `SKU ${evidence.sku_gt}` : evidence.product_title || evidence.product_id || "";
  const raw = evidence.raw_value || evidence.resolved_value || evidence.canonical_value || "";
  const resolved = evidence.resolved_value && evidence.resolved_value !== raw ? ` -> ${evidence.resolved_value}` : "";
  return `${source}${sku ? ` · ${sku}` : ""}: ${raw}${resolved}`;
}

function providerCoverageLabel(provider: ValueItemProvider, item: ValueItem) {
  const mode = String(provider.mode || "").toLowerCase();
  if (mode === "number") return "единицы";
  const valueCount = Number(item.value_count || 0);
  const covered = Number(provider.covered_count || 0);
  const missing = Number(provider.missing_count || 0);
  if (valueCount > 0 && (covered > 0 || missing > 0 || provider.needs_mapping)) {
    return `${covered}/${valueCount} PIM`;
  }
  if (Number(provider.mapped_count || 0) > 0) return `${provider.mapped_count} ручн.`;
  if (Number(provider.allowed_count || 0) > 0) return `${provider.allowed_count} знач.`;
  return "свободно";
}

function normValueKey(value: string) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
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

export default function SourcesValueMappingSection({ selectedCategoryId: selectedCategoryIdProp = "", focusParameter = "", onSelectedCategoryChange }: Props) {
  const selectedCategoryId = selectedCategoryIdProp || (typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("category") || "" : "");
  const [nodes, setNodes] = useState<CatalogNode[]>([]);
  const [loadingTree, setLoadingTree] = useState(true);
  const [treeQuery, setTreeQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>("all");
  const [workFilter, setWorkFilter] = useState<WorkFilter>("all");
  const [fieldQuery, setFieldQuery] = useState("");
  const [data, setData] = useState<ValuesResp | null>(null);
  const [loadingValues, setLoadingValues] = useState(false);
  const [activeDictId, setActiveDictId] = useState("");
  const [categoryDrawerOpen, setCategoryDrawerOpen] = useState(false);
  const [aiValueLoading, setAiValueLoading] = useState("");
  const [aiValueMessage, setAiValueMessage] = useState("");
  const [valueMapDraft, setValueMapDraft] = useState<Record<string, string>>({});
  const [valueMapSaving, setValueMapSaving] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoadingTree(true);
    void api<NodesResp>("/catalog/nodes")
      .then((resp) => {
        if (cancelled) return;
        setNodes(Array.isArray(resp) ? resp : Array.isArray(resp?.nodes) ? resp.nodes : []);
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
        const providers = usefulProviders(item);
        const hasGap = providers.some(providerHasGap);
        if (workFilter === "blockers") return hasGap;
        if (workFilter === "ready") return Number(item.value_count || 0) > 0 && providers.length > 0 && !hasGap;
        return true;
      })
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
  }, [data, fieldQuery, scopeFilter, workFilter]);

  const rawItemsCount = Array.isArray(data?.items) ? data!.items.length : 0;
  const mappingItemsCount = useMemo(() => {
    const list = Array.isArray(data?.items) ? data!.items : [];
    return list.filter((item) => needsValueMapping(item)).length;
  }, [data]);

  useEffect(() => {
    const focus = String(focusParameter || "").trim().toLowerCase();
    const list = Array.isArray(data?.items) ? data!.items : [];
    if (!focus || !list.length) return;
    const match = list.find((item) => {
      const hay = `${item.catalog_name || ""} ${item.title || ""} ${item.group || ""}`.toLowerCase();
      return hay.includes(focus) || focus.includes(String(item.catalog_name || item.title || "").trim().toLowerCase());
    });
    setFieldQuery(focusParameter);
    setScopeFilter("all");
    setWorkFilter("all");
    if (match) setActiveDictId(match.dict_id);
  }, [focusParameter, data]);

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
        <div
          className={`csb-treeNode ${selectedCategoryId === id ? "is-active" : ""}`}
          onClick={() => {
            onSelectedCategoryChange?.(id, node.name);
            setCategoryDrawerOpen(false);
          }}
        >
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
  const allMappingItems = useMemo(() => {
    const list = Array.isArray(data?.items) ? data!.items : [];
    return list.filter((item) => needsValueMapping(item));
  }, [data]);
  const allUnresolvedCount = allMappingItems.filter((item) =>
    usefulProviders(item).some(providerHasGap),
  ).length;
  const allReadyCount = allMappingItems.filter((item) => {
    const providers = usefulProviders(item);
    return Number(item.value_count || 0) > 0 && providers.length > 0 && providers.every((provider) => !providerHasGap(provider));
  }).length;
  const nextBlocker = allMappingItems.find((item) => usefulProviders(item).some(providerHasGap)) || null;
  const unitCheckCount = allMappingItems.filter((item) => Boolean(item.needs_unit_check)).length;
  const branchSourcesCount = Array.isArray(data?.branch_sources) ? data!.branch_sources.length : 0;
  const emptyValuesMessage = useMemo(() => {
    if (!mappingItemsCount && !rawItemsCount) {
      return "В этой категории еще нет PIM-параметров. Сначала соберите и подтвердите черновик модели, затем здесь появятся значения для Я.Маркета и Ozon.";
    }
    if (!mappingItemsCount) return "В модели нет полей со справочниками или контролируемыми значениями площадок. Можно перейти к проверке экспорта.";
    if (workFilter === "blockers") return "Блокеров по значениям нет. Открой «Все», чтобы проверить поля со справочниками.";
    if (workFilter === "ready") return "Готовых сопоставлений значений пока нет.";
    return "Поля есть, но текущий поиск или фильтр их скрыл.";
  }, [mappingItemsCount, rawItemsCount, workFilter]);

  useEffect(() => {
    if (!data?.category?.id || !data.category.name) return;
    onSelectedCategoryChange?.(data.category.id, data.category.name);
  }, [data?.category?.id, data?.category?.name]);

  function jumpToNextBlocker() {
    if (!nextBlocker) return;
    setWorkFilter("blockers");
    setScopeFilter("all");
    setFieldQuery("");
    setActiveDictId(nextBlocker.dict_id);
  }

  async function runValueAi(provider: ValueItemProvider) {
    if (!selectedCategoryId || !activeItem?.dict_id || !provider.code) return;
    const key = `${activeItem.dict_id}:${provider.code}`;
    setAiValueLoading(key);
    setAiValueMessage("");
    try {
      const job = await api<ValueAiJobResp>(
        `/marketplaces/mapping/import/values/${encodeURIComponent(selectedCategoryId)}/dictionaries/${encodeURIComponent(activeItem.dict_id)}/ai-suggest/jobs`,
        {
          method: "POST",
          body: JSON.stringify({ provider: provider.code, apply: true }),
        },
      );
      const jobId = String(job?.job_id || "");
      if (!jobId) throw new Error("VALUE_AI_JOB_NOT_CREATED");
      setAiValueMessage(job?.message || "AI-сопоставление значений поставлено в очередь.");

      let result: ValueAiJobResp = job;
      for (let attempt = 0; attempt < 90; attempt += 1) {
        if (!["queued", "running"].includes(String(result?.status || ""))) break;
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        result = await api<ValueAiJobResp>(`/marketplaces/mapping/import/values/ai-suggest/jobs/${encodeURIComponent(jobId)}`);
        if (result?.message) setAiValueMessage(result.message);
      }
      if (["queued", "running"].includes(String(result?.status || ""))) {
        throw new Error("VALUE_AI_JOB_TIMEOUT");
      }
      if (String(result?.status || "") === "failed") {
        throw new Error(result?.error || result?.message || "VALUE_AI_JOB_FAILED");
      }
      const suggestions = Number(result?.summary?.suggestions || 0);
      const aiSuggestions = Number(result?.summary?.ai_suggestions || 0);
      const ruleSuggestions = Number(result?.summary?.rule_suggestions || 0);
      setAiValueMessage(
        suggestions
          ? `Сопоставлено: ${suggestions} знач. (AI ${aiSuggestions}, правило ${ruleSuggestions}).`
          : result?.message || result?.ai_error || "AI не нашел уверенных пар.",
      );
      setLoadingValues(true);
      const refreshed = await api<ValuesResp>(`/marketplaces/mapping/import/values/${encodeURIComponent(selectedCategoryId)}`);
      setData(refreshed);
    } catch (e: any) {
      setAiValueMessage(e?.message || "AI_VALUE_MATCH_FAILED");
    } finally {
      setAiValueLoading("");
      setLoadingValues(false);
    }
  }

  async function saveInlineValueMapping(provider: ValueItemProvider, canonicalValue: string, outputValue: string) {
    if (!selectedCategoryId || !activeItem?.dict_id || !provider.code) return;
    const saveKey = `${activeItem.dict_id}:${provider.code}:${canonicalValue}`;
    setValueMapSaving(saveKey);
    try {
      await api(
        `/marketplaces/mapping/import/values/${encodeURIComponent(selectedCategoryId)}/dictionaries/${encodeURIComponent(activeItem.dict_id)}/export-map`,
        {
          method: "PATCH",
          body: JSON.stringify({
            provider: provider.code,
            canonical_value: canonicalValue,
            output_value: outputValue.trim() || null,
          }),
        },
      );
      setLoadingValues(true);
      const refreshed = await api<ValuesResp>(`/marketplaces/mapping/import/values/${encodeURIComponent(selectedCategoryId)}`);
      setData(refreshed);
      setValueMapDraft((prev) => {
        const next = { ...prev };
        delete next[saveKey];
        return next;
      });
    } catch (e: any) {
      setAiValueMessage(e?.message || "VALUE_MAPPING_SAVE_FAILED");
    } finally {
      setValueMapSaving("");
      setLoadingValues(false);
    }
  }

  function renderInlineValueEditor(provider: ValueItemProvider) {
    if (!activeItem || String(provider.mode || "").toLowerCase() === "number") return null;
    const pimValues = (activeItem.pim_values?.length ? activeItem.pim_values : activeItem.pim_sample || []).filter(Boolean);
    const allowedValues = (provider.allowed_values?.length ? provider.allowed_values : provider.allowed_sample || []).filter(Boolean);
    if (!pimValues.length || !allowedValues.length) return null;
    const missingKeys = new Set((provider.missing_values || []).map(normValueKey));
    const mappedValues = provider.mapped_values || {};
    const rows = [...pimValues]
      .sort((a, b) => {
        const am = missingKeys.has(normValueKey(a));
        const bm = missingKeys.has(normValueKey(b));
        if (am !== bm) return am ? -1 : 1;
        return a.localeCompare(b, "ru");
      })
      .slice(0, 36);
    const listId = `value-provider-${activeItem.dict_id}-${provider.code}`;
    const hiddenCount = Math.max(0, pimValues.length - rows.length);

    return (
      <div className="sm-valuesInlineMap" key={provider.code}>
        <div className="sm-valuesInlineMapHead">
          <div>
            <strong>{provider.title}: значения для выгрузки</strong>
            <span>{Number(provider.missing_count || 0) ? `не покрыто ${provider.missing_count}` : "все покрыто"}</span>
          </div>
          <small>{provider.param_name || "поле площадки"}</small>
        </div>
        <div className="sm-valuesInlineRows">
          {rows.map((value) => {
            const valueKey = normValueKey(value);
            const saveKey = `${activeItem.dict_id}:${provider.code}:${value}`;
            const mapped = mappedValues[valueKey] || "";
            const draft = valueMapDraft[saveKey] ?? mapped;
            const isMissing = missingKeys.has(valueKey);
            return (
              <div className={`sm-valuesInlineRow ${isMissing ? "is-missing" : ""}`} key={`${provider.code}:${value}`}>
                <div className="sm-valuesInlineCanon">
                  <span>PIM</span>
                  <strong title={value}>{value}</strong>
                </div>
                <input
                  list={listId}
                  value={draft}
                  onChange={(event) => setValueMapDraft((prev) => ({ ...prev, [saveKey]: event.target.value }))}
                  placeholder="Значение площадки"
                />
                <button
                  className="btn sm"
                  type="button"
                  disabled={valueMapSaving === saveKey || draft.trim() === mapped}
                  onClick={() => void saveInlineValueMapping(provider, value, draft)}
                >
                  {valueMapSaving === saveKey ? "Сохраняю…" : "Сохранить"}
                </button>
                <button
                  className="btn sm"
                  type="button"
                  disabled={valueMapSaving === saveKey || !mapped}
                  onClick={() => void saveInlineValueMapping(provider, value, "")}
                >
                  Снять
                </button>
              </div>
            );
          })}
        </div>
        {hiddenCount ? <div className="sm-valuesInlineFoot">Показаны первые {rows.length} значений, еще {hiddenCount} доступны в полном редакторе ниже.</div> : null}
        <datalist id={listId}>
          {allowedValues.map((value) => <option key={value} value={value} />)}
        </datalist>
      </div>
    );
  }

  return (
    <div className="sm-valuesPage">
      <div className="sm-valuesLayout">
        {categoryDrawerOpen ? (
          <div className="sm-valuesCategoryDrawer" role="dialog" aria-modal="true">
            <button className="sm-valuesDrawerBackdrop" type="button" aria-label="Закрыть выбор категории" onClick={() => setCategoryDrawerOpen(false)} />
            <CategorySidebar
              title="Выбор категории"
              hint="Категория задает набор полей со справочниками. После выбора экран остается сфокусированным на значениях."
              searchValue={treeQuery}
              onSearchChange={setTreeQuery}
              searchPlaceholder="Быстрый поиск"
              controls={(
                <div className="sm-valuesDrawerControls">
                  <button className="btn sm" type="button" onClick={toggleAll}>
                    {Object.values(expanded).some(Boolean) ? "Свернуть" : "Развернуть"}
                  </button>
                  <button className="btn sm" type="button" onClick={() => setCategoryDrawerOpen(false)}>Закрыть</button>
                </div>
              )}
            >
              <div className="csb-tree">
                {loadingTree ? <div className="muted">Загружаю каталог…</div> : rootNodes.map((node) => renderTreeRow(node, 0))}
              </div>
            </CategorySidebar>
          </div>
        ) : null}

        <div className="sm-valuesMain">
          <div className="sm-valuesHead">
            <div>
              <div className="sm-valuesKicker">Значения для выгрузки</div>
              <div className="sm-shellTitle">Сопоставление значений</div>
              <div className="sm-shellSub">
                Слева выбирается поле PIM, справа задается, как его значения должны называться на Я.Маркете, Ozon и других площадках.
              </div>
            </div>
            <div className="sm-valuesActions">
              <button className="btn" type="button" onClick={() => setCategoryDrawerOpen(true)}>Сменить категорию</button>
              <Link className="btn" to={`/sources?tab=params&category=${encodeURIComponent(selectedCategoryId)}`}>К параметрам</Link>
              <Link className="btn btn-primary" to={`/catalog/exchange?tab=export&category=${encodeURIComponent(selectedCategoryId)}`}>Проверить выгрузку</Link>
            </div>
          </div>

          <div className="sm-valuesSummary">
            <span>{data?.category?.path || "Категория не выбрана"}</span>
            {branchSourcesCount ? <span>{branchSourcesCount} дочерних категорий</span> : null}
            <span>{mappingItemsCount} из {rawItemsCount} полей со справочниками</span>
            <span>{allUnresolvedCount} блокеров</span>
            <span>{unitCheckCount} числовых проверок</span>
            <span>{allReadyCount} готовы</span>
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
                    ["blockers", `Блокеры ${allUnresolvedCount}`],
                    ["all", `Все ${mappingItemsCount}`],
                    ["ready", `Готово ${allReadyCount}`],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      className={`mm-tab ${workFilter === value ? "active" : ""}`}
                      onClick={() => setWorkFilter(value as WorkFilter)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
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
                <button
                  className="btn sm-valuesNextBtn"
                  type="button"
                  disabled={!nextBlocker}
                  onClick={jumpToNextBlocker}
                >
                  Следующий блокер
                </button>
              </div>

              <div className="sm-valuesFieldList">
                {!selectedCategoryId ? (
                  <div className="sm-valuesEmpty">Выбери категорию слева.</div>
                ) : loadingValues ? (
                  <div className="sm-valuesEmpty">Загружаю поля со значениями…</div>
                ) : filteredItems.length === 0 ? (
                  <div className="sm-valuesEmpty">
                    <p>{emptyValuesMessage}</p>
                    {!mappingItemsCount && !rawItemsCount ? (
                      <div className="sm-valuesEmptyActions">
                        <Link className="btn" to={`/sources?tab=params&category=${encodeURIComponent(selectedCategoryId)}`}>К параметрам</Link>
                        <Link className="btn btn-primary" to={`/templates/${encodeURIComponent(selectedCategoryId)}`}>Собрать модель</Link>
                      </div>
                    ) : !mappingItemsCount ? (
                      <div className="sm-valuesEmptyActions">
                        <Link className="btn" to={`/sources?tab=params&category=${encodeURIComponent(selectedCategoryId)}`}>Проверить параметры</Link>
                        <Link className="btn btn-primary" to={`/catalog/exchange?tab=export&category=${encodeURIComponent(selectedCategoryId)}`}>Проверить экспорт</Link>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  filteredItems.map((item) => {
                    const providers = usefulProviders(item);
                    const status = valueItemStatus(item);
                    return (
                      <button
                        key={item.dict_id}
                        type="button"
                        className={`sm-valuesFieldItem ${activeDictId === item.dict_id ? "is-active" : ""}`}
                        onClick={() => setActiveDictId(item.dict_id)}
                      >
                        <div className="sm-valuesFieldTop">
                          <strong>{item.catalog_name}</strong>
                          <span className={`sm-valuesState is-${status.tone}`}>{status.label}</span>
                        </div>
                        <div className="sm-valuesFieldMeta">
                          <span>{item.group || "Без группы"}</span>
                          <span>{item.scope_label}</span>
                          {item.source_category?.name ? <span>{item.source_category.name}</span> : null}
                          <span>{valueModeLabel(item)}</span>
                          <span>{item.value_count} PIM-знач.</span>
                        </div>
                        <div className="sm-valuesProviderRow">
                          {providers.length ? providers.map((provider) => (
                            <span
                              key={provider.code}
                              className={`sm-valuesProviderPill ${providerHasGap(provider) ? "is-gap" : "is-ready"}`}
                            >
                              {provider.title}: {providerCoverageLabel(provider, item)}
                            </span>
                          )) : (
                            <span className="sm-valuesProviderPill is-empty">У площадок нет справочника</span>
                          )}
                        </div>
                        {providers.some((provider) => providerSampleText(provider)) ? (
                          <div className="sm-valuesEvidenceRow">
                            {providers.map((provider) => {
                              const sample = providerSampleText(provider);
                              if (!sample) return null;
                              return <span key={`${provider.code}-sample`}>{provider.title}: {sample}</span>;
                            })}
                          </div>
                        ) : null}
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            <div className="sm-valuesEditor">
              {activeItem ? (
                <>
                  <div className="sm-valuesRouteCard">
                    <div className="sm-valuesRouteStep">
                      <span>PIM поле</span>
                      <strong>{activeItem.catalog_name}</strong>
                      <small>
                        {[
                          activeItem.group || "Без группы",
                          activeItem.scope_label,
                          activeItem.source_category?.name,
                          valueModeLabel(activeItem),
                        ].filter(Boolean).join(" · ")}
                      </small>
                    </div>
                    <div className="sm-valuesRouteStep">
                      <span>Канон</span>
                      <strong>{activeItem.value_count || 0} знач.</strong>
                      <small>{activeItem.pim_sample?.length ? activeItem.pim_sample.slice(0, 3).join(" · ") : "редактируются ниже"}</small>
                    </div>
                    {["yandex_market", "ozon"].map((providerCode) => {
                      const provider = activeItem.providers.find((item) => item.code === providerCode);
                      const gap = provider ? providerHasGap(provider) : false;
                      return (
                        <div className={`sm-valuesRouteStep ${gap ? "is-gap" : provider ? "is-ready" : "is-muted"}`} key={providerCode}>
                          <span>{provider?.title || (providerCode === "yandex_market" ? "Я.Маркет" : "Ozon")}</span>
                          <strong>{provider ? providerCoverageLabel(provider, activeItem) : "нет поля"}</strong>
                          <small>{provider?.param_name || "справочник не подключен"}</small>
                        </div>
                      );
                    })}
                    <div className={`sm-valuesRouteStep is-status ${valueItemStatus(activeItem).tone === "warn" ? "is-gap" : "is-ready"}`}>
                      <span>Статус</span>
                      <strong>{valueItemStatus(activeItem).label}</strong>
                      <small>{valueItemStatus(activeItem).tone === "warn" ? "сначала закрыть маппинг" : "можно проверять экспорт"}</small>
                    </div>
                  </div>
                  <div className="sm-valuesEvidencePanel">
                    {activeItem.pim_sample?.length ? (
                      <div className="sm-valuesEvidenceCard">
                        <strong>PIM словарь</strong>
                        <span>Канонические значения</span>
                        <small>{activeItem.pim_sample.slice(0, 4).join(" · ")}</small>
                      </div>
                    ) : null}
                    {usefulProviders(activeItem).map((provider) => (
                      <div className="sm-valuesEvidenceCard" key={provider.code}>
                        <strong>{provider.title}</strong>
                        <span>{provider.param_name || "Поле площадки не указано"}</span>
                        <small>{providerSampleText(provider) || "Образцов значений пока нет."}</small>
                        {provider.dictionary_quality?.issues?.length ? (
                          <div className="sm-valuesQualityWarnings">
                            {provider.dictionary_quality.issues.slice(0, 2).map((issue) => (
                              <em key={issue.code || issue.label}>{issue.label || "проверь справочник"}</em>
                            ))}
                          </div>
                        ) : null}
                        {String(provider.mode || "").toLowerCase() !== "number" && Number(activeItem.value_count || 0) > 0 && Number(provider.allowed_count || 0) > 0 ? (
                          <button
                            className="btn sm"
                            type="button"
                            disabled={aiValueLoading === `${activeItem.dict_id}:${provider.code}`}
                            onClick={() => void runValueAi(provider)}
                          >
                            {aiValueLoading === `${activeItem.dict_id}:${provider.code}` ? "AI подбирает…" : "Подобрать AI"}
                          </button>
                        ) : null}
                      </div>
                    ))}
                  </div>
                  {aiValueMessage ? <div className="sm-valuesEmpty">{aiValueMessage}</div> : null}
                  {activeItem.source_evidence?.length ? (
                    <div className="sm-valuesSourceEvidence">
                      <div className="sm-valuesSourceEvidenceHead">
                        <strong>Raw values из источников</strong>
                        <span>что пришло с конкурентов и площадок до нормализации</span>
                      </div>
                      <div className="sm-valuesSourceEvidenceList">
                        {activeItem.source_evidence.slice(0, 8).map((evidence, index) => (
                          <div key={`${evidence.product_id || index}:${evidence.source_id || evidence.source_group}:${evidence.raw_value || evidence.resolved_value}`} className="sm-valuesSourceEvidenceItem">
                            <span>{evidence.source_label || evidence.source_id || evidence.source_group || "источник"}</span>
                            <strong>{evidence.raw_value || evidence.resolved_value || evidence.canonical_value}</strong>
                            <small>{sourceEvidenceText(evidence)}</small>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {usefulProviders(activeItem).map((provider) => renderInlineValueEditor(provider))}
                  <DictionaryEditorFeature embedded dictIdOverride={activeItem.dict_id} />
                </>
              ) : (
                <div className="sm-valuesEmpty">
                  {!mappingItemsCount && !rawItemsCount
                    ? "Здесь появятся значения после сборки и подтверждения PIM-параметров."
                    : "Выбери поле слева, чтобы открыть сопоставление значений."}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
