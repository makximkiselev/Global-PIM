import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import "../styles/catalog.css";
import "../styles/templates.css";
import { api } from "../lib/api";

type DictValueObj = { value: string; count?: number; last_seen?: string; sources?: Record<string, number> };
type DictValue = string | DictValueObj;

type DictProviderReference = {
  id?: string | null;
  name?: string | null;
  kind?: string | null;
  required?: boolean;
  allowed_values?: string[];
};

type DictMeta = {
  required?: boolean;
  service?: boolean;
  param_group?: string;
  source_reference?: Record<string, DictProviderReference>;
  export_map?: Record<string, Record<string, string>>;
};

type DictItem = {
  id: string;
  title: string;
  meta?: DictMeta;
  created_at?: string | null;
  updated_at?: string | null;
  values: DictValue[];
};

type DedupeMerge = {
  keep: string;
  merged: string[];
  merged_items: number;
  merged_count: number;
  last_seen?: string | null;
};

type DedupeResp = {
  ok: boolean;
  apply: boolean;
  before_count: number;
  after_count: number;
  removed: number;
  merges: DedupeMerge[];
};

type ValueViewFilter = "all" | "empty" | "duplicates";

const TYPE_LABEL: Record<string, string> = {
  text: "Текст",
  number: "Число",
  select: "Список",
  bool: "Да/Нет",
  date: "Дата",
  json: "JSON",
};
const PROVIDER_LABEL: Record<string, string> = {
  yandex_market: "Я.Маркет",
  ozon: "OZON",
};
const PARAM_GROUPS = ["Артикулы", "О товаре", "Логистика", "Гарантия", "Прочее"] as const;
type ParamGroup = (typeof PARAM_GROUPS)[number];

function normalizeParamGroup(value: string | undefined | null, title?: string): ParamGroup {
  const v = String(value || "").trim() as ParamGroup;
  if ((PARAM_GROUPS as readonly string[]).includes(v)) return v;
  return inferParamGroup(title);
}

function inferParamGroup(title?: string): ParamGroup {
  const s = String(title || "").toLowerCase();
  if (/(sku|штрихкод|barcode|партномер|код продавца|серийн)/i.test(s)) return "Артикулы";
  if (/(гарант|срок службы|страна производства|страна происхождения|страна сборки)/i.test(s)) return "Гарантия";
  if (/(вес|ширина|высота|толщина|размер|длина|упаков|количество|габарит|объем)/i.test(s)) return "Логистика";
  if (/(rich|видео|хештег|seo)/i.test(s)) return "Прочее";
  return "О товаре";
}

function asText(v: DictValue): string {
  return typeof v === "string" ? v : v?.value || "";
}

