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
  summary?: {
    changed_rows?: number;
    improved_rows?: number;
    provider_added?: Record<string, number>;
    before?: { total?: number; ready?: number; attention?: number; unmapped?: number; sample_unmapped?: string[] };
    after?: { total?: number; ready?: number; attention?: number; unmapped?: number; sample_unmapped?: string[] };
  };
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
type ParamGroupKey = "all" | "product" | "technical" | "logistics" | "media" | "service" | "other";

const PROVIDER_LABEL: Record<string, string> = {
  yandex_market: "Я.Маркет",
  ozon: "Ozon",
  restore: "re:Store",
  store77: "Store77",
};
const MARKETPLACE_CODES = ["yandex_market", "ozon"];
const PARAM_GROUPS: Array<{ key: Exclude<ParamGroupKey, "all">; label: string; hint: string }> = [
  { key: "product", label: "Товарные", hint: "Название, бренд, модель, цвет" },
  { key: "technical", label: "Технические", hint: "Память, экран, SIM, характеристики" },
  { key: "logistics", label: "Логистика", hint: "Вес, габариты, упаковка, страна" },
  { key: "media", label: "Медиа", hint: "Фото, описание, контент" },
  { key: "service", label: "Служебные", hint: "SKU, offerId, штрихкод" },
  { key: "other", label: "Прочие", hint: "Нужна классификация" },
];
const PARAM_GROUP_LABEL = Object.fromEntries(PARAM_GROUPS.map((item) => [item.key, item.label])) as Record<Exclude<ParamGroupKey, "all">, string>;

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

function paramGroupKey(row: AttrRow): Exclude<ParamGroupKey, "all"> {
  const service = serviceKey(row);
  if (service) {
    if (service === "description" || service === "media_images") return "media";
    return "service";
  }
  const source = qnorm(`${row.group || ""} ${row.catalog_name || ""}`);
  if (/(логист|габарит|размер|вес|длина|ширина|высота|упаков|страна|сертифик|код тн|штрихкод)/.test(source)) return "logistics";
  if (/(медиа|фото|изображ|картин|видео|описан|контент|rich|инфограф)/.test(source)) return "media";
  if (/(технич|памят|накопител|процессор|камера|экран|дисплей|аккумулятор|sim|esim|wi[- ]?fi|bluetooth|операцион|разъем|частот|разрешен|диагонал|ядр|датчик)/.test(source)) {
    return "technical";
  }
  if (/(товар|назван|бренд|марка|модель|цвет|серия|комплект|гарант|линейк|тип товара|назначен)/.test(source)) return "product";
  return "other";
}

function paramGroupLabel(row: AttrRow) {
  return PARAM_GROUP_LABEL[paramGroupKey(row)];
}

