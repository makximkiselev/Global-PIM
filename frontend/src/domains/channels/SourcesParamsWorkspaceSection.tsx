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
  match_source?: string;
  match_confidence?: number | null;
  match_reason?: string;
  bindings?: ProviderBinding[];
};

type ProviderBinding = Omit<ProviderParam, "bindings">;

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
  mapping_meta?: {
    direct?: Record<string, string>;
    effective?: Record<string, string>;
    sources?: Record<string, string>;
    inherited?: boolean;
  };
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

type AttrAiMatchJobResp = {
  ok: boolean;
  job_id: string;
  catalog_category_id: string;
  status: "queued" | "running" | "completed" | "failed" | string;
  phase?: string;
  message?: string;
  engine?: string | null;
  ai_error?: string;
  rows_count?: number | null;
  summary?: AttrAiMatchResp["summary"];
  error?: string;
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
  focusParameter?: string;
  onSelectedCategoryChange?: (categoryId: string, categoryName: string) => void;
};

type QueueFilter = "attention" | "unmapped" | "complex" | "ready" | "all";
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
  { key: "sku_gt", title: "SKU GT", target: "offerId / SKU площадки", note: "Идентификатор товара. Передается в экспортном payload, не как характеристика." },
  { key: "title", title: "Название", target: "name", note: "Название карточки товара. Берется из товарной карточки." },
  { key: "description", title: "Описание", target: "description", note: "Текст карточки. Передается через контентный блок экспорта." },
  { key: "media_images", title: "Фото", target: "pictures / images", note: "Основная галерея товара. Передается через медиа-блок экспорта." },
  { key: "barcode", title: "Штрихкод", target: "barcode", note: "Передается при наличии в товаре, не требует выбора характеристики." },
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
  return codes.filter((code) => providerBindings(row.provider_map?.[code]).length > 0).length;
}

function rowNeedsAttention(row: AttrRow, codes: string[]) {
  return !row.confirmed || rowProviderCoverage(row, codes) === 0;
}

function rowHasValues(row: AttrRow, codes: string[]) {
  return codes.some((code) => providerBindings(row.provider_map?.[code]).some((item) => providerValueMode(item).needsValues));
}

function rowHasComplexBindings(row: AttrRow, codes: string[]) {
  return codes.some((code) => providerBindings(row.provider_map?.[code]).length > 1);
}

function rowStatusLabel(row: AttrRow, codes: string[]) {
  if (rowProviderCoverage(row, codes) === 0 && row.confirmed) return "не передавать";
  if (rowProviderCoverage(row, codes) === 0) return "без связки";
  if (!row.confirmed) return "нужна проверка";
  return "подтвержден";
}

function rowStatusReason(row: AttrRow, codes: string[]) {
  const coverage = rowProviderCoverage(row, codes);
  if (coverage === 0) {
    if (row.confirmed) {
      return "Пользователь подтвердил, что это поле не передается как характеристика площадки. Если решение изменилось, сбросьте его и выберите поле площадки.";
    }
    return "Поле PIM пока не связано ни с одной площадкой. Выберите подходящие поля вручную или запустите AI-подбор по всей категории.";
  }
  if (rowHasComplexBindings(row, codes)) {
    return "У поля есть сложная связка: один параметр PIM передается в несколько полей площадки. Проверьте это вручную перед подтверждением.";
  }
  if (!row.confirmed) {
    return "Связка найдена, но еще не подтверждена пользователем. Проверьте названия полей и сохраните решение.";
  }
  return "Поле подтверждено. Дальше проверьте значения, если у площадки есть справочник или альтернативные написания.";
}

function mappingOriginLabel(source?: string) {
  const value = qnorm(source || "");
  if (value === "ai" || value === "ollama" || value === "llm") return "AI";
  if (value === "rule" || value === "fallback" || value === "deterministic") return "Правило";
  if (value === "memory" || value === "ai_mapping_memory") return "Память";
  if (value === "manual" || value === "user") return "Ручное";
  if (value === "system") return "Системное";
  return "Источник не указан";
}

function mappingOriginClass(source?: string) {
  const value = qnorm(source || "");
  if (value === "ai" || value === "ollama" || value === "llm") return "isAi";
  if (value === "rule" || value === "fallback" || value === "deterministic") return "isRule";
  if (value === "memory" || value === "ai_mapping_memory") return "isMemory";
  if (value === "manual" || value === "user") return "isManual";
  return "";
}

