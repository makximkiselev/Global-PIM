import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import "../styles/catalog.css";
import "../styles/templates.css";
import { api } from "../lib/api";

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
  const [attrTab, setAttrTabState] = useState<"all" | "base" | "category">(normalizeAttrTab(searchParams.get("tab")));
  const [saving, setSaving] = useState(false);

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

  async function load() {
    if (!categoryId) return;
    const data = await api<{
      ok: boolean;
      category: CategoryInfo;
      owner_template: TemplateT | null;
      own_template: TemplateT | null;
      inherited_from: CategoryInfo | null;
      attributes: AttrT[];
      master?: TemplateMaster | null;
    }>(`/templates/editor-bootstrap/${encodeURIComponent(categoryId)}`);

    setCategory(data.category);
    setOwnerTpl(data.own_template || null);
    setInheritedFrom(data.inherited_from || null);
    setTpl(data.owner_template || null);
    setTplName(data.owner_template?.name || "");
    setAttrs(
      sortAttrs(data.attributes || []).map((a: any) => ({
        ...a,
        attribute_id: a.attribute_id || a?.options?.attribute_id || undefined,
        _codeTouched: !!a.locked,
      }))
    );
    setMaster(data.master || null);
    setImportTplName("");
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
    setAttrs((prev) => [
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
    ]);
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

  const yandexSource = useMemo<TemplateSourceInfo | null>(() => {
    const row = master?.sources?.yandex_market;
    return row && typeof row === "object" ? (row as TemplateSourceInfo) : null;
  }, [master]);
  const templateStatus = useMemo(() => {
    if (!master) return "";
    const confirmed = Number(master.stats?.confirmed_count || 0);
    const rows = Number(master.stats?.row_count || 0);
    if (rows > 0 && confirmed >= rows) return "ready";
    if (confirmed > 0) return "in_progress";
    return "draft";
  }, [master]);

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
      const r = await api<{ items: DictItem[] }>("/dictionaries");
      const items = (r.items || []).slice().sort((a, b) => a.title.localeCompare(b.title, "ru"));
      setDictItems(items);
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
        const r = await api<{ items: GlobalAttr[] }>("/attributes?limit=2000");
        attrsList = r.items || [];
        setAllAttributes(attrsList);
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
        const r = await api<{ items: GlobalAttr[] }>("/attributes?limit=2000");
        attrsList = r.items || [];
        setAllAttributes(attrsList);
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
      await load();
      showToast("Импортировано");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="templates-page page-shell">
      {/* ✅ toast */}
      {toast && <div className="tpl-toast">{toast}</div>}

      <div className="page-header">
        <div className="page-header-main">
          <div className="page-title">{title}</div>
          <div className="page-subtitle">Редактирование мастер-параметров.</div>
          {hasAnyTpl ? (
            <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
              <span className={`tpl-pill ${templateStatus === "ready" ? "is-own" : templateStatus === "in_progress" ? "is-inherit" : ""}`}>
                {templateStatus === "ready" ? "Готов" : templateStatus === "in_progress" ? "В работе" : "Черновик"}
              </span>
              {master?.stats ? (
                <span className="tpl-pill">
                  Подтверждено {Number(master.stats.confirmed_count || 0)} / {Number(master.stats.row_count || 0)}
                </span>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="page-header-actions">
          <button className="btn" type="button" onClick={() => nav("/templates")}>
            ← К категориям
          </button>

          <button className="btn" type="button" onClick={() => setImportOpen(true)} disabled={!categoryId || saving}>
            Импорт
          </button>

          <button
            className="btn"
            type="button"
            onClick={createTemplateIfMissing}
            disabled={!categoryId || !!ownerTpl?.id || saving}
            title={ownerTpl?.id ? "Шаблон уже создан" : "Создать мастер-шаблон для этой категории"}
          >
            + Шаблон
          </button>

          <button className="btn danger" type="button" onClick={deleteTemplate} disabled={!ownerTpl?.id || saving}>
            Удалить
          </button>

          <button className="btn primary" type="button" onClick={saveAll} disabled={!ownerTpl?.id || saving}>
            {saving ? "Сохраняю…" : "Сохранить"}
          </button>
        </div>
      </div>

      {/* ===== BREADCRUMBS ===== */}
      {category && (
        <div
          className="tpl-breadcrumbs"
          style={{
            marginBottom: 14,
            display: "flex",
            flexWrap: "wrap",
            gap: 6,
            fontSize: 13,
            color: "var(--muted)",
            alignItems: "center",
          }}
        >
          <span style={{ cursor: "pointer", color: "var(--brand)", fontWeight: 800 }} onClick={() => nav("/templates")}>
            Мастер-шаблоны
          </span>

          {category.path.map((c, i) => {
            const isLast = i === category.path.length - 1;
            return (
              <span key={c.id} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span>→</span>
                <span
                  style={{
                    cursor: isLast ? "default" : "pointer",
                    color: isLast ? "var(--text)" : "var(--brand)",
                    fontWeight: isLast ? 900 : 800,
                  }}
                  onClick={() => {
                    if (isLast) return;
                    nav(`/templates/${c.id}`);
                  }}
                >
                  {c.name}
                </span>
              </span>
            );
          })}
        </div>
      )}

      {hasAnyTpl && inheritedFrom && !ownerTpl?.id && (
        <div className="card" style={{ marginBottom: 14, borderStyle: "dashed" }}>
          <div style={{ fontWeight: 1000, marginBottom: 6 }}>Шаблон наследуется</div>
          <div className="muted" style={{ lineHeight: 1.45 }}>
            Эта категория не имеет своего мастер-шаблона. Используется шаблон из: <b>{inheritedFrom.name}</b>.
            <br />
            Чтобы сделать отдельный шаблон — нажмите <b>“+ Шаблон”</b> (атрибуты будут скопированы).
          </div>
        </div>
      )}

      {!tpl ? (
        <div className="card">
          <div className="muted">
            Для этой категории и её родителей ещё нет мастер-шаблона. Нажми <b>“+ Шаблон”</b> или сделай импорт.
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="field" style={{ marginBottom: 12 }}>
            <div className="field-label">Название шаблона</div>
            <input
              value={tplName}
              onChange={(e) => setTplName(e.target.value)}
              style={{ width: "100%" }}
              disabled={!ownerTpl?.id}
              title={!ownerTpl?.id ? "Наследованный шаблон нельзя переименовывать. Создайте свой шаблон." : ""}
            />
          </div>

          <div className="card-head" style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div className="card-title" style={{ marginBottom: 0 }}>
                Параметры
              </div>
              <div className="muted">
                {REQUIRED_HELP_TEXT}
                {!canEdit ? " (Сейчас открыт наследованный шаблон — редактирование отключено.)" : ""}
              </div>
            </div>

            <button className="btn" type="button" onClick={addAttr} disabled={!canEdit || attrTab === "base"}>
              + Добавить параметр
            </button>
          </div>

          <div className="mm-tabs" style={{ marginBottom: 12 }}>
            <button type="button" className={`mm-tab ${attrTab === "all" ? "active" : ""}`} onClick={() => setAttrTab("all")}>
              Все
              <span className="mm-tabCount">{attrs.length}</span>
            </button>
            <button type="button" className={`mm-tab ${attrTab === "base" ? "active" : ""}`} onClick={() => setAttrTab("base")}>
              Основа товара
              <span className="mm-tabCount">{master?.stats?.base_count ?? visibleAttrRows.filter((x) => x.attr?.options?.layer === "base" || x.attr.locked).length}</span>
            </button>
            <button type="button" className={`mm-tab ${attrTab === "category" ? "active" : ""}`} onClick={() => setAttrTab("category")}>
              Параметры категории
              <span className="mm-tabCount">{master?.stats?.category_count ?? visibleAttrRows.filter((x) => !(x.attr?.options?.layer === "base" || x.attr.locked)).length}</span>
            </button>
          </div>

          {master?.stats ? (
            <div className="stats-grid" style={{ marginBottom: yandexSource?.enabled ? 10 : 14 }}>
              <div className="tile">
                <div className="muted">Основа товара</div>
                <div className="num">{master.stats.base_count}</div>
              </div>
              <div className="tile">
                <div className="muted">Параметры категории</div>
                <div className="num">{master.stats.category_count}</div>
              </div>
              <div className="tile">
                <div className="muted">Обязательные</div>
                <div className="num">{master.stats.required_count}</div>
              </div>
            </div>
          ) : null}

          {yandexSource?.enabled ? (
            <div
              className="card"
              style={{
                marginBottom: 14,
                padding: 14,
                borderStyle: "dashed",
                background: "rgba(255,255,255,.78)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                <div>
                  <div style={{ fontWeight: 900, marginBottom: 4 }}>Источник структуры: Я.Маркет</div>
                  <div className="muted" style={{ lineHeight: 1.45 }}>
                    {yandexSource.category_name || "Категория не привязана"}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
                  <div>
                    <div className="muted">Параметров площадки</div>
                    <div style={{ fontWeight: 900, fontSize: 18 }}>{Number(yandexSource.params_count || 0)}</div>
                  </div>
                  <div>
                    <div className="muted">Обязательных</div>
                    <div style={{ fontWeight: 900, fontSize: 18 }}>{Number(yandexSource.required_params_count || 0)}</div>
                  </div>
                  <div>
                    <div className="muted">Сопоставлено</div>
                    <div style={{ fontWeight: 900, fontSize: 18 }}>{Number(yandexSource.mapped_rows || 0)}</div>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          {visibleAttrRows.length === 0 ? (
            <div className="muted">Пока нет параметров. Добавь первый.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
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

              {visibleAttrRows.map(({ attr: a, idx }) => (
                <div
                  key={a.id || `row-${idx}`}
                  className="card attr-card"
                  draggable={canEdit && attrTab === "all"}
                  onDragStart={() => {
                    if (!canEdit || attrTab !== "all") return;
                    dragIndex.current = idx;
                  }}
                  onDragOver={(e) => {
                    if (!canEdit || attrTab !== "all") return;
                    e.preventDefault();
                  }}
                  onDrop={() => {
                    if (!canEdit || attrTab !== "all") return;
                    const from = dragIndex.current;
                    const to = idx;
                    if (from === null || from === to) return;
                    move(from, to);
                    dragIndex.current = null;
                  }}
                >
                  <div className="attr-row">
                    <span className="attr-drag" title={canEdit && attrTab === "all" ? "Перетащить" : ""} aria-label="Перетащить">
                      ☰
                    </span>

                    <label
                      className="attr-required"
                      title={a.locked ? "Системный параметр нельзя менять" : REQUIRED_HELP_TEXT}
                      aria-label="Обязательный параметр"
                    >
                      <input
                        type="checkbox"
                        checked={!!a.required}
                        onChange={(e) => updateAttr(idx, { required: e.target.checked })}
                        disabled={!canEdit || a.locked}
                      />
                    </label>

                    {/* ✅ Name + suggestions */}
                    <div className="attr-name-cell">
                      <div className="attr-name-input">
                        <input
                          className={`attr-name ${a.required ? "is-required" : ""}`}
                          value={a.name}
                          onChange={(e) => onNameChange(idx, e.target.value)}
                        onFocus={() => {
                          if (!canEdit) return;
                          if (a.locked) return;
                          setSuggestOpenIdx(idx);
                          scheduleSuggest(idx, a.name);
                        }}
                          onBlur={() => {
                            // даём кликнуть по подсказке
                            window.setTimeout(() => {
                              setSuggestOpenIdx((cur) => (cur === idx ? null : cur));
                            }, 140);

                            // ✅ если ушли с поля и совпадений нет — создадим при сохранении.
                            // Если хочешь создавать сразу — раскомментируй:
                            // ensureGlobalAndBind(idx);
                          }}
                          placeholder="Название (например: Встроенная память)"
                        disabled={!canEdit || a.locked}
                      />

                        {canEdit &&
                          suggestOpenIdx === idx &&
                          (suggestLoading || suggestItems.length > 0 || (a.name || "").trim().length > 0) && (
                            <div
                              style={{
                                position: "absolute",
                                left: 0,
                                right: 0,
                                top: "calc(100% + 6px)",
                                zIndex: 300,
                                background: "var(--card)",
                                border: "1px solid var(--line)",
                                borderRadius: 12,
                                boxShadow: "0 16px 40px rgba(17,24,39,.12)",
                                overflow: "hidden",
                              }}
                              onMouseDown={(e) => e.preventDefault()} // ✅ чтобы blur не убил клик
                            >
                              {suggestLoading && (
                                <div style={{ padding: 10, fontSize: 12, color: "var(--muted)" }}>
                                  Ищу совпадения…
                                </div>
                              )}

                              {!suggestLoading && suggestItems.length === 0 && (a.name || "").trim() && (
                                <div style={{ padding: 10, fontSize: 12, color: "var(--muted)" }}>
                                  Совпадений нет — будет создан новый параметр при сохранении.
                                </div>
                              )}

                              {!suggestLoading &&
                                suggestItems.map((s, si) => (
                                  <button
                                    key={s.id}
                                    type="button"
                                    className="btn"
                                    style={{
                                      width: "100%",
                                      justifyContent: "space-between",
                                      borderRadius: 0,
                                      border: "none",
                                      borderBottom: si === suggestItems.length - 1 ? "none" : "1px solid var(--line)",
                                      background: "transparent",
                                      padding: "10px 12px",
                                      display: "flex",
                                      gap: 10,
                                      alignItems: "center",
                                    }}
                                    onClick={() => bindToGlobalAttr(idx, s)}
                                    title="Использовать существующий параметр"
                                  >
                                    <span
                                      style={{
                                        fontWeight: 900,
                                        overflow: "hidden",
                                        textOverflow: "ellipsis",
                                        whiteSpace: "nowrap",
                                      }}
                                    >
                                      {s.title}
                                    </span>
                                    <span style={{ fontSize: 12, color: "var(--muted)", flex: "0 0 auto" }}>
                                      {TYPE_LABEL[s.type]}
                                    </span>
                                  </button>
                                ))}
                            </div>
                          )}
                      </div>
                      <button
                        className="btn sm attr-name-pick"
                        type="button"
                        onClick={() => openDictPicker(idx)}
                        disabled={!canEdit || a.locked}
                        title="Выбрать словарь"
                      >
                        Выбрать
                      </button>
                    </div>

                    <select
                      value={a.type}
                      onChange={(e) => updateAttr(idx, { type: e.target.value as AttrType, attribute_id: undefined })}
                      disabled
                      title={
                        a.locked
                          ? "Системный параметр нельзя менять"
                          : a.attribute_id
                          ? "Тип фиксируется глобальным параметром. Измени название или отвяжи."
                          : ""
                      }
                    >
                      {Object.entries(TYPE_LABEL).map(([k, label]) => (
                        <option key={k} value={k}>
                          {label}
                        </option>
                      ))}
                    </select>

                    <div style={{ fontWeight: 700 }}>{SCOPE_LABEL[a.scope]}</div>

                    <button
                      className="icon-btn danger"
                      type="button"
                      title={
                        a.locked
                          ? "Этот параметр является системным и не может быть удален"
                          : canEdit
                          ? "Удалить параметр"
                          : "Нельзя удалить параметр в наследованном шаблоне"
                      }
                      onClick={() => {
                        if (!canEdit || a.locked) return;
                        setAttrs((p) => p.filter((_, i) => i !== idx));
                      }}
                      disabled={!canEdit || a.locked}
                      style={{
                        opacity: !canEdit || a.locked ? 0.6 : 1,
                        cursor: !canEdit || a.locked ? "not-allowed" : "pointer",
                      }}
                    >
                      🗑
                    </button>
                  </div>
                </div>
              ))}

              <div style={{ display: "flex", justifyContent: "flex-start" }}>
                <button className="btn" type="button" onClick={addAttr} disabled={!canEdit}>
                  + Добавить параметр
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="page-actions" style={{ marginTop: 16 }}>
        <button className="btn primary" type="button" onClick={saveAll} disabled={!ownerTpl?.id || saving}>
          {saving ? "Сохраняю…" : "Сохранить"}
        </button>
      </div>

      {importOpen && (
        <div className="modal-backdrop" onClick={() => !saving && setImportOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">Импорт / экспорт</div>
            <div className="modal-sub">
              Скачайте Excel-шаблон, заполните параметры и загрузите файл обратно — данные появятся в интерфейсе.
            </div>

            {!ownerTpl?.id && (
              <div className="field" style={{ marginTop: 12 }}>
                <div className="field-label">Название нового шаблона</div>
                <input
                  value={importTplName}
                  onChange={(e) => setImportTplName(e.target.value)}
                  placeholder={category?.name ? `Например: ${category.name}` : "Например: Смартфоны"}
                  style={{ width: "100%" }}
                  disabled={saving}
                />
                <div className="muted" style={{ marginTop: 6, lineHeight: 1.4 }}>
                  Шаблона ещё нет — при импорте мы автоматически создадим его и применим параметры из Excel.
                </div>
              </div>
            )}

            <div className="modal-actions">
              <button className="btn" type="button" onClick={downloadXlsx} disabled={saving}>
                Скачать шаблон (.xlsx)
              </button>

              <input
                ref={fileRef}
                type="file"
                accept=".xlsx"
                style={{ display: "none" }}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) uploadXlsx(f);
                  if (fileRef.current) fileRef.current.value = "";
                }}
              />

              <button className="btn primary" type="button" onClick={() => fileRef.current?.click()} disabled={saving}>
                {saving ? "Импортирую…" : "Загрузить файл"}
              </button>

              <button className="btn" type="button" onClick={() => setImportOpen(false)} disabled={saving}>
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}

      {dictOpen && (
        <div className="modal-backdrop" onClick={() => setDictOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">Выбор словаря</div>
            <div className="modal-sub">Выберите словарь для параметра типа “Список”.</div>

            <div className="field" style={{ marginTop: 12 }}>
              <div className="field-label">Поиск</div>
              <input
                value={dictQuery}
                onChange={(e) => setDictQuery(e.target.value)}
                placeholder="Название или id словаря…"
                style={{ width: "100%" }}
              />
            </div>

            <div
              style={{
                marginTop: 12,
                border: "1px solid var(--line)",
                borderRadius: 12,
                maxHeight: 320,
                overflow: "auto",
              }}
            >
              {dictLoading ? (
                <div style={{ padding: 12 }} className="muted">
                  Загрузка…
                </div>
              ) : (
                (() => {
                  const q = dictQuery.trim().toLowerCase();
                  const filtered = (dictItems || []).filter((d) => {
                    if (!q) return true;
                    return (d.title || "").toLowerCase().includes(q) || (d.id || "").toLowerCase().includes(q);
                  });
                  if (filtered.length === 0) {
                    return (
                      <div style={{ padding: 12 }} className="muted">
                        Параметры не найдены.
                      </div>
                    );
                  }
                  return filtered.map((d) => (
                    <button
                      key={d.id}
                      type="button"
                      className="btn"
                      style={{
                        width: "100%",
                        justifyContent: "space-between",
                        borderRadius: 0,
                        border: "none",
                        borderBottom: "1px solid var(--line)",
                        background: "transparent",
                        padding: "10px 12px",
                        display: "flex",
                        gap: 10,
                        alignItems: "center",
                      }}
                      onClick={() => pickDict(d.id)}
                    >
                      <span style={{ fontWeight: 900, textAlign: "left" }}>{d.title || d.id}</span>
                      <span style={{ fontSize: 12, color: "var(--muted)" }}>
                        {d.size != null ? `${d.size} знач.` : d.id}
                      </span>
                    </button>
                  ));
                })()
              )}
            </div>

            <div className="modal-actions" style={{ marginTop: 14 }}>
              <button className="btn" type="button" onClick={() => setDictOpen(false)}>
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
 
