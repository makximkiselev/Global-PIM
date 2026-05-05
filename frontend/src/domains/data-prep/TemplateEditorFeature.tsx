import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import "../../styles/catalog.css";
import "../../styles/templates.css";
import { api } from "../../lib/api";
import DataToolbar from "../../components/data/DataToolbar";
import Alert from "../../components/ui/Alert";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import EmptyState from "../../components/ui/EmptyState";
import Field from "../../components/ui/Field";
import IconButton from "../../components/ui/IconButton";
import Modal from "../../components/ui/Modal";
import PageHeader from "../../components/ui/PageHeader";
import PageTabs from "../../components/ui/PageTabs";
import TextInput from "../../components/ui/TextInput";
import WorkspaceFrame from "../../components/layout/WorkspaceFrame";
import type { InfoModelCandidate, InfoModelSummary } from "./infoModelDraft";
import { candidateTone, modelStatusLabel } from "./infoModelDraft";

type AttrType = "text" | "number" | "select" | "bool" | "date" | "json";
type ScopeT = "common" | "variant";

type AttrT = {
  id?: string;

  // ✅ связь с глобальным атрибутом (единый параметр на все шаблоны)
  attribute_id?: string;

  name: string;
  code?: string;
  type: AttrType;
  required: boolean;
  scope: ScopeT;
  options?: any;
  position?: number;
  locked?: boolean;

  _codeTouched?: boolean;
};

type TemplateT = { id: string; category_id: string; name: string };
type TemplateMaster = {
  version: number;
  base_attributes: AttrT[];
  category_attributes: AttrT[];
  stats: {
    base_count: number;
    category_count: number;
    required_count: number;
    total_count: number;
  };
  sources?: Record<string, any>;
};

type TemplateSourceInfo = {
  enabled?: boolean;
  mode?: string;
  category_id?: string | null;
  category_name?: string | null;
  params_count?: number;
  required_params_count?: number;
  mapped_rows?: number;
};

type CategoryCrumb = { id: string; name: string };
type CategoryInfo = { id: string; name: string; path: CategoryCrumb[] };

type TreeNodeT = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
  template_id: string | null;
};

type GlobalAttr = {
  id: string;
  title: string;
  code: string;
  type: AttrType;
  dict_id?: string | null;
  scope?: string | null;
};

type DictItem = {
  id: string;
  title: string;
  size?: number;
};

type EditorReferenceResp = {
  ok: boolean;
  dict_items: DictItem[];
  attributes: GlobalAttr[];
};

const TYPE_LABEL: Record<AttrType, string> = {
  text: "Текст",
  number: "Число",
  select: "Список",
  bool: "Да/Нет",
  date: "Дата",
  json: "JSON",
};
const SCOPE_LABEL: Record<ScopeT, string> = {
  common: "Товар",
  variant: "SKU",
};

const TYPE_HELP_TEXT = [
  "Текст — строки (цвет, модель, комментарий).",
  "Число — числовые значения (вес, диагональ) лучше без единиц.",
  "Да/Нет — флаги (NFC, eSIM, MagSafe).",
  "Дата — релиз/поступление/гарантия.",
  "Список — короткие фикс. справочники (лучше наполнять из парсера/словаря).",
  "JSON — редко, для сложных структур.",
].join("\n");

const REQUIRED_HELP_TEXT = "Если параметр отмечен как обязательный — товар без него сохранить нельзя.";
const SOURCE_LABEL: Record<string, string> = {
  products: "Товары PIM",
  existing_products: "Товары PIM",
  marketplaces: "Площадки",
  yandex_market: "Я.Маркет",
  ozon: "Ozon",
  product: "Товарные данные",
  marketplace: "Площадка",
};

const CANDIDATE_STATUS_LABEL: Record<InfoModelCandidate["status"], string> = {
  accepted: "Добавлено",
  needs_review: "На проверке",
  rejected: "Отклонено",
};

type DraftFilter = "all" | InfoModelCandidate["status"];