function formatConfidence(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "";
  return `${Math.round(Math.max(0, Math.min(1, Number(value))) * 100)}%`;
}

function providerValueMode(binding?: ProviderBinding | ProviderParam | null) {
  const kind = qnorm(binding?.kind || "");
  const valuesCount = Array.isArray(binding?.values) ? binding.values.length : 0;
  if (kind.includes("boolean") || kind === "bool") {
    return {
      code: "boolean",
      label: "Да/Нет",
      hint: "Площадка ждет булево значение. Нужна нормализация да/нет из PIM.",
      needsValues: true,
    };
  }
  if (kind.includes("мульти") || kind.includes("multi")) {
    return {
      code: "multi",
      label: "Мультивыбор",
      hint: valuesCount ? "Площадка принимает несколько значений из справочника." : "Площадка принимает несколько значений; справочник не загружен.",
      needsValues: true,
    };
  }
  if (kind.includes("enum") || kind.includes("select") || kind.includes("list") || valuesCount > 0) {
    return {
      code: "dictionary",
      label: "Справочник",
      hint: valuesCount ? "Нужна нормализация PIM-значений в допустимые значения площадки." : "Справочник ожидается, но допустимые значения не загружены.",
      needsValues: true,
    };
  }
  if (kind.includes("numeric") || kind.includes("decimal") || kind.includes("integer") || kind.includes("number")) {
    return {
      code: "number",
      label: "Число",
      hint: "Площадка ждет число. Проверьте единицы измерения и не отправляйте текст с единицами.",
      needsValues: false,
    };
  }
  if (kind.includes("text") || kind.includes("string")) {
    return {
      code: "text",
      label: "Текст",
      hint: "Площадка принимает свободный текст без справочника значений.",
      needsValues: false,
    };
  }
  return {
    code: "unknown",
    label: "Тип не указан",
    hint: "Тип поля площадки не загружен. Проверьте вручную перед подтверждением.",
    needsValues: false,
  };
}

function serviceExportStatus(row: AttrRow | undefined, codes: string[]) {
  if (!row) {
    return {
      label: "системно",
      className: "isSystem",
      hint: "Поле не заведено как параметр категории и заполняется экспортом, если есть данные товара.",
    };
  }
  const coverage = rowProviderCoverage(row, codes);
  if (coverage > 0) {
    return {
      label: "проверьте связку",
      className: "isWarn",
      hint: "Служебное поле связано как характеристика. Обычно это ошибка: его нужно передавать через export payload.",
    };
  }
  if (row.confirmed) {
    return {
      label: "экспорт",
      className: "isOk",
      hint: "Подтверждено: поле не уходит как характеристика площадки.",
    };
  }
  return {
    label: "не характеристика",
    className: "isMuted",
    hint: "Поле похоже на служебное. Подтвердите 'Не передавать', если оно должно идти через экспорт.",
  };
}

