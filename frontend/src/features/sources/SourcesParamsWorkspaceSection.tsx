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
        <div className={`csb-treeNode ${selectedCategoryId === id ? "is-active" : ""}`} onClick={() => onSelectedCategoryChange?.(id, node.name)}>
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
      <CategorySidebar
        className="paramsWorkspaceSidebar"
        title="Каталог"
        hint="Выберите категорию для настройки полей"
        searchValue={query}
        onSearchChange={setQuery}
        controls={<button className="btn sm" type="button" onClick={toggleAll}>{Object.values(expanded).some(Boolean) ? "Свернуть" : "Развернуть"}</button>}
      >
        <div className="csb-tree">
          {(childrenByParent.get("") || []).map((root) => renderTree(root, 0))}
        </div>
      </CategorySidebar>

      <section className="paramsWorkspaceMain">
        <div className="paramsCommand">
          <div>
            <div className="paramsEyebrow">Рабочий экран категории</div>
            <h2>{details?.category?.name || "Выберите категорию"}</h2>
            <p>{details?.category?.path || "Здесь настраиваются служебные поля, параметры товара и значения для выгрузки."}</p>
          </div>
          <div className="paramsCommandActions">
            <Link className="btn" to={`/sources-mapping?tab=values&category=${encodeURIComponent(selectedCategoryId)}`}>К значениям</Link>
            <button className="btn" type="button" onClick={runAiMatch} disabled={!selectedCategoryId || aiMatching || loading}>
              {aiMatching ? "Сопоставляю..." : "Сопоставить с AI"}
            </button>
            <Link className="btn btn-primary" to={`/catalog/export?category=${encodeURIComponent(selectedCategoryId)}`}>Проверить выгрузку</Link>
          </div>
        </div>

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
          <div className="paramsStep isDone"><span>2</span><strong>Служебные поля</strong><em>SKU GT → offerId</em></div>
          <div className={`paramsStep ${stats.attention ? "isWarn" : "isDone"}`}><span>3</span><strong>Параметры</strong><em>{stats.ready}/{stats.total} готово</em></div>
          <div className="paramsStep"><span>4</span><strong>Значения</strong><em>{stats.values} полей</em></div>
          <div className="paramsStep"><span>5</span><strong>Выгрузка</strong><em>финальная проверка</em></div>
        </div>

        <div className="paramsSourceBlock">
          <div className="paramsSectionHead">
            <div>
              <h3>Источники параметров</h3>
              <p>Здесь видно, какие источники реально дают поля для модели. Если Ozon связан, но параметров нет, это блок загрузки, а не готовое состояние.</p>
            </div>
          </div>
          <div className="paramsSourceGrid">
            {MARKETPLACE_CODES.map((code) => {
              const provider = details?.providers?.[code];
              const count = Number(provider?.count || provider?.params?.length || 0);
              const categoryId = String(provider?.category_id || details?.mapping?.[code] || "").trim();
              const state = count > 0 ? "ready" : categoryId ? "empty" : "missing";
              return (
                <div className={`paramsSourceCard is-${state}`} key={code}>
                  <div>
                    <strong>{PROVIDER_LABEL[code] || code}</strong>
                    <span>{provider?.category_name || categoryId || "категория не связана"}</span>
                  </div>
                  <b>{count > 0 ? `${count} полей загружено` : categoryId ? "параметры не загружены" : "нет связки"}</b>
                  <p>
                    {count > 0
                      ? "Можно сопоставлять с полями PIM."
                      : categoryId
                        ? "Нужно обновить импорт характеристик в коннекторах."
                        : "Сначала свяжите категорию во вкладке «Категории и источники»."}
                  </p>
                </div>
              );
            })}
          </div>
        </div>

        <div className="paramsServiceBlock">
          <div className="paramsSectionHead">
            <div>
              <h3>Служебные поля выгрузки</h3>
              <p>Эти поля передаются напрямую в площадки. Они не попадают в сопоставление значений, потому что у них нет справочников вроде “256 ГБ → 256”.</p>
            </div>
          </div>
          <div className="paramsServiceGrid">
            {SERVICE_EXPORTS.map((item) => {
              const row = serviceRows.find((candidate) => serviceKey(candidate) === item.key);
              return (
                <div className="paramsServiceCard" key={item.key}>
                  <div className="paramsServiceTop">
                    <strong>{item.title}</strong>
                    <span className="isOk">передается напрямую</span>
                  </div>
                  <b>{item.target}</b>
                  <p>{item.note}</p>
                  <div className="paramsProviderMini">
                    {codes.map((code) => (
                      <span key={code}>{PROVIDER_LABEL[code] || code}: {row?.provider_map?.[code]?.name || "системно"}</span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="paramsCompetitorBlock">
          <div className="paramsSectionHead">
            <div>
              <h3>Конкурентные источники</h3>
              <p>re-store и Store77 дают evidence для насыщения товаров. Они не заменяют Я.Маркет/Ozon, но должны быть видны в этом же рабочем процессе.</p>
            </div>
            <Link className="btn" to={`/sources-mapping?tab=competitors&category=${encodeURIComponent(selectedCategoryId)}`}>Открыть очередь</Link>
          </div>
          {competitorsLoading ? <div className="paramsAlert">Загружаю конкурентные источники...</div> : null}
          {competitorsError ? <div className="paramsAlert">{competitorsError}</div> : null}
          <div className="paramsCompetitorGrid">
            {(competitors?.sources || []).map((source) => (
              <div className="paramsCompetitorCard" key={source.id}>
                <div className="paramsCompetitorHead">
                  <div>
                    <strong>{source.name}</strong>
                    <span>{source.domain}</span>
                  </div>
                  <b>{source.products_count || 0} SKU</b>
                </div>
                <div className="paramsCompetitorStats">
                  <span>{source.confirmed_count || 0} подтверждено</span>
                  <span>{source.candidates_count || 0} кандидатов</span>
                  <span>{source.needs_review_count || 0} на модерации</span>
                </div>
                <div className="paramsCompetitorSuggestions">
                  {(source.suggestions || []).slice(0, 3).map((suggestion) => (
                    <a href={suggestion.url} target="_blank" rel="noreferrer" key={suggestion.id}>
                      <span>{suggestion.label}</span>
                      <em>{suggestion.type === "search" ? "поиск" : "найдено"} · {confidenceLabel(suggestion.confidence)}</em>
                    </a>
                  ))}
                  {!source.suggestions?.length ? <p>Нет предложений по разделу. Данные появятся после discovery/enrichment.</p> : null}
                </div>
              </div>
            ))}
            {!competitorsLoading && !competitors?.sources?.length ? (
              <div className="paramsAlert">Для этой категории пока нет competitor context.</div>
            ) : null}
          </div>
        </div>

        <div className="paramsQueueBlock">
          <div className="paramsSectionHead">
            <div>
              <h3>Очередь параметров</h3>
              <p>Сначала показываем то, что мешает готовности категории. Табличный режим больше не является основным рабочим экраном.</p>
            </div>
            <div className="paramsStats">
              <span>{stats.attention} требует внимания</span>
              <span>{stats.unmapped} без связки</span>
              <span>{stats.ready} готово</span>
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
              return (
                <article className={`paramsParamCard ${needsAttention ? "isAttention" : "isReady"}`} key={row.id || row.catalog_name}>
                  <div className="paramsParamMain">
                    <div className="paramsParamHead">
                      <strong>{row.catalog_name || "Параметр"}</strong>
                      <span>{row.group || "О товаре"}</span>
                    </div>
                    <div className="paramsParamMeta">
                      <span>{coverage}/{codes.length} источников</span>
                      <span>{row.confirmed ? "подтвержден" : "нужна проверка"}</span>
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
                </article>
              );
            }) : (
              <div className="paramsAlert">По текущему фильтру параметров нет.</div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