function normValueKey(value: string): string {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function parseNumericValue(text: string): number | null {
  const raw = (text || "").trim();
  if (!raw) return null;
  const numMatch = raw.match(/(\d+(?:[.,]\d+)?)/);
  if (!numMatch) return null;
  const num = Number(numMatch[1].replace(",", "."));
  if (Number.isNaN(num)) return null;
  const unitMatch = raw.match(/(tb|тб|gb|гб|mb|мб)/i);
  if (!unitMatch) {
    if (/^\s*\d+(?:[.,]\d+)?\s*$/.test(raw)) return num;
    return null;
  }
  const unit = unitMatch[1].toLowerCase();
  if (unit === "tb" || unit === "тб") return num * 1024;
  if (unit === "mb" || unit === "мб") return num / 1024;
  return num;
}

function parseImportText(text: string): string[] {
  const raw = (text || "").replace(/\r/g, "");
  const lines = raw.split("\n");
  const out: string[] = [];
  for (const line of lines) {
    const trimmed = (line || "").trim();
    if (!trimmed) continue;
    const header = trimmed.replace(/^\"|\"$/g, "").trim().toLowerCase();
    if (out.length === 0 && (header === "value" || header === "значение")) {
      continue;
    }
    let cell = trimmed;
    if (trimmed.includes(",") || trimmed.includes(";") || trimmed.includes("\t")) {
      cell = trimmed.split(/[,;\t]/)[0] || "";
    }
    cell = cell.replace(/^\"|\"$/g, "").trim();
    if (cell) out.push(cell);
  }
  return out;
}

function downloadTemplate(dictTitle: string, values: DictValue[]) {
  const name = (dictTitle || "dictionary").replace(/[^\w\-]+/g, "_");
  const lines = ["value"];
  for (const v of values || []) {
    const text = asText(v);
    if (text) lines.push(text);
  }
  const csv = `${lines.join("\n")}\n`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name}_template.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function DictionaryEditor() {
  const nav = useNavigate();
  const location = useLocation();
  const { dictId } = useParams();
  const requiredInputId = `dict-required-${dictId || "current"}`;
  const navState = (location.state || {}) as { backTo?: string; backLabel?: string };

  const [item, setItem] = useState<DictItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [attrId, setAttrId] = useState<string | null>(null);
  const [attrType, setAttrType] = useState<string>("select");
  const [attrLoading, setAttrLoading] = useState(false);
  const [requiredFlag, setRequiredFlag] = useState(false);
  const [paramGroup, setParamGroup] = useState<ParamGroup>("О товаре");
  const [valueFilter, setValueFilter] = useState<ValueViewFilter>("all");
  const [savedToast, setSavedToast] = useState(false);
  const [activeProvider, setActiveProvider] = useState("");
  const [exportMapDraft, setExportMapDraft] = useState<Record<string, Record<string, string>>>({});
  const toastTimerRef = useRef<number | null>(null);

  const [q, setQ] = useState("");

  // add
  const [addOpen, setAddOpen] = useState(false);
  const [newValue, setNewValue] = useState("");
  const addRef = useRef<HTMLInputElement | null>(null);

  // edit row
  const [editKey, setEditKey] = useState<string | null>(null); // key = original value (display)
  const [editValue, setEditValue] = useState("");

  // dedupe
  const [dedupeOpen, setDedupeOpen] = useState(false);
  const [dedupeLoading, setDedupeLoading] = useState(false);
  const [dedupePreview, setDedupePreview] = useState<DedupeResp | null>(null);

  // import
  const [importOpen, setImportOpen] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [importErr, setImportErr] = useState<string | null>(null);
  const [importFileName, setImportFileName] = useState<string>("");
  const importRef = useRef<HTMLInputElement | null>(null);

  function flashSavedToast() {
    setSavedToast(true);
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => {
      setSavedToast(false);
      toastTimerRef.current = null;
    }, 2200);
  }

  async function load() {
    if (!dictId) return;
    setLoading(true);
    try {
      const r = await api<{ item: DictItem }>(`/dictionaries/${encodeURIComponent(dictId)}`);
      const raw = r.item as DictItem & { items?: DictValue[] };
      if (!raw.values && Array.isArray((raw as any).items)) {
        raw.values = (raw as any).items;
      }
      setItem(raw);
      setRequiredFlag(!!raw?.meta?.required || !!raw?.meta?.service);
      setParamGroup(normalizeParamGroup(raw?.meta?.param_group, raw?.title));
      setExportMapDraft((raw?.meta?.export_map || {}) as Record<string, Record<string, string>>);
      const providerCodes = Object.keys(raw?.meta?.source_reference || {});
      setActiveProvider((prev) => (prev && providerCodes.includes(prev) ? prev : providerCodes[0] || ""));
    } finally {
      setLoading(false);
    }
  }

  async function loadAttribute() {
    if (!dictId) return;
    setAttrLoading(true);
    try {
      const r = await api<{
        items: Array<{ id: string; dict_id?: string | null; type?: string | null; scope?: string | null }>;
      }>("/attributes?limit=2000");
      let hit = (r.items || []).find((x) => (x.dict_id || "") === dictId);
      if (!hit && item?.title) {
        const code = dictId.startsWith("dict_") ? dictId.slice("dict_".length) : undefined;
        const created = await api<{ attribute: { id: string; type?: string | null; scope?: string | null } }>(
          "/attributes/ensure",
          {
            method: "POST",
            body: JSON.stringify({ title: item.title, type: "select", code, scope: "both" }),
          }
        );
        if (created?.attribute?.id) {
          await api(`/attributes/${encodeURIComponent(created.attribute.id)}`, {
            method: "PATCH",
            body: JSON.stringify({ dict_id: dictId }),
          });
          hit = { id: created.attribute.id, dict_id: dictId, type: created.attribute.type, scope: created.attribute.scope };
        }
      }
      setAttrId(hit?.id || null);
      setAttrType(hit?.type || "select");
    } finally {
      setAttrLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dictId]);

  useEffect(() => {
    void loadAttribute();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dictId, item?.title]);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        window.clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const providerCodes = Object.keys(item?.meta?.source_reference || {});
    if (!providerCodes.length) {
      if (activeProvider) setActiveProvider("");
      return;
    }
    if (!activeProvider || !providerCodes.includes(activeProvider)) {
      setActiveProvider(providerCodes[0]);
    }
  }, [item?.meta?.source_reference, activeProvider]);

  const values = item?.values || [];

  const duplicateKeySet = useMemo(() => {
    const freq = new Map<string, number>();
    for (const v of values) {
      const key = normValueKey(asText(v));
      if (!key) continue;
      freq.set(key, (freq.get(key) || 0) + 1);
    }
    const out = new Set<string>();
    for (const [k, n] of freq.entries()) {
      if (n > 1) out.add(k);
    }
    return out;
  }, [values]);

  const filtered = useMemo(() => {
    const s = (q || "").trim().toLowerCase();
    let list = !s ? [...values] : values.filter((v) => asText(v).toLowerCase().includes(s));
    if (valueFilter === "empty") {
      list = list.filter((v) => !asText(v).trim());
    } else if (valueFilter === "duplicates") {
      list = list.filter((v) => duplicateKeySet.has(normValueKey(asText(v))));
    }

    const getText = (v: DictValue) => (asText(v) || "").toLowerCase();

    list.sort((a, b) => {
      const na = parseNumericValue(asText(a));
      const nb = parseNumericValue(asText(b));
      if (na !== null && nb !== null) return na - nb;
      return getText(a).localeCompare(getText(b), "ru");
    });

    return list;
  }, [values, q, valueFilter, duplicateKeySet]);

  const stats = useMemo(() => {
    let updatedAt = item?.updated_at || item?.created_at || "";
    const sourceCount: Record<string, number> = {};
    for (const v of values) {
      if (typeof v !== "object" || !v) continue;
      const src = v.sources || {};
      for (const [k, n] of Object.entries(src)) {
        sourceCount[k] = (sourceCount[k] || 0) + Number(n || 0);
      }
      if (v.last_seen && (!updatedAt || new Date(v.last_seen).getTime() > new Date(updatedAt).getTime())) {
        updatedAt = v.last_seen;
      }
    }
    const topSource = Object.entries(sourceCount).sort((a, b) => b[1] - a[1])[0]?.[0] || "manual";
    return {
      valuesTotal: values.length,
      duplicatesTotal: duplicateKeySet.size,
      updatedAt,
      topSource,
    };
  }, [values, duplicateKeySet, item]);

  const providerRefs = useMemo(() => {
    return (item?.meta?.source_reference || {}) as Record<string, DictProviderReference>;
  }, [item]);

  const providerCodes = useMemo(() => Object.keys(providerRefs), [providerRefs]);

  const activeProviderRef = useMemo(() => {
    return activeProvider ? providerRefs[activeProvider] || null : null;
  }, [activeProvider, providerRefs]);

  const activeProviderAllowedValues = useMemo(() => {
    return Array.isArray(activeProviderRef?.allowed_values) ? activeProviderRef.allowed_values : [];
  }, [activeProviderRef]);

  async function addValue() {
    if (!dictId) return;
    const v = (newValue || "").trim();
    if (!v) return;

    await api(`/dictionaries/${encodeURIComponent(dictId)}/values`, {
      method: "POST",
      body: JSON.stringify({ value: v, source: "manual" }),
    });

    setNewValue("");
    setAddOpen(false);
    await load();
  }

  async function renameValue(fromValue: string, toValue: string) {
    if (!dictId) return;
    const to = (toValue || "").trim();
    if (!to) return;

    await api(`/dictionaries/${encodeURIComponent(dictId)}/values/rename`, {
      method: "PUT",
      body: JSON.stringify({ from: fromValue, to }),
    });

    setEditKey(null);
    setEditValue("");
    await load();
  }

  async function deleteValue(value: string) {
    if (!dictId) return;
    await api(`/dictionaries/${encodeURIComponent(dictId)}/values`, {
      method: "DELETE",
      body: JSON.stringify({ value }),
    });
    await load();
  }

  async function runDedupePreview() {
    if (!dictId) return;
    setDedupeLoading(true);
    try {
      const r = await api<DedupeResp>(`/dictionaries/${encodeURIComponent(dictId)}/dedupe`, {
        method: "POST",
        body: JSON.stringify({ apply: false }),
      });
      setDedupePreview(r);
      setDedupeOpen(true);
    } finally {
      setDedupeLoading(false);
    }
  }

  async function applyDedupe() {
    if (!dictId) return;
    const prev = dedupePreview;
    const removed = prev?.removed ?? 0;

    if (!removed) {
      setDedupeOpen(false);
      return;
    }

    if (!confirm(`Склеить и удалить дубли? Будет удалено: ${removed}.`)) return;

    setDedupeLoading(true);
    try {
      await api<DedupeResp>(`/dictionaries/${encodeURIComponent(dictId)}/dedupe`, {
        method: "POST",
        body: JSON.stringify({ apply: true }),
      });
      setDedupeOpen(false);
      setDedupePreview(null);
      await load();
    } finally {
      setDedupeLoading(false);
    }
  }

  function goBack() {
    const backTo = String(navState?.backTo || "").trim();
    if (backTo) {
      nav(backTo);
      return;
    }
    if (window.history.length > 1) {
      nav(-1);
      return;
    }
    nav("/dictionaries");
  }

  async function importValues(file: File | null) {
    if (!dictId || !file) return;
    setImportErr(null);
    setImportLoading(true);
    try {
      const text = await file.text();
      const values = parseImportText(text);
      if (!values.length) {
        setImportErr("Файл пустой или не содержит значений.");
        return;
      }
      await api(`/dictionaries/${encodeURIComponent(dictId)}/values/import`, {
        method: "POST",
        body: JSON.stringify({ values, source: "import", replace: true }),
      });
      setImportOpen(false);
      setImportFileName("");
      if (importRef.current) importRef.current.value = "";
      await load();
    } catch (e: any) {
      setImportErr(e?.message || "IMPORT_FAILED");
    } finally {
      setImportLoading(false);
    }
  }

  function exportMappedValue(provider: string, canonicalValue: string): string {
    const key = normValueKey(canonicalValue);
    if (!key) return "";
    return exportMapDraft?.[provider]?.[key] || item?.meta?.export_map?.[provider]?.[key] || "";
  }

  function updateExportMapDraft(provider: string, canonicalValue: string, mappedValue: string) {
    const key = normValueKey(canonicalValue);
    if (!key) return;
    setExportMapDraft((prev) => {
      const next = { ...(prev || {}) };
      const current = { ...(next[provider] || {}) };
      if (mappedValue.trim()) current[key] = mappedValue;
      else delete current[key];
      if (Object.keys(current).length) next[provider] = current;
      else delete next[provider];
      return next;
    });
  }

  async function saveExportMapping(provider: string, canonicalValue: string, mappedValue: string) {
    if (!dictId) return;
    const payload = {
      export_map: {
        [provider]: {
          [canonicalValue]: mappedValue.trim() || null,
        },
      },
    };
    const res = await api<{ item: DictItem }>(`/dictionaries/${encodeURIComponent(dictId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    if (res?.item) {
      const raw = res.item as DictItem & { items?: DictValue[] };
      if (!raw.values && Array.isArray((raw as any).items)) raw.values = (raw as any).items;
      setItem(raw);
      setExportMapDraft((raw?.meta?.export_map || {}) as Record<string, Record<string, string>>);
    }
    flashSavedToast();
  }

  return (
    <div className="templates-page page-shell">
      <div className="page-header">
        <div className="page-header-main">
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <div className="page-title">{item?.title || "Параметр"}</div>
            {requiredFlag ? (
              <span
                style={{
                  border: "1px solid rgba(61,107,255,.3)",
                  background: "rgba(61,107,255,.08)",
                  color: "#1d4ed8",
                  borderRadius: 999,
                  padding: "2px 8px",
                  fontSize: 12,
                  fontWeight: 800,
                }}
              >
                Обязательный
              </span>
            ) : null}
          </div>
          <div className="page-subtitle">Редактирование значений (ручная чистка дублей/опечаток).</div>
        </div>

        <div className="page-header-actions">
          <button className="btn" type="button" onClick={goBack}>
            ← {navState?.backLabel || "Назад"}
          </button>

          <button className="btn" type="button" onClick={() => void load()} disabled={loading}>
            {loading ? "Обновляю…" : "Обновить"}
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gap: 14, gridTemplateColumns: "minmax(420px, 1.25fr) minmax(320px, 1fr)", marginBottom: 14 }}>
        <div className="card">
          <div style={{ fontWeight: 800, marginBottom: 10 }}>Метаданные</div>
          <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(2, minmax(220px, 1fr))" }}>
            <div className="field" style={{ marginBottom: 0 }}>
              <div className="field-label">Тип данных</div>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <select
                  value={attrType}
                  onChange={async (e) => {
                    const next = e.target.value;
                    if (!attrId) return;
                    setAttrType(next);
                  await api(`/attributes/${encodeURIComponent(attrId)}`, {
                    method: "PATCH",
                    body: JSON.stringify({ type: next }),
                  });
                  await loadAttribute();
                  flashSavedToast();
                }}
                disabled={!attrId || attrLoading}
              >
                  {Object.entries(TYPE_LABEL).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
                </select>
                {!attrId && <span className="muted">Нет связанного параметра.</span>}
              </div>
            </div>

            <div className="field" style={{ marginBottom: 0 }}>
              <div className="field-label">Категория параметра</div>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <select
                  value={paramGroup}
                  onChange={async (e) => {
                    const next = e.target.value as ParamGroup;
                    if (!dictId) return;
                    setParamGroup(next);
                  const res = await api<{ item: DictItem }>(`/dictionaries/${encodeURIComponent(dictId)}`, {
                    method: "PATCH",
                    body: JSON.stringify({ param_group: next }),
                  });
                  if (res?.item) {
                    setItem((prev) => (prev ? { ...prev, meta: res.item.meta } : prev));
                  }
                  flashSavedToast();
                }}
                disabled={loading}
              >
                  {PARAM_GROUPS.map((group) => (
                    <option key={group} value={group}>
                      {group}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="field" style={{ marginBottom: 0, display: "flex", flexDirection: "column", gridColumn: "1 / -1" }}>
              <div className="field-label">Обязательный параметр</div>
              <label
                htmlFor={requiredInputId}
                className="muted"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 10,
                  marginTop: 8,
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                  alignSelf: "flex-start",
                }}
              >
                <input
                  id={requiredInputId}
                  type="checkbox"
                  checked={requiredFlag}
                  onChange={async (e) => {
                    const next = e.target.checked;
                    if (!dictId) return;
                    setRequiredFlag(next);
                    const res = await api<{ item: DictItem }>(`/dictionaries/${encodeURIComponent(dictId)}`, {
                      method: "PATCH",
                      body: JSON.stringify({ required: next }),
                    });
                    if (res?.item) {
                      setItem((prev) => (prev ? { ...prev, meta: res.item.meta } : prev));
                    }
                    flashSavedToast();
                  }}
                  disabled={loading}
                  style={{ margin: 0 }}
                />
                Пометить как обязательный для заполнения
              </label>
            </div>
          </div>
        </div>

        <div className="card">
          <div style={{ fontWeight: 800, marginBottom: 10 }}>Статистика</div>
          <div style={{ display: "grid", gap: 8 }}>
            <div className="muted" style={{ fontSize: 13 }}>Значений: <b style={{ color: "var(--text)" }}>{stats.valuesTotal}</b></div>
            <div className="muted" style={{ fontSize: 13 }}>Дублей: <b style={{ color: "var(--text)" }}>{stats.duplicatesTotal}</b></div>
            <div className="muted" style={{ fontSize: 13 }}>Последнее обновление: <b style={{ color: "var(--text)" }}>{stats.updatedAt ? new Date(stats.updatedAt).toLocaleString() : "—"}</b></div>
            <div className="muted" style={{ fontSize: 13 }}>Основной источник: <b style={{ color: "var(--text)" }}>{stats.topSource}</b></div>
          </div>
        </div>
      </div>

      {providerCodes.length ? (
        <div className="card" style={{ marginBottom: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", alignItems: "flex-start" }}>
            <div>
              <div style={{ fontWeight: 800, marginBottom: 6 }}>Значения площадки</div>
              <div className="muted" style={{ fontSize: 13 }}>
                Справочник площадки хранится отдельно. Здесь настраивается соответствие нашего значения и значения источника.
              </div>
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {providerCodes.map((provider) => (
                <button
                  key={provider}
                  className={`btn ${activeProvider === provider ? "primary" : ""}`}
                  type="button"
                  onClick={() => setActiveProvider(provider)}
                >
                  {PROVIDER_LABEL[provider] || provider}
                </button>
              ))}
            </div>
          </div>

          {activeProviderRef ? (
            <div
              style={{
                marginTop: 14,
                display: "grid",
                gap: 14,
                gridTemplateColumns: "minmax(260px, 320px) minmax(0, 1fr)",
                alignItems: "start",
              }}
            >
              <div
                style={{
                  border: "1px solid var(--line)",
                  borderRadius: 16,
                  background: "rgba(255,255,255,.92)",
                  padding: 14,
                }}
              >
                <div style={{ fontSize: 12, fontWeight: 800, color: "var(--muted)", textTransform: "uppercase", letterSpacing: ".04em" }}>
                  {PROVIDER_LABEL[activeProvider] || activeProvider}
                </div>
                <div style={{ fontWeight: 900, fontSize: 18, marginTop: 6 }}>
                  {activeProviderRef.name || "Поле не указано"}
                </div>
                <div className="muted" style={{ marginTop: 8, fontSize: 13, display: "grid", gap: 6 }}>
                  <div>Тип: <b style={{ color: "var(--text)" }}>{activeProviderRef.kind || "—"}</b></div>
                  <div>Обязательный: <b style={{ color: "var(--text)" }}>{activeProviderRef.required ? "да" : "нет"}</b></div>
                  <div>Допустимых значений: <b style={{ color: "var(--text)" }}>{activeProviderAllowedValues.length}</b></div>
                </div>
              </div>

              <div
                style={{
                  border: "1px solid var(--line)",
                  borderRadius: 16,
                  background: "rgba(255,255,255,.92)",
                  padding: 14,
                  minHeight: 120,
                }}
              >
                <div style={{ fontWeight: 800, marginBottom: 10 }}>Допустимые значения</div>
                {activeProviderAllowedValues.length ? (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, maxHeight: 172, overflow: "auto" }}>
                    {activeProviderAllowedValues.map((value) => (
                      <span
                        key={value}
                        style={{
                          padding: "6px 10px",
                          borderRadius: 999,
                          border: "1px solid rgba(11,18,32,.10)",
                          background: "rgba(11,18,32,.04)",
                          fontSize: 12,
                          fontWeight: 700,
                        }}
                      >
                        {value}
                      </span>
                    ))}
                  </div>
                ) : (
                  <div className="muted" style={{ fontSize: 13 }}>У площадки нет справочника значений для этого параметра.</div>
                )}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* SEARCH + ACTIONS */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="field" style={{ marginBottom: 0 }}>
          <div className="field-label">Поиск по значениям</div>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Например: black, 256, titanium…" />

          <div style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "center", flexWrap: "wrap" }}>
            <button className={`btn ${valueFilter === "all" ? "primary" : ""}`} type="button" onClick={() => setValueFilter("all")}>
              Все
            </button>
            <button className={`btn ${valueFilter === "duplicates" ? "primary" : ""}`} type="button" onClick={() => setValueFilter("duplicates")}>
              Дубли
            </button>
            <button className={`btn ${valueFilter === "empty" ? "primary" : ""}`} type="button" onClick={() => setValueFilter("empty")}>
              Пустые
            </button>
          </div>

          <div style={{ position: "sticky", top: 6, zIndex: 2, background: "var(--card)", paddingTop: 10 }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <button
              className="btn"
              type="button"
              onClick={() => {
                setAddOpen((x) => !x);
                setTimeout(() => addRef.current?.focus(), 0);
              }}
              disabled={!item || loading}
            >
              + Добавить значение
            </button>

            <button
              className="btn"
              type="button"
              onClick={() => downloadTemplate(item?.title || "dictionary", values)}
              disabled={!item}
            >
              ⬇️ Шаблон импорта
            </button>

            <button
              className="btn"
              type="button"
              onClick={() => setImportOpen((x) => !x)}
              disabled={!item || loading}
            >
              ⬆️ Импорт значений
            </button>

            <button
              className="btn"
              type="button"
              onClick={() => void runDedupePreview()}
              disabled={!item || loading || dedupeLoading}
            >
              {dedupeLoading ? "Проверяю дубли…" : "🧹 Чистка дублей"}
            </button>

            <div className="muted" style={{ fontSize: 12 }}>
              Если переименовать значение в уже существующее — они будут <b>склеены</b>.
            </div>
          </div>
          </div>

          {addOpen && (
            <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
              <input
                ref={addRef}
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="Новое значение…"
                style={{ flex: 1 }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void addValue();
                  if (e.key === "Escape") {
                    setAddOpen(false);
                    setNewValue("");
                  }
                }}
              />
              <button className="btn primary" type="button" onClick={() => void addValue()} disabled={!newValue.trim()}>
                Добавить
              </button>
              <button
                className="btn"
                type="button"
                onClick={() => {
                  setAddOpen(false);
                  setNewValue("");
                }}
              >
                Отмена
              </button>
            </div>
          )}

          {importOpen && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
              <input
                ref={importRef}
                type="file"
                accept=".csv,.txt"
                onChange={(e) => {
                  const file = e.target.files?.[0] || null;
                  setImportFileName(file?.name || "");
                  setImportErr(null);
                }}
              />
              {importFileName ? (
                <div className="muted" style={{ fontSize: 12 }}>
                  Файл: <b>{importFileName}</b>
                </div>
              ) : null}
              {importErr ? (
                <div className="muted" style={{ fontSize: 12, color: "rgba(239,68,68,.90)" }}>
                  {importErr}
                </div>
              ) : null}
              <div style={{ display: "flex", gap: 10 }}>
                <button
                  className="btn primary"
                  type="button"
                  onClick={() => void importValues(importRef.current?.files?.[0] || null)}
                  disabled={importLoading || !importRef.current?.files?.[0]}
                >
                  {importLoading ? "Импортирую…" : "Импортировать"}
                </button>
                <button
                  className="btn"
                  type="button"
                  onClick={() => {
                    setImportOpen(false);
                    setImportErr(null);
                    setImportFileName("");
                    if (importRef.current) importRef.current.value = "";
                  }}
                >
                  Отмена
                </button>
              </div>
              <div className="muted" style={{ fontSize: 12 }}>
                Формат: одна строка = одно значение (CSV/текст). При импорте список синхронизируется.
              </div>
            </div>
          )}
        </div>
      </div>

      {/* DEDUPE PREVIEW */}
      {dedupeOpen && dedupePreview ? (
        <div className="card" style={{ marginBottom: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
            <div>
              <div style={{ fontWeight: 900 }}>Чистка дублей</div>
              <div className="muted" style={{ marginTop: 6, fontSize: 12, lineHeight: 1.35 }}>
                Было: <b>{dedupePreview.before_count}</b> → станет: <b>{dedupePreview.after_count}</b> (удалится:{" "}
                <b>{dedupePreview.removed}</b>)
              </div>
            </div>

            {/* ✅ больше расстояние между кнопками */}
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <button className="btn" type="button" onClick={() => setDedupeOpen(false)} disabled={dedupeLoading}>
                Закрыть
              </button>
              <button
                className="btn primary"
                type="button"
                onClick={() => void applyDedupe()}
                disabled={dedupeLoading || !dedupePreview.removed}
                title={dedupePreview.removed ? "Применить чистку" : "Дублей нет"}
              >
                {dedupeLoading ? "Применяю…" : "Применить"}
              </button>
            </div>
          </div>

          {dedupePreview.merges?.length ? (
            <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
              {dedupePreview.merges.slice(0, 50).map((m, idx) => (
                <div key={`${m.keep}-${idx}`} className="card" style={{ padding: 10 }}>
                  <div style={{ fontWeight: 600 }}>{m.keep}</div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                    Склеено: {m.merged_items} (значения: {m.merged.join(", ")})
                  </div>
                </div>
              ))}
              {dedupePreview.merges.length > 50 ? (
                <div className="muted" style={{ fontSize: 12 }}>
                  Показаны первые 50 merge-групп.
                </div>
              ) : null}
            </div>
          ) : (
            // ✅ убрали exact normalize из текста
            <div className="muted" style={{ marginTop: 10 }}>
              Дублей не найдено.
            </div>
          )}
        </div>
      ) : null}

      {!item ? (
        <div className="card">
          <div className="muted">{loading ? "Загрузка…" : "Параметр не найден."}</div>
        </div>
      ) : (
        <div className="card">
          <div className="muted" style={{ marginBottom: 10 }}>
            Значений: <b>{values.length}</b>
          </div>

          {filtered.length === 0 ? (
            <div className="muted">Ничего не найдено.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {filtered.map((v, i) => {
                const text = asText(v);
                const isEditing = editKey === text;

                return (
                  <div
                    key={`${text}-${i}`}
                    className="card"
                    style={{
                      padding: 10,
                      display: "grid",
                      gridTemplateColumns: activeProvider ? "minmax(220px, 1fr) minmax(260px, 340px) auto" : "minmax(220px, 1fr) auto",
                      gap: 10,
                      alignItems: "center",
                    }}
                  >
                    <div style={{ minWidth: 0, flex: 1 }}>
                      {!isEditing ? (
                        <div
                          style={{
                            fontWeight: 400,
                            fontSize: 15,
                            lineHeight: "20px",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                          title={text}
                        >
                          {text}
                        </div>
                      ) : (
                        <input
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === "Enter") void renameValue(text, editValue);
                            if (e.key === "Escape") {
                              setEditKey(null);
                              setEditValue("");
                            }
                          }}
                        />
                      )}
                    </div>

                    {activeProvider ? (
                      <div style={{ minWidth: 0 }}>
                        <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
                          {PROVIDER_LABEL[activeProvider] || activeProvider}
                        </div>
                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                          <input
                            list={`provider-values-${activeProvider}`}
                            value={exportMappedValue(activeProvider, text)}
                            onChange={(e) => updateExportMapDraft(activeProvider, text, e.target.value)}
                            placeholder="Значение площадки…"
                            disabled={isEditing}
                            style={{ flex: 1, minWidth: 0 }}
                          />
                          <button
                            className="btn primary"
                            type="button"
                            disabled={isEditing}
                            onClick={() => void saveExportMapping(activeProvider, text, exportMappedValue(activeProvider, text))}
                          >
                            Сохранить
                          </button>
                          <button
                            className="btn"
                            type="button"
                            disabled={isEditing || !exportMappedValue(activeProvider, text)}
                            onClick={() => {
                              updateExportMapDraft(activeProvider, text, "");
                              void saveExportMapping(activeProvider, text, "");
                            }}
                          >
                            Снять
                          </button>
                        </div>
                      </div>
                    ) : null}

                    <div style={{ display: "flex", gap: 8, flex: "0 0 auto" }}>
                      {!isEditing ? (
                        <>
                          <button
                            className="icon-btn"
                            type="button"
                            title="Переименовать / склеить"
                            onClick={() => {
                              setEditKey(text);
                              setEditValue(text);
                            }}
                          >
                            ✏️
                          </button>

                          <button
                            className="icon-btn danger"
                            type="button"
                            title="Удалить значение"
                            onClick={() => {
                              if (!confirm(`Удалить значение "${text}"?`)) return;
                              void deleteValue(text);
                            }}
                          >
                            🗑
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            className="btn primary"
                            type="button"
                            onClick={() => void renameValue(text, editValue)}
                            disabled={!editValue.trim() || editValue.trim() === text}
                          >
                            Сохранить
                          </button>
                          <button
                            className="btn"
                            type="button"
                            onClick={() => {
                              setEditKey(null);
                              setEditValue("");
                            }}
                          >
                            Отмена
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {providerCodes.map((provider) => {
        const valuesForProvider = providerRefs[provider]?.allowed_values || [];
        if (!valuesForProvider.length) return null;
        return (
          <datalist key={provider} id={`provider-values-${provider}`}>
            {valuesForProvider.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>
        );
      })}

      {savedToast ? (
        <div
          style={{
            position: "fixed",
            left: "50%",
            bottom: 20,
            transform: "translateX(-50%)",
            zIndex: 50,
            background: "rgba(11,18,32,.92)",
            color: "#fff",
            padding: "10px 14px",
            borderRadius: 12,
            fontSize: 13,
            fontWeight: 700,
            boxShadow: "0 8px 24px rgba(11,18,32,.28)",
          }}
        >
          Изменения сохранены
        </div>
      ) : null}
    </div>
  );
}
