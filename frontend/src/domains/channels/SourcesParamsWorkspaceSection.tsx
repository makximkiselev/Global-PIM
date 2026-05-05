import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import CategorySidebar from "../../components/CategorySidebar";
import { api } from "../../lib/api";

type CatalogNode = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
};
type NodesResp = CatalogNode[] | { nodes?: CatalogNode[] };

type ProviderParam = {
  id: string;
  name: string;
  kind?: string;
  values?: string[];
  required?: boolean;
  export?: boolean;
};

type AttrRow = {
  id: string;
  catalog_name: string;
  group?: string;
  provider_map?: Record<string, ProviderParam>;
  confirmed?: boolean;
};

type AttrDetailsResp = {
  ok: boolean;
  category: { id: string; name: string; path: string };
  mapping: Record<string, string>;
  providers: Record<string, { category_id: string | null; category_name?: string | null; params: ProviderParam[]; count: number }>;
  rows: AttrRow[];
  template_id?: string | null;
  master_template?: { row_count?: number; confirmed_count?: number } | null;
};

type AttrAiMatchResp = {
  ok: boolean;
  engine: string;
  applied: boolean;
  rows: AttrRow[];
  rows_count: number;
};

type CompetitorSourceSuggestion = {
  id: string;
  type: "observed" | "search" | string;
  label: string;
  url: string;
  confidence?: number;
};

type CompetitorCategorySource = {
  id: "restore" | "store77" | string;
  name: string;
  domain: string;
  products_count: number;
  confirmed_count: number;
  candidates_count: number;
  needs_review_count: number;
  suggestions: CompetitorSourceSuggestion[];
};

type CompetitorCategoryResp = {
  ok: boolean;
  category: { id: string; name: string; products_count: number };
  sources: CompetitorCategorySource[];
};

type Props = {
  selectedCategoryId?: string;
  onSelectedCategoryChange?: (categoryId: string, categoryName: string) => void;
};

type QueueFilter = "attention" | "unmapped" | "ready" | "all";

const PROVIDER_LABEL: Record<string, string> = {
  yandex_market: "Я.Маркет",
  ozon: "Ozon",
  restore: "re:Store",
  store77: "Store77",
};
const MARKETPLACE_CODES = ["yandex_market", "ozon"];

const SERVICE_EXPORTS = [
  { key: "sku_gt", title: "SKU GT", target: "offerId / SKU площадки", note: "Главный идентификатор товара для выгрузки." },
  { key: "title", title: "Название", target: "name", note: "Название карточки товара." },
  { key: "brand", title: "Бренд", target: "vendor / brand", note: "Производитель товара." },
  { key: "description", title: "Описание", target: "description", note: "Текст карточки." },
  { key: "media_images", title: "Фото", target: "pictures / images", note: "Основная галерея товара." },
  { key: "barcode", title: "Штрихкод", target: "barcode", note: "Передается при наличии." },
];

function qnorm(value: string) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function buildChildren(nodes: CatalogNode[]) {
  const map = new Map<string, CatalogNode[]>();
  for (const node of nodes) {
    const parent = String(node.parent_id || "");
    const bucket = map.get(parent) || [];
    bucket.push(node);
    map.set(parent, bucket);
  }
  for (const children of map.values()) {
    children.sort((a, b) => {
      const pa = Number(a.position || 0);
      const pb = Number(b.position || 0);
      if (pa !== pb) return pa - pb;
      return String(a.name || "").localeCompare(String(b.name || ""), "ru");
    });
  }
  return map;
}

function serviceKey(row: AttrRow) {
  const id = String(row.id || "");
  if (id.startsWith("svc:")) return id.slice(4);
  const name = qnorm(row.catalog_name || "");
  if (name === "sku gt" || name.includes("sku")) return "sku_gt";
  if (name.includes("штрихкод") || name.includes("barcode")) return "barcode";
  if (name.includes("наименование") || name === "название") return "title";
  if (name.includes("бренд")) return "brand";
  if (name.includes("описание")) return "description";
  if (name.includes("фото") || name.includes("картин")) return "media_images";
  return "";
}

function providerCodes(details: AttrDetailsResp | null) {
  const codes = Object.keys(details?.providers || {});
  return codes.length ? codes : ["yandex_market", "ozon"];
}