function providerCodes(details: AttrDetailsResp | null) {
  const codes = Object.keys(details?.providers || {});
  return codes.length ? codes : ["yandex_market", "ozon"];
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

function aiEngineLabel(engine: string) {
  return engine === "ollama" ? "Ollama" : "локальные правила";
}

function formatAiMatchNotice(resp: AttrAiMatchResp) {
  const summary = resp.summary || {};
  const after = summary.after || {};
  const improved = Number(summary.improved_rows || 0);
  const changed = Number(summary.changed_rows || 0);
  const ready = Number(after.ready || 0);
  const total = Number(after.total || resp.rows_count || 0);
  const unmapped = Number(after.unmapped || 0);
  const attention = Number(after.attention || 0);
  const providerAdded = summary.provider_added || {};
  const providerParts = Object.entries(providerAdded)
    .filter(([, count]) => Number(count || 0) > 0)
    .map(([provider, count]) => `${provider === "yandex_market" ? "Я.Маркет" : provider === "ozon" ? "Ozon" : provider}: +${count}`);
  const providerText = providerParts.length ? ` Источники: ${providerParts.join(", ")}.` : "";
  if (improved > 0) {
    return `AI-сопоставление (${aiEngineLabel(resp.engine)}) улучшило ${improved} полей, изменено ${changed}. Готово ${ready}/${total}, без связки ${unmapped}, требует внимания ${attention}.${providerText}`;
  }
  return `AI-сопоставление (${aiEngineLabel(resp.engine)}) проверило ${total} полей, но новых уверенных связок не нашло. Готово ${ready}/${total}, без связки ${unmapped}, требует внимания ${attention}.`;
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
  const [groupFilter, setGroupFilter] = useState<ParamGroupKey>("all");
  const [fieldQuery, setFieldQuery] = useState("");
  const [selectedRowId, setSelectedRowId] = useState("");
  const [categoryDrawerOpen, setCategoryDrawerOpen] = useState(false);
  const [savingRowId, setSavingRowId] = useState("");
  const [providerSearch, setProviderSearch] = useState<Record<string, string>>({});

  async function loadDetails(categoryId: string) {
    const resp = await api<AttrDetailsResp>(`/marketplaces/mapping/import/attributes/${encodeURIComponent(categoryId)}`);
    setDetails(resp);
    onSelectedCategoryChange?.(resp.category.id, resp.category.name);
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
  const groupStats = useMemo(() => {
    const base = new Map(
      PARAM_GROUPS.map((item) => [
        item.key,
        {
          ...item,
          total: 0,
          ready: 0,
          attention: 0,
          unmapped: 0,
          percent: 0,
        },
      ]),
    );
    for (const row of paramRows) {
      const group = paramGroupKey(row);
      const current = base.get(group);
      if (!current) continue;
      current.total += 1;
      if (rowProviderCoverage(row, codes) === 0) current.unmapped += 1;
      if (rowNeedsAttention(row, codes)) current.attention += 1;
      else current.ready += 1;
    }
    return PARAM_GROUPS.map((item) => {
      const current = base.get(item.key) || { ...item, total: 0, ready: 0, attention: 0, unmapped: 0, percent: 0 };
      return { ...current, percent: current.total ? Math.round((current.ready / current.total) * 100) : 0 };
    });
  }, [paramRows, codes]);

  const queueRows = useMemo(() => {
    const q = qnorm(fieldQuery);
    return paramRows
      .filter((row) => {
        if (groupFilter !== "all" && paramGroupKey(row) !== groupFilter) return false;
        if (queueFilter === "attention" && !rowNeedsAttention(row, codes)) return false;
        if (queueFilter === "unmapped" && rowProviderCoverage(row, codes) > 0) return false;
        if (queueFilter === "ready" && (!row.confirmed || rowProviderCoverage(row, codes) === 0)) return false;
        if (!q) return true;
        const hay = [
          row.catalog_name,
          row.group,
          paramGroupLabel(row),
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
  }, [paramRows, codes, queueFilter, groupFilter, fieldQuery]);

  const selectedRow = useMemo(() => {
    const fromSelected = queueRows.find((row) => String(row.id) === selectedRowId);
    return fromSelected || queueRows[0] || null;
  }, [queueRows, selectedRowId]);

  const categoryName = details?.category?.name || "Выберите категорию";
  const categoryPath = details?.category?.path || "Категория не выбрана";
  const initialParamsLoading = loading && !details;
  const readinessText = initialParamsLoading
    ? "загружаю поля инфо-модели"
    : stats.total
      ? `${stats.ready}/${stats.total} полей инфо-модели готово`
      : "нет полей инфо-модели";
  const competitorTotals = useMemo(() => {
    const sources = competitors?.sources || [];
    return sources.reduce(
      (acc, source) => ({
        sources: acc.sources + 1,
        products: acc.products + Number(source.products_count || 0),
        links: acc.links + Number(source.confirmed_count || 0),
        review: acc.review + Number(source.needs_review_count || 0),
      }),
      { sources: 0, products: 0, links: 0, review: 0 },
    );
  }, [competitors]);

  useEffect(() => {
    if (!paramRows.length || !queueRows.length) {
      setSelectedRowId("");
      return;
    }
    if (selectedRowId && queueRows.some((row) => String(row.id) === selectedRowId)) return;
    const next = queueRows[0];
    setSelectedRowId(String(next?.id || ""));
  }, [paramRows, queueRows, selectedRowId]);

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
      setNotice(formatAiMatchNotice(resp));
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

  function providerParamOptions(code: string, current?: ProviderParam) {
    const search = qnorm(providerSearch[code] || "");
    const params = details?.providers?.[code]?.params || [];
    const sorted = [...params].sort((a, b) => {
      const currentId = String(current?.id || "");
      if (currentId && String(a.id) === currentId) return -1;
      if (currentId && String(b.id) === currentId) return 1;
      const aq = qnorm(a.name || "");
      const bq = qnorm(b.name || "");
      const aStarts = search ? aq.startsWith(search) : false;
      const bStarts = search ? bq.startsWith(search) : false;
      if (aStarts !== bStarts) return aStarts ? -1 : 1;
      return String(a.name || "").localeCompare(String(b.name || ""), "ru");
    });
    const filtered = search
      ? sorted.filter((param) => {
          const hay = `${param.name || ""} ${param.kind || ""}`.toLowerCase();
          return hay.includes(search);
        })
      : sorted;
    return { allCount: params.length, filtered, visible: filtered.slice(0, 8) };
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
            <div className="paramsEyebrow">Параметры инфо-модели</div>
            <h2>{categoryName}</h2>
            <div className="paramsCommandBadges" aria-label="Готовность параметров">
              <span>{Object.keys(details?.mapping || {}).length ? "категории связаны" : "нужна связка категорий"}</span>
              <span>{codes.length} площадки</span>
              <span>{readinessText}</span>
              <span>{stats.values} с вариантами значений</span>
            </div>
          </div>
          <div className="paramsCommandActions">
            <button className="btn" type="button" onClick={() => setCategoryDrawerOpen(true)}>Сменить категорию</button>
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

        <div className="paramsFocusLayout">
          <div className="paramsQueueBlock">
            <div className="paramsSectionHead">
              <div>
                <h3>Параметры инфо-модели</h3>
                <p>
                  Рабочие поля PIM для товаров этой категории. Справа выберите поля площадок и подтвердите результат.
                </p>
              </div>
            </div>

            <div className="paramsQueueToolbar">
              <input
                value={fieldQuery}
                onChange={(event) => {
                  setFieldQuery(event.target.value);
                  if (event.target.value.trim()) setQueueFilter("all");
                }}
                placeholder="Поиск: память, цвет, SIM..."
              />
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
                  disabled={initialParamsLoading}
                >
                  {label}<span>{initialParamsLoading ? "..." : count}</span>
                </button>
              ))}
            </div>

            <div className="paramsGroupRail" aria-label="Группы параметров">
              <button
                type="button"
                className={`paramsGroupChip ${groupFilter === "all" ? "isActive" : ""}`}
                onClick={() => {
                  setGroupFilter("all");
                  setQueueFilter("attention");
                }}
                disabled={initialParamsLoading}
              >
                <strong>Все поля</strong>
                <span>{initialParamsLoading ? "..." : `${stats.ready}/${stats.total}`}</span>
                <em>общая готовность</em>
              </button>
              {groupStats.filter((group) => group.total > 0).map((group) => (
                <button
                  key={group.key}
                  type="button"
                  className={`paramsGroupChip ${groupFilter === group.key ? "isActive" : ""} ${group.attention ? "hasAttention" : ""}`}
                  onClick={() => {
                    setGroupFilter(group.key);
                    setQueueFilter("all");
                  }}
                  disabled={initialParamsLoading}
                >
                  <strong>{group.label}</strong>
                  <span>{initialParamsLoading ? "..." : `${group.percent}%`}</span>
                  <em>{group.total ? `${group.ready}/${group.total} готово` : group.hint}</em>
                </button>
              ))}
            </div>

            <div className="paramsQueueList">
              <div className="paramsMatrixHead" aria-hidden="true">
                <span>Поле PIM</span>
                <span>Статус</span>
                {codes.map((code) => <span key={code}>{PROVIDER_LABEL[code] || code}</span>)}
              </div>
              {initialParamsLoading ? (
                Array.from({ length: 5 }).map((_, index) => (
                  <div className="paramsParamCard paramsParamCardSkeleton" key={`params-loading-${index}`}>
                    <div className="paramsSkeletonLine isTitle" />
                    <div className="paramsSkeletonGrid">
                      <span />
                      <span />
                    </div>
                  </div>
                ))
              ) : queueRows.length ? queueRows.map((row) => {
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
                        <span>{paramGroupLabel(row)}</span>
                      </div>
                      <div className="paramsParamMeta">
                        {rowHasValues(row, codes) ? <span>есть значения</span> : null}
                      </div>
                    </div>
                    <div className="paramsParamStatus">
                      <span>{coverage}/{codes.length}</span>
                      <strong>{rowStatusLabel(row, codes)}</strong>
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
            {initialParamsLoading ? (
              <div className="paramsInspectorLoading">
                <div className="paramsSkeletonLine isTitle" />
                <div className="paramsSkeletonLine" />
                <div className="paramsSkeletonLine" />
                <div className="paramsSkeletonGrid">
                  <span />
                  <span />
                </div>
              </div>
            ) : selectedRow ? (
              <>
                <div className="paramsInspectorHead">
                  <div>
                    <span>Выбранный параметр</span>
                    <h3>{selectedRow.catalog_name || "Параметр"}</h3>
                    <p>{paramGroupLabel(selectedRow)}{selectedRow.group ? ` · ${selectedRow.group}` : ""}</p>
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
                    const options = providerParamOptions(code, current);
                    return (
                      <div className="paramsFieldSelect" key={code}>
                        <div className="paramsProviderBindHead">
                          <span>{PROVIDER_LABEL[code] || code}</span>
                          <b className={current?.id ? "isOk" : "isWarn"}>{current?.id ? "связано" : "не связано"}</b>
                        </div>
                        <div className="paramsProviderCurrent">
                          <strong>{current?.name || "Поле площадки не выбрано"}</strong>
                          <em>{current?.values?.length ? `${current.values.length} значений` : current?.kind || "тип не указан"}</em>
                        </div>
                        <input
                          value={providerSearch[code] || ""}
                          disabled={savingRowId === String(selectedRow.id)}
                          onChange={(event) => setProviderSearch((prev) => ({ ...prev, [code]: event.target.value }))}
                          placeholder={`Найти поле ${PROVIDER_LABEL[code] || code}`}
                        />
                        <div className="paramsProviderOptionList">
                          <button
                            type="button"
                            className={!current?.id ? "isSelected" : ""}
                            disabled={savingRowId === String(selectedRow.id)}
                            onClick={() => void updateProviderParam(selectedRow, code, "")}
                          >
                            <strong>Не связывать</strong>
                            <em>Поле не передается на площадку</em>
                          </button>
                          {options.visible.map((param) => (
                            <button
                              type="button"
                              key={String(param.id)}
                              className={String(current?.id || "") === String(param.id) ? "isSelected" : ""}
                              disabled={savingRowId === String(selectedRow.id)}
                              onClick={() => void updateProviderParam(selectedRow, code, String(param.id))}
                            >
                              <strong>{param.name}</strong>
                              <em>{param.values?.length ? `${param.values.length} значений` : param.kind || "тип не указан"}</em>
                            </button>
                          ))}
                        </div>
                        <small>
                          {options.filtered.length
                            ? `Показано ${Math.min(options.visible.length, options.filtered.length)} из ${options.filtered.length}`
                            : `Нет совпадений из ${provider?.count || options.allCount || 0} полей`}
                        </small>
                      </div>
                    );
                  })}
                </div>

                <div className="paramsInspectorSection">
                  <h4>Источники наполнения</h4>
                  <p>Конкуренты используются как источник фактов для товара и значений.</p>
                  {competitorsLoading ? <div className="paramsMiniAlert">Загружаю конкурентов...</div> : null}
                  {competitorsError ? <div className="paramsMiniAlert">{competitorsError}</div> : null}
                  <div className="paramsEvidenceGrid">
                    <div className="paramsEvidenceCard">
                      <strong>{competitorTotals.sources || "нет"} источников</strong>
                      <span>{competitorTotals.products || 0} SKU в пуле</span>
                      <em>{competitorTotals.links || 0} подтверждено</em>
                    </div>
                    <div className="paramsEvidenceCard">
                      <strong>{competitorTotals.review || 0} на проверке</strong>
                      <span>re-store / store77</span>
                      <em>отдельная очередь</em>
                    </div>
                  </div>
                  <Link className="btn" to={`/data-prep/competitors?category=${encodeURIComponent(selectedCategoryId)}`}>Открыть конкурентов</Link>
                </div>

                <div className="paramsInspectorSection">
                  <h4>Следующее действие</h4>
                  <p>После подтверждения поля настройте варианты написания для площадок.</p>
                  <div className="paramsInspectorActions">
                    <button
                      className="btn btn-primary"
                      type="button"
                      disabled={savingRowId === String(selectedRow.id)}
                      onClick={() => void confirmRow(selectedRow)}
                    >
                      {savingRowId === String(selectedRow.id) ? "Сохраняю..." : "Подтвердить"}
                    </button>
                    <Link className="btn" to={`/sources-mapping?tab=values&category=${encodeURIComponent(selectedCategoryId)}`}>Настроить значения</Link>
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