function providerOriginChips(bindings: ProviderBinding[]) {
  const bySource = new Map<string, { source: string; count: number; confidence: number | null; reasons: string[] }>();
  for (const binding of bindings) {
    const source = String(binding.match_source || "").trim() || "unknown";
    const current = bySource.get(source) || { source, count: 0, confidence: null, reasons: [] };
    current.count += 1;
    const confidence = binding.match_confidence === null || binding.match_confidence === undefined ? null : Number(binding.match_confidence);
    if (confidence !== null && !Number.isNaN(confidence)) {
      current.confidence = current.confidence === null ? confidence : Math.max(current.confidence, confidence);
    }
    if (binding.match_reason) current.reasons.push(binding.match_reason);
    bySource.set(source, current);
  }
  return [...bySource.values()].sort((a, b) => {
    const order = ["manual", "user", "memory", "ai_mapping_memory", "ai", "ollama", "llm", "rule", "fallback", "deterministic", "system", "unknown"];
    const ai = order.indexOf(qnorm(a.source));
    const bi = order.indexOf(qnorm(b.source));
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });
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

function formatAiJobNotice(job: AttrAiMatchJobResp) {
  return formatAiMatchNotice({
    ok: true,
    engine: String(job.engine || "fallback"),
    applied: true,
    rows: [],
    rows_count: Number(job.rows_count || 0),
    summary: job.summary,
  });
}

function providerBindingPayload(param?: ProviderParam | ProviderBinding): ProviderBinding | null {
  if (!param) return null;
  const id = String(param.id || "").trim();
  const name = String(param.name || "").trim();
  if (!id && !name) return null;
  return {
    id,
    name,
    kind: param.kind || "",
    values: param.values || [],
    required: !!param.required,
    export: param.export !== false,
    match_source: param.match_source || "",
    match_confidence: param.match_confidence ?? null,
    match_reason: param.match_reason || "",
  };
}

function providerBindings(value?: ProviderParam): ProviderBinding[] {
  const out: ProviderBinding[] = [];
  const seen = new Set<string>();
  const add = (item?: ProviderParam | ProviderBinding) => {
    const payload = providerBindingPayload(item);
    if (!payload) return;
    const key = payload.id || `name:${qnorm(payload.name)}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push(payload);
  };
  add(value);
  (value?.bindings || []).forEach(add);
  return out;
}

function providerMapFromBindings(bindings: ProviderBinding[]): ProviderParam | undefined {
  const filtered = bindings.map(providerBindingPayload).filter(Boolean) as ProviderBinding[];
  if (!filtered.length) return undefined;
  const primary = filtered[0];
  return { ...primary, bindings: filtered };
}

function asManualBinding(param: ProviderBinding): ProviderBinding {
  return {
    ...param,
    match_source: "manual",
    match_confidence: null,
    match_reason: "Поле выбрано пользователем в редакторе сопоставления.",
  };
}

function providerOptionGroups(row: AttrRow, visible: ProviderParam[], currentIds: Set<string>, search: string) {
  const selected: ProviderParam[] = [];
  const suggested: ProviderParam[] = [];
  const manual: ProviderParam[] = [];
  const target = qnorm(row.catalog_name || "");
  const targetTokens = target.split(" ").filter((token) => token.length >= 4);
  const isSearch = !!qnorm(search || "");

  for (const param of visible) {
    const id = String(param.id || "").trim();
    const name = qnorm(param.name || "");
    if (id && currentIds.has(id)) {
      selected.push(param);
      continue;
    }
    const closeByName = !isSearch && target && name && (
      name.includes(target) ||
      target.includes(name) ||
      targetTokens.some((token) => name.includes(token))
    );
    if (closeByName) {
      suggested.push(param);
      continue;
    }
    manual.push(param);
  }

  return [
    { key: "selected", title: "Связано сейчас", hint: "Рекомендация или ручной выбор уже применены к этому PIM-полю.", items: selected },
    { key: "suggested", title: "Близко по названию", hint: "Поля площадки, похожие на выбранный PIM-параметр. Проверьте тип и значения.", items: suggested },
    { key: "manual", title: isSearch ? "Ручной поиск" : "Все остальные поля", hint: "Полный ручной выбор из параметров выбранной категории площадки.", items: manual },
  ].filter((group) => group.items.length > 0);
}

export default function SourcesParamsWorkspaceSection({ selectedCategoryId: selectedCategoryIdProp = "", focusParameter = "", onSelectedCategoryChange }: Props) {
  const selectedCategoryId = selectedCategoryIdProp || (typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("category") || "" : "");
  const [nodes, setNodes] = useState<CatalogNode[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [query, setQuery] = useState("");
  const [details, setDetails] = useState<AttrDetailsResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [detailsReloadSeq, setDetailsReloadSeq] = useState(0);
  const [notice, setNotice] = useState("");
  const [aiMatching, setAiMatching] = useState(false);
  const [aiJob, setAiJob] = useState<AttrAiMatchJobResp | null>(null);
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
  }, [selectedCategoryId, detailsReloadSeq]);

  const retryDetailsLoad = () => {
    if (!selectedCategoryId || loading) return;
    setDetailsReloadSeq((value) => value + 1);
  };

  useEffect(() => {
    if (!aiJob?.job_id || aiJob.status === "completed" || aiJob.status === "failed") return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const next = await api<AttrAiMatchJobResp>(
          `/marketplaces/mapping/import/attributes/ai-match/jobs/${encodeURIComponent(aiJob.job_id)}`
        );
        if (cancelled) return;
        setAiJob(next);
        setAiMatching(next.status === "queued" || next.status === "running");
        if (next.status === "completed") {
          await loadDetails(next.catalog_category_id || selectedCategoryId);
          if (!cancelled) setNotice(formatAiJobNotice(next));
        }
        if (next.status === "failed") {
          setError(next.error || "AI-сопоставление не завершилось");
        }
      } catch (err) {
        if (!cancelled) {
          setAiMatching(false);
          setError(err instanceof Error ? err.message : "Не удалось получить статус AI-сопоставления");
        }
      }
    }, 1600);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [aiJob, selectedCategoryId]);

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
    const complex = paramRows.filter((row) => rowHasComplexBindings(row, codes)).length;
    const values = paramRows.filter((row) => rowHasValues(row, codes)).length;
    return { total, ready, unmapped, attention, complex, values };
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
        if (queueFilter === "complex" && !rowHasComplexBindings(row, codes)) return false;
        if (queueFilter === "ready" && (!row.confirmed || rowProviderCoverage(row, codes) === 0)) return false;
        if (!q) return true;
        const hay = [
          row.catalog_name,
          row.group,
          paramGroupLabel(row),
          ...codes.flatMap((code) => providerBindings(row.provider_map?.[code]).flatMap((item) => [item.name || "", item.kind || ""])),
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
  const mappingInherited = !!details?.mapping_meta?.inherited;
  const hasProviderCategoryMapping = Object.keys(details?.mapping || {}).length > 0;
  const inheritedProviderLabels = useMemo(() => {
    if (!details?.mapping_meta?.inherited) return [];
    const sources = details.mapping_meta.sources || {};
    const labels: string[] = [];
    for (const code of codes) {
      const source = String(sources[code] || "").trim();
      if (source && source !== selectedCategoryId) labels.push(PROVIDER_LABEL[code] || code);
    }
    return labels;
  }, [details?.mapping_meta, codes, selectedCategoryId]);
  const initialParamsLoading = loading && !details;
  const readinessText = initialParamsLoading
    ? "загружаю черновик параметров"
    : stats.total
      ? `${stats.ready}/${stats.total} параметров черновика готово`
      : "черновик параметров пуст";
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
  const hasCompetitorEvidence = competitorTotals.links > 0 || competitorTotals.review > 0;
  const infoModelIsEmpty = !!selectedCategoryId && !initialParamsLoading && hasProviderCategoryMapping && stats.total === 0;

  useEffect(() => {
    const focus = qnorm(focusParameter);
    if (!focus || !paramRows.length) return;
    const match = paramRows.find((row) => {
      const hay = qnorm([row.catalog_name, row.group, row.id].join(" "));
      return hay.includes(focus) || focus.includes(qnorm(row.catalog_name || ""));
    });
    setFieldQuery(focusParameter);
    setGroupFilter("all");
    setQueueFilter("all");
    if (match) setSelectedRowId(String(match.id || ""));
  }, [focusParameter, paramRows]);

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
    setAiJob(null);
    try {
      const resp = await api<AttrAiMatchJobResp>(`/marketplaces/mapping/import/attributes/${encodeURIComponent(selectedCategoryId)}/ai-match/jobs`, {
        method: "POST",
        body: JSON.stringify({ apply: true }),
      });
      setAiJob(resp);
      setNotice(resp.message || "AI-подбор запущен. Можно продолжать работу на странице.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка AI-сопоставления");
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

  async function saveProviderBindings(row: AttrRow, code: string, bindings: ProviderBinding[]) {
    const nextProvider = providerMapFromBindings(bindings);
    const nextRows = rows.map((candidate) => {
      if (String(candidate.id) !== String(row.id)) return candidate;
      const nextMap = { ...(candidate.provider_map || {}) };
      if (!nextProvider) {
        delete nextMap[code];
      } else {
        nextMap[code] = nextProvider;
      }
      return { ...candidate, provider_map: nextMap, confirmed: false };
    });
    await saveRows(nextRows, String(row.id));
  }

  async function addProviderParam(row: AttrRow, code: string, paramId: string) {
    const providerParam = (details?.providers?.[code]?.params || []).find((param) => String(param.id) === String(paramId));
    const payload = providerBindingPayload(providerParam);
    if (!payload) return;
    await saveProviderBindings(row, code, [...providerBindings(row.provider_map?.[code]), asManualBinding(payload)]);
  }

  async function removeProviderParam(row: AttrRow, code: string, paramId: string) {
    const target = String(paramId || "").trim();
    await saveProviderBindings(
      row,
      code,
      providerBindings(row.provider_map?.[code]).filter((item) => String(item.id || "").trim() !== target),
    );
  }

  async function clearProviderParam(row: AttrRow, code: string) {
    await saveProviderBindings(row, code, []);
  }

  async function confirmRow(row: AttrRow) {
    const nextRows = rows.map((candidate) => (String(candidate.id) === String(row.id) ? { ...candidate, confirmed: true } : candidate));
    await saveRows(nextRows, String(row.id));
  }

  async function clearRowAllProviders(row: AttrRow) {
    const nextRows = rows.map((candidate) => {
      if (String(candidate.id) !== String(row.id)) return candidate;
      return { ...candidate, provider_map: {}, confirmed: true };
    });
    await saveRows(nextRows, String(row.id));
  }

  async function resetRowDecision(row: AttrRow) {
    const nextRows = rows.map((candidate) => {
      if (String(candidate.id) !== String(row.id)) return candidate;
      return { ...candidate, provider_map: {}, confirmed: false };
    });
    await saveRows(nextRows, String(row.id));
  }

  function providerParamOptions(code: string, current?: ProviderParam) {
    const search = qnorm(providerSearch[code] || "");
    const params = details?.providers?.[code]?.params || [];
    const currentIds = new Set(providerBindings(current).map((item) => String(item.id || "").trim()).filter(Boolean));
    const sorted = [...params].sort((a, b) => {
      const aSelected = currentIds.has(String(a.id || "").trim());
      const bSelected = currentIds.has(String(b.id || "").trim());
      if (aSelected !== bSelected) return aSelected ? -1 : 1;
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
            <div className="paramsEyebrow">Черновик параметров</div>
            <h2>{categoryName}</h2>
            <div className="paramsCommandBadges" aria-label="Готовность параметров">
              <span>
                {hasProviderCategoryMapping
                  ? mappingInherited
                    ? "связка унаследована"
                    : "категории связаны"
                  : "нужна связка категорий"}
              </span>
              <span>{codes.length} площадки</span>
              <span>{readinessText}</span>
              <span>{stats.values} с вариантами значений</span>
            </div>
          </div>
          <div className="paramsCommandActions">
            <button className="btn" type="button" onClick={() => setCategoryDrawerOpen(true)}>Сменить категорию</button>
            {!infoModelIsEmpty ? (
              <>
                <button className="btn" type="button" onClick={runAiMatch} disabled={!selectedCategoryId || aiMatching || loading}>
                  {aiMatching ? "Собираю..." : "Собрать черновик"}
                </button>
                <Link className="btn btn-primary" to={`/catalog/exchange?tab=export&category=${encodeURIComponent(selectedCategoryId)}`}>Проверить выгрузку</Link>
              </>
            ) : null}
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
          <div className="paramsAlert isError">
            <span>
              {error.includes("CATEGORY_NOT_DIRECTLY_MAPPED")
              ? "Для этой категории или ее родителя сначала нужна связка с категориями площадок."
              : error}
            </span>
            <button className="btn sm" type="button" onClick={retryDetailsLoad} disabled={loading}>Повторить</button>
            {error === "AUTH_REQUIRED" ? <Link className="btn sm" to="/login">Войти</Link> : null}
          </div>
        ) : null}
        {mappingInherited && !infoModelIsEmpty ? (
          <div className="paramsAlert isInfo">
            Эта товарная категория использует связку площадок родительской ветки
            {inheritedProviderLabels.length ? `: ${inheritedProviderLabels.join(", ")}` : ""}.
            Можно насыщать товары здесь, а параметры площадок брать из общей категории.
          </div>
        ) : null}
        {!infoModelIsEmpty && !hasCompetitorEvidence ? (
          <div className="paramsAlert isInfo">
            Площадки уже дают список обязательных и полезных полей, но финальная инфо-модель строится после конкурентных карточек и товарных данных.
            Сначала подтвердите карточки конкурентов для SKU, затем возвращайтесь к черновику параметров.
            <Link className="btn sm" to={`/sources?tab=sources&category=${encodeURIComponent(selectedCategoryId)}`}>Открыть источники</Link>
          </div>
        ) : null}
        {notice ? <div className="paramsAlert isSuccess">{notice}</div> : null}
        {aiJob && (aiJob.status === "queued" || aiJob.status === "running") ? (
          <div className="paramsAlert">
            {aiJob.status === "queued" ? "AI-подбор в очереди." : "AI-подбор выполняется."} {aiJob.message || ""}
          </div>
        ) : null}
        {loading ? <div className="paramsAlert">Загружаю параметры категории...</div> : null}

        {infoModelIsEmpty ? (
          <div className="paramsInfoModelSetup">
            <div>
              <span>Следующий шаг</span>
              <h3>Соберите инфо-модель категории</h3>
              <p>
                Категории площадок уже связаны{mappingInherited ? " через родительскую ветку" : ""}, но PIM-полей для сопоставления еще нет.
                Сначала соберите черновик модели из товаров, площадок и конкурентов, затем возвращайтесь сюда для сопоставления полей.
              </p>
            </div>
            <div className="paramsInfoModelSetupActions">
              <Link className="btn btn-primary" to={`/templates/${encodeURIComponent(selectedCategoryId)}`}>Собрать инфо-модель</Link>
              <Link className="btn" to={`/sources?tab=sources&category=${encodeURIComponent(selectedCategoryId)}`}>Проверить источники</Link>
            </div>
          </div>
        ) : (
        <div className="paramsFocusLayout">
          <div className="paramsQueueBlock">
            <div className="paramsSectionHead">
              <div>
                <h3>Черновик PIM-параметров</h3>
                <p>
                  Это не финальная инфо-модель: строки собираются из площадок, конкурентов и товарных данных. Утверждайте только проверенные параметры.
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
                ["complex", "Сложные", stats.complex],
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
              ) : error ? (
                <div className="paramsAlert isError">
                  <strong>Не удалось загрузить параметры категории</strong>
                  <span>{error === "AUTH_REQUIRED" ? "Сессия истекла или нет прав доступа. Войдите заново и вернитесь к этой категории." : error}</span>
                  <button className="btn sm" type="button" onClick={retryDetailsLoad} disabled={loading}>Повторить</button>
                  {error === "AUTH_REQUIRED" ? <Link className="btn sm" to="/login">Войти</Link> : null}
                </div>
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
                        {rowHasComplexBindings(row, codes) ? <span>несколько полей площадки</span> : null}
                      </div>
                    </div>
                    <div className="paramsParamStatus">
                      <span>{coverage}/{codes.length}</span>
                      <strong>{rowStatusLabel(row, codes)}</strong>
                    </div>
                    <div className="paramsParamProviders">
                      {codes.map((code) => {
                        const value = row.provider_map?.[code];
                        const bindings = providerBindings(value);
                        const valuesCount = bindings.reduce((acc, item) => acc + (item.values?.length || 0), 0);
                        const originChips = providerOriginChips(bindings);
                        const valueModes = bindings.map(providerValueMode);
                        return (
                          <div className="paramsProviderCell" key={`${row.id}-${code}`}>
                            <span>{PROVIDER_LABEL[code] || code}</span>
                            {bindings.length ? (
                              <div className="paramsProviderBindings">
                                {bindings.map((item) => <b key={`${code}-${item.id || item.name}`}>{item.name || item.id}</b>)}
                                {bindings.length > 1 ? <small>{bindings.length} поля площадки</small> : null}
                              </div>
                            ) : (
                              <strong>не связано</strong>
                            )}
                            {originChips.length ? (
                              <div className="paramsProviderOrigins">
                                {originChips.map((item) => (
                                  <i
                                    key={`${code}-${item.source}`}
                                    className={mappingOriginClass(item.source)}
                                    title={item.reasons.join("\n") || "Причина сопоставления пока не записана."}
                                  >
                                    {mappingOriginLabel(item.source)}
                                    {formatConfidence(item.confidence) ? ` ${formatConfidence(item.confidence)}` : ""}
                                    {item.count > 1 ? ` x${item.count}` : ""}
                                  </i>
                                ))}
                              </div>
                            ) : null}
                            {valueModes.length ? (
                              <div className="paramsProviderKinds">
                                {valueModes.map((mode, index) => (
                                  <i key={`${code}-${mode.code}-${index}`} className={`is${mode.code}`} title={mode.hint}>
                                    {mode.label}
                                  </i>
                                ))}
                              </div>
                            ) : null}
                            <em>{valuesCount ? `${valuesCount} значений` : bindings.length > 1 ? `${bindings.length} поля` : bindings[0]?.kind || "параметр"}</em>
                          </div>
                        );
                      })}
                    </div>
                  </button>
                );
              }) : (
                <div className="paramsAlert">
                  {infoModelIsEmpty
                    ? "Инфо-модель пустая. Сначала соберите черновик модели категории из источников."
                    : "Черновик параметров пуст. Подтвердите конкурентные карточки для SKU, затем соберите черновик из источников."}
                </div>
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
                <div className={`paramsMiniAlert ${rowNeedsAttention(selectedRow, codes) ? "" : "isSuccess"}`}>
                  {rowStatusReason(selectedRow, codes)}
                </div>

                <div className="paramsInspectorSection">
                  <h4>Привязка к площадкам</h4>
                  <p>Здесь редактируется, какое поле площадки наполняет поле PIM.</p>
                  {(() => {
                    const provenance = providerOriginChips(
                      codes.flatMap((code) => providerBindings(selectedRow.provider_map?.[code])),
                    );
                    return provenance.length ? (
                      <div className="paramsProvenancePanel">
                        <div>
                          <strong>Почему предложена эта связь</strong>
                          <span>AI, правила и память показываются до ручного подтверждения.</span>
                        </div>
                        <div className="paramsProvenanceList">
                          {provenance.map((item) => (
                            <span key={item.source} className={mappingOriginClass(item.source)} title={item.reasons.join("\n") || "Причина сопоставления пока не записана."}>
                              <b>{mappingOriginLabel(item.source)}{formatConfidence(item.confidence) ? ` ${formatConfidence(item.confidence)}` : ""}</b>
                              <em>{item.reasons[0] || "Причина сопоставления пока не записана."}</em>
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : null;
                  })()}
                  <div className="paramsModeLegend" aria-label="Режимы передачи параметров">
                    <span><i className="paramsValueMode isdictionary">Справочник</i> выбрать поле и настроить значения</span>
                    <span><i className="paramsValueMode ismulti">Мультивыбор</i> значения могут быть списком</span>
                    <span><i className="paramsValueMode isboolean">Да/Нет</i> нормализовать булево значение</span>
                    <span><i className="paramsValueMode isnumber">Число</i> проверить единицы измерения</span>
                    <span><i className="paramsValueMode istext">Текст</i> передается вручную/из PIM без справочника</span>
                  </div>
                  {codes.map((code) => {
                    const provider = details?.providers?.[code];
                    const current = selectedRow.provider_map?.[code];
                    const options = providerParamOptions(code, current);
                    const bindings = providerBindings(current);
                    const currentIds = new Set(bindings.map((item) => String(item.id || "").trim()).filter(Boolean));
                    const optionGroups = providerOptionGroups(selectedRow, options.visible, currentIds, providerSearch[code] || "");
                    return (
                      <div className="paramsFieldSelect" key={code}>
                        <div className="paramsProviderBindHead">
                          <span>{PROVIDER_LABEL[code] || code}</span>
                          <b className={bindings.length ? "isOk" : "isWarn"}>{bindings.length ? `${bindings.length} полей` : "не связано"}</b>
                        </div>
                        <div className="paramsProviderCurrent">
                          {bindings.length ? (
                            <div className="paramsCurrentBindings">
                              {bindings.length > 1 ? (
                                <div className="paramsComplexNote">
                                  Один параметр PIM будет передан в несколько полей площадки.
                                </div>
                              ) : null}
                              {bindings.map((item, index) => (
                                <span key={`${code}-current-${item.id || item.name}`}>
                                  {(() => {
                                    const mode = providerValueMode(item);
                                    return (
                                      <i className={`paramsValueMode is${mode.code}`} title={mode.hint}>
                                        {mode.label}
                                      </i>
                                    );
                                  })()}
                                  <strong>{item.name || item.id}</strong>
                                  <em>{index === 0 ? "основное поле" : "доп. поле"}</em>
                                  <small className="paramsValueModeHint">{providerValueMode(item).hint}</small>
                                  <div className="paramsOriginLine">
                                    <b className={mappingOriginClass(item.match_source)}>
                                      {mappingOriginLabel(item.match_source)}
                                      {formatConfidence(item.match_confidence) ? ` ${formatConfidence(item.match_confidence)}` : ""}
                                    </b>
                                    <small>{item.match_reason || "Причина сопоставления пока не записана. Проверьте связь вручную."}</small>
                                  </div>
                                  <button
                                    type="button"
                                    disabled={savingRowId === String(selectedRow.id)}
                                    onClick={() => void removeProviderParam(selectedRow, code, item.id)}
                                  >
                                    Убрать
                                  </button>
                                </span>
                              ))}
                            </div>
                          ) : (
                            <>
                              <strong>Поле площадки не выбрано</strong>
                              <em>тип не указан</em>
                            </>
                          )}
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
                            className={!bindings.length ? "isSelected" : ""}
                            disabled={savingRowId === String(selectedRow.id)}
                            onClick={() => void clearProviderParam(selectedRow, code)}
                          >
                            <strong>Не связывать</strong>
                            <em>Поле не передается на площадку</em>
                          </button>
                          {optionGroups.map((group) => (
                            <div className={`paramsProviderOptionGroup is-${group.key}`} key={`${code}-${group.key}`}>
                              <div className="paramsProviderOptionGroupHead">
                                <b>{group.title}</b>
                                <small>{group.hint}</small>
                              </div>
                              {group.items.map((param) => {
                                const selected = currentIds.has(String(param.id || "").trim());
                                const mode = providerValueMode(param);
                                return (
                                  <button
                                    type="button"
                                    key={String(param.id)}
                                    className={selected ? "isSelected" : ""}
                                    disabled={savingRowId === String(selectedRow.id)}
                                    onClick={() => void (selected ? removeProviderParam(selectedRow, code, String(param.id)) : addProviderParam(selectedRow, code, String(param.id)))}
                                  >
                                    <strong>{param.name}</strong>
                                    <em>
                                      {selected
                                        ? "Нажмите, чтобы убрать"
                                        : param.values?.length
                                          ? `${mode.label} · ${param.values.length} значений`
                                          : mode.label || param.kind || "тип не указан"}
                                    </em>
                                  </button>
                                );
                              })}
                            </div>
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
                  <Link className="btn" to={`/sources?tab=sources&category=${encodeURIComponent(selectedCategoryId)}`}>Открыть источники</Link>
                </div>

                <div className="paramsInspectorSection">
                  <h4>Следующее действие</h4>
                  <p>Если конкуренты еще не подтверждены, сначала соберите источники. Затем подтвердите параметры, отключите лишнее и переходите к значениям.</p>
                  <div className="paramsInspectorActions">
                    <button
                      className="btn"
                      type="button"
                      disabled={!selectedCategoryId || aiMatching || loading}
                      onClick={runAiMatch}
                    >
                      {aiMatching ? "Собираю черновик..." : "Собрать черновик"}
                    </button>
                    <button
                      className="btn btn-primary"
                      type="button"
                      disabled={savingRowId === String(selectedRow.id)}
                      onClick={() => void confirmRow(selectedRow)}
                    >
                      {savingRowId === String(selectedRow.id) ? "Сохраняю..." : "Подтвердить"}
                    </button>
                    <button
                      className="btn"
                      type="button"
                      disabled={savingRowId === String(selectedRow.id)}
                      onClick={() => void clearRowAllProviders(selectedRow)}
                    >
                      Не передавать
                    </button>
                    <button
                      className="btn"
                      type="button"
                      disabled={savingRowId === String(selectedRow.id)}
                      onClick={() => void resetRowDecision(selectedRow)}
                    >
                      Сбросить решение
                    </button>
                    <Link className="btn" to={`/sources?tab=values&category=${encodeURIComponent(selectedCategoryId)}`}>Настроить значения</Link>
                  </div>
                </div>

                <details className="paramsServiceDetails">
                  <summary>Служебные поля выгрузки, не характеристики</summary>
                  <p>Эти поля выбираются и заполняются в товаре или экспортном канале. Их не нужно матчить с характеристиками категории, если площадка принимает их как базовые поля карточки.</p>
                  <div className="paramsServiceCompact">
                    {SERVICE_EXPORTS.map((item) => {
                      const row = serviceRows.find((candidate) => serviceKey(candidate) === item.key);
                      const status = serviceExportStatus(row, codes);
                      return (
                        <div key={item.key}>
                          <strong>{item.title}</strong>
                          <span>{item.target}</span>
                          <em className={status.className} title={status.hint}>{status.label}</em>
                          <small>{item.note}</small>
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
        )}
      </section>
    </div>
  );
}
