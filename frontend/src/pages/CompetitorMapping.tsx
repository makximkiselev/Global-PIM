import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import "../styles/app.css";
import "../styles/competitor-mapping.css";

type SiteKey = "restore" | "store77";

type TemplateItem = {
  id: string;
  name: string;
  category_id?: string | null;
};

type MasterField = {
  code: string;
  name?: string | null;
  type?: string | null;
  required?: boolean | null;
};
const PARAM_GROUPS = ["Артикулы", "Описание", "Медиа", "О товаре", "Логистика", "Гарантия", "Прочее"] as const;
type ParamGroup = (typeof PARAM_GROUPS)[number];

const FALLBACK_SERVICE_CODES = new Set(["sku_gt", "sku_id", "barcode"]);

type DictionaryItem = {
  id?: string | null;
  code?: string | null;
  attr_id?: string | null;
  title?: string | null;
  meta?: { service?: boolean | string };
};
type FieldMeta = {
  name: string;
  section?: string;
  key?: string;
};

type TemplateMappingResp = {
  ok: boolean;
  template_id: string;
  template: { id?: string; name?: string; category_id?: string };
  master_fields: MasterField[];
  data: {
    priority_site?: SiteKey | null;
    links?: Partial<Record<SiteKey, string>>;
    mapping_by_site?: Partial<Record<SiteKey, Record<string, string>>>;
    mapping?: Record<string, string>;
    updated_at?: string;
  };
};

type FlagsResp = { ok: boolean; flags: Record<string, boolean> };

type FieldsBatchItemOk = {
  ok: true;
  site: SiteKey;
  fields: string[];
  fields_meta?: FieldMeta[];
  skipped?: boolean;
};
type FieldsBatchItemErr = { ok: false; error: string };
type FieldsBatchResp = {
  ok: boolean;
  results: Record<SiteKey, FieldsBatchItemOk | FieldsBatchItemErr>;
};

type MappingState = {
  prioritySite: SiteKey | null;
  links: Record<SiteKey, string>;
  mappingBySite: Record<SiteKey, Record<string, string>>;
};

type StatusKind = "ok" | "warn" | "bad";
type CompetitorMappingView = "all" | "links" | "mapping";
type CompetitorMappingProps = {
  embedded?: boolean;
  view?: CompetitorMappingView;
  categoryId?: string;
  categoryName?: string;
};

// -------------------- utils --------------------
function apiPath(path: string): string {
  return path.startsWith("/api") ? path : `/api${path}`;
}

function tryParseJson(text: string): any {
  const s = (text || "").trim();
  if (!s) return null;
  if ((s.startsWith("{") && s.endsWith("}")) || (s.startsWith("[") && s.endsWith("]"))) {
    try {
      return JSON.parse(s);
    } catch {
      return null;
    }
  }
  return null;
}

async function safeErr(r: Response): Promise<string> {
  try {
    const t = await r.text();
    const j = tryParseJson(t);
    return (j?.detail || j?.message || t || `${r.status} ${r.statusText}`) as string;
  } catch {
    return `${r.status} ${r.statusText}`;
  }
}

function shallowEqualObj(a: any, b: any): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  const ka = Object.keys(a);
  const kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  for (const k of ka) {
    if (a[k] !== b[k]) return false;
  }
  return true;
}

function normalizeLinks(l: Record<SiteKey, string>): Record<SiteKey, string> {
  return {
    restore: (l.restore || "").trim(),
    store77: (l.store77 || "").trim(),
  };
}

function buildPatchPayload(saved: MappingState, draft: MappingState) {
  const patch: any = {};
  if (saved.prioritySite !== draft.prioritySite) patch.priority_site = draft.prioritySite;

  const sLinks = normalizeLinks(saved.links);
  const dLinks = normalizeLinks(draft.links);
  if (!shallowEqualObj(sLinks, dLinks)) patch.links = dLinks;

  // mapping diff by site
  const mDiffBySite: Partial<Record<SiteKey, Record<string, string | null>>> = {};
  let anyChanged = false;

  (["restore", "store77"] as SiteKey[]).forEach((site) => {
    const sMap = saved.mappingBySite?.[site] || {};
    const dMap = draft.mappingBySite?.[site] || {};
    const keys = new Set<string>([...Object.keys(sMap), ...Object.keys(dMap)]);
    const mDiff: Record<string, string | null> = {};
    let changed = false;

    for (const k of keys) {
      const sv = sMap[k] || "";
      const dv = dMap[k] || "";
      if (sv !== dv) {
        changed = true;
        mDiff[k] = dv ? dv : null;
      }
    }
    if (changed) {
      mDiffBySite[site] = mDiff;
      anyChanged = true;
    }
  });

  if (anyChanged) patch.mapping_by_site = mDiffBySite;

  return patch;
}

function mergeServerUpdate(prev: MappingState, patch: any): MappingState {
  // merge для UI — до того как починим backend
  const next: MappingState = {
    prioritySite: prev.prioritySite,
    links: { ...prev.links },
    mappingBySite: {
      restore: { ...prev.mappingBySite.restore },
      store77: { ...prev.mappingBySite.store77 },
    },
  };

  if ("priority_site" in patch) next.prioritySite = patch.priority_site ?? null;
  if (patch?.links) {
    next.links = { ...next.links, ...patch.links };
  }
  if (patch?.mapping_by_site) {
    (["restore", "store77"] as SiteKey[]).forEach((site) => {
      const d: Record<string, string | null> = patch.mapping_by_site?.[site] || {};
      for (const k of Object.keys(d)) {
        const v = d[k];
        if (!v) delete next.mappingBySite[site][k];
        else next.mappingBySite[site][k] = v;
      }
    });
  }
  return next;
}

