import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import "../../styles/catalog.css";
import "../../styles/templates.css";
import "../../styles/dictionary-modern.css";
import { api } from "../../lib/api";
import DataFilters from "../../components/data/DataFilters";
import DataToolbar from "../../components/data/DataToolbar";
import Alert from "../../components/ui/Alert";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import Field from "../../components/ui/Field";
import IconButton from "../../components/ui/IconButton";
import Modal from "../../components/ui/Modal";
import Select from "../../components/ui/Select";
import TextInput from "../../components/ui/TextInput";

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
  ozon: "Ozon",
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

function providerValueSuggestion(canonicalValue: string, allowedValues: string[]): string {
  const key = normValueKey(canonicalValue);
  if (!key) return "";
  const exact = allowedValues.find((value) => normValueKey(value) === key);
  if (exact) return exact;

  const canonicalNumber = parseNumericValue(canonicalValue);
  if (canonicalNumber == null) return "";
  return allowedValues.find((value) => parseNumericValue(value) === canonicalNumber) || "";
}

function chooseBestProvider(sourceReference?: Record<string, DictProviderReference>, currentProvider = "") {
  const refs = sourceReference || {};
  const providerCodes = Object.keys(refs);
  if (!providerCodes.length) return "";
  if (currentProvider && providerCodes.includes(currentProvider) && (refs[currentProvider]?.allowed_values || []).length > 0) {
    return currentProvider;
  }
  return providerCodes.find((code) => (refs[code]?.allowed_values || []).length > 0) || currentProvider || providerCodes[0] || "";
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

type DictionaryEditorProps = {
  embedded?: boolean;
  dictIdOverride?: string;
};

export default function DictionaryEditor({ embedded = false, dictIdOverride }: DictionaryEditorProps) {
  const nav = useNavigate();
  const location = useLocation();
  const { dictId } = useParams();
  const effectiveDictId = String(dictIdOverride || dictId || "").trim();
  const requiredInputId = `dict-required-${effectiveDictId || "current"}`;
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
  const [providerAllowedQuery, setProviderAllowedQuery] = useState("");
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
  const [dedupeConfirmOpen, setDedupeConfirmOpen] = useState(false);
  const [deleteValueTarget, setDeleteValueTarget] = useState("");

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
    if (!effectiveDictId) return;
    setLoading(true);
    try {
      const r = await api<{ item: DictItem }>(`/dictionaries/${encodeURIComponent(effectiveDictId)}`);
      const raw = r.item as DictItem & { items?: DictValue[] };
      if (!raw.values && Array.isArray((raw as any).items)) {
        raw.values = (raw as any).items;
      }
      setItem(raw);
      setRequiredFlag(!!raw?.meta?.required || !!raw?.meta?.service);
      setParamGroup(normalizeParamGroup(raw?.meta?.param_group, raw?.title));
      setExportMapDraft((raw?.meta?.export_map || {}) as Record<string, Record<string, string>>);
      setActiveProvider((prev) => chooseBestProvider(raw?.meta?.source_reference, prev));
    } finally {
      setLoading(false);
    }
  }

  async function loadAttribute() {
    if (!effectiveDictId) return;
    setAttrLoading(true);
    try {
      const r = await api<{
        items: Array<{ id: string; dict_id?: string | null; type?: string | null; scope?: string | null }>;
      }>("/attributes?limit=2000");
      let hit = (r.items || []).find((x) => (x.dict_id || "") === effectiveDictId);
      if (!hit && item?.title) {
        const code = effectiveDictId.startsWith("dict_") ? effectiveDictId.slice("dict_".length) : undefined;
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
            body: JSON.stringify({ dict_id: effectiveDictId }),
          });
          hit = { id: created.attribute.id, dict_id: effectiveDictId, type: created.attribute.type, scope: created.attribute.scope };
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
  }, [effectiveDictId]);

  useEffect(() => {
    void loadAttribute();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveDictId, item?.title]);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        window.clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const sourceReference = item?.meta?.source_reference || {};
    const providerCodes = Object.keys(sourceReference);
    if (!providerCodes.length) {
      if (activeProvider) setActiveProvider("");
      return;
    }
    const nextProvider = chooseBestProvider(sourceReference, activeProvider);
    if (nextProvider !== activeProvider) {
      setActiveProvider(nextProvider);
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

  const visibleProviderAllowedValues = useMemo(() => {
    const query = providerAllowedQuery.trim().toLowerCase();
    const source = !query
      ? activeProviderAllowedValues
      : activeProviderAllowedValues.filter((value) => value.toLowerCase().includes(query));
    return source.slice(0, 18);
  }, [activeProviderAllowedValues, providerAllowedQuery]);

  const activeProviderMappedCount = useMemo(() => {
    if (!activeProvider) return 0;
    const providerMap = exportMapDraft?.[activeProvider] || item?.meta?.export_map?.[activeProvider] || {};
    return values.filter((value) => !!providerMap[normValueKey(asText(value))]).length;
  }, [activeProvider, exportMapDraft, item?.meta?.export_map, values]);

  async function addValue() {
    if (!effectiveDictId) return;
    const v = (newValue || "").trim();
    if (!v) return;

    await api(`/dictionaries/${encodeURIComponent(effectiveDictId)}/values`, {
      method: "POST",
      body: JSON.stringify({ value: v, source: "manual" }),
    });

    setNewValue("");
    setAddOpen(false);
    await load();
  }

  async function renameValue(fromValue: string, toValue: string) {
    if (!effectiveDictId) return;
    const to = (toValue || "").trim();
    if (!to) return;

    await api(`/dictionaries/${encodeURIComponent(effectiveDictId)}/values/rename`, {
      method: "PUT",
      body: JSON.stringify({ from: fromValue, to }),
    });

    setEditKey(null);
    setEditValue("");
    await load();
  }

  async function deleteValue(value: string) {
    if (!effectiveDictId) return;
    await api(`/dictionaries/${encodeURIComponent(effectiveDictId)}/values`, {
      method: "DELETE",
      body: JSON.stringify({ value }),
    });
    await load();
  }

  async function runDedupePreview() {
    if (!effectiveDictId) return;
    setDedupeLoading(true);
    try {
      const r = await api<DedupeResp>(`/dictionaries/${encodeURIComponent(effectiveDictId)}/dedupe`, {
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
    if (!effectiveDictId) return;
    const prev = dedupePreview;
    const removed = prev?.removed ?? 0;

    if (!removed) {
      setDedupeOpen(false);
      return;
    }

    setDedupeLoading(true);
    try {
      await api<DedupeResp>(`/dictionaries/${encodeURIComponent(effectiveDictId)}/dedupe`, {
        method: "POST",
        body: JSON.stringify({ apply: true }),
      });
      setDedupeOpen(false);
      setDedupeConfirmOpen(false);
      setDedupePreview(null);
      await load();
    } finally {
      setDedupeLoading(false);
    }
  }

  function goBack() {
    if (embedded) return;
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
    if (!effectiveDictId || !file) return;
    setImportErr(null);
    setImportLoading(true);
    try {
      const text = await file.text();
      const values = parseImportText(text);
      if (!values.length) {
        setImportErr("Файл пустой или не содержит значений.");
        return;
      }
      await api(`/dictionaries/${encodeURIComponent(effectiveDictId)}/values/import`, {
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
    if (!effectiveDictId) return;
    const payload = {
      export_map: {
        [provider]: {
          [canonicalValue]: mappedValue.trim() || null,
        },
      },
    };
    const res = await api<{ item: DictItem }>(`/dictionaries/${encodeURIComponent(effectiveDictId)}`, {
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
    <div className={embedded ? "dict-editorEmbedded dictionaryValueEditor" : "templates-page page-shell"}>
      {embedded ? (
        <div className="dictionaryValueHeader">
          <div className="dictionaryValueHeaderMain">
            <div className="dictionaryValueEyebrow">Поле каталога</div>
            <div className="dictionaryValueTitle">{item?.title || "Параметр"}</div>
            <div className="dictionaryValueSub">Написания для выбранной площадки.</div>
          </div>
          <Button onClick={() => void load()} disabled={loading}>
            {loading ? "Обновляю…" : "Обновить"}
          </Button>
        </div>
      ) : (
        <header className="dictEditorCommandHeader">
          <div className="dictEditorCommandContext">
            <span>Справочник параметра</span>
            <h1>{item?.title || "Параметр"}</h1>
            <p>Редактирование значений, ручная чистка дублей и настройка соответствий площадок.</p>
          </div>
          <div className="dictEditorCommandControls">
            <Button onClick={goBack}>{navState?.backLabel || "Назад"}</Button>
            <Button onClick={() => void load()} disabled={loading}>
              {loading ? "Обновляю…" : "Обновить"}
            </Button>
          </div>
        </header>
      )}

      {requiredFlag ? (
        !embedded ? (
        <DataToolbar
          compact
          className="dictionaryEditorToolbar"
          actions={
            <span className="dictionaryRequiredBadge">
              Обязательный
            </span>
          }
        />
        ) : null
      ) : null}

      {!embedded ? <div className="dictionaryEditorTop">
        <Card title="Метаданные">
          <div className="dictionaryEditorMetaGrid">
            <Field label="Тип данных" className="dictionaryEditorField">
              <div className="dictionaryEditorInlineControls">
                <Select
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
                </Select>
                {!attrId ? <span className="muted">Нет связанного параметра.</span> : null}
              </div>
            </Field>

            <Field label="Категория параметра" className="dictionaryEditorField">
              <Select
                value={paramGroup}
                onChange={async (e) => {
                  const next = e.target.value as ParamGroup;
                  if (!effectiveDictId) return;
                  setParamGroup(next);
                  const res = await api<{ item: DictItem }>(`/dictionaries/${encodeURIComponent(effectiveDictId)}`, {
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
              </Select>
            </Field>

            <Field label="Обязательный параметр" className="dictionaryEditorField" hint="Пометить как обязательный для заполнения">
              <label htmlFor={requiredInputId} className="muted dictionaryEditorCheckLabel">
                <input
                  id={requiredInputId}
                  type="checkbox"
                  checked={requiredFlag}
                  onChange={async (e) => {
                    const next = e.target.checked;
                    if (!effectiveDictId) return;
                    setRequiredFlag(next);
                    const res = await api<{ item: DictItem }>(`/dictionaries/${encodeURIComponent(effectiveDictId)}`, {
                      method: "PATCH",
                      body: JSON.stringify({ required: next }),
                    });
                    if (res?.item) {
                      setItem((prev) => (prev ? { ...prev, meta: res.item.meta } : prev));
                    }
                    flashSavedToast();
                  }}
                  disabled={loading}
                  className="dictionaryEditorCheckInput"
                />
                Пометить как обязательный для заполнения
              </label>
            </Field>
          </div>
        </Card>

        <section className="dictionaryEditorStatusStrip" aria-label="Состояние справочника">
          <div>
            <span>Значений</span>
            <strong>{stats.valuesTotal}</strong>
          </div>
          <div>
            <span>Дублей</span>
            <strong>{stats.duplicatesTotal}</strong>
          </div>
          <div>
            <span>Источник</span>
            <strong>{stats.topSource}</strong>
          </div>
          <div>
            <span>Обновление</span>
            <strong>{stats.updatedAt ? new Date(stats.updatedAt).toLocaleString() : "—"}</strong>
          </div>
        </section>
      </div> : null}

      {providerCodes.length ? (
        <Card className="dictionaryProviderCompactCard">
          <DataToolbar
            title="Площадка для выгрузки"
            subtitle="Здесь не меняем значение каталога. Здесь задаем, какое написание примет маркетплейс при экспорте."
            actions={
              <>
                {providerCodes.map((provider) => (
                  <Button
                    key={provider}
                    variant={activeProvider === provider ? "primary" : "default"}
                    onClick={() => setActiveProvider(provider)}
                  >
                    {PROVIDER_LABEL[provider] || provider}
                  </Button>
                ))}
              </>
            }
          />

          {activeProviderRef ? (
            <div className="dictionaryEditorProviderGrid isCompact">
              <Card className="dictionaryEditorProviderCard">
                <div className="dictionaryProviderEyebrow">
                  {PROVIDER_LABEL[activeProvider] || activeProvider}
                </div>
                <div className="dictionaryProviderTitle">
                  {activeProviderRef.name || "Поле не указано"}
                </div>
                <div className="dictionaryProviderFacts">
                  <div>Тип площадки: <b>{activeProviderRef.kind || "—"}</b></div>
                  <div>Обязательный: <b>{activeProviderRef.required ? "да" : "нет"}</b></div>
                  <div>Допустимых значений: <b>{activeProviderAllowedValues.length}</b></div>
                  <div>Сопоставлено: <b>{activeProviderMappedCount}/{values.length}</b></div>
                </div>
              </Card>

              <Card className="dictionaryEditorProviderCard">
                <div className="dictionaryProviderCardHead">
                  <div>Справочник площадки</div>
                  <span>
                    показано {visibleProviderAllowedValues.length} из {activeProviderAllowedValues.length}
                  </span>
                </div>
                {activeProviderAllowedValues.length ? (
                  <>
                    <TextInput
                      value={providerAllowedQuery}
                      onChange={(event) => setProviderAllowedQuery(event.target.value)}
                      placeholder="Найти значение площадки..."
                      className="dictionaryProviderSearch"
                    />
                    <div className="dictionaryAllowedValuesCloud">
                      {visibleProviderAllowedValues.map((value) => (
                        <span key={value}>
                          {value}
                        </span>
                      ))}
                    </div>
                    {activeProviderAllowedValues.length > visibleProviderAllowedValues.length ? (
                      <div className="dictionaryProviderHint">
                        Полный список не выводится простыней. Используйте поиск или поле сопоставления ниже.
                      </div>
                    ) : null}
                  </>
                ) : (
                  <div className="dictionaryProviderHint">
                    У площадки нет справочника значений для этого параметра.
                  </div>
                )}
              </Card>
            </div>
          ) : null}
        </Card>
      ) : null}

      <Card className="dictionarySearchCompactCard">
        <Field label="Поиск по значениям" className="dictionaryEditorField">
          <TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Например: black, 256, titanium…" />
        </Field>

        <DataFilters className="dictionaryEditorFilters">
          <Button variant={valueFilter === "all" ? "primary" : "default"} onClick={() => setValueFilter("all")}>
            Все
          </Button>
          <Button variant={valueFilter === "duplicates" ? "primary" : "default"} onClick={() => setValueFilter("duplicates")}>
            Дубли
          </Button>
          <Button variant={valueFilter === "empty" ? "primary" : "default"} onClick={() => setValueFilter("empty")}>
            Пустые
          </Button>
        </DataFilters>

        <DataToolbar
          compact
          className="dictionaryEditorActions"
          actions={
            <>
              <Button
                onClick={() => {
                  setAddOpen((x) => !x);
                  setTimeout(() => addRef.current?.focus(), 0);
                }}
                disabled={!item || loading}
              >
                + Добавить значение
              </Button>
              <Button onClick={() => downloadTemplate(item?.title || "dictionary", values)} disabled={!item}>
                Шаблон импорта
              </Button>
              <Button onClick={() => setImportOpen((x) => !x)} disabled={!item || loading}>
                Импорт значений
              </Button>
              <Button onClick={() => void runDedupePreview()} disabled={!item || loading || dedupeLoading}>
                {dedupeLoading ? "Проверяю дубли…" : "Чистка дублей"}
              </Button>
            </>
          }
        >
          <div className="muted dictionaryEditorHelpText">
            Если переименовать значение в уже существующее — они будут <b>склеены</b>.
          </div>
        </DataToolbar>

        {addOpen ? (
          <div className="dictionaryEditorAddRow">
            <TextInput
              ref={addRef}
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              placeholder="Новое значение…"
              className="dictionaryEditorGrowInput"
              onKeyDown={(e) => {
                if (e.key === "Enter") void addValue();
                if (e.key === "Escape") {
                  setAddOpen(false);
                  setNewValue("");
                }
              }}
            />
            <Button variant="primary" onClick={() => void addValue()} disabled={!newValue.trim()}>
              Добавить
            </Button>
            <Button
              onClick={() => {
                setAddOpen(false);
                setNewValue("");
              }}
            >
              Отмена
            </Button>
          </div>
        ) : null}

        {importOpen ? (
          <div className="dictionaryEditorImportBox">
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
              <div className="muted dictionaryEditorHelpText">
                Файл: <b>{importFileName}</b>
              </div>
            ) : null}
            {importErr ? <Alert tone="error">{importErr}</Alert> : null}
            <div className="dictionaryEditorInlineActions">
              <Button
                variant="primary"
                onClick={() => void importValues(importRef.current?.files?.[0] || null)}
                disabled={importLoading || !importRef.current?.files?.[0]}
              >
                {importLoading ? "Импортирую…" : "Импортировать"}
              </Button>
              <Button
                onClick={() => {
                  setImportOpen(false);
                  setImportErr(null);
                  setImportFileName("");
                  if (importRef.current) importRef.current.value = "";
                }}
              >
                Отмена
              </Button>
            </div>
            <div className="muted dictionaryEditorHelpText">
              Формат: одна строка = одно значение (CSV/текст). При импорте список синхронизируется.
            </div>
          </div>
        ) : null}
      </Card>

      {dedupeOpen && dedupePreview ? (
        <Card className="dictionaryDedupeCard">
          <div className="dictionaryDedupeHead">
            <div>
              <div className="dictionaryDedupeTitle">Чистка дублей</div>
              <div className="muted dictionaryDedupeMeta">
                Было: <b>{dedupePreview.before_count}</b> → станет: <b>{dedupePreview.after_count}</b> (удалится: <b>{dedupePreview.removed}</b>)
              </div>
            </div>
            <div className="dictionaryEditorInlineActions">
              <Button onClick={() => setDedupeOpen(false)} disabled={dedupeLoading}>
                Закрыть
              </Button>
              <Button
                variant="primary"
                onClick={() => setDedupeConfirmOpen(true)}
                disabled={dedupeLoading || !dedupePreview.removed}
                title={dedupePreview.removed ? "Применить чистку" : "Дублей нет"}
              >
                {dedupeLoading ? "Применяю…" : "Применить"}
              </Button>
            </div>
          </div>

          {dedupePreview.merges?.length ? (
            <div className="dictionaryDedupeList">
              {dedupePreview.merges.slice(0, 50).map((m, idx) => (
                <Card key={`${m.keep}-${idx}`} className="dictionaryDedupeMergeCard">
                  <div className="dictionaryDedupeMergeTitle">{m.keep}</div>
                  <div className="muted dictionaryDedupeMergeMeta">
                    Склеено: {m.merged_items} (значения: {m.merged.join(", ")})
                  </div>
                </Card>
              ))}
              {dedupePreview.merges.length > 50 ? (
                <div className="muted dictionaryEditorHelpText">
                  Показаны первые 50 merge-групп.
                </div>
              ) : null}
            </div>
          ) : (
            <div className="muted dictionaryDedupeEmpty">
              Дублей не найдено.
            </div>
          )}
        </Card>
      ) : null}

      {!item ? (
        <Card>
          <div className="muted">{loading ? "Загрузка…" : "Параметр не найден."}</div>
        </Card>
      ) : (
        <Card>
          <div className="muted dictionaryValuesCounter">
            Значений: <b>{values.length}</b>
          </div>

          {filtered.length === 0 ? (
            <div className="muted">Ничего не найдено.</div>
          ) : (
            <div className="dictionaryValuesList">
              {filtered.map((v, i) => {
                const text = asText(v);
                const isEditing = editKey === text;
                const mappedValue = activeProvider ? exportMappedValue(activeProvider, text) : "";
                const suggestedValue =
                  activeProvider && !mappedValue
                    ? providerValueSuggestion(text, activeProviderAllowedValues)
                    : "";

                return (
                  <Card
                    key={`${text}-${i}`}
                    className={`dictionaryValueRow ${activeProvider ? "hasProvider" : ""}`}
                  >
                    <div className="dictionaryValueMainCell">
                      {!isEditing ? (
                        <div className="dictionaryValueText" title={text}>
                          {text}
                        </div>
                      ) : (
                        <TextInput
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
                      <div className="dictionaryValueProviderCell">
                        <div className="dictionaryValueProviderHead">
                          <span>{PROVIDER_LABEL[activeProvider] || activeProvider}</span>
                          {mappedValue ? (
                            <b>Сопоставлено</b>
                          ) : suggestedValue ? (
                            <b>Есть предложение</b>
                          ) : (
                            <b>Нужно выбрать</b>
                          )}
                        </div>
                        <div className="dictionaryValueProviderControls">
                          <TextInput
                            list={`provider-values-${activeProvider}`}
                            value={mappedValue}
                            onChange={(e) => updateExportMapDraft(activeProvider, text, e.target.value)}
                            placeholder={suggestedValue || "Значение площадки…"}
                            disabled={isEditing}
                            className="dictionaryEditorGrowInput"
                          />
                          {suggestedValue ? (
                            <Button
                              disabled={isEditing}
                              onClick={() => {
                                updateExportMapDraft(activeProvider, text, suggestedValue);
                                void saveExportMapping(activeProvider, text, suggestedValue);
                              }}
                            >
                              Принять
                            </Button>
                          ) : null}
                          <Button
                            variant="primary"
                            disabled={isEditing}
                            onClick={() => void saveExportMapping(activeProvider, text, exportMappedValue(activeProvider, text))}
                          >
                            Сохранить
                          </Button>
                          <Button
                            disabled={isEditing || !exportMappedValue(activeProvider, text)}
                            onClick={() => {
                              updateExportMapDraft(activeProvider, text, "");
                              void saveExportMapping(activeProvider, text, "");
                            }}
                          >
                            Снять
                          </Button>
                        </div>
                      </div>
                    ) : null}

                    <div className="dictionaryValueActions">
                      {!isEditing ? (
                        <>
                          <IconButton
                            type="button"
                            title="Переименовать / склеить"
                            onClick={() => {
                              setEditKey(text);
                              setEditValue(text);
                            }}
                          >
                            Изм.
                          </IconButton>
                          <IconButton
                            tone="danger"
                            type="button"
                            title="Удалить значение"
                            onClick={() => setDeleteValueTarget(text)}
                          >
                            Уд.
                          </IconButton>
                        </>
                      ) : (
                        <>
                          <Button
                            variant="primary"
                            onClick={() => void renameValue(text, editValue)}
                            disabled={!editValue.trim() || editValue.trim() === text}
                          >
                            Сохранить
                          </Button>
                          <Button
                            onClick={() => {
                              setEditKey(null);
                              setEditValue("");
                            }}
                          >
                            Отмена
                          </Button>
                        </>
                      )}
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </Card>
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
        <div className="dictionarySavedToast">
          Изменения сохранены
        </div>
      ) : null}

      <Modal
        open={dedupeConfirmOpen}
        onClose={() => !dedupeLoading && setDedupeConfirmOpen(false)}
        title="Применить чистку дублей"
        subtitle="Система склеит совпадающие значения и удалит дубли из словаря."
      >
        <div className="dict-deleteSummary">
          <strong>{dedupePreview?.removed || 0}</strong>
          <span>значений будет удалено</span>
        </div>
        <div className="modal-actions dict-modalActions">
          <Button onClick={() => setDedupeConfirmOpen(false)} disabled={dedupeLoading}>Отмена</Button>
          <Button variant="primary" onClick={() => void applyDedupe()} disabled={dedupeLoading || !dedupePreview?.removed}>
            {dedupeLoading ? "Применяю…" : "Применить"}
          </Button>
        </div>
      </Modal>

      <Modal
        open={!!deleteValueTarget}
        onClose={() => setDeleteValueTarget("")}
        title="Удалить значение"
        subtitle="Значение будет удалено из словаря без возможности восстановления."
      >
        <div className="dict-deleteSummary">
          <strong>{deleteValueTarget}</strong>
          <span>значение словаря</span>
        </div>
        <div className="modal-actions dict-modalActions">
          <Button onClick={() => setDeleteValueTarget("")}>Отмена</Button>
          <Button
            variant="danger"
            onClick={() => {
              const value = deleteValueTarget;
              setDeleteValueTarget("");
              void deleteValue(value);
            }}
            disabled={!deleteValueTarget}
          >
            Удалить значение
          </Button>
        </div>
      </Modal>
    </div>
  );
}