function normTitle(s: string) {
  return (s || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function slugifyRu(input: string) {
  const map: Record<string, string> = {
    а: "a",
    б: "b",
    в: "v",
    г: "g",
    д: "d",
    е: "e",
    ё: "e",
    ж: "zh",
    з: "z",
    и: "i",
    й: "y",
    к: "k",
    л: "l",
    м: "m",
    н: "n",
    о: "o",
    п: "p",
    р: "r",
    с: "s",
    т: "t",
    у: "u",
    ф: "f",
    х: "h",
    ц: "ts",
    ч: "ch",
    ш: "sh",
    щ: "sch",
    ъ: "",
    ы: "y",
    ь: "",
    э: "e",
    ю: "yu",
    я: "ya",
  };

  const s = (input || "").trim().toLowerCase();
  let out = "";
  for (const ch of s) out += map[ch] ?? ch;

  out = out
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_+/g, "_");

  return out;
}

function sortAttrs(list: AttrT[]) {
  return (list || []).slice().sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
}

function buildPathFromTree(nodes: TreeNodeT[], targetId: string): CategoryCrumb[] {
  const byId = new Map<string, TreeNodeT>();
  for (const n of nodes) byId.set(n.id, n);

  const out: CategoryCrumb[] = [];
  let cur: TreeNodeT | undefined = byId.get(targetId);
  const guard = new Set<string>();

  while (cur && !guard.has(cur.id)) {
    guard.add(cur.id);
    out.push({ id: cur.id, name: cur.name });
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }

  return out.reverse();
}

function normalizeAttrTab(value: string | null): "all" | "base" | "category" {
  return value === "base" || value === "category" ? value : "all";
}

function sourceLabel(value: string) {
  return SOURCE_LABEL[value] || value.replace(/_/g, " ");
}

function typeLabel(value: string) {
  return TYPE_LABEL[value as AttrType] || value || "Текст";
}

function matchQualityLabel(confidence?: number) {
  const percent = Math.round(Math.max(0, Math.min(1, Number(confidence || 0))) * 100);
  if (percent >= 86) return `высокое совпадение ${percent}%`;
  if (percent >= 70) return `среднее совпадение ${percent}%`;
  if (percent > 0) return `низкое совпадение ${percent}%`;
  return "совпадение не рассчитано";
}

function candidateSources(candidate: InfoModelCandidate) {
  return (candidate.sources || [])
    .map((source) => {
      const provider = sourceLabel(source.provider || source.kind || "");
      const field = source.field_name ? ` · ${source.field_name}` : "";
      const count = source.count ? ` · ${source.count} совп.` : "";
      return `${provider}${field}${count}`;
    })
    .filter(Boolean);
}

export default function TemplateEditor() {
  const nav = useNavigate();
  const { categoryId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();

  const [category, setCategory] = useState<CategoryInfo | null>(null);

  const [tpl, setTpl] = useState<TemplateT | null>(null);
  const [ownerTpl, setOwnerTpl] = useState<TemplateT | null>(null);
  const [inheritedFrom, setInheritedFrom] = useState<CategoryCrumb | null>(null);

  const [tplName, setTplName] = useState("");
  const [attrs, setAttrs] = useState<AttrT[]>([]);
  const [master, setMaster] = useState<TemplateMaster | null>(null);
  const [infoModel, setInfoModel] = useState<InfoModelSummary>({ status: "none" });
  const [attrTab, setAttrTabState] = useState<"all" | "base" | "category">(normalizeAttrTab(searchParams.get("tab")));
  const [draftFilter, setDraftFilter] = useState<DraftFilter>("needs_review");
  const [saving, setSaving] = useState(false);
  const [draftBusy, setDraftBusy] = useState(false);

  const [importOpen, setImportOpen] = useState(false);
  const [importTplName, setImportTplName] = useState("");
  const fileRef = useRef<HTMLInputElement | null>(null);

  // drag reorder
  const dragIndex = useRef<number | null>(null);

  // ✅ toast
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<number | null>(null);
  function showToast(msg: string) {
    setToast(msg);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 1400);
  }

  // ✅ suggest
  const [suggestOpenIdx, setSuggestOpenIdx] = useState<number | null>(null);
  const [suggestItems, setSuggestItems] = useState<GlobalAttr[]>([]);
  const [suggestLoading, setSuggestLoading] = useState(false);
  const [dictOpen, setDictOpen] = useState(false);
  const [dictLoading, setDictLoading] = useState(false);
  const [dictItems, setDictItems] = useState<DictItem[]>([]);
  const [dictQuery, setDictQuery] = useState("");
  const [dictTargetIdx, setDictTargetIdx] = useState<number | null>(null);
  const [allAttributes, setAllAttributes] = useState<GlobalAttr[] | null>(null);
  const [selectedAttrIdx, setSelectedAttrIdx] = useState<number | null>(null);
  const [bootstrapLoading, setBootstrapLoading] = useState(true);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);

  useEffect(() => {
    setAttrTabState(normalizeAttrTab(searchParams.get("tab")));
  }, [searchParams]);

  function setAttrTab(nextTab: "all" | "base" | "category") {
    setAttrTabState(nextTab);
    const next = new URLSearchParams(searchParams);
    next.set("tab", nextTab);
    setSearchParams(next, { replace: true });
  }

  // debounce fetch
  const suggestTimer = useRef<number | null>(null);

  const isInherited = !!tpl?.id && !ownerTpl?.id;
  const canEdit = !!ownerTpl?.id;
  const hasAnyTpl = !!tpl?.id;

  const title = isInherited ? "Шаблон категории (наследование)" : "Шаблон категории";

  const suggestMapByIdx = useMemo(() => {
    // текущие подсказки относятся к открытой строке
    return suggestItems;
  }, [suggestItems]);

  async function putAttributes(templateId: string, list: AttrT[]) {
    await api(`/templates/${templateId}/attributes`, {
      method: "PUT",
      body: JSON.stringify({
        attributes: list.map((a, i) => {
          const baseOptions = a.options || {};
          const options = { ...baseOptions, attribute_id: a.attribute_id || baseOptions.attribute_id || null };
          return {
            name: (a.name || "").trim(),
            code: (a.code || "").trim(),
            type: a.type,
            scope: a.scope,
            required: !!a.required,
            options,
            position: i,
          };
        }),
      }),
    });
  }

  async function createTemplateForCategory(catId: string, name: string) {
    return api<{ template: TemplateT }>(`/templates/by-category/${encodeURIComponent(catId)}`, {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  }

  async function loadEditorReference(force = false) {
    if (!force && dictItems.length && allAttributes?.length) {
      return { dictItems, attributes: allAttributes };
    }
    const ref = await api<EditorReferenceResp>(`/templates/editor-reference`);
    const nextDicts = (ref.dict_items || []).slice().sort((a, b) => a.title.localeCompare(b.title, "ru"));
    const nextAttrs = ref.attributes || [];
    setDictItems(nextDicts);
    setAllAttributes(nextAttrs);
    return { dictItems: nextDicts, attributes: nextAttrs };
  }

  async function load() {
    if (!categoryId) return;
    setBootstrapLoading(true);
    setBootstrapError(null);
    try {
      const data = await api<{
        ok: boolean;
        category: CategoryInfo;
        owner_template: TemplateT | null;
        own_template: TemplateT | null;
        inherited_from: CategoryInfo | null;
        attributes: AttrT[];
        master?: TemplateMaster | null;
        info_model?: InfoModelSummary;
      }>(`/templates/editor-bootstrap/${encodeURIComponent(categoryId)}`);

      const nextAttrs = sortAttrs(data.attributes || []).map((a: any) => ({
        ...a,
        attribute_id: a.attribute_id || a?.options?.attribute_id || undefined,
        _codeTouched: !!a.locked,
      }));

      setCategory(data.category);
      setOwnerTpl(data.own_template || null);
      setInheritedFrom(data.inherited_from || null);
      setTpl(data.owner_template || null);
      setTplName(data.owner_template?.name || "");
      setAttrs(nextAttrs);
      setMaster(data.master || null);
      setInfoModel(data.info_model || { status: data.owner_template?.id ? "approved" : "none" });
      setSelectedAttrIdx(nextAttrs.length ? 0 : null);
      setImportTplName("");
    } catch (error) {
      setBootstrapError((error as Error).message || "Не удалось загрузить модель.");
      setCategory(null);
      setOwnerTpl(null);
      setInheritedFrom(null);
      setTpl(null);
      setTplName("");
      setAttrs([]);
      setMaster(null);
      setInfoModel({ status: "none" });
      setSelectedAttrIdx(null);
    } finally {
      setBootstrapLoading(false);
    }
  }

  useEffect(() => {
    load();
    return () => {
      if (toastTimer.current) window.clearTimeout(toastTimer.current);
      if (suggestTimer.current) window.clearTimeout(suggestTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoryId]);

  function addAttr() {
    if (!canEdit) return;
    if (attrTab === "base") return;
    setAttrs((prev) => {
      const next = [
        ...prev,
        {
        name: "",
        code: "",
        type: "text",
        required: false,
        scope: "common",
        options: {},
        position: prev.length,
        _codeTouched: false,
        },
      ];
      setSelectedAttrIdx(next.length - 1);
      return next;
    });
  }

  const visibleAttrRows = useMemo(() => {
    const withIndex = attrs.map((attr, idx) => ({ attr, idx }));
    if (attrTab === "base") {
      return withIndex.filter(({ attr }) => attr?.options?.layer === "base" || attr.locked);
    }
    if (attrTab === "category") {
      return withIndex.filter(({ attr }) => !(attr?.options?.layer === "base" || attr.locked));
    }
    return withIndex;
  }, [attrTab, attrs]);

  const draftCandidates = infoModel.candidates || [];
  const acceptedCandidates = draftCandidates.filter((candidate) => candidate.status === "accepted").length;
  const reviewCandidates = draftCandidates.filter((candidate) => candidate.status === "needs_review").length;
  const rejectedCandidates = draftCandidates.filter((candidate) => candidate.status === "rejected").length;
  const visibleDraftCandidates = useMemo(() => {
    if (draftFilter === "all") return draftCandidates;
    return draftCandidates.filter((candidate) => candidate.status === draftFilter);
  }, [draftCandidates, draftFilter]);

  const sourceCoverage = useMemo(() => {
    const byProvider = new Map<string, { provider: string; fields: number; required: number; examples: number }>();
    for (const candidate of draftCandidates) {
      for (const source of candidate.sources || []) {
        const key = source.provider || source.kind || "source";
        const current = byProvider.get(key) || { provider: key, fields: 0, required: 0, examples: 0 };
        current.fields += 1;
        current.required += candidate.required ? 1 : 0;
        current.examples += source.examples?.length || 0;
        byProvider.set(key, current);
      }
    }
    return Array.from(byProvider.values()).sort((a, b) => b.fields - a.fields);
  }, [draftCandidates]);

  const yandexSource = useMemo<TemplateSourceInfo | null>(() => {
    const row = master?.sources?.yandex_market;
    return row && typeof row === "object" ? (row as TemplateSourceInfo) : null;
  }, [master]);

  async function updateDraftCandidate(candidateId: string, patch: Partial<InfoModelCandidate>) {
    const templateId = ownerTpl?.id || tpl?.id;
    if (!templateId || draftBusy) return;
    setDraftBusy(true);
    try {
      const response = await api<{ info_model: InfoModelSummary; candidate: InfoModelCandidate }>(
        `/info-models/${encodeURIComponent(templateId)}/draft-candidates/${encodeURIComponent(candidateId)}`,
        {
          method: "PATCH",
          body: JSON.stringify(patch),
        }
      );
      setInfoModel(response.info_model || infoModel);
      showToast("Предложение обновлено");
    } finally {
      setDraftBusy(false);
    }
  }

  async function openDictPicker(idx: number) {
    if (!canEdit) return;
    setDictTargetIdx(idx);
    setDictOpen(true);
    setDictQuery("");
    if (dictItems.length) {
      setDictItems((prev) => prev.slice().sort((a, b) => a.title.localeCompare(b.title, "ru")));
      return;
    }
    setDictLoading(true);
    try {
      await loadEditorReference();
    } finally {
      setDictLoading(false);
    }
  }

  async function pickDict(id: string) {
    if (dictTargetIdx == null) return;
    const row = attrs[dictTargetIdx];
    const baseOptions = (row?.options || {}) as any;
    const dictTitle = dictItems.find((d) => d.id === id)?.title || id;

    try {
      let attrsList = allAttributes;
      if (!attrsList) {
        const ref = await loadEditorReference();
        attrsList = ref.attributes || [];
      }

      const matched = (attrsList || []).find((a) => (a.dict_id || "") === id);
      if (matched) {
        bindToGlobalAttr(dictTargetIdx, matched);
        updateAttr(dictTargetIdx, {
          type: matched.type,
          scope: mapAttrScope(matched.scope),
          options: { ...baseOptions, dict_id: id },
        });
        setDictOpen(false);
        return;
      }

      const dictCode = id.startsWith("dict_") ? id.slice(5) : id;
      const created = await api<{ attribute: GlobalAttr }>(`/attributes/ensure`, {
        method: "POST",
        body: JSON.stringify({
          title: dictTitle,
          type: "select",
          code: dictCode,
          scope: "both",
        }),
      });

      if (created?.attribute?.id) {
        bindToGlobalAttr(dictTargetIdx, created.attribute);
        updateAttr(dictTargetIdx, {
          type: created.attribute.type,
          scope: mapAttrScope(created.attribute.scope),
          options: { ...baseOptions, dict_id: created.attribute.dict_id || id },
        });
      }
    } finally {
      setDictOpen(false);
    }
  }

  function updateAttr(idx: number, patch: Partial<AttrT>) {
    if (!canEdit) return;
    setAttrs((prev) => prev.map((x, i) => (i === idx ? { ...x, ...patch } : x)));
  }

  function mapAttrScope(scope?: string | null): ScopeT {
    return scope === "variant" ? "variant" : "common";
  }

  function mapTemplateScopeToAttrScope(scope?: ScopeT | null): string {
    return scope === "variant" ? "variant" : "feature";
  }

  function bindToGlobalAttr(idx: number, ga: GlobalAttr) {
    if (!canEdit) return;
    setAttrs((prev) =>
      prev.map((x, i) => {
        if (i !== idx) return x;
        return {
          ...x,
          attribute_id: ga.id,
          name: ga.title,
          code: ga.code,
          type: ga.type,
          scope: mapAttrScope(ga.scope),
          options: ga.dict_id ? { ...(x.options || {}), dict_id: ga.dict_id } : x.options,
          _codeTouched: true,
        };
      })
    );
    setSuggestOpenIdx(null);
    setSuggestItems([]);
  }

  async function fetchSuggestions(q: string) {
    const qq = (q || "").trim();
    if (!qq) {
      setSuggestItems([]);
      return;
    }

    setSuggestLoading(true);
    try {
      const r = await api<{ items: GlobalAttr[] }>(
        `/attributes/suggest?q=${encodeURIComponent(qq)}&limit=8`
      );
      setSuggestItems(r.items || []);
    } catch {
      // ignore
    } finally {
      setSuggestLoading(false);
    }
  }

  function scheduleSuggest(idx: number, q: string) {
    setSuggestOpenIdx(idx);

    if (suggestTimer.current) window.clearTimeout(suggestTimer.current);
    suggestTimer.current = window.setTimeout(() => {
      fetchSuggestions(q);
    }, 180);
  }

  async function ensureGlobalAndBind(idx: number) {
    if (!canEdit) return;
    const row = attrs[idx];
    if (!row) return;

    const title = (row.name || "").trim();
    if (!title) return;

    // уже привязан
    if (row.attribute_id) return;

    // если есть точное совпадение в текущих подсказках — используем его
    const tn = normTitle(title);
    const exact = (suggestMapByIdx || []).find((x) => normTitle(x.title) === tn);
    if (exact) {
      bindToGlobalAttr(idx, exact);
      return;
    }

    // иначе создаём глобальный атрибут и привязываем
    const created = await api<{ attribute: GlobalAttr }>(`/attributes/ensure`, {
      method: "POST",
      body: JSON.stringify({
        title,
        type: row.type,
        code: (row.code || "").trim() || undefined,
        scope: mapTemplateScopeToAttrScope(row.scope),
      }),
    });

    if (created?.attribute?.id) {
      bindToGlobalAttr(idx, created.attribute);
    }
  }

  function onNameChange(idx: number, name: string) {
    if (!canEdit) return;

    setAttrs((prev) =>
      prev.map((x, i) => {
        if (i !== idx) return x;
        const next: AttrT = {
          ...x,
          name,
          // ✅ если меняем имя — сбрасываем привязку (иначе будет “старый глобальный параметр”)
          attribute_id: undefined,
        };
        if (!next._codeTouched) next.code = slugifyRu(name);
        return next;
      })
    );

    scheduleSuggest(idx, name);
  }

  async function createTemplateIfMissing() {
    if (!categoryId) return;
    if (ownerTpl?.id) return;

    const name = (tplName || "").trim() || "Мастер-шаблон";

    setSaving(true);
    try {
      const created = await createTemplateForCategory(categoryId, name);
      const newTpl = created.template;

      if (newTpl?.id && attrs.length > 0) {
        await putAttributes(newTpl.id, attrs);
      }

      await load();
      showToast("Создано");
    } finally {
      setSaving(false);
    }
  }

  async function collectDraftModel() {
    if (!categoryId || draftBusy) return;
    setDraftBusy(true);
    try {
      const response = await api<{ template: TemplateT; info_model: InfoModelSummary; candidates: InfoModelCandidate[] }>("/info-models/draft-from-sources", {
        method: "POST",
        body: JSON.stringify({ category_id: categoryId, sources: ["products", "marketplaces"] }),
      });
      setOwnerTpl(response.template);
      setTpl(response.template);
      setInfoModel({ ...(response.info_model || { status: "draft" }), candidates: response.candidates || [] });
      showToast("Draft-модель собрана");
      await load();
    } finally {
      setDraftBusy(false);
    }
  }

  async function approveDraftModel() {
    const templateId = ownerTpl?.id || tpl?.id;
    if (!templateId || draftBusy) return;
    setDraftBusy(true);
    try {
      const response = await api<{ info_model: InfoModelSummary; attributes: AttrT[] }>(`/info-models/${encodeURIComponent(templateId)}/approve`, {
        method: "POST",
      });
      setInfoModel(response.info_model || { status: "approved" });
      setAttrs(sortAttrs((response.attributes || []) as AttrT[]));
      showToast("Инфо-модель утверждена");
      await load();
    } finally {
      setDraftBusy(false);
    }
  }

  async function saveAll() {
    if (!ownerTpl?.id) return;

    // 1) чистим
    const prepared = attrs
      .map((a) => {
        const nm = (a.name || "").trim();
        const code = (a.code || "").trim() || slugifyRu(nm);
        return { ...a, name: nm, code };
      })
      .filter((a) => a.name);

    setSaving(true);
    try {
      // 2) ensure global attribute for rows without attribute_id
      let attrsList = allAttributes;
      if (!attrsList) {
        const ref = await loadEditorReference();
        attrsList = ref.attributes || [];
      }
      const attrById = new Map<string, GlobalAttr>();
      for (const it of attrsList || []) {
        if (it?.id) attrById.set(it.id, it);
      }

      const ensured: AttrT[] = [];
      for (let i = 0; i < prepared.length; i++) {
        const row = prepared[i];

        if (row.attribute_id) {
          let dictId = (row.options?.dict_id || "").trim();
          const ga = attrById.get(row.attribute_id);
          if (!dictId && ga?.dict_id) dictId = ga.dict_id;
          if (!dictId) {
            const baseCode = (ga?.code || row.code || slugifyRu(row.name)).trim();
            dictId = `dict_${baseCode}`;
            await api(`/dictionaries/${encodeURIComponent(dictId)}/ensure`, {
              method: "POST",
              body: JSON.stringify({ title: ga?.title || row.name }),
            });
            if (ga?.id) {
              const patched = await api<{ attribute: GlobalAttr }>(`/attributes/${encodeURIComponent(ga.id)}`, {
                method: "PATCH",
                body: JSON.stringify({ dict_id: dictId }),
              });
              if (patched?.attribute) {
                attrById.set(patched.attribute.id, patched.attribute);
              }
            }
          }
          ensured.push({
            ...row,
            options: dictId ? { ...(row.options || {}), dict_id: dictId } : row.options,
          });
          continue;
        }

        let created = await api<{ attribute: GlobalAttr }>(`/attributes/ensure`, {
          method: "POST",
          body: JSON.stringify({
            title: row.name,
            type: row.type,
            code: row.code,
            scope: mapTemplateScopeToAttrScope(row.scope),
          }),
        });

        let ga = created.attribute;
        let dictId = (ga?.dict_id || "").trim();
        if (!dictId) {
          const baseCode = (ga?.code || row.code || slugifyRu(row.name)).trim();
          dictId = `dict_${baseCode}`;
          await api(`/dictionaries/${encodeURIComponent(dictId)}/ensure`, {
            method: "POST",
            body: JSON.stringify({ title: ga?.title || row.name }),
          });
          const patched = await api<{ attribute: GlobalAttr }>(`/attributes/${encodeURIComponent(ga.id)}`, {
            method: "PATCH",
            body: JSON.stringify({ dict_id: dictId }),
          });
          ga = patched.attribute || ga;
        }

        ensured.push({
          ...row,
          attribute_id: ga.id,
          name: ga.title,
          code: ga.code,
          type: ga.type,
          options: dictId ? { ...(row.options || {}), dict_id: dictId } : row.options,
          _codeTouched: true,
        });
      }

      // 3) rename template if needed
      if (tplName.trim() && tplName.trim() !== ownerTpl.name) {
        await api(`/templates/${ownerTpl.id}`, {
          method: "PUT",
          body: JSON.stringify({ name: tplName.trim() }),
        });
      }

      // 4) save
      await putAttributes(ownerTpl.id, ensured);

      await loadEditorReference(true);
      await load();
      showToast("Сохранено");
    } finally {
      setSaving(false);
    }
  }

  async function deleteTemplate() {
    if (!categoryId) return;
    if (!ownerTpl?.id) return;
    setSaving(true);
    try {
      await api(`/templates/${encodeURIComponent(ownerTpl.id)}`, { method: "DELETE" });
      await load();
      showToast("Удалено");
    } finally {
      setSaving(false);
    }
  }

  function move(from: number, to: number) {
    if (!canEdit) return;
    setAttrs((prev) => {
      const next = prev.slice();
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next;
    });
  }

  function downloadXlsx() {
    if (!categoryId) return;
    window.location.href = `/api/templates/by-category/${encodeURIComponent(categoryId)}/export.xlsx`;
  }

  async function uploadXlsx(file: File) {
    if (!categoryId) return;

    const fd = new FormData();
    fd.append("file", file);

    const r = await fetch(`/api/templates/by-category/${encodeURIComponent(categoryId)}/import.xlsx`, {
      method: "POST",
      body: fd,
    });

    if (!r.ok) {
      const t = await r.text();
      alert(t || "Ошибка импорта");
      return;
    }

    const data = await r.json();
    const importedAttrs: AttrT[] = (data.attributes || []).map((a: any) => ({
      ...a,
      _codeTouched: true,
      attribute_id: a.attribute_id || a?.options?.attribute_id || undefined,
    }));
    const excelName: string = (data.template_name || "").trim();

    if (ownerTpl?.id) {
      setAttrs(importedAttrs);
      if (!tplName && excelName) setTplName(excelName);
      setImportOpen(false);
      showToast("Импортировано");
      return;
    }

    const finalName =
      (importTplName || "").trim() ||
      excelName ||
      (category?.name ? `Мастер-шаблон: ${category.name}` : "Мастер-шаблон");

    if (!finalName.trim()) {
      alert("Введите название нового шаблона.");
      return;
    }

    setSaving(true);
    try {
      const created = await createTemplateForCategory(categoryId, finalName.trim());
      const newTpl = created.template;

      if (newTpl?.id) {
        await putAttributes(newTpl.id, importedAttrs);
      }

      setImportOpen(false);
      setImportTplName("");
      await loadEditorReference(true);
      await load();
      showToast("Импортировано");
    } finally {
      setSaving(false);
    }
  }

  const attrTabItems = [
    { key: "all", label: `Все (${attrs.length})` },
    {
      key: "base",
      label: `Основа (${master?.stats?.base_count ?? visibleAttrRows.filter((x) => x.attr?.options?.layer === "base" || x.attr.locked).length})`,
    },
    {
      key: "category",
      label: `Категория (${master?.stats?.category_count ?? visibleAttrRows.filter((x) => !(x.attr?.options?.layer === "base" || x.attr.locked)).length})`,
    },
  ] as const;

  const draftFilterItems = [
    { key: "needs_review", label: `На проверке (${reviewCandidates})` },
    { key: "accepted", label: `В модели (${acceptedCandidates})` },
    { key: "rejected", label: `Не используется (${rejectedCandidates})` },
    { key: "all", label: `Все (${draftCandidates.length})` },
  ] as const;

  const dictFiltered = (() => {
    const query = dictQuery.trim().toLowerCase();
    return (dictItems || []).filter((item) => {
      if (!query) return true;
      return (item.title || "").toLowerCase().includes(query) || (item.id || "").toLowerCase().includes(query);
    });
  })();

  return (
    <div className="templates-page page-shell">
      {toast ? <div className="tpl-toast">{toast}</div> : null}

      <PageHeader
        title="Инфо-модель"
        subtitle={category?.name ? `${category.name}: поля, источники и подготовка к маппингу.` : "Поля, источники и подготовка к маппингу."}
      />

      {hasAnyTpl && inheritedFrom && !ownerTpl?.id ? (
        <Alert>
          Эта категория наследует модель из <b>{inheritedFrom.name}</b>. Чтобы начать отдельную настройку, создай свою модель и продолжай работу уже на ней.
        </Alert>
      ) : null}

      <WorkspaceFrame
        className="templatesEditorFrame templatesEditorFrameFocused"
        main={
          <div className="tplCanvasStack">
            {bootstrapLoading ? (
              <Card className="tplCanvasCard">
                <div className="muted">Загружаю модель и структуру категории…</div>
              </Card>
            ) : bootstrapError ? (
              <Card className="tplCanvasCard">
                <Alert tone="error">{bootstrapError}</Alert>
              </Card>
            ) : !tpl ? (
              <Card className="tplCanvasCard">
                <EmptyState
                  title="Инфо-модель еще не собрана"
                  body="Сначала соберите предложения полей из реальных источников: товаров категории, импортов и подключенных каналов. После проверки модель можно утвердить и использовать в товарах."
                  action={
                    <div className="tplEmptyActions">
                      <Button variant="primary" onClick={collectDraftModel} disabled={!categoryId || draftBusy}>
                        {draftBusy ? "Собираю…" : "Собрать предложения"}
                      </Button>
                      <Button onClick={createTemplateIfMissing} disabled={!categoryId || saving || draftBusy}>
                        Создать вручную
                      </Button>
                      <Button onClick={() => setImportOpen(true)} disabled={!categoryId || saving || draftBusy}>
                        Импортировать Excel
                      </Button>
                    </div>
                  }
                />
              </Card>
            ) : (
              <>
                <Card className="tplCanvasCard tplModelCommandCard">
                  <div className="tplModelCommandTop">
                    <div>
                      <div className="tplSectionEyebrow">Сборка инфо-модели</div>
                      <h2>{category?.name || tplName || tpl.name}</h2>
                      <p>
                        Соберите поля из площадок и товаров, объедините одинаковые параметры, утвердите модель и используйте ее в карточках SKU.
                      </p>
                    </div>
                    <div className="tplModelCommandActions">
                      <Badge tone={infoModel.status === "approved" ? "active" : infoModel.status === "draft" ? "pending" : "neutral"}>
                        {modelStatusLabel(infoModel.status)}
                      </Badge>
                      <Button onClick={saveAll} disabled={!ownerTpl?.id || saving}>
                        {saving ? "Сохраняю…" : "Сохранить"}
                      </Button>
                      <Button onClick={collectDraftModel} disabled={!categoryId || draftBusy}>
                        {draftBusy ? "Собираю…" : "Собрать из источников"}
                      </Button>
                      {infoModel.status === "approved" ? (
                        <Button variant="primary" onClick={() => nav(`/products?parent=${encodeURIComponent(categoryId || "")}`)} disabled={!categoryId}>
                          Перейти к товарам
                        </Button>
                      ) : (
                        <Button
                          variant="primary"
                          onClick={approveDraftModel}
                          disabled={draftBusy || infoModel.status !== "draft" || acceptedCandidates === 0}
                        >
                          Утвердить модель
                        </Button>
                      )}
                    </div>
                  </div>

                  <div className="tplModelStatusBar">
                    <div className="tplModelStatusItem">
                      <span>Найдено полей</span>
                      <strong>{infoModel.status === "approved" ? attrs.length : draftCandidates.length || attrs.length}</strong>
                    </div>
                    <div className="tplModelStatusItem">
                      <span>В модели</span>
                      <strong>{acceptedCandidates}</strong>
                    </div>
                    <div className="tplModelStatusItem is-wide">
                      <span>Источники</span>
                      <strong>
                        {sourceCoverage.length
                          ? sourceCoverage.map((source) => `${sourceLabel(source.provider)} ${source.fields}`).join(" · ")
                          : "не собраны"}
                      </strong>
                    </div>
                  </div>

                  <details className="tplModelMore">
                    <summary>Дополнительные действия</summary>
                    <div className="tplModelMorePanel">
                      <Field label="Название модели" className="templateEditorField tplEditorNameField">
                        <TextInput
                          value={tplName}
                          onChange={(event) => setTplName(event.target.value)}
                          disabled={!ownerTpl?.id}
                          title={!ownerTpl?.id ? "Наследованную модель нельзя переименовать. Сначала создай свою." : ""}
                        />
                      </Field>
                      <div className="tplModelNextActions">
                        <span>Дальше:</span>
                        <button type="button" onClick={() => nav(`/products?parent=${encodeURIComponent(categoryId || "")}`)} disabled={!categoryId}>
                          Товары категории
                        </button>
                        <button type="button" onClick={() => nav(`/sources-mapping?tab=params&category=${encodeURIComponent(categoryId || "")}`)} disabled={!categoryId}>
                          Маппинг полей
                        </button>
                        <button type="button" onClick={() => nav(`/catalog?selected=${encodeURIComponent(categoryId || "")}`)} disabled={!categoryId}>
                          Открыть категорию
                        </button>
                        <button type="button" onClick={() => setImportOpen(true)} disabled={!categoryId || saving}>
                          Импорт / экспорт
                        </button>
                        {ownerTpl?.id ? (
                          <button type="button" className="tplDangerLink" onClick={deleteTemplate} disabled={saving}>
                            Удалить модель
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </details>
                </Card>

                {infoModel.status === "draft" ? (
                  <Card className="tplCanvasCard tplDraftCard">
                    <div className="tplDraftHeader">
                      <div>
                        <div className="tplSectionEyebrow">Предложения полей</div>
                        <h3>Поля из площадок и товаров</h3>
                        <p>
                          Система нашла похожие параметры в источниках. Добавьте полезные поля в модель, а дубли и мусор не используйте.
                        </p>
                        <div className="tplDraftCountersLine">
                          <span>{acceptedCandidates} добавлено в модель</span>
                          <span>{reviewCandidates} на проверке</span>
                          <span>{rejectedCandidates} не используется</span>
                        </div>
                      </div>
                      <details className="tplDraftHelp">
                        <summary>Как читать предложения</summary>
                        <p>
                          Совпадение показывает, насколько уверенно система считает найденный параметр тем же смыслом для PIM. Высокое можно принимать быстрее, среднее и низкое лучше проверить руками.
                        </p>
                      </details>
                    </div>
                    <PageTabs
                      items={draftFilterItems.map((item) => ({ key: item.key, label: item.label }))}
                      activeKey={draftFilter}
                      onChange={(key) => setDraftFilter(key as DraftFilter)}
                    />
                    <div className="tplDraftList">
                      {visibleDraftCandidates.length ? (
                        visibleDraftCandidates.map((candidate) => (
                          <div className={`tplDraftRow is-${candidate.status}`} key={candidate.id}>
                            <div className="tplDraftMain">
                              <strong>{candidate.name}</strong>
                              <span>
                                {candidate.group} · {typeLabel(candidate.type)} · {matchQualityLabel(candidate.confidence)}
                              </span>
                              <div className="tplDraftSources">
                                {candidateSources(candidate).slice(0, 3).map((source) => (
                                  <small key={source}>{source}</small>
                                ))}
                              </div>
                            </div>
                            <div className="tplDraftExamples">{candidate.examples?.slice(0, 3).join(", ") || "Без примеров"}</div>
                            <div className="tplDraftActions">
                              <Badge tone={candidateTone(candidate)}>{CANDIDATE_STATUS_LABEL[candidate.status]}</Badge>
                              {candidate.status !== "accepted" ? (
                                <Button onClick={() => updateDraftCandidate(candidate.id, { status: "accepted" })} disabled={draftBusy}>
                                  Добавить в модель
                                </Button>
                              ) : null}
                              {candidate.status !== "rejected" ? (
                                <Button onClick={() => updateDraftCandidate(candidate.id, { status: "rejected" })} disabled={draftBusy}>
                                  Не использовать
                                </Button>
                              ) : null}
                            </div>
                          </div>
                        ))
                      ) : (
                        <EmptyState
                          title={draftCandidates.length ? "В этом фильтре пусто" : "Источники не дали параметров"}
                          body={
                            draftCandidates.length
                              ? "Переключите фильтр выше, чтобы посмотреть остальные предложения."
                              : "В этой категории пока нет товарных характеристик для автоматической сборки. Можно создать модель вручную или импортировать Excel."
                          }
                          action={
                            draftCandidates.length ? (
                              <Button onClick={() => setDraftFilter("all")}>Показать все</Button>
                            ) : (
                              <Button onClick={createTemplateIfMissing} disabled={!categoryId || saving || draftBusy}>Создать вручную</Button>
                            )
                          }
                        />
                      )}
                    </div>
                  </Card>
                ) : null}

                <Card className="tplCanvasCard tplEditorMainCard">
                  <DataToolbar
                    title="Поля модели"
                    subtitle={`${REQUIRED_HELP_TEXT}${!canEdit ? " Сейчас открыт наследуемый контур — редактирование отключено." : ""}`}
                    actions={
                      <>
                        <PageTabs
                          items={attrTabItems.map((item) => ({ key: item.key, label: item.label }))}
                          activeKey={attrTab}
                          onChange={(key) => setAttrTab(key as "all" | "base" | "category")}
                        />
                        <Badge tone={infoModel.status === "approved" ? "active" : infoModel.status === "draft" ? "pending" : canEdit ? "active" : "pending"}>
                          {modelStatusLabel(infoModel.status)}
                        </Badge>
                        <Button onClick={addAttr} disabled={!canEdit || attrTab === "base"}>
                          Добавить поле вручную
                        </Button>
                      </>
                    }
                  />

                  {yandexSource?.enabled ? (
                    <Card className="tplSectionCard tplEditorSourceCard">
                      <div className="tplSectionHead">
                        <div>
                          <h3>Источник структуры</h3>
                          <p>{yandexSource.category_name || "Категория канала еще не привязана."}</p>
                        </div>
                        <Badge tone="pending">Я.Маркет</Badge>
                      </div>
                      <div className="tplUsageStatsRow">
                        <div className="tplUsageStat">
                          <span>Параметров площадки</span>
                          <strong>{Number(yandexSource.params_count || 0)}</strong>
                        </div>
                        <div className="tplUsageStat">
                          <span>Обязательных</span>
                          <strong>{Number(yandexSource.required_params_count || 0)}</strong>
                        </div>
                        <div className="tplUsageStat">
                          <span>Сопоставлено</span>
                          <strong>{Number(yandexSource.mapped_rows || 0)}</strong>
                        </div>
                      </div>
                    </Card>
                  ) : null}

                  {visibleAttrRows.length === 0 ? (
                    <EmptyState
                      title="Полей пока нет"
                      body="Добавь первое поле модели или загрузи Excel-шаблон. После этого страница превратится в рабочий конструктор структуры."
                      action={canEdit ? <Button onClick={addAttr}>Добавить поле вручную</Button> : undefined}
                    />
                  ) : (
                    <div className="tplAttrBoard">
                      <div className="attr-head">
                        <div />
                        <div className="attr-head-required">
                          <span>Обяз.</span>
                          <span className="help-tip" data-tip={REQUIRED_HELP_TEXT} aria-label="Подсказка: обязательный">
                            ?
                          </span>
                        </div>
                        <div>Название</div>
                        <div className="attr-head-type">
                          <span>Тип данных</span>
                          <span className="help-tip" data-tip={TYPE_HELP_TEXT} aria-label="Подсказка по типам данных">
                            ?
                          </span>
                        </div>
                        <div className="attr-head-scope">
                          <span>Применяемость</span>
                        </div>
                        <div />
                      </div>

                      <div className="tplAttrRows">
                        {visibleAttrRows.map(({ attr: attr, idx }) => (
                          <div
                            key={attr.id || `row-${idx}`}
                            className={`card attr-card${selectedAttrIdx === idx ? " is-selected" : ""}`}
                            draggable={canEdit && attrTab === "all"}
                            onClick={() => setSelectedAttrIdx(idx)}
                            onDragStart={() => {
                              if (!canEdit || attrTab !== "all") return;
                              dragIndex.current = idx;
                            }}
                            onDragOver={(event) => {
                              if (!canEdit || attrTab !== "all") return;
                              event.preventDefault();
                            }}
                            onDrop={() => {
                              if (!canEdit || attrTab !== "all") return;
                              const from = dragIndex.current;
                              const to = idx;
                              if (from == null || from === to) return;
                              move(from, to);
                              dragIndex.current = null;
                              setSelectedAttrIdx(to);
                            }}
                          >
                            <div className="attr-row">
                              <span className="attr-drag" title={canEdit && attrTab === "all" ? "Перетащить" : ""} aria-label="Перетащить">
                                ☰
                              </span>

                              <label
                                className="attr-required"
                                title={attr.locked ? "Системный параметр нельзя менять" : REQUIRED_HELP_TEXT}
                                aria-label="Обязательный параметр"
                              >
                                <input
                                  type="checkbox"
                                  checked={!!attr.required}
                                  onChange={(event) => updateAttr(idx, { required: event.target.checked })}
                                  disabled={!canEdit || attr.locked}
                                />
                              </label>

                              <div className="attr-name-cell">
                                <div className="attr-name-input">
                                  <input
                                    className={`attr-name ${attr.required ? "is-required" : ""}`}
                                    value={attr.name}
                                    onChange={(event) => onNameChange(idx, event.target.value)}
                                    onFocus={() => {
                                      if (!canEdit || attr.locked) return;
                                      setSelectedAttrIdx(idx);
                                      setSuggestOpenIdx(idx);
                                      scheduleSuggest(idx, attr.name);
                                    }}
                                    onBlur={() => {
                                      window.setTimeout(() => {
                                        setSuggestOpenIdx((current) => (current === idx ? null : current));
                                      }, 140);
                                    }}
                                    placeholder="Название поля"
                                    disabled={!canEdit || attr.locked}
                                  />

                                  {canEdit &&
                                  suggestOpenIdx === idx &&
                                  (suggestLoading || suggestItems.length > 0 || (attr.name || "").trim().length > 0) ? (
                                    <div className="tplSuggestList" onMouseDown={(event) => event.preventDefault()}>
                                      {suggestLoading ? (
                                        <div className="tplSuggestHint">Ищу совпадения…</div>
                                      ) : null}

                                      {!suggestLoading && suggestItems.length === 0 && (attr.name || "").trim() ? (
                                        <div className="tplSuggestHint">Совпадений нет. Новый глобальный атрибут создастся при сохранении.</div>
                                      ) : null}

                                      {!suggestLoading
                                        ? suggestItems.map((item, itemIndex) => (
                                            <button
                                              key={item.id}
                                              type="button"
                                              className="tplSuggestItem"
                                              onClick={() => bindToGlobalAttr(idx, item)}
                                            >
                                              <span>{item.title}</span>
                                              <small>{TYPE_LABEL[item.type]}</small>
                                            </button>
                                          ))
                                        : null}
                                    </div>
                                  ) : null}
                                </div>
                                <button
                                  className="btn sm attr-name-pick"
                                  type="button"
                                  onClick={() => openDictPicker(idx)}
                                  disabled={!canEdit || attr.locked}
                                  title="Выбрать словарь"
                                >
                                  Словарь
                                </button>
                              </div>

                              <select
                                value={attr.type}
                                onChange={(event) => updateAttr(idx, { type: event.target.value as AttrType, attribute_id: undefined })}
                                disabled
                                title={
                                  attr.locked
                                    ? "Системный параметр нельзя менять"
                                    : attr.attribute_id
                                      ? "Тип фиксируется глобальным атрибутом."
                                      : ""
                                }
                              >
                                {Object.entries(TYPE_LABEL).map(([key, label]) => (
                                  <option key={key} value={key}>
                                    {label}
                                  </option>
                                ))}
                              </select>

                              <div className="tplAttrScope">{SCOPE_LABEL[attr.scope]}</div>

                              <IconButton
                                tone="danger"
                                type="button"
                                title={
                                  attr.locked
                                    ? "Системное поле нельзя удалить"
                                    : canEdit
                                      ? "Удалить поле"
                                      : "Нельзя удалить поле в наследуемой модели"
                                }
                                onClick={() => {
                                  if (!canEdit || attr.locked) return;
                                  setAttrs((prev) => prev.filter((_, rowIndex) => rowIndex !== idx));
                                  setSelectedAttrIdx((current) => (current === idx ? null : current != null && current > idx ? current - 1 : current));
                                }}
                                disabled={!canEdit || attr.locked}
                              >
                                ×
                              </IconButton>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </Card>
              </>
            )}
          </div>
        }
      />

      <Modal
        open={importOpen}
        onClose={() => !saving && setImportOpen(false)}
        title="Импорт / экспорт"
        subtitle="Скачай Excel-шаблон, заполни модель и загрузи файл обратно."
      >
        {!ownerTpl?.id ? (
          <Field
            label="Название новой модели"
            className="templateEditorField"
            hint="Если модели еще нет, импорт создаст ее автоматически."
          >
            <TextInput
              value={importTplName}
              onChange={(event) => setImportTplName(event.target.value)}
              placeholder={category?.name ? `Например: ${category.name}` : "Например: Смартфоны"}
              disabled={saving}
            />
          </Field>
        ) : null}

        <div className="modal-actions">
          <Button onClick={downloadXlsx} disabled={saving}>
            Скачать шаблон (.xlsx)
          </Button>

          <input
            ref={fileRef}
            type="file"
            accept=".xlsx"
            style={{ display: "none" }}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void uploadXlsx(file);
              if (fileRef.current) fileRef.current.value = "";
            }}
          />

          <Button variant="primary" onClick={() => fileRef.current?.click()} disabled={saving}>
            {saving ? "Импортирую…" : "Загрузить файл"}
          </Button>
        </div>
      </Modal>

      <Modal
        open={dictOpen}
        onClose={() => setDictOpen(false)}
        title="Выбор словаря"
        subtitle="Подбери словарь для поля типа «Список»."
      >
        <Field label="Поиск" className="templateEditorField">
          <TextInput value={dictQuery} onChange={(event) => setDictQuery(event.target.value)} placeholder="Название или id словаря…" />
        </Field>

        <div className="tplDictList">
          {dictLoading ? (
            <div className="tplDictHint muted">Загрузка…</div>
          ) : dictFiltered.length === 0 ? (
            <div className="tplDictHint muted">Словари не найдены.</div>
          ) : (
            dictFiltered.map((item) => (
              <button key={item.id} type="button" className="tplDictItem" onClick={() => pickDict(item.id)}>
                <span>{item.title || item.id}</span>
                <small>{item.size != null ? `${item.size} знач.` : item.id}</small>
              </button>
            ))
          )}
        </div>
      </Modal>
    </div>
  );
}
 