function classifyFieldGroup(field: MasterField): ParamGroup {
  const s = `${String(field.name || "")} ${String(field.code || "")}`.toLowerCase();
  if (/(sku|штрихкод|barcode|артикул|партномер|серийн)/i.test(s)) return "Артикулы";
  if (/(описани|аннотац|description)/i.test(s)) return "Описание";
  if (/(картин|изображ|фото|media|video|видеооблож|видео)/i.test(s)) return "Медиа";
  if (/(гарант|срок службы|service life)/i.test(s)) return "Гарантия";
  if (/(вес|ширина|высота|толщина|размер|длина|упаков|габарит|логист)/i.test(s)) return "Логистика";
  return "О товаре";
}

// -------------------- API helpers --------------------
async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(apiPath(path), { credentials: "include" });
  if (!r.ok) throw new Error(await safeErr(r));
  const t = await r.text();
  const j = tryParseJson(t);
  return (j ?? (t as any)) as T;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(apiPath(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body ?? {}),
  });
  if (!r.ok) throw new Error(await safeErr(r));
  const t = await r.text();
  const j = tryParseJson(t);
  return (j ?? (t as any)) as T;
}

async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(apiPath(path), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body ?? {}),
  });
  if (!r.ok) throw new Error(await safeErr(r));
  const t = await r.text();
  const j = tryParseJson(t);
  return (j ?? (t as any)) as T;
}

async function apiGetSoft<T>(path: string): Promise<{ ok: boolean; status: number; data?: T; error?: string }> {
  try {
    const r = await fetch(apiPath(path), { credentials: "include" });
    const status = r.status;
    if (!r.ok) return { ok: false, status, error: await safeErr(r) };
    const t = await r.text();
    const j = tryParseJson(t);
    return { ok: true, status, data: (j ?? (t as any)) as T };
  } catch (e: any) {
    return { ok: false, status: 0, error: String(e?.message || e) };
  }
}

// -------------------- UI bits --------------------
function SpinnerDot({ show }: { show: boolean }) {
  if (!show) return null;
  return <span className="cm-spinner" aria-label="Загрузка" title="Загрузка" />;
}

function Toggle({
  on,
  onChange,
  label,
  disabled,
}: {
  on: boolean;
  onChange: (next: boolean) => void;
  label?: string;
  disabled?: boolean;
}) {
  return (
    <button
      className="btn"
      type="button"
      onClick={() => (!disabled ? onChange(!on) : null)}
      aria-pressed={on}
      title={label || ""}
      disabled={disabled}
    >
      <span className="cm-toggle">
        <span className={`cm-toggleTrack ${on ? "isOn" : ""} ${disabled ? "isDisabled" : ""}`}>
          <span className={`cm-toggleKnob ${on ? "isOn" : ""} ${disabled ? "isDisabled" : ""}`} />
        </span>
        {label ? <span className="cm-toggleLabel">{label}</span> : null}
      </span>
    </button>
  );
}

function Badge({
  kind,
  text,
}: {
  kind: "ok" | "warn" | "bad";
  text: string;
}) {
  const cls = kind === "ok" ? "cm-badgeOk" : kind === "warn" ? "cm-badgeWarn" : "cm-badgeBad";
  return <span className={`cm-badge ${cls}`}>{text}</span>;
}

function PrimarySaveButton({
  loading,
  onClick,
  disabled,
}: {
  loading: boolean;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button className="cm-saveBtn" type="button" onClick={onClick} disabled={disabled || loading} aria-busy={loading}>
      <span className="cm-saveIcon" aria-hidden>
        💾
      </span>
      <span>{loading ? "Сохранение..." : "Сохранить"}</span>
    </button>
  );
}

function LinkCard({
  site,
  title,
  hint,
  link,
  onLinkChange,
  onLinkCommit,
  fieldsCount,
  fieldsLoading,
  fieldsError,
  fieldsAttempted,
  disabled,
}: {
  site: SiteKey;
  title: string;
  hint: string;
  link: string;
  onLinkChange: (v: string) => void;
  onLinkCommit?: () => void;
  fieldsCount: number;
  fieldsLoading: boolean;
  fieldsError?: string;
  fieldsAttempted: boolean;
  disabled: boolean;
}) {
  const cardCls = site === "restore" ? "cm-linkCard cm-linkCard--restore" : "cm-linkCard cm-linkCard--store77";
  const dotCls = site === "restore" ? "cm-dot cm-dot--restore" : "cm-dot cm-dot--store77";
  const hasLink = !!link.trim();
  const statusText = fieldsLoading
    ? "Загрузка..."
    : fieldsError
      ? "Ошибка"
      : fieldsCount
        ? "Успешно"
        : fieldsAttempted && hasLink
          ? "Не загружено"
          : "";

  return (
    <div className={`mm-aggItem ${cardCls} ${disabled ? "isDisabled" : ""}`}>
      <div className="cm-linkCardHeader">
        <div className="cm-linkTitleRow">
          <span className={dotCls} aria-hidden />
          <div>
            <div className="mm-providerPath cm-linkTitle">{title}</div>
            <div className="mm-breadcrumbs cm-linkHint">{hint}</div>
          </div>
        </div>
      </div>

      <div className="cm-sep" />

      <div className="cm-fieldLabel">Ссылка</div>
      <input
        className="input cm-inputBig"
        value={link}
        onChange={(e) => onLinkChange(e.target.value)}
        onBlur={() => onLinkCommit?.()}
        placeholder={site === "restore" ? "https://re-store.ru/..." : "https://store77.net/..."}
        disabled={disabled}
      />

      {hasLink || fieldsError || fieldsCount || fieldsAttempted || fieldsLoading ? (
        <div className="cm-linkActions">
          <span className="cm-pill" style={{ display: "inline-flex", gap: 10 }}>
            <SpinnerDot show={fieldsLoading} />
            <span style={{ color: fieldsError ? "#ef4444" : fieldsCount ? "#166534" : undefined, fontWeight: 900 }}>
              {statusText || (hasLink ? "Ссылка не загружена" : "")}
            </span>
            {fieldsCount ? <span>Полей: {fieldsCount}</span> : null}
            {fieldsError ? <span style={{ color: "#ef4444" }}>{fieldsError}</span> : null}
          </span>
        </div>
      ) : null}
    </div>
  );
}