function confidenceLabel(value?: number) {
  const raw = Number(value || 0);
  if (!Number.isFinite(raw) || raw <= 0) return "нет score";
  return `${Math.round(raw * 100)}%`;
}

function rowProviderCoverage(row: AttrRow, codes: string[]) {
  return codes.filter((code) => !!String(row.provider_map?.[code]?.id || row.provider_map?.[code]?.name || "").trim()).length;
}

function rowNeedsAttention(row: AttrRow, codes: string[]) {
  return !row.confirmed || rowProviderCoverage(row, codes) === 0;
}

function rowHasValues(row: AttrRow, codes: string[]) {
  if (["select", "enum", "list", "multiselect"].some((part) => qnorm(row.provider_map?.yandex_market?.kind || "").includes(part))) return true;
  return codes.some((code) => Array.isArray(row.provider_map?.[code]?.values) && (row.provider_map?.[code]?.values || []).length > 0);
}

function rowStatusLabel(row: AttrRow, codes: string[]) {
  if (rowProviderCoverage(row, codes) === 0) return "без связки";
  if (!row.confirmed) return "нужна проверка";
  return "подтвержден";
}

export default function SourcesParamsWorkspaceSection({ selectedCategoryId = "", onSelectedCategoryChange }: Props) {
  const [nodes, setNodes] = useState<CatalogNode[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [query, setQuery] = useState("");
  const [details, setDetails] = useState<AttrDetailsResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [aiMatching, setAiMatching] = useState(false);
  const [competitors, setCompetitors] = useState<CompetitorCategoryResp | null>(null);
  const [competitorsLoading, setCompetitorsLoading] = useState(false);
  const [competitorsError, setCompetitorsError] = useState("");
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("attention");
  const [fieldQuery, setFieldQuery] = useState("");
  const [selectedRowId, setSelectedRowId] = useState("");
  const [categoryDrawerOpen, setCategoryDrawerOpen] = useState(false);
  const [savingRowId, setSavingRowId] = useState("");

  async function loadDetails(categoryId: string) {
    const resp = await api<AttrDetailsResp>(`/marketplaces/mapping/import/attributes/${encodeURIComponent(categoryId)}`);
    setDetails(resp);
    onSelectedCategoryChange?.(resp.category.id, resp.category.name);
  }

  async function loadCompetitors(categoryId: string) {
    setCompetitorsLoading(true);
    setCompetitorsError("");
    try {
      const resp = await api<CompetitorCategoryResp>(`/competitor-mapping/discovery/categories/${encodeURIComponent(categoryId)}`);
      setCompetitors(resp);
    } catch (err) {
      setCompetitors(null);
      setCompetitorsError(err instanceof Error ? err.message : "Не удалось загрузить конкурентные источники");
    } finally {
      setCompetitorsLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    void api<NodesResp>("/catalog/nodes").then((resp) => {
      const items = Array.isArray(resp) ? resp : Array.isArray(resp?.nodes) ? resp.nodes : [];
      if (!cancelled) setNodes(items);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedCategoryId) {
      setDetails(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    void loadDetails(selectedCategoryId)
      .then(() => {
        if (cancelled) return;
      })
      .catch((err) => {
        if (cancelled) return;
        setDetails(null);
        setError(err instanceof Error ? err.message : "Не удалось загрузить параметры категории");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedCategoryId]);

  useEffect(() => {
    if (!selectedCategoryId) {
      setCompetitors(null);
      setCompetitorsError("");
      return;
    }
    let cancelled = false;
    setCompetitorsLoading(true);
    setCompetitorsError("");
    void api<CompetitorCategoryResp>(`/competitor-mapping/discovery/categories/${encodeURIComponent(selectedCategoryId)}`)
      .then((resp) => {
        if (!cancelled) setCompetitors(resp);
      })
      .catch((err) => {
        if (cancelled) return;
        setCompetitors(null);
        setCompetitorsError(err instanceof Error ? err.message : "Не удалось загрузить конкурентные источники");
      })
      .finally(() => {
        if (!cancelled) setCompetitorsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedCategoryId]);

  const childrenByParent = useMemo(() => buildChildren(nodes), [nodes]);
  const codes = useMemo(() => providerCodes(details), [details]);
  const rows = details?.rows || [];
  const serviceRows = useMemo(() => rows.filter((row) => serviceKey(row)), [rows]);
  const paramRows = useMemo(() => rows.filter((row) => !serviceKey(row)), [rows]);
  const stats = useMemo(() => {
    const total = paramRows.length;
    const ready = paramRows.filter((row) => !!row.confirmed && rowProviderCoverage(row, codes) > 0).length;
    const unmapped = paramRows.filter((row) => rowProviderCoverage(row, codes) === 0).length;
    const attention = paramRows.filter((row) => rowNeedsAttention(row, codes)).length;
    const values = paramRows.filter((row) => rowHasValues(row, codes)).length;
    return { total, ready, unmapped, attention, values };
  }, [paramRows, codes]);

  const queueRows = useMemo(() => {
    const q = qnorm(fieldQuery);
    return paramRows
      .filter((row) => {
        if (queueFilter === "attention" && !rowNeedsAttention(row, codes)) return false;
        if (queueFilter === "unmapped" && rowProviderCoverage(row, codes) > 0) return false;
        if (queueFilter === "ready" && (!row.confirmed || rowProviderCoverage(row, codes) === 0)) return false;
        if (!q) return true;
        const hay = [
          row.catalog_name,
          row.group,
          ...codes.flatMap((code) => [row.provider_map?.[code]?.name || "", row.provider_map?.[code]?.kind || ""]),
        ].join(" ").toLowerCase();
        return hay.includes(q);
      })
      .sort((a, b) => {
        const aa = rowNeedsAttention(a, codes) ? 0 : 1;
        const bb = rowNeedsAttention(b, codes) ? 0 : 1;
        if (aa !== bb) return aa - bb;
        return String(a.catalog_name || "").localeCompare(String(b.catalog_name || ""), "ru");
      });
  }, [paramRows, codes, queueFilter, fieldQuery]);

  const selectedRow = useMemo(() => {
    const fromSelected = paramRows.find((row) => String(row.id) === selectedRowId);
    return fromSelected || queueRows[0] || paramRows[0] || null;
  }, [paramRows, queueRows, selectedRowId]);

  const categoryName = details?.category?.name || "Выберите категорию";
  const categoryPath = details?.category?.path || "Категория не выбрана";
  const readinessText = stats.total ? `${stats.ready}/${stats.total} готово` : "нет параметров";
  const topSourceCandidates = useMemo(() => {
    return (competitors?.sources || []).flatMap((source) =>
      (source.suggestions || []).slice(0, 2).map((suggestion) => ({
        source,
        suggestion,
      }))
    );
  }, [competitors]);

  useEffect(() => {
    if (!paramRows.length) {
      setSelectedRowId("");
      return;
    }
    if (selectedRowId && paramRows.some((row) => String(row.id) === selectedRowId)) return;
    const next = queueRows[0] || paramRows.find((row) => rowNeedsAttention(row, codes)) || paramRows[0];
    setSelectedRowId(String(next?.id || ""));
  }, [paramRows, queueRows, codes, selectedRowId]);

  function toggleAll() {
    const ids = nodes.filter((node) => (childrenByParent.get(String(node.id || "")) || []).length > 0).map((node) => String(node.id || ""));
    const hasExpanded = ids.some((id) => expanded[id]);
    if (hasExpanded) {
      setExpanded({});
      return;
    }
    setExpanded(Object.fromEntries(ids.map((id) => [id, true])));
  }

  async function runAiMatch() {
    if (!selectedCategoryId) return;
    setAiMatching(true);
    setError("");
    setNotice("");
    try {
      const resp = await api<AttrAiMatchResp>(`/marketplaces/mapping/import/attributes/${encodeURIComponent(selectedCategoryId)}/ai-match`, {
        method: "POST",
        body: JSON.stringify({ apply: true }),
      });
      await loadDetails(selectedCategoryId);
      setNotice(`AI-сопоставление применено (${resp.engine === "ollama" ? "Ollama" : "fallback"}), строк: ${resp.rows_count}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка AI-сопоставления");
    } finally {
      setAiMatching(false);
    }
  }

  async function saveRows(nextRows: AttrRow[], rowId = "") {
    if (!selectedCategoryId) return;
    setSavingRowId(rowId || "__all__");
    setError("");
    setNotice("");
    try {
      await api(`/marketplaces/mapping/import/attributes/${encodeURIComponent(selectedCategoryId)}`, {
        method: "PUT",
        body: JSON.stringify({ rows: nextRows, apply_to_category_ids: [] }),
      });
      await loadDetails(selectedCategoryId);
      setNotice("Изменения по параметру сохранены.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить привязку параметра");
    } finally {
      setSavingRowId("");
    }
  }

  async function updateProviderParam(row: AttrRow, code: string, paramId: string) {
    const providerParam = (details?.providers?.[code]?.params || []).find((param) => String(param.id) === String(paramId));
    const nextRows = rows.map((candidate) => {
      if (String(candidate.id) !== String(row.id)) return candidate;
      const nextMap = { ...(candidate.provider_map || {}) };
      if (!providerParam) {
        delete nextMap[code];
      } else {
        nextMap[code] = {
          id: String(providerParam.id || ""),
          name: String(providerParam.name || ""),
          kind: providerParam.kind,
          values: providerParam.values || [],
          required: !!providerParam.required,
          export: providerParam.export !== false,
        };
      }
      return { ...candidate, provider_map: nextMap, confirmed: false };
    });
    await saveRows(nextRows, String(row.id));
  }

  async function confirmRow(row: AttrRow) {
    const nextRows = rows.map((candidate) => (String(candidate.id) === String(row.id) ? { ...candidate, confirmed: true } : candidate));
    await saveRows(nextRows, String(row.id));
  }

  function renderTree(node: CatalogNode, depth = 0): JSX.Element | null {
    const id = String(node.id || "");
    const children = childrenByParent.get(id) || [];
    const q = qnorm(query);
    const childRows = children.map((child) => renderTree(child, depth + 1)).filter(Boolean) as JSX.Element[];
    const visible = !q || qnorm(node.name || "").includes(q) || childRows.length > 0;
    if (!visible) return null;
    const isExpanded = !!expanded[id];
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
              onClick={(event) => {
                event.stopPropagation();
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
        {children.length && isExpanded ? childRows : null}
      </div>
    );
  }

  return (
    <div className="paramsWorkspace">
      <section className="paramsWorkspaceMain">
        <div className="paramsCommand">
          <div>
            <div className="paramsEyebrow">Категория · параметры · выгрузка</div>
            <h2>{categoryName}</h2>
            <p>{categoryPath}</p>
          </div>
          <div className="paramsCommandActions">
            <button className="btn" type="button" onClick={() => setCategoryDrawerOpen(true)}>Сменить категорию</button>
            <Link className="btn" to={`/sources-mapping?tab=values&category=${encodeURIComponent(selectedCategoryId)}`}>К значениям</Link>
            <button className="btn" type="button" onClick={runAiMatch} disabled={!selectedCategoryId || aiMatching || loading}>
              {aiMatching ? "Собираю..." : "Собрать с AI"}
            </button>
            <Link className="btn btn-primary" to={`/catalog/export?category=${encodeURIComponent(selectedCategoryId)}`}>Проверить выгрузку</Link>
          </div>
        </div>

        {categoryDrawerOpen ? (
          <div className="paramsCategoryDrawer" role="dialog" aria-modal="true">
            <button className="paramsDrawerBackdrop" type="button" aria-label="Закрыть выбор категории" onClick={() => setCategoryDrawerOpen(false)} />
            <CategorySidebar
              className="paramsWorkspaceSidebar"
              title="Выбор категории"
              hint="Каталог нужен только для выбора контекста. Рабочий экран остается сфокусированным на одной категории."
              searchValue={query}
              onSearchChange={setQuery}
              controls={
                <div className="paramsDrawerControls">
                  <button className="btn sm" type="button" onClick={toggleAll}>
                    {Object.values(expanded).some(Boolean) ? "Свернуть" : "Развернуть"}
                  </button>
                  <button className="btn sm" type="button" onClick={() => setCategoryDrawerOpen(false)}>Закрыть</button>
                </div>
              }
            >
              <div className="csb-tree">
                {(childrenByParent.get("") || []).map((root) => renderTree(root, 0))}
              </div>
            </CategorySidebar>
          </div>
        ) : null}

        {error ? (
          <div className="paramsAlert">
            {error.includes("CATEGORY_NOT_DIRECTLY_MAPPED")
              ? "Для этой категории сначала нужна прямая связка с категориями площадок."
              : error}
          </div>
        ) : null}
        {notice ? <div className="paramsAlert isSuccess">{notice}</div> : null}
        {loading ? <div className="paramsAlert">Загружаю параметры категории...</div> : null}

        <div className="paramsSteps">
          <div className="paramsStep isDone"><span>1</span><strong>Категории</strong><em>{Object.keys(details?.mapping || {}).length ? "связаны" : "нужна связка"}</em></div>
          <div className="paramsStep isDone"><span>2</span><strong>Источники</strong><em>{codes.length} площадки</em></div>
          <div className={`paramsStep ${stats.attention ? "isWarn" : "isDone"}`}><span>3</span><strong>Параметры</strong><em>{readinessText}</em></div>
          <Link className="paramsStep" to={`/sources-mapping?tab=values&category=${encodeURIComponent(selectedCategoryId)}`}><span>4</span><strong>Значения</strong><em>варианты написания</em></Link>
          <Link className="paramsStep" to={`/catalog/export?category=${encodeURIComponent(selectedCategoryId)}`}><span>5</span><strong>Выгрузка</strong><em>проверить готовность</em></Link>
        </div>

        <div className="paramsFocusLayout">
          <div className="paramsQueueBlock">
            <div className="paramsSectionHead">
              <div>
                <h3>Параметры инфо-модели</h3>
                <p>Рабочая очередь показывает только поля категории. Выберите поле, проверьте источники справа и подтвердите привязку.</p>
              </div>
            </div>

            <div className="paramsQueueToolbar">
              <input value={fieldQuery} onChange={(event) => setFieldQuery(event.target.value)} placeholder="Поиск: память, цвет, SIM..." />
              {[
                ["attention", "Внимание", stats.attention],
                ["unmapped", "Без связки", stats.unmapped],
                ["ready", "Готово", stats.ready],
                ["all", "Все", stats.total],
              ].map(([key, label, count]) => (
                <button
                  key={String(key)}
                  type="button"
                  className={`paramsChip ${queueFilter === key ? "isActive" : ""}`}
                  onClick={() => setQueueFilter(key as QueueFilter)}
                >
                  {label}<span>{count}</span>
                </button>
              ))}
            </div>

            <div className="paramsQueueList">
              {queueRows.length ? queueRows.map((row) => {
                const coverage = rowProviderCoverage(row, codes);
                const needsAttention = rowNeedsAttention(row, codes);
                const active = String(selectedRow?.id || "") === String(row.id || "");
                return (
                  <button
                    className={`paramsParamCard ${needsAttention ? "isAttention" : "isReady"} ${active ? "isSelected" : ""}`}
                    key={row.id || row.catalog_name}
                    type="button"
                    onClick={() => setSelectedRowId(String(row.id || ""))}
                  >
                    <div className="paramsParamMain">
                      <div className="paramsParamHead">
                        <strong>{row.catalog_name || "Параметр"}</strong>
                        <span>{row.group || "О товаре"}</span>
                      </div>
                      <div className="paramsParamMeta">
                        <span>{coverage}/{codes.length} источников</span>
                        <span>{rowStatusLabel(row, codes)}</span>
                        {rowHasValues(row, codes) ? <span>есть значения</span> : null}
                      </div>
                    </div>
                    <div className="paramsParamProviders">
                      {codes.map((code) => {
                        const value = row.provider_map?.[code];
                        return (
                          <div className="paramsProviderCell" key={`${row.id}-${code}`}>
                            <span>{PROVIDER_LABEL[code] || code}</span>
                            <strong>{value?.name || "не связано"}</strong>
                            <em>{value?.values?.length ? `${value.values.length} значений` : value?.kind || "параметр"}</em>
                          </div>
                        );
                      })}
                    </div>
                  </button>
                );
              }) : (
                <div className="paramsAlert">По текущему фильтру параметров нет.</div>
              )}
            </div>
          </div>

          <aside className="paramsInspector">
            {selectedRow ? (
              <>
                <div className="paramsInspectorHead">
                  <div>
                    <span>Выбранный параметр</span>
                    <h3>{selectedRow.catalog_name || "Параметр"}</h3>
                    <p>{selectedRow.group || "О товаре"}</p>
                  </div>
                  <b className={rowNeedsAttention(selectedRow, codes) ? "isWarn" : "isOk"}>
                    {rowStatusLabel(selectedRow, codes)}
                  </b>
                </div>

                <div className="paramsInspectorSection">
                  <h4>Привязка к площадкам</h4>
                  <p>Здесь редактируется, какое поле площадки наполняет поле PIM.</p>
                  {codes.map((code) => {
                    const provider = details?.providers?.[code];
                    const current = selectedRow.provider_map?.[code];
                    return (
                      <label className="paramsFieldSelect" key={code}>
                        <span>{PROVIDER_LABEL[code] || code}</span>
                        <select
                          value={String(current?.id || "")}
                          disabled={savingRowId === String(selectedRow.id)}
                          onChange={(event) => void updateProviderParam(selectedRow, code, event.target.value)}
                        >
                          <option value="">Не связано</option>
                          {(provider?.params || []).map((param) => (
                            <option value={String(param.id)} key={String(param.id)}>
                              {param.name}
                            </option>
                          ))}
                        </select>
                        <em>{current?.values?.length ? `${current.values.length} значений` : current?.kind || "тип не указан"}</em>
                      </label>
                    );
                  })}
                </div>

                <div className="paramsInspectorSection">
                  <h4>Конкуренты для наполнения</h4>
                  <p>Конкуренты помогают заполнить товары и проверить значения, но не заменяют поля Я.Маркет/Ozon.</p>
                  {competitorsLoading ? <div className="paramsMiniAlert">Загружаю конкурентов...</div> : null}
                  {competitorsError ? <div className="paramsMiniAlert">{competitorsError}</div> : null}
                  <div className="paramsEvidenceGrid">
                    {(competitors?.sources || []).map((source) => (
                      <div className="paramsEvidenceCard" key={source.id}>
                        <strong>{source.name}</strong>
                        <span>{source.products_count || 0} SKU · {source.confirmed_count || 0} связей</span>
                        <em>{source.needs_review_count || 0} на проверке</em>
                      </div>
                    ))}
                    {!competitorsLoading && !competitors?.sources?.length ? <div className="paramsMiniAlert">Источники конкурентов еще не найдены.</div> : null}
                  </div>
                  {topSourceCandidates.length ? (
                    <div className="paramsSuggestionList">
                      {topSourceCandidates.slice(0, 4).map(({ source, suggestion }) => (
                        <a href={suggestion.url} target="_blank" rel="noreferrer" key={`${source.id}-${suggestion.id}`}>
                          <span>{source.name}</span>
                          <strong>{suggestion.label}</strong>
                          <em>{suggestion.type === "search" ? "поиск" : "найдено"} · {confidenceLabel(suggestion.confidence)}</em>
                        </a>
                      ))}
                    </div>
                  ) : null}
                </div>

                <div className="paramsInspectorSection">
                  <h4>Значения и выгрузка</h4>
                  <p>Если поле имеет варианты значений, следующий шаг — настроить написание для каждой площадки.</p>
                  <div className="paramsInspectorActions">
                    <button
                      className="btn btn-primary"
                      type="button"
                      disabled={savingRowId === String(selectedRow.id)}
                      onClick={() => void confirmRow(selectedRow)}
                    >
                      {savingRowId === String(selectedRow.id) ? "Сохраняю..." : "Подтвердить"}
                    </button>
                    <Link className="btn" to={`/sources-mapping?tab=values&category=${encodeURIComponent(selectedCategoryId)}`}>Открыть значения</Link>
                    <Link className="btn" to={`/sources-mapping?tab=competitors&category=${encodeURIComponent(selectedCategoryId)}`}>Очередь конкурентов</Link>
                  </div>
                </div>

                <details className="paramsServiceDetails">
                  <summary>Служебные поля выгрузки</summary>
                  <div className="paramsServiceCompact">
                    {SERVICE_EXPORTS.map((item) => {
                      const row = serviceRows.find((candidate) => serviceKey(candidate) === item.key);
                      return (
                        <div key={item.key}>
                          <strong>{item.title}</strong>
                          <span>{item.target}</span>
                          <em>{row ? "настроено" : "системно"}</em>
                        </div>
                      );
                    })}
                  </div>
                </details>
              </>
            ) : (
              <div className="paramsAlert">Выберите категорию и параметр для работы.</div>
            )}
          </aside>
        </div>
      </section>
    </div>
  );
}