function SelectBig({
  value,
  onChange,
  disabled,
  children,
}: {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={`cm-selectWrap ${disabled ? "isDisabled" : ""}`}>
      <select className="input cm-selectBig" value={value} onChange={onChange} disabled={disabled}>
        {children}
      </select>
      <div className="cm-caret" aria-hidden>
        ▼
      </div>
    </div>
  );
}

// -------------------- PAGE --------------------
export default function CompetitorMapping(props: CompetitorMappingProps = {}) {
  const { embedded = false, view = "all", categoryId = "", categoryName = "" } = props;
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [flags, setFlags] = useState<Record<string, boolean>>({});

  const [selectedId, setSelectedId] = useState<string>("");
  const [tplInfo, setTplInfo] = useState<TemplateMappingResp | null>(null);

  const emptyState: MappingState = useMemo(
    () => ({
      prioritySite: null,
      links: { restore: "", store77: "" },
      mappingBySite: { restore: {}, store77: {} },
    }),
    []
  );

  const [saved, setSaved] = useState<MappingState>(emptyState);
  const [draft, setDraft] = useState<MappingState>(emptyState);
  const [isEditing, setIsEditing] = useState(false);

  const [fieldsBySite, setFieldsBySite] = useState<Record<SiteKey, string[]>>({ restore: [], store77: [] });
  const [fieldsMetaBySite, setFieldsMetaBySite] = useState<Record<SiteKey, FieldMeta[]>>({
    restore: [],
    store77: [],
  });
  const [fieldsAttemptedBySite, setFieldsAttemptedBySite] = useState<Record<SiteKey, boolean>>({
    restore: false,
    store77: false,
  });
  const [fieldsLoadingAll, setFieldsLoadingAll] = useState(false);
  const [fieldsErrorBySite, setFieldsErrorBySite] = useState<Partial<Record<SiteKey, string>>>({});
  const [serviceCodes, setServiceCodes] = useState<string[]>([]);
  const [serviceNames, setServiceNames] = useState<string[]>([]);

  const API = useMemo(
    () => ({
      async listTemplates(): Promise<TemplateItem[]> {
        const soft = await apiGetSoft<{ ok: boolean; items: any[] }>(`/templates/list`);
        if (soft.ok && soft.data?.items && Array.isArray(soft.data.items)) {
          return soft.data.items
            .filter(Boolean)
            .map((t: any) => ({
              id: String(t.id),
              name: String(t.name || "Без названия"),
              category_id: t.category_id ? String(t.category_id) : null,
            }))
            .sort((a, b) => a.name.localeCompare(b.name, "ru"));
        }

        const data = await apiGet<any>(`/templates/tree`);
        if (data?.templates && typeof data.templates === "object" && !Array.isArray(data.templates)) {
          return Object.values<any>(data.templates)
            .filter((t) => t && t.id)
            .map((t) => ({
              id: String(t.id),
              name: String(t.name || "Без названия"),
              category_id: t.category_id ? String(t.category_id) : null,
            }))
            .sort((a, b) => a.name.localeCompare(b.name, "ru"));
        }
        return [];
      },

      async templateFlags(): Promise<FlagsResp> {
        return apiGet<FlagsResp>(`/competitor-mapping/template-flags`);
      },

      async listServiceCodes(): Promise<{ codes: string[]; names: string[] }> {
        const data = await apiGet<{ items?: DictionaryItem[] }>(`/dictionaries?include_service=1`);
        const out = new Set<string>();
        const names = new Set<string>();
        for (const it of data?.items || []) {
          const service = it?.meta?.service;
          if (service !== true && service !== "true") continue;
          if (it?.code) out.add(String(it.code).trim());
          if (it?.attr_id) out.add(String(it.attr_id).trim());
          if (it?.id) out.add(String(it.id).trim());
          if (it?.title) names.add(String(it.title).trim());
        }
        return { codes: Array.from(out), names: Array.from(names) };
      },

      async getTemplateMapping(templateId: string): Promise<TemplateMappingResp> {
        return apiGet<TemplateMappingResp>(`/competitor-mapping/template/${templateId}`);
      },
      async getCategoryMapping(categoryIdIn: string): Promise<TemplateMappingResp> {
        return apiGet<TemplateMappingResp>(`/competitor-mapping/category/${categoryIdIn}`);
      },

      async saveTemplateMapping(templateId: string, payload: unknown): Promise<{ ok: boolean }> {
        return apiPut<{ ok: boolean }>(`/competitor-mapping/template/${templateId}`, payload);
      },
      async saveCategoryMapping(categoryIdIn: string, payload: unknown): Promise<{ ok: boolean }> {
        return apiPut<{ ok: boolean }>(`/competitor-mapping/category/${categoryIdIn}`, payload);
      },

      async competitorFieldsBatch(linksIn: Record<SiteKey, string>): Promise<FieldsBatchResp> {
        return apiPost<FieldsBatchResp>(`/competitor-mapping/competitor-fields-batch`, { links: linksIn });
      },
    }),
    []
  );

  const masterFields: MasterField[] = tplInfo?.master_fields || [];
  const serviceCodeSet = useMemo(() => {
    const out = new Set<string>();
    for (const code of serviceCodes) {
      const norm = (code || "").trim().toLowerCase();
      if (norm) out.add(norm);
    }
    return out;
  }, [serviceCodes]);
  const serviceNameSet = useMemo(() => {
    const out = new Set<string>();
    for (const name of serviceNames) {
      const norm = (name || "").trim().toLowerCase();
      if (norm) out.add(norm);
    }
    return out;
  }, [serviceNames]);
  const visibleFields = useMemo(() => {
    if (!masterFields.length) return [];
    return masterFields.filter((f) => {
      const code = (f.code || "").trim().toLowerCase();
      const name = (f.name || "").trim().toLowerCase();
      if (!code) return false;
      if (serviceCodeSet.size > 0 || serviceNameSet.size > 0) {
        if (serviceCodeSet.has(code)) return false;
        if (name && serviceNameSet.has(name)) return false;
        return true;
      }
      return !FALLBACK_SERVICE_CODES.has(code);
    });
  }, [masterFields, serviceCodeSet, serviceNameSet]);
  const groupedVisibleFields = useMemo(() => {
    const byGroup: Record<ParamGroup, MasterField[]> = {
      "Артикулы": [],
      "Описание": [],
      "Медиа": [],
      "О товаре": [],
      "Логистика": [],
      "Гарантия": [],
      "Прочее": [],
    };
    for (const f of visibleFields) {
      const g = classifyFieldGroup(f);
      byGroup[g].push(f);
    }
    for (const g of PARAM_GROUPS) {
      byGroup[g].sort((a, b) => {
        const an = String(a.name || a.code || "").trim();
        const bn = String(b.name || b.code || "").trim();
        return an.localeCompare(bn, "ru");
      });
    }
    return PARAM_GROUPS.map((group) => ({ group, fields: byGroup[group] })).filter((x) => x.fields.length > 0);
  }, [visibleFields]);
  const viewState = isEditing ? draft : saved;

  const missingCount = useMemo(() => {
    if (!visibleFields.length) return 0;
    let n = 0;
    for (const f of visibleFields) {
      const code = (f.code || "").trim();
      if (!code) continue;
      (["restore", "store77"] as SiteKey[]).forEach((site) => {
        const hasLink = (viewState.links[site] || "").trim().length > 0;
        if (!hasLink) return;
        if (!viewState.mappingBySite?.[site]?.[code]) n += 1;
      });
    }
    return n;
  }, [visibleFields, viewState.links, viewState.mappingBySite]);

  // ✅ статус для выбранного шаблона (для левого списка)
  const activeStatus: { kind: StatusKind; text: string } = useMemo(() => {
    const hasAnyLink = !!(viewState.links.restore || "").trim() || !!(viewState.links.store77 || "").trim();
    const hasAnyMap =
      (!!viewState.mappingBySite.restore && Object.keys(viewState.mappingBySite.restore).length > 0) ||
      (!!viewState.mappingBySite.store77 && Object.keys(viewState.mappingBySite.store77).length > 0);

    // Поля в шаблоне отсутствуют => считаем "не настроен" (по твоей логике — красный)
    if (!visibleFields.length) {
      return { kind: "bad", text: "Не настроен" };
    }

    if (!hasAnyLink && !hasAnyMap) {
      return { kind: "bad", text: "Не настроен" };
    }

    // Есть ссылки/маппинг, но не всё сопоставлено
    if (missingCount > 0) {
      return { kind: "warn", text: "Частично настроен" };
    }

    // missingCount == 0
    return { kind: "ok", text: "Все атрибуты сопоставлены" };
  }, [visibleFields.length, missingCount, viewState.links.restore, viewState.links.store77, viewState.mappingBySite]);

  // -------------------- bootstrap --------------------
  useEffect(() => {
    if (categoryId) {
      setTemplates([]);
      setFlags({});
      API.listServiceCodes()
        .then((svc: any) => {
          setServiceCodes(svc?.codes || []);
          setServiceNames(svc?.names || []);
        })
        .catch(() => {
          setServiceCodes([]);
          setServiceNames([]);
        });
      return;
    }
    let mounted = true;
    (async () => {
      setErr("");
      setLoading(true);
      try {
        const [tpls, fl, svc] = await Promise.all([
          API.listTemplates(),
          API.templateFlags(),
          API.listServiceCodes().catch(() => []),
        ]);
        if (!mounted) return;
        setTemplates(tpls);
        setFlags(fl?.flags || {});
        setServiceCodes((svc as any)?.codes || []);
        setServiceNames((svc as any)?.names || []);
      } catch (e: any) {
        if (!mounted) return;
        setErr(String(e?.message || e));
      } finally {
        if (!mounted) return;
        setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [API, categoryId]);

  // -------------------- load selected --------------------
  useEffect(() => {
    const activeId = categoryId || selectedId;
    if (!activeId) {
      setTplInfo(null);
      setSaved(emptyState);
      setDraft(emptyState);
      setIsEditing(false);
      setFieldsBySite({ restore: [], store77: [] });
      setFieldsErrorBySite({});
      return;
    }

    let mounted = true;
    (async () => {
      setErr("");
      setLoading(true);
      try {
        const resp = categoryId ? await API.getCategoryMapping(categoryId) : await API.getTemplateMapping(selectedId);
        if (!mounted) return;

        setTplInfo(resp);

        const data = resp?.data || {};
        const p = (data?.priority_site ?? null) as SiteKey | null;

        const restoreLink = (data?.links?.restore || "") as string;
        const storeLink = (data?.links?.store77 || "") as string;
        const links: Record<SiteKey, string> = { restore: restoreLink, store77: storeLink };

        const mappingBySite = (data?.mapping_by_site || {}) as Partial<Record<SiteKey, Record<string, string>>>;
        const legacy = (data?.mapping || {}) as Record<string, string>;
        const fullMappingBySite: Record<SiteKey, Record<string, string>> = {
          restore: mappingBySite.restore || legacy || {},
          store77: mappingBySite.store77 || legacy || {},
        };

        const nextSaved: MappingState = {
          prioritySite: p,
          links,
          mappingBySite: fullMappingBySite,
        };

        setSaved(nextSaved);
        setDraft(nextSaved);
        setIsEditing(false);
        setFieldsErrorBySite({});

        if (activeId) {
          try {
            const raw = localStorage.getItem(`competitor.fields.${activeId}`);
            const parsed = raw ? JSON.parse(raw) : null;
            const restoreFields = Array.isArray(parsed?.restore) ? parsed.restore : [];
            const storeFields = Array.isArray(parsed?.store77) ? parsed.store77 : [];
            const meta = parsed?.meta || {};
            const restoreMeta = Array.isArray(meta?.restore) ? meta.restore : [];
            const storeMeta = Array.isArray(meta?.store77) ? meta.store77 : [];

            setFieldsBySite({ restore: restoreFields, store77: storeFields });
            setFieldsMetaBySite({ restore: restoreMeta, store77: storeMeta });
            setFieldsAttemptedBySite({
              restore: restoreFields.length > 0,
              store77: storeFields.length > 0,
            });
          } catch {
            setFieldsBySite({ restore: [], store77: [] });
            setFieldsMetaBySite({ restore: [], store77: [] });
            setFieldsAttemptedBySite({ restore: false, store77: false });
          }
        } else {
          setFieldsBySite({ restore: [], store77: [] });
          setFieldsMetaBySite({ restore: [], store77: [] });
          setFieldsAttemptedBySite({ restore: false, store77: false });
        }
      } catch (e: any) {
        if (!mounted) return;
        setErr(String(e?.message || e));
      } finally {
        if (!mounted) return;
        setLoading(false);
      }
    })();

    return () => {
      mounted = false;
    };
  }, [API, selectedId, emptyState, categoryId]);

  // -------------------- draft setters --------------------
  function setLink(site: SiteKey, value: string) {
    setDraft((p) => ({ ...p, links: { ...p.links, [site]: value } }));
    setFieldsBySite((p) => ({ ...p, [site]: [] }));
    setFieldsMetaBySite((p) => ({ ...p, [site]: [] }));
    setFieldsAttemptedBySite((p) => ({ ...p, [site]: false }));
    setFieldsErrorBySite((p) => ({ ...p, [site]: undefined }));
  }

  function setMap(site: SiteKey, ourCode: string, competitorField: string) {
    setDraft((p) => {
      const next = { ...p.mappingBySite[site] };
      if (!competitorField) delete next[ourCode];
      else next[ourCode] = competitorField;
      return { ...p, mappingBySite: { ...p.mappingBySite, [site]: next } };
    });
  }

  function startEdit() {
    if (!(categoryId || selectedId)) return;
    setDraft(saved);
    setIsEditing(true);
  }

  function cancelEdit() {
    setDraft(saved);
    setIsEditing(false);
    setErr("");
  }

  // -------------------- load fields --------------------
  async function loadFieldsBoth() {
    const inlineLinksMode = !!categoryId && view === "links";
    if (!isEditing && !inlineLinksMode) return;

    const rUrl = (draft.links.restore || "").trim();
    const sUrl = (draft.links.store77 || "").trim();

    if (!rUrl && !sUrl) {
      setErr("Сначала вставь хотя бы одну ссылку конкурента.");
      return;
    }

    setErr("");
    setFieldsErrorBySite({});
    setFieldsLoadingAll(true);
    setFieldsAttemptedBySite({
      restore: !!rUrl,
      store77: !!sUrl,
    });

    try {
      const resp = await API.competitorFieldsBatch({ restore: rUrl, store77: sUrl });

      const nextFields: Record<SiteKey, string[]> = { ...fieldsBySite };
      const nextErrs: Partial<Record<SiteKey, string>> = {};
      const nextMeta: Record<SiteKey, FieldMeta[]> = { ...fieldsMetaBySite };

      (["restore", "store77"] as SiteKey[]).forEach((k) => {
        const it = resp?.results?.[k];
        if (!it) return;

        if ((it as FieldsBatchItemOk).ok) {
          const okItem = it as FieldsBatchItemOk;
          if (!okItem.skipped) {
            nextFields[k] = okItem.fields || [];
            nextMeta[k] = okItem.fields_meta || [];
          }
        } else {
          nextErrs[k] = (it as FieldsBatchItemErr).error || "Ошибка";
          nextFields[k] = [];
          nextMeta[k] = [];
        }
      });

      setFieldsBySite(nextFields);
      setFieldsMetaBySite(nextMeta);
      setFieldsErrorBySite(nextErrs);

      const activeId = categoryId || selectedId;
      if (activeId) {
        try {
          localStorage.setItem(
            `competitor.fields.${activeId}`,
            JSON.stringify({ restore: nextFields.restore, store77: nextFields.store77, meta: nextMeta })
          );
        } catch {
          // ignore storage errors
        }
      }

    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setFieldsLoadingAll(false);
    }
  }

  async function saveLinksOnly() {
    const activeId = categoryId || selectedId;
    if (!activeId) return;
    const linksPatch = buildPatchPayload(saved, draft);
    if (!("links" in linksPatch) || Object.keys(linksPatch).length === 0) return;

    setErr("");
    setLoading(true);
    try {
      if (categoryId) {
        await API.saveCategoryMapping(categoryId, { links: linksPatch.links });
      } else {
        await API.saveTemplateMapping(selectedId, { links: linksPatch.links });
      }
      const merged = mergeServerUpdate(saved, { links: linksPatch.links });
      setSaved(merged);
      setDraft((prev) => ({ ...prev, links: merged.links }));
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  // -------------------- save --------------------
  async function saveAll() {
    const activeId = categoryId || selectedId;
    if (!activeId) return;
    const inlineLinksMode = !!categoryId && view === "links";
    if (!isEditing && !inlineLinksMode) return;

    setErr("");
    setLoading(true);

    try {
      const patchPayload = buildPatchPayload(saved, draft);

      const noChanges = Object.keys(patchPayload).length === 0;
      if (noChanges) {
        if (!inlineLinksMode) setIsEditing(false);
        return;
      }

      if (categoryId) {
        await API.saveCategoryMapping(categoryId, patchPayload);
      } else {
        await API.saveTemplateMapping(selectedId, patchPayload);
      }

      const merged = mergeServerUpdate(saved, patchPayload);
      setSaved(merged);
      setDraft(merged);

      const fl = await API.templateFlags();
      setFlags(fl?.flags || {});

      if (!inlineLinksMode) setIsEditing(false);
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  // -------------------- derived UI --------------------
  const hasRestore = !!viewState.links.restore.trim();
  const hasStore77 = !!viewState.links.store77.trim();
  const inlineLinksMode = !!categoryId && view === "links";
  const linksEditable = inlineLinksMode || isEditing;
  const canMapRestore = (fieldsMetaBySite.restore.length || fieldsBySite.restore.length) > 0;
  const canMapStore = (fieldsMetaBySite.store77.length || fieldsBySite.store77.length) > 0;

  const mappingDisabledRestore = !linksEditable;
  const mappingDisabledStore = !linksEditable;
  const cardFieldsLoading = fieldsLoadingAll;

  function buildSelectOptions(current: string, fields: string[], meta?: FieldMeta[]) {
    const out: { value: string; label: string }[] = [];
    const rest: { value: string; label: string }[] = [];
    const seen = new Set<string>();
    const cur = (current || "").trim();

    const labelForValue = (value: string) => {
      if (!meta || meta.length === 0) return value;
      const hit = meta.find((m) => (m.key || m.name) === value) || meta.find((m) => m.name === value);
      return hit?.name || value;
    };

    if (cur) {
      out.push({ value: cur, label: labelForValue(cur) });
      seen.add(cur);
    }

    if (meta && meta.length > 0) {
      for (const m of meta) {
        const value = String(m.key || m.name || "").trim();
        const label = String(m.name || value).trim();
        if (!value || seen.has(value)) continue;
        seen.add(value);
        rest.push({ value, label: label || value });
      }
      rest.sort((a, b) => a.label.localeCompare(b.label, "ru"));
      out.push(...rest);
      return out;
    }

    for (const f of fields || []) {
      const s = String(f || "").trim();
      if (!s || seen.has(s)) continue;
      seen.add(s);
      rest.push({ value: s, label: s });
    }
    rest.sort((a, b) => a.label.localeCompare(b.label, "ru"));
    out.push(...rest);
    return out;
  }

  // ✅ статус для карточек слева:
  // - если флаг true => OK (зелёный)
  // - иначе: если это активный шаблон — показываем warn/bad по реальным данным
  // - иначе — bad (красный), потому что других данных про шаблон нет
  function getListStatus(templateId: string, isActive: boolean): { kind: StatusKind; text: string } {
    if (flags?.[templateId]) return { kind: "ok", text: "Все атрибуты сопоставлены" };
    if (isActive) return activeStatus; // warn / bad / ok
    return { kind: "bad", text: "Не настроен" };
  }

  const showErrBanner = !!err && !(categoryId && tplInfo);

  return (
    <div className={`dashboard-page cm-page page-shell${embedded ? " cm-pageEmbedded" : ""}`}>
      {!embedded && (
        <div className="page-header">
          <div className="page-header-main">
            <div className="page-title">Маппинг конкурентов</div>
            <div className="page-subtitle">Сопоставление характеристик (ваши атрибуты ↔ поля конкурента) по мастер-шаблону.</div>
          </div>

          <div className="page-header-actions">
            <Link className="btn" to="/">
              ← На главную
            </Link>
          </div>
        </div>
      )}

      {showErrBanner ? (
        <div className="card" style={{ padding: 12, border: "1px solid #ef4444" }}>
          <div style={{ fontWeight: 900, marginBottom: 6 }}>Ошибка</div>
          <div style={{ color: "var(--muted)" }}>{err}</div>
        </div>
      ) : null}

      <div className={`cm-layout${embedded ? " isEmbedded" : ""}${categoryId ? " isCategoryDriven" : ""}`}>
        {/* LEFT */}
        {!categoryId ? (
        <div className="card cm-panel cm-panelLeft">
          <div className="cm-panelHead">
            <div className="cm-panelTitle">Мастер-шаблоны</div>
          </div>

          {!templates.length && !loading ? (
            <div className="cm-emptyText">
              Нет мастер-шаблонов для выбора. Проверь, что API /api/templates/list отдаёт templates.json.
            </div>
          ) : null}

          <div className="cm-templateList">
            {templates.map((t) => {
              const active = t.id === selectedId;

              const st = getListStatus(t.id, active);

              return (
                <button
                  key={t.id}
                  className="btn cm-templateBtn"
                  onClick={() => setSelectedId(t.id)}
                  data-active={active ? "true" : "false"}
                >
                  <div className="cm-templateBtnMain">
                    <div className="cm-templateBtnName">{t.name}</div>

                    <Badge kind={st.kind} text={st.text} />
                  </div>

                  <div className="cm-templateBtnMark">{flags?.[t.id] ? "✅" : "○"}</div>
                </button>
              );
            })}
          </div>
        </div>
        ) : null}

        {/* RIGHT */}
        <div className="cm-panelRight cm-mirrorPanel mm-providerDetailCard">
          {!categoryId && !selectedId ? (
            <div className="cm-emptyText">
              Выбери мастер-шаблон слева — появятся ссылки, поля конкурента и маппинг.
            </div>
          ) : (
            <>
              {inlineLinksMode ? (
                <>
                  <div className="mm-providerDetailHead">
                    <div className="mm-providerLead">
                      <div className="mm-lineProvider cm-title">Конкуренты</div>
                    </div>
                  </div>
                  <div className="mm-providerActionsBar">
                    <div className="mm-providerActionBtns">
                      <button
                        type="button"
                        className="btn mm-miniBtn mm-ghostBtn"
                        onClick={loadFieldsBoth}
                        disabled={fieldsLoadingAll}
                        title="Загрузить поля для обеих ссылок"
                      >
                        {fieldsLoadingAll ? "Загрузка..." : "Загрузить"}
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="cm-rightHeader mm-providerDetailHead">
                  <div style={{ minWidth: 0 }}>
                    <div className="mm-lineProvider cm-title">{categoryId ? (categoryName || "Категория") : (tplInfo?.template?.name || "Мастер-шаблон")}</div>
                    <div className="cm-sub mm-breadcrumbs">
                      {categoryId
                        ? `Ссылки и сопоставления конкурентов для категории.${tplInfo?.template?.name ? ` Эффективный шаблон: ${tplInfo.template.name}.` : ""}`
                        : "Настрой ссылки и сопоставь атрибуты."}
                    </div>
                  </div>

                  <div className="cm-actions mm-providerActionBtns" style={{ columnGap: 8, rowGap: 8 }}>
                    {!isEditing ? (
                      <button type="button" className="btn cm-editBtn" onClick={startEdit} disabled={!(categoryId || selectedId) || loading}>
                        ✏️ Редактировать
                      </button>
                    ) : (
                      <button type="button" className="btn cm-cancelBtn" onClick={cancelEdit} disabled={loading}>
                        ✖ Отмена
                      </button>
                    )}

                    <PrimarySaveButton loading={loading} onClick={saveAll} disabled={!(categoryId || selectedId) || !isEditing} />
                  </div>
                </div>
              )}

              {!inlineLinksMode ? <div className="cm-spaceMd" /> : null}

              {view !== "mapping" && (
                <>
                  <div className="cm-linksGrid">
                    <LinkCard
                      site="restore"
                      title="re:Store"
                      hint="Вставь страницу товара/каталога"
                      link={viewState.links.restore}
                      onLinkChange={(v) => setLink("restore", v)}
                      onLinkCommit={() => {
                        void saveLinksOnly();
                      }}
                      fieldsCount={fieldsMetaBySite.restore.length || fieldsBySite.restore.length}
                      fieldsLoading={cardFieldsLoading}
                      fieldsError={fieldsErrorBySite.restore}
                      fieldsAttempted={fieldsAttemptedBySite.restore}
                      disabled={!linksEditable}
                    />

                    <LinkCard
                      site="store77"
                      title="Store77"
                      hint="Вставь страницу товара/каталога"
                      link={viewState.links.store77}
                      onLinkChange={(v) => setLink("store77", v)}
                      onLinkCommit={() => {
                        void saveLinksOnly();
                      }}
                      fieldsCount={fieldsMetaBySite.store77.length || fieldsBySite.store77.length}
                      fieldsLoading={cardFieldsLoading}
                      fieldsError={fieldsErrorBySite.store77}
                      fieldsAttempted={fieldsAttemptedBySite.store77}
                      disabled={!linksEditable}
                    />
                  </div>

                  {view === "all" ? (
                    <div className="cm-loadRow cm-loadRowLeft">
                      <button
                        type="button"
                        className="cm-loadAllBtn"
                        onClick={loadFieldsBoth}
                        disabled={!isEditing || fieldsLoadingAll}
                        title="Загрузить поля для обеих ссылок"
                      >
                        <span className="cm-loadIcon" aria-hidden>
                          {fieldsLoadingAll ? <span className="cm-spinner" /> : "⇅"}
                        </span>
                        <span>{fieldsLoadingAll ? "Загрузка..." : "Загрузить параметры"}</span>
                      </button>
                    </div>
                  ) : null}
                </>
              )}

              {view === "all" && <div className="cm-spaceLg" />}

              {view !== "links" && (
                <>
                  <div className="cm-blockHead">
                    <div className="cm-blockTitle">Сопоставление атрибутов</div>
                    {missingCount > 0 ? (
                      <div className="cm-warnPill" title="В шаблоне есть параметры без сопоставления">
                        ⚠️ {missingCount}
                      </div>
                    ) : null}
                  </div>

                  <div className="cm-spaceSm" />

                  {!visibleFields.length ? (
                    <div className="cm-emptyText">
                      В этом шаблоне пока нет атрибутов. Добавь атрибуты в “Шаблоны”.
                    </div>
                  ) : (
                    <div className="cm-groupList">
                  {groupedVisibleFields.map((section) => (
                    <div key={section.group} className="cm-groupBlock">
                      <div className="cm-groupHead">
                        <span>{section.group}</span>
                        <span className="cm-groupCount">{section.fields.length}</span>
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                        {section.fields.map((f) => {
                          const code = (f.code || "").trim();
                          if (!code) return null;

                          const ourName = (f.name || code) as string;
                          const required = !!f.required;
                          const selectedRestore = viewState.mappingBySite?.restore?.[code] || "";
                          const selectedStore = viewState.mappingBySite?.store77?.[code] || "";
                          const missingRestore = (viewState.links.restore || "").trim().length > 0 && !selectedRestore;
                          const missingStore = (viewState.links.store77 || "").trim().length > 0 && !selectedStore;
                          const missingAny = missingRestore || missingStore;

                          const optionsRestore = buildSelectOptions(
                            selectedRestore,
                            fieldsBySite.restore,
                            fieldsMetaBySite.restore
                          );
                          const optionsStore = buildSelectOptions(
                            selectedStore,
                            fieldsBySite.store77,
                            fieldsMetaBySite.store77
                          );

                          return (
                            <div key={code} className="cm-mapRow">
                              <div className="cm-mapField">
                                <div className="cm-mapFieldNameRow">
                                  <span className="cm-mapFieldName">{ourName}</span>
                                  {missingAny ? (
                                    <span className="cm-missingMark" title="Нет сопоставления">
                                      !
                                    </span>
                                  ) : null}
                                </div>

                                <div className="cm-mapFieldMeta">
                                  {required ? "Обязательное поле" : "Необязательное поле"}
                                </div>
                              </div>

                              <div className="cm-mapCols">
                                <div>
                                  <div className="cm-colLabel">
                                    Поле конкурента (re:Store)
                                  </div>
                                  {canMapRestore ? (
                                    <SelectBig
                                      value={selectedRestore}
                                      onChange={(e) => setMap("restore", code, e.target.value)}
                                      disabled={mappingDisabledRestore}
                                    >
                                      <option value="">— не выбрано —</option>
                                      {optionsRestore.map((opt) => (
                                        <option key={opt.value} value={opt.value}>
                                          {opt.label}
                                        </option>
                                      ))}
                                    </SelectBig>
                                  ) : (
                                    <SelectBig value="" disabled>
                                      <option value="">— загрузите параметры —</option>
                                    </SelectBig>
                                  )}
                                  {!canMapRestore && fieldsAttemptedBySite.restore && (viewState.links.restore || "").trim() ? (
                                    <div className="cm-help">
                                      {fieldsErrorBySite.restore
                                        ? `Поля не загрузились: ${fieldsErrorBySite.restore}. Возможно, сайт защитил страницу.`
                                        : "Поля не загрузились. Проверьте ссылку или защиту сайта."}
                                    </div>
                                  ) : !canMapRestore && hasRestore ? (
                                    <div className="cm-help">Нажмите “Загрузить параметры”, чтобы увидеть поля конкурента.</div>
                                  ) : null}
                                </div>

                                <div>
                                  <div className="cm-colLabel">
                                    Поле конкурента (Store77)
                                  </div>
                                  {canMapStore ? (
                                    <SelectBig
                                      value={selectedStore}
                                      onChange={(e) => setMap("store77", code, e.target.value)}
                                      disabled={mappingDisabledStore}
                                    >
                                      <option value="">— не выбрано —</option>
                                      {optionsStore.map((opt) => (
                                        <option key={opt.value} value={opt.value}>
                                          {opt.label}
                                        </option>
                                      ))}
                                    </SelectBig>
                                  ) : (
                                    <SelectBig value="" disabled>
                                      <option value="">— загрузите параметры —</option>
                                    </SelectBig>
                                  )}
                                  {!canMapStore && fieldsAttemptedBySite.store77 && (viewState.links.store77 || "").trim() ? (
                                    <div className="cm-help">
                                      {fieldsErrorBySite.store77
                                        ? `Поля не загрузились: ${fieldsErrorBySite.store77}. Возможно, сайт защитил страницу.`
                                        : "Поля не загрузились. Проверьте ссылку или защиту сайта."}
                                    </div>
                                  ) : !canMapStore && hasStore77 ? (
                                    <div className="cm-help">Нажмите “Загрузить параметры”, чтобы увидеть поля конкурента.</div>
                                  ) : null}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
