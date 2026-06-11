import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { createPortal } from "react-dom";
import { useOrgPath } from "../../app/orgRoutes";
import "../../styles/product-new.css";

function apiBase() {
  return "/api";
}

const API_TEMPLATES_BY_CATEGORY = `${apiBase()}/templates/by-category`;
const API_TEMPLATE_GET = `${apiBase()}/templates`;
const API_ALLOCATE_SKUS = `${apiBase()}/products/allocate-skus`;
const API_PRODUCT_CREATE_FAMILY = `${apiBase()}/products/create-family`;
const API_DICT_GET = (dictId: string) => `${apiBase()}/dictionaries/${encodeURIComponent(dictId)}`;
const API_DICT_ENSURE_VALUE = (dictId: string) =>
  `${apiBase()}/dictionaries/${encodeURIComponent(dictId)}/values/ensure`;

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  const text = await r.text();
  const data = text ? JSON.parse(text) : null;
  if (!r.ok) {
    const detail = data?.detail || data?.message || `HTTP_${r.status}`;
    throw new Error(String(detail));
  }
  return data as T;
}

async function postJson<T>(url: string, body: any): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const text = await r.text();
  const data = text ? JSON.parse(text) : null;

  if (!r.ok) {
    const detail = data?.detail || data?.message || `HTTP_${r.status}`;
    throw new Error(String(detail));
  }
  return data as T;
}

// ===== catalog

type CatalogNodeFlat = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
  template_id?: string | null;
};

type ProductNewBootstrapResp = {
  ok: boolean;
  catalog_nodes: CatalogNodeFlat[];
  template_tree: TemplateTreeNode[];
  attributes: AttributeItem[];
  dictionaries: DictionaryListItem[];
};

type TemplateTreeNode = {
  id: string;
  parent_id: string | null;
  template_id?: string | null;
};

type CatalogNodeTree = CatalogNodeFlat & { children: CatalogNodeTree[] };

function buildTree(nodes: CatalogNodeFlat[]): CatalogNodeTree[] {
  const byId = new Map<string, CatalogNodeTree>();
  for (const n of nodes) byId.set(n.id, { ...n, children: [] });

  const roots: CatalogNodeTree[] = [];
  for (const n of nodes) {
    const cur = byId.get(n.id)!;
    const pid = n.parent_id;
    if (!pid) roots.push(cur);
    else {
      const parent = byId.get(pid);
      if (parent) parent.children.push(cur);
      else roots.push(cur);
    }
  }

  const sortRec = (arr: CatalogNodeTree[]) => {
    arr.sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
    for (const x of arr) sortRec(x.children);
  };
  sortRec(roots);
  return roots;
}

function indexTree(roots: CatalogNodeTree[]) {
  const map = new Map<string, CatalogNodeTree>();
  const walk = (n: CatalogNodeTree) => {
    map.set(n.id, n);
    for (const c of n.children || []) walk(c);
  };
  for (const r of roots) walk(r);
  return map;
}

function buildPathString(byId: Map<string, CatalogNodeFlat>, id: string): string {
  const chain: string[] = [];
  let cur = byId.get(id);
  const guard = new Set<string>();
  while (cur) {
    if (guard.has(cur.id)) break;
    guard.add(cur.id);
    chain.push(cur.name);
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }
  return chain.reverse().join(" / ");
}

function isLeaf(node: CatalogNodeTree) {
  return !(node.children && node.children.length);
}

function normStr(s: string) {
  return (s || "").trim().replace(/\s+/g, " ");
}

function uniqTrim(arr: string[]) {
  const out: string[] = [];
  const set = new Set<string>();
  for (const raw of arr || []) {
    const v = normStr(raw);
    if (!v) continue;
    const k = v.toLowerCase();
    if (set.has(k)) continue;
    set.add(k);
    out.push(v);
  }
  return out;
}

function _normKey(v: string) {
  return normStr(v).toLowerCase();
}

const VARIANT_AXIS_PATTERNS = [
  /название цвета/,
  /^цвет$/,
  /встроенн.*пам/,
  /оперативн.*пам/,
  /конфигурац.*пам/,
  /sim|сим|количество sim|сим-карт/i,
  /(?:^|\s)размер(?:\s|$)|диагонал/i,
];

const VARIANT_AXIS_PRIORITY = [
  /название цвета/,
  /^цвет$/,
  /встроенн.*пам/,
  /оперативн.*пам/,
  /количество sim|sim-карт|sim|сим/i,
  /конфигурац.*пам/,
  /(?:^|\s)размер(?:\s|$)|диагонал/i,
];

const VARIANT_AXIS_DENY_PATTERNS = [
  /^sku\b/i,
  /\bsku\b/i,
  /артикул/,
  /штрих.?код/,
  /barcode/,
  /разрешени.*видео/,
  /разрешени.*съем/,
  /разрешени.*съём/,
];

function variantAxisLabelKey(value: string) {
  return _normKey(value).replace(/ё/g, "е");
}

function isVariantAxisCandidate(title: string, code: string, scope?: string | null) {
  const scopeKey = _normKey(scope || "");
  const text = variantAxisLabelKey(`${title} ${code}`);
  if (VARIANT_AXIS_DENY_PATTERNS.some((pattern) => pattern.test(text))) return false;
  return scopeKey === "variant" || scopeKey === "both" || VARIANT_AXIS_PATTERNS.some((pattern) => pattern.test(text));
}

function variantAxisRank(title: string, code: string) {
  const text = variantAxisLabelKey(`${title} ${code}`);
  const index = VARIANT_AXIS_PRIORITY.findIndex((pattern) => pattern.test(text));
  return index === -1 ? 999 : index;
}

// ===== modals

function CategoryModal(props: {
  open: boolean;
  title?: string;
  roots: CatalogNodeTree[];
  treeById: Map<string, CatalogNodeTree>;
  flatById: Map<string, CatalogNodeFlat>;
  selectedId: string;
  onPickLeaf: (node: CatalogNodeTree) => void;
  onClose: () => void;
}) {
  const {
    open,
    title = "Выбор категории",
    roots,
    treeById,
    flatById,
    selectedId,
    onPickLeaf,
    onClose,
  } = props;

  const [q, setQ] = useState("");
  const [activeParentId, setActiveParentId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setQ("");

    if (selectedId && flatById.size) {
      const leafFlat = flatById.get(selectedId);
      setActiveParentId(leafFlat?.parent_id || null);
    } else {
      setActiveParentId(null);
    }
  }, [open, selectedId, flatById]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  function openFolder(id: string) {
    setActiveParentId(id);
  }

  function goBack() {
    if (activeParentId === null) return;
    const node = treeById.get(activeParentId);
    if (!node?.parent_id) {
      setActiveParentId(null);
    } else {
      setActiveParentId(node.parent_id);
    }
  }

  const currentChildren = useMemo(() => {
    if (activeParentId === null) return roots;
    const node = treeById.get(activeParentId);
    return node?.children || [];
  }, [activeParentId, roots, treeById]);

  const searchResults = useMemo(() => {
    const qq = q.trim().toLowerCase();
    if (!qq) return [] as CatalogNodeTree[];
    const out: CatalogNodeTree[] = [];
    treeById.forEach((node) => {
      if (node.name.toLowerCase().includes(qq)) out.push(node);
    });
    out.sort((a, b) => a.name.localeCompare(b.name, "ru"));
    return out.slice(0, 80);
  }, [q, treeById]);

  if (!open) return null;

  return createPortal(
    <div className="pn-modalOverlay" onMouseDown={onClose} role="dialog" aria-modal="true">
      <div className="pn-modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="pn-modalHead">
          <div className="pn-modalTitle">{title}</div>
          <button className="pn-iconBtn" onClick={onClose} aria-label="close" type="button">
            ✕
          </button>
        </div>

        <div className="pn-modalBody">
          <div className="pn-catSearchBlock">
            <div className="pn-catSearchLabel">Поиск категории</div>
            <input
              className="pn-catSearchInput"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="например: смартфоны"
              autoFocus
            />
          </div>

          <div className="pn-catList">
            {!q.trim() && activeParentId !== null && (
              <button className="pn-catRow pn-catRowBack" onClick={goBack} type="button" title="Назад">
                <span className="pn-catTitle">← Назад</span>
                <span className="pn-catChevron" aria-hidden="true" />
              </button>
            )}

            {q.trim() ? (
              <>
                {searchResults.map((node) => (
                  <button
                    key={node.id}
                    className={`pn-catRow ${node.id === selectedId ? "isActive" : ""}`}
                    onClick={() => onPickLeaf(node)}
                    type="button"
                    title={buildPathString(flatById, node.id)}
                  >
                    <span className="pn-catTitle">{node.name}</span>
                    <span className="pn-catMeta">{buildPathString(flatById, node.id)}</span>
                    <span className="pn-catChevron" aria-hidden="true" />
                  </button>
                ))}
                {!searchResults.length && <div className="pn-catEmpty">Ничего не найдено</div>}
              </>
            ) : (
              <>
                {currentChildren.map((node) => {
                  const leaf = isLeaf(node);
                  return (
                    <button
                      key={node.id}
                      className={`pn-catRow ${node.id === selectedId ? "isActive" : ""}`}
                      onClick={() => (leaf ? onPickLeaf(node) : openFolder(node.id))}
                      type="button"
                      title={leaf ? node.name : "Открыть"}
                    >
                      <span className="pn-catTitle">{node.name}</span>
                      <span className="pn-catMeta" />
                      <span className="pn-catChevron" aria-hidden="true">
                        {leaf ? "" : "›"}
                      </span>
                    </button>
                  );
                })}
                {!currentChildren.length && <div className="pn-catEmpty">На этом уровне ничего нет</div>}
              </>
            )}
          </div>

          <div className="pn-hint" style={{ marginTop: 10 }}>
            Выбирайте конечную категорию — окно закроется автоматически.
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

// ===== dictionaries/params

type AttributeItem = {
  id: string;
  title: string;
  code?: string | null;
  type: string;
  scope?: string | null;
  dict_id?: string | null;
};

type DictionaryListItem = {
  id: string;
  title?: string | null;
  code?: string | null;
  meta?: { service?: boolean };
};

type DictItem = {
  value: string;
};

type DictionaryResp = {
  item: { id: string; title: string; items: DictItem[] };
};

type VariantParam = {
  attr_id: string;
  title: string;
  code: string;
  dict_id: string;
  options: string[];
};

type ParamPickerResult = {
  selectedOrder: string[];
  selectedValues: Record<string, string[]>;
};

function ParamPickerModal(props: {
  open: boolean;
  params: VariantParam[];
  initialOrder: string[];
  initialValues: Record<string, string[]>;
  onApply: (res: ParamPickerResult) => void;
  onClose: () => void;
}) {
  const { open, params, initialOrder, initialValues, onApply, onClose } = props;

  const [q, setQ] = useState("");
  const [activeAttrId, setActiveAttrId] = useState<string>("");
  const [order, setOrder] = useState<string[]>([]);
  const [values, setValues] = useState<Record<string, string[]>>({});
  const [optionsByAttr, setOptionsByAttr] = useState<Record<string, string[]>>({});
  const [newValue, setNewValue] = useState("");
  const [savingNewValue, setSavingNewValue] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setQ("");
    setNewValue("");
    setErr(null);

    const opt: Record<string, string[]> = {};
    for (const p of params) opt[p.attr_id] = p.options || [];
    setOptionsByAttr(opt);

    setOrder(initialOrder || []);
    setValues({ ...(initialValues || {}) });

    const first = (initialOrder && initialOrder[0]) || params[0]?.attr_id || "";
    setActiveAttrId(first);
  }, [open, params, initialOrder, initialValues]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const filteredParams = useMemo(() => {
    const qq = q.trim().toLowerCase();
    if (!qq) return params;
    return params.filter(
      (p) => (p.title || "").toLowerCase().includes(qq) || (p.code || "").toLowerCase().includes(qq)
    );
  }, [q, params]);

  const activeParam = useMemo(
    () => params.find((p) => p.attr_id === activeAttrId) || null,
    [params, activeAttrId]
  );

  function isSelected(attrId: string) {
    return order.includes(attrId);
  }

  function toggleParam(attrId: string) {
    setOrder((prev) => {
      const has = prev.includes(attrId);
      if (has) return prev.filter((x) => x !== attrId);
      return [...prev, attrId];
    });
    setActiveAttrId(attrId);
  }

  async function addNewValue() {
    setErr(null);
    const v = normStr(newValue);
    if (!v) return;
    if (!activeParam) return;

    if (!isSelected(activeParam.attr_id)) {
      setErr("Сначала включите параметр слева.");
      return;
    }

    setSavingNewValue(true);
    try {
      await postJson<{ ok: boolean }>(API_DICT_ENSURE_VALUE(activeParam.dict_id), {
        value: v,
        source: "ui",
      });

      setOptionsByAttr((prev) => {
        const next = { ...prev };
        const cur = next[activeParam.attr_id] || [];
        next[activeParam.attr_id] = uniqTrim([...cur, v]);
        return next;
      });

      setValues((prev) => {
        const next = { ...prev };
        const cur = next[activeParam.attr_id] || [];
        next[activeParam.attr_id] = uniqTrim([...cur, v]);
        return next;
      });

      setNewValue("");
    } catch (e: any) {
      setErr(e?.message || "Не удалось добавить значение");
    } finally {
      setSavingNewValue(false);
    }
  }

  function apply() {
    onApply({ selectedOrder: order, selectedValues: values });
    onClose();
  }

  if (!open) return null;

  return createPortal(
    <div className="pn-modalOverlay" onMouseDown={onClose} role="dialog" aria-modal="true">
      <div className="pn-modal" onMouseDown={(e) => e.stopPropagation()} style={{ maxWidth: 1020 }}>
        <div className="pn-modalHead">
          <div className="pn-modalTitle">Оси вариантов</div>
          <button className="pn-iconBtn" onClick={onClose} aria-label="close" type="button">
            ✕
          </button>
        </div>

        <div className="pn-modalBody" style={{ display: "grid", gridTemplateColumns: "380px 1fr", gap: 14 }}>
          <div>
            <div className="pn-catSearchBlock">
              <div className="pn-catSearchLabel">Поиск оси</div>
              <input
                className="pn-catSearchInput"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="память, цвет, SIM…"
                autoFocus
              />
            </div>

            <div className="pn-catList" style={{ marginTop: 10 }}>
              {filteredParams.map((p) => {
                const sel = isSelected(p.attr_id);
                const act = activeAttrId === p.attr_id;
                return (
                  <button
                    key={p.attr_id}
                    className={`pn-catRow ${act ? "isActive" : ""}`}
                    onClick={() => setActiveAttrId(p.attr_id)}
                    type="button"
                    title={p.title}
                    style={{ alignItems: "center" }}
                  >
                    <span className="pn-catTitle pn-smallText" style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <input
                        type="checkbox"
                        checked={sel}
                        onChange={() => toggleParam(p.attr_id)}
                        onClick={(e) => e.stopPropagation()}
                      />
                      {p.title}
                    </span>
                    <span className="pn-catMeta">
                      {(optionsByAttr[p.attr_id] || []).length} знач.
                    </span>
                    <span className="pn-catChevron" aria-hidden="true" />
                  </button>
                );
              })}
            </div>

            <div className="pn-hint" style={{ marginTop: 10 }}>
              Здесь только параметры, по которым реально строятся SKU-варианты.
            </div>
          </div>

          <div>
            <div className="pn-card pn-cardInner" style={{ margin: 0 }}>
              <div className="pn-cardTitle" style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                <span>{activeParam ? activeParam.title : "Выберите ось"} — значения</span>
                {activeParam && !isSelected(activeParam.attr_id) && (
                  <span className="pn-muted">сначала включите слева</span>
                )}
              </div>

              {!!err && (
                <div className="pn-alert pn-alertBad" style={{ marginTop: 8 }}>
                  <div className="pn-alertTitle">Ошибка</div>
                  <div className="pn-alertText">{err}</div>
                </div>
              )}

              <select
                className="pn-input"
                multiple
                value={activeParam ? values[activeParam.attr_id] || [] : []}
                onChange={(e) => {
                  if (!activeParam) return;
                  const vals = Array.from(e.target.selectedOptions).map((o) => o.value);
                  setValues((prev) => ({ ...prev, [activeParam.attr_id]: uniqTrim(vals) }));
                }}
                style={{ height: 220 }}
                disabled={!activeParam || !isSelected(activeParam.attr_id)}
              >
                {(activeParam ? optionsByAttr[activeParam.attr_id] || [] : []).map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </select>

              <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
                <input
                  className="pn-input"
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                  placeholder="добавить новое значение…"
                  disabled={!activeParam || !isSelected(activeParam.attr_id) || savingNewValue}
                />
                <button
                  className="pn-editBtn"
                  onClick={addNewValue}
                  type="button"
                  disabled={!activeParam || !isSelected(activeParam.attr_id) || savingNewValue}
                >
                  {savingNewValue ? "..." : "＋ Добавить"}
                </button>
              </div>

              <div className="pn-hint" style={{ marginTop: 10 }}>
                Выберите значения из словаря. Каждая комбинация станет отдельным SKU.
              </div>
            </div>

            <div className="pn-variantsActions" style={{ marginTop: 12, justifyContent: "flex-end" }}>
              <button className="pn-editBtn" onClick={onClose} type="button">
                Отмена
              </button>
              <button className="pn-saveBtn" onClick={apply} type="button">
                Выбрать
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

// ===== data models

type TemplateAttr = {
  id?: string;
  attribute_id?: string;
  name: string;
  code?: string;
  type: string;
  scope: "common" | "variant";
  options?: any;
  required?: boolean;
};

type TemplatesByCategoryResp = {
  template: { id: string; category_id: string; name: string } | null;
  attributes: TemplateAttr[];
};

type SkuTriplet = { sku_pim: string; sku_gt: string };

type VariantContent = {
  features: {
    code: string;
    name: string;
    restore: string;
    store77: string;
    selected: "restore" | "store77" | "custom";
    value: string;
  }[];
  media: { url: string; source?: string }[];
  description: {
    restore: string;
    store77: string;
    selected: "restore" | "store77" | "custom";
    custom: string;
  };
};

type Variant = {
  key: string;
  title: string;
  params: Record<string, string>;
  sku_pim: string;
  sku_gt: string;
  enabled: boolean;
  links: { source: "restore" | "store77"; url: string }[];
  content: VariantContent;
};

type ProductContent = {
  documents: { name: string; url: string }[];
  analogs: { sku: string; name: string }[];
  related: { sku: string; name: string }[];
};

function emptyVariantContent(): VariantContent {
  return {
    features: [],
    media: [],
    description: { restore: "", store77: "", selected: "custom", custom: "" },
  };
}

function makeVariantKey(order: string[], params: Record<string, string>) {
  const vals = order.map((id) => _normKey(params[id] || ""));
  return vals.join("|") || "v1";
}

function buildCombinations(order: string[], valuesByAttr: Record<string, string[]>) {
  let acc: Record<string, string>[] = [{}];
  for (const attrId of order) {
    const opts = (valuesByAttr[attrId] && valuesByAttr[attrId].length ? valuesByAttr[attrId] : [""]).map((x) =>
      normStr(x)
    );
    const next: Record<string, string>[] = [];
    for (const base of acc) for (const v of opts) next.push({ ...base, [attrId]: v });
    acc = next;
  }
  return acc;
}

function buildVariantTitle(baseTitle: string, order: string[], params: Record<string, string>) {
  const tokens = order.map((id) => normStr(params[id] || "")).filter(Boolean);
  const base = normStr(baseTitle);
  return tokens.length ? `${base} ${tokens.join(" ")}` : base || "Товар";
}

function BadgeLike({ label }: { label: string }) {
  return <span className="pnWizardBadge">{label}</span>;
}

function buildFeatureSkeleton(attrs: TemplateAttr[]) {
  const out: VariantContent["features"] = [];
  const seen = new Set<string>();
  for (const a of attrs || []) {
    const code = (a.code || "").trim();
    if (!code || seen.has(code)) continue;
    const options = a.options || {};
    const layer = String(options.layer || "").trim().toLowerCase();
    const paramGroup = String(options.param_group || "").trim();
    if (layer === "base" || paramGroup === "Описание" || paramGroup === "Медиа") continue;
    seen.add(code);
    out.push({
      code,
      name: a.name || code,
      restore: "",
      store77: "",
      selected: "custom",
      value: "",
    });
  }
  return out;
}

function variantContentPatch(
  variant: Variant,
  shared: ProductContent
): ProductContent & {
  description: string;
  media: { url: string; source?: string }[];
  media_images: { url: string; source?: string }[];
  links: { label: string; url: string }[];
  features: { code: string; name: string; value: string; source_values?: any }[];
} {
  const links = variant.links.map((link) => ({ label: link.source, url: normStr(link.url) }));
  const media = variant.content.media || [];
  return {
    ...shared,
    description: variant.content.description.custom || "",
    media,
    media_images: media,
    links,
    features: (variant.content.features || [])
      .filter((feature) => normStr(feature.value))
      .map((feature) => ({
        code: feature.code,
        name: feature.name,
        value: feature.value,
        source_values: {
          competitor: {
            restore: feature.restore ? { raw_value: feature.restore, resolved_value: feature.restore } : undefined,
            store77: feature.store77 ? { raw_value: feature.store77, resolved_value: feature.store77 } : undefined,
          },
        },
      })),
  };
}

export default function ProductNewFeature() {
  const navigate = useNavigate();
  const orgPath = useOrgPath();
  const [searchParams] = useSearchParams();
  const [title, setTitle] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [categoryPath, setCategoryPath] = useState("");
  const [productType, setProductType] = useState<"single" | "multi">("single");

  const [catalogTree, setCatalogTree] = useState<CatalogNodeTree[]>([]);
  const [treeById, setTreeById] = useState<Map<string, CatalogNodeTree>>(new Map());
  const [flatById, setFlatById] = useState<Map<string, CatalogNodeFlat>>(new Map());
  const [catModalOpen, setCatModalOpen] = useState(false);
  const [catalogErr, setCatalogErr] = useState<string | null>(null);

  const [templateId, setTemplateId] = useState<string | null>(null);
  const [templateAttrs, setTemplateAttrs] = useState<TemplateAttr[]>([]);
  const [templateErr, setTemplateErr] = useState<string | null>(null);
  const [templateTreeById, setTemplateTreeById] = useState<Map<string, TemplateTreeNode>>(new Map());

  const [globalAttrs, setGlobalAttrs] = useState<AttributeItem[]>([]);
  const [dictionaryItems, setDictionaryItems] = useState<DictionaryListItem[]>([]);

  const [dictLoadingIds, setDictLoadingIds] = useState<Record<string, boolean>>({});
  const dictCacheRef = useRef<Map<string, string[]>>(new Map());

  const [paramModalOpen, setParamModalOpen] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState<string[]>([]);
  const [selectedValues, setSelectedValues] = useState<Record<string, string[]>>({});

  const [variants, setVariants] = useState<Variant[]>([]);
  const [variantErr, setVariantErr] = useState<string | null>(null);
  const [activeVariantKey, setActiveVariantKey] = useState<string>("v1");

  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [created, setCreated] = useState<{ id: string; title: string } | null>(null);
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    (async () => {
      try {
        const res = await getJson<ProductNewBootstrapResp>(`${apiBase()}/products/new-bootstrap`);
        const nodes = res.catalog_nodes || [];
        const tree = buildTree(nodes);
        const mapFlat = new Map<string, CatalogNodeFlat>();
        for (const n of nodes) mapFlat.set(n.id, n);
        const templateMap = new Map<string, TemplateTreeNode>();
        for (const n of res.template_tree || []) templateMap.set(n.id, n);

        setCatalogTree(tree);
        setTreeById(indexTree(tree));
        setFlatById(mapFlat);
        setTemplateTreeById(templateMap);
        setGlobalAttrs(res.attributes || []);
        setDictionaryItems(res.dictionaries || []);
        const initialCategoryId = searchParams.get("category_id") || "";
        if (initialCategoryId && mapFlat.has(initialCategoryId)) {
          setCategoryId(initialCategoryId);
          setCategoryPath(buildPathString(mapFlat, initialCategoryId));
        }
      } catch (e: any) {
        setCatalogErr(e?.message || "CATALOG_LOAD_FAILED");
        setTemplateTreeById(new Map());
        setGlobalAttrs([]);
        setDictionaryItems([]);
      }
    })();
  }, [searchParams]);

  useEffect(() => {
    if (!categoryId) return;
    (async () => {
      setTemplateErr(null);
      try {
        let tplId: string | null = null;
        if (templateTreeById.size) {
          let curId: string | null = categoryId;
          const guard = new Set<string>();
          while (curId && !guard.has(curId)) {
            guard.add(curId);
            const node = templateTreeById.get(curId);
            if (node?.template_id) {
              tplId = node.template_id;
              break;
            }
            curId = node?.parent_id || null;
          }
        }

        if (!tplId) {
          const legacy = await getJson<TemplatesByCategoryResp>(
            `${API_TEMPLATES_BY_CATEGORY}/${encodeURIComponent(categoryId)}`
          );
          tplId = legacy.template?.id || null;
          if (tplId) {
            setTemplateId(tplId);
            setTemplateAttrs(legacy.attributes || []);
          } else {
            setTemplateId(null);
            setTemplateAttrs([]);
          }
          return;
        }

        const res = await getJson<{ template: TemplateAttr | null; attributes: TemplateAttr[] }>(
          `${API_TEMPLATE_GET}/${encodeURIComponent(tplId)}`
        );
        setTemplateId(tplId);
        setTemplateAttrs(res.attributes || []);
      } catch (e: any) {
        setTemplateId(null);
        setTemplateAttrs([]);
        setTemplateErr(e?.message || "TEMPLATE_LOAD_FAILED");
      }
    })();
  }, [categoryId, templateTreeById]);

  const globalAttrById = useMemo(() => {
    const map = new Map<string, AttributeItem>();
    for (const a of globalAttrs) map.set(a.id, a);
    return map;
  }, [globalAttrs]);

  const featureDictByCode = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of templateAttrs || []) {
      const global = a.attribute_id ? globalAttrById.get(a.attribute_id) : null;
      const code = (a.code || global?.code || a.name || a.id || "").trim();
      if (!code) continue;
      const opts = a.options || {};
      const dictId =
        opts.dict_id ||
        opts.dictId ||
        (a.attribute_id && globalAttrById.get(a.attribute_id || "")?.dict_id) ||
        (opts.attribute_id && globalAttrById.get(opts.attribute_id || "")?.dict_id) ||
        "";
      if (dictId) map.set(code, dictId);
    }
    return map;
  }, [templateAttrs, globalAttrById]);

  const variantParams = useMemo(() => {
    if (productType !== "multi") return [];
    const byDict = new Map<string, VariantParam>();
    const addParam = (dictId: string, title: string, code: string, scope?: string | null) => {
      const id = dictId.trim();
      const normalizedCode = code.trim() || id;
      const normalizedTitle = title.trim() || normalizedCode;
      if (!id || byDict.has(id)) return;
      if (!isVariantAxisCandidate(normalizedTitle, normalizedCode, scope)) return;
      byDict.set(id, {
        attr_id: id,
        title: normalizedTitle,
        code: normalizedCode,
        dict_id: id,
        options: [],
      });
    };

    for (const attr of templateAttrs || []) {
      const global = attr.attribute_id ? globalAttrById.get(attr.attribute_id) : null;
      const options = attr.options || {};
      const dictId =
        options.dict_id ||
        options.dictId ||
        global?.dict_id ||
        (options.attribute_id && globalAttrById.get(options.attribute_id || "")?.dict_id) ||
        "";
      const title = attr.name || global?.title || attr.code || global?.code || "";
      const code = attr.code || global?.code || title;
      const scope = attr.scope || global?.scope || "";
      addParam(String(dictId || ""), title, code, scope);
    }

    if (!byDict.size) {
      for (const item of dictionaryItems || []) {
        if (item?.meta?.service) continue;
        const id = (item.id || "").trim();
        const title = (item.title || item.code || id || "").trim();
        const code = (item.code || id || "").trim();
        addParam(id, title, code, "");
      }
    }

    return Array.from(byDict.values())
      .sort((a, b) => {
        const rankA = variantAxisRank(a.title, a.code);
        const rankB = variantAxisRank(b.title, b.code);
        if (rankA !== rankB) return rankA - rankB;
        return a.title.localeCompare(b.title, "ru");
      });
  }, [dictionaryItems, globalAttrById, productType, templateAttrs]);

  useEffect(() => {
    if (productType !== "multi") return;
    const allowedIds = new Set(variantParams.map((param) => param.attr_id));
    setSelectedOrder((prev) => prev.filter((id) => allowedIds.has(id)));
    setSelectedValues((prev) => {
      let changed = false;
      const next: Record<string, string[]> = {};
      for (const [id, values] of Object.entries(prev)) {
        if (!allowedIds.has(id)) {
          changed = true;
          continue;
        }
        next[id] = values;
      }
      return changed ? next : prev;
    });
  }, [productType, variantParams]);

  useEffect(() => {
    (async () => {
      for (const p of variantParams) {
        if (!p.dict_id) continue;
        if (dictCacheRef.current.has(p.dict_id)) continue;
        setDictLoadingIds((prev) => ({ ...prev, [p.dict_id]: true }));
        try {
          const res = await getJson<DictionaryResp>(API_DICT_GET(p.dict_id));
          const vals = (res.item?.items || []).map((x) => x.value).filter(Boolean);
          dictCacheRef.current.set(p.dict_id, vals);
        } catch {
          dictCacheRef.current.set(p.dict_id, []);
        } finally {
          setDictLoadingIds((prev) => ({ ...prev, [p.dict_id]: false }));
        }
      }
    })();
  }, [variantParams]);

  const paramDefs = useMemo(() => {
    return variantParams.map((p) => ({
      ...p,
      options: p.dict_id ? dictCacheRef.current.get(p.dict_id) || [] : [],
    }));
  }, [variantParams, dictLoadingIds]);

  const hasVariantParams = paramDefs.length > 0;

  useEffect(() => {
    if (!templateAttrs.length || !variants.length) return;
    const skeleton = buildFeatureSkeleton(templateAttrs);
    if (!skeleton.length) return;

    setVariants((prev) => {
      let changed = false;
      const next = prev.map((v) => {
        const existing = v.content.features || [];
        const existingMap = new Map(existing.map((f) => [f.code, f]));
        const skeletonCodes = new Set(skeleton.map((f) => f.code));
        const needsAdd = skeleton.some((f) => !existingMap.has(f.code));
        if (needsAdd) {
          const merged = skeleton.map((f) => existingMap.get(f.code) || f);
          for (const f of existing) {
            if (!skeletonCodes.has(f.code)) merged.push(f);
          }
          changed = true;
          return { ...v, content: { ...v.content, features: merged } };
        }
        return v;
      });
      return changed ? next : prev;
    });
  }, [templateAttrs, variants.length]);

  function selectCategory(node: CatalogNodeTree) {
    setCategoryId(node.id);
    setCategoryPath(buildPathString(flatById, node.id) || node.name);
    setCatModalOpen(false);
  }

  function ensureSingleVariant() {
    setVariants((prev) => {
      if (prev.length) return prev;
      return [
        {
          key: "v1",
          title: normStr(title) || "Товар",
          params: {},
          sku_pim: "",
          sku_gt: "",
          enabled: true,
          links: [
            { source: "restore", url: "" },
            { source: "store77", url: "" },
          ],
          content: emptyVariantContent(),
        },
      ];
    });
  }

  useEffect(() => {
    if (productType === "single") {
      ensureSingleVariant();
    } else {
      setVariants([]);
    }
  }, [productType]);

  useEffect(() => {
    if (productType !== "single") return;
    const nextTitle = normStr(title);
    if (!nextTitle) return;
    setVariants((prev) => {
      if (!prev.length) return prev;
      return prev.map((variant) => (variant.key === "v1" ? { ...variant, title: nextTitle } : variant));
    });
  }, [productType, title]);

  useEffect(() => {
    if (!variants.length) return;
    if (!variants.find((v) => v.key === activeVariantKey)) {
      setActiveVariantKey(variants[0].key);
    }
  }, [variants, activeVariantKey]);

  async function allocateSkus(count: number) {
    if (count <= 0) return [] as SkuTriplet[];
    const res = await postJson<{ items: SkuTriplet[] }>(API_ALLOCATE_SKUS, { count });
    return res.items || [];
  }

  async function ensureSkusForVariants(next: Variant[]) {
    const missing = next.filter((v) => !v.sku_pim || !v.sku_gt);
    if (!missing.length) return next;
    const triplets = await allocateSkus(missing.length);
    const tripletQueue = triplets.slice();
    return next.map((v) => {
      if (v.sku_pim && v.sku_gt) return v;
      const t = tripletQueue.shift();
      if (!t) return v;
      return { ...v, sku_pim: t.sku_pim, sku_gt: t.sku_gt };
    });
  }

  async function onGenerateVariants() {
    setVariantErr(null);
    if (!selectedOrder.length) {
      setVariantErr("Выберите параметры для вариантов.");
      return;
    }

    for (const id of selectedOrder) {
      if (!selectedValues[id] || !selectedValues[id].length) {
        setVariantErr("Заполните значения для всех выбранных параметров.");
        return;
      }
    }

    const combos = buildCombinations(selectedOrder, selectedValues || {});
    if (!combos.length) {
      setVariantErr("Для параметров не выбраны значения.");
      return;
    }

    const existingByKey = new Map<string, Variant>();
    for (const v of variants) existingByKey.set(v.key, v);

    let next: Variant[] = combos.map((p) => {
      const key = makeVariantKey(selectedOrder, p);
      const existing = existingByKey.get(key);
      return (
        existing || {
          key,
          title: buildVariantTitle(title, selectedOrder, p),
          params: p,
          sku_pim: "",
          sku_gt: "",
          enabled: true,
          links: [
            { source: "restore", url: "" },
            { source: "store77", url: "" },
          ],
          content: emptyVariantContent(),
        }
      );
    });

    next = await ensureSkusForVariants(next);
    setVariants(next);
  }

  async function ensureSingleSkus() {
    if (productType !== "single") return;
    if (!variants.length) {
      ensureSingleVariant();
      return;
    }
    const next = await ensureSkusForVariants(variants);
    setVariants(next);
  }

  function activeVariant() {
    return variants.find((v) => v.key === activeVariantKey) || variants[0];
  }

  function updateActiveVariantContent(patch: Partial<VariantContent>) {
    const v = activeVariant();
    if (!v) return;
    setVariants((prev) =>
      prev.map((row) => (row.key === v.key ? { ...row, content: { ...row.content, ...patch } } : row))
    );
  }

  function updateActiveDescription(next: Partial<VariantContent["description"]>) {
    const v = activeVariant();
    if (!v) return;
    setVariants((prev) =>
      prev.map((row) =>
        row.key === v.key
          ? { ...row, content: { ...row.content, description: { ...row.content.description, ...next } } }
          : row
      )
    );
  }

  function toggleVariantEnabled(key: string) {
    setVariants((prev) =>
      prev.map((variant) =>
        variant.key === key ? { ...variant, enabled: variant.enabled === false } : variant
      )
    );
  }

  function updateVariantRow(key: string, patch: Partial<Pick<Variant, "title" | "sku_gt" | "sku_pim">>) {
    setVariants((prev) =>
      prev.map((variant) => (variant.key === key ? { ...variant, ...patch } : variant))
    );
  }

  function validateBeforeSave() {
    if (!title.trim()) return "Заполните название товара.";
    if (!categoryId.trim()) return "Выберите категорию.";
    if (!variants.length) return "Нет вариантов товара.";
    if (!variants.some((variant) => variant.enabled !== false)) return "Включите хотя бы один SKU для создания.";
    const seenSkuGt = new Set<string>();
    for (const variant of variants.filter((item) => item.enabled !== false)) {
      const skuGt = normStr(variant.sku_gt).toLowerCase();
      if (!skuGt) continue;
      if (seenSkuGt.has(skuGt)) return "SKU GT повторяется в матрице вариантов.";
      seenSkuGt.add(skuGt);
    }
    return "";
  }

  async function onSaveAll() {
    const err = validateBeforeSave();
    if (err) {
      setSaveErr(err);
      return;
    }

    setSaveErr(null);
    setSaving(true);
    try {
      const enabledVariants = variants.filter((variant) => variant.enabled !== false);
      const nextVariants = await ensureSkusForVariants(enabledVariants);
      const dictPairs: Array<{ dictId: string; value: string }> = [];
      const seenDictVals = new Set<string>();
      for (const v of nextVariants) {
        for (const f of v.content.features || []) {
          const dictId = featureDictByCode.get(f.code || "");
          const val = normStr(f.value || "");
          if (!dictId || !val) continue;
          const key = `${dictId}::${val.toLowerCase()}`;
          if (seenDictVals.has(key)) continue;
          seenDictVals.add(key);
          dictPairs.push({ dictId, value: val });
        }
      }
      for (const item of dictPairs) {
        await postJson<{ ok: boolean }>(API_DICT_ENSURE_VALUE(item.dictId), {
          value: item.value,
          source: "pim",
        });
      }
      const nextByKey = new Map(nextVariants.map((variant) => [variant.key, variant]));
      setVariants((prev) => prev.map((variant) => nextByKey.get(variant.key) || variant));

      const sharedContent: ProductContent = { documents: [], analogs: [], related: [] };
      const createPayload = {
        category_id: categoryId,
        type: productType,
        title: normStr(title),
        selected_params: productType === "multi" ? selectedOrder : [],
        feature_params: [],
        exports_enabled: {},
        variants: nextVariants.map((variant) => ({
          title: variant.title,
          sku_pim: variant.sku_pim,
          sku_gt: variant.sku_gt,
          content: variantContentPatch(variant, sharedContent),
        })),
      };
      const res = await postJson<{
        group?: { id: string; name?: string } | null;
        products: Array<{ id: string; title: string }>;
        first_product?: { id: string; title: string } | null;
      }>(API_PRODUCT_CREATE_FAMILY, createPayload);

      const firstCreated = res.first_product || res.products?.[0];
      if (firstCreated) {
        setCreated(firstCreated);
        const groupId = String(res.group?.id || "").trim();
        if (productType === "multi" && groupId) {
          navigate(orgPath(`/catalog/groups?group=${encodeURIComponent(groupId)}&created=1`));
        } else {
          navigate(orgPath(`/products/${encodeURIComponent(firstCreated.id)}?tab=sources&created=1`));
        }
      }
    } catch (e: any) {
      setSaveErr(e?.message || "SAVE_FAILED");
    } finally {
      setSaving(false);
    }
  }

  const canGenerateVariants = productType === "multi" && !!selectedOrder.length && !created;
  const canSave = !saving && !created;

  const active = activeVariant();

  const wizardSteps = [
    { label: "Основа", meta: "название, категория, тип" },
    { label: "SKU и варианты", meta: "один SKU или группа" },
    { label: "Источники", meta: "подбор после создания" },
    { label: "Проверка", meta: "создать реальные SKU" },
  ];
  const activeStep = Math.min(currentStep, wizardSteps.length - 1);
  const filledFeatures = active?.content.features.filter((feature) => normStr(feature.value)).length || 0;
  const selectedParamLabels = selectedOrder.map((id) => {
    const param = paramDefs.find((item) => item.attr_id === id);
    const values = selectedValues[id] || [];
    return {
      id,
      label: param?.title || id,
      values,
    };
  });
  const enabledVariantCount = variants.filter((variant) => variant.enabled !== false).length;
  const disabledVariantCount = Math.max(0, variants.length - enabledVariantCount);
  const variantAxisColumns = selectedParamLabels.length ? selectedParamLabels : [{ id: "__variant", label: "Вариант", values: [] }];
  const readyToCreate = Boolean(normStr(title) && categoryId && enabledVariantCount);
  const canGoNext =
    activeStep === 0
      ? Boolean(normStr(title) && categoryId)
    : activeStep === 1
      ? Boolean(enabledVariantCount)
      : true;

  return (
    <div className="pn-wrap pn-page pnWizardPage">
      <div className="pnWizardShell">
        <aside className="pnWizardRail" aria-label="Создание товара">
          <div className="pnWizardBrand">
            <span>SmartPim</span>
            <strong>Новый SKU</strong>
          </div>
          <div className="pnWizardSteps">
            {wizardSteps.map((step, index) => (
              <button
                key={step.label}
                type="button"
                className={`pnWizardStep${index === activeStep ? " isActive" : ""}${index < activeStep ? " isDone" : ""}`}
                onClick={() => setCurrentStep(index)}
              >
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{step.label}</strong>
                <em>{step.meta}</em>
              </button>
            ))}
          </div>
          <div className="pnWizardRailSummary" aria-label="Состояние создания товара">
            <div>
              <span>Категория</span>
              <strong>{categoryPath ? "выбрана" : "не выбрана"}</strong>
            </div>
            <div>
              <span>SKU</span>
              <strong>{variants.length ? `${enabledVariantCount}/${variants.length}` : 0}</strong>
            </div>
            <div>
              <span>Источники</span>
              <strong>{variants.length ? "после создания" : "—"}</strong>
            </div>
          </div>
          <div className="pnWizardRailHint">
            Создание должно быть коротким: сначала SKU, затем карточка товара для полноценного наполнения.
          </div>
        </aside>

        <main className="pnWizardMain">
          <div className="pnWizardTopbar">
            <div>
              <div className="pnWizardEyebrow">Создание товара</div>
              <h1>{wizardSteps[activeStep].label}</h1>
              <p>{wizardSteps[activeStep].meta}</p>
            </div>
            <div className="pnWizardTopActions">
              <Link className="btn" to={orgPath("/products")}>К товарам</Link>
              <button className="btn primary" onClick={onSaveAll} disabled={!canSave || !readyToCreate}>
                {saving ? "Создаем..." : productType === "single" ? "Создать SKU" : "Создать группу"}
              </button>
            </div>
          </div>

          {catalogErr ? (
            <div className="pn-alert pn-alertBad">
              <div className="pn-alertTitle">Ошибка загрузки</div>
              <div className="pn-alertText">{catalogErr}</div>
            </div>
          ) : null}
          {saveErr ? (
            <div className="pn-alert pn-alertBad">
              <div className="pn-alertTitle">Ошибка сохранения</div>
              <div className="pn-alertText">{saveErr}</div>
            </div>
          ) : null}
          {created ? (
            <div className="pnWizardSuccess">
              <div>
                <strong>Товар создан</strong>
                <span>ID: {created.id}. Дальше лучше открыть карточку и довести параметры, медиа и каналы.</span>
              </div>
              <Link className="btn primary" to={orgPath(`/products/${created.id}`)}>Открыть карточку</Link>
            </div>
          ) : null}

          <section className="pnWizardCard">
            {activeStep === 0 ? (
              <div className="pnWizardTwoCol">
                <div className="pnWizardFormStack">
                  <label className="pnWizardField">
                    <span>Название товара</span>
                    <input className="pn-input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Смартфон Apple iPhone 17 Pro 256Gb..." />
                  </label>
                  <label className="pnWizardField">
                    <span>Категория</span>
                    <button className="pn-input pn-inputBtn" onClick={() => setCatModalOpen(true)} type="button">
                      {categoryPath || "Выбрать категорию"}
                    </button>
                    {templateErr ? <em>{templateErr}</em> : null}
                  </label>
                  <div className="pnWizardTypeGrid">
                    <button className={`pnWizardChoice${productType === "single" ? " isActive" : ""}`} onClick={() => setProductType("single")} type="button">
                      <strong>Один SKU</strong>
                      <span>Обычная карточка без variant-family.</span>
                    </button>
                    <button className={`pnWizardChoice${productType === "multi" ? " isActive" : ""}`} onClick={() => setProductType("multi")} type="button">
                      <strong>С вариантами</strong>
                      <span>Цвет, память, размер и другие SKU в группе.</span>
                    </button>
                  </div>
                </div>
                <div className="pnWizardPreviewCard">
                  <span>Preview</span>
                  <strong>{normStr(title) || "Название товара"}</strong>
                  <p>{categoryPath || "Категория появится здесь после выбора."}</p>
                  <div>
                    <BadgeLike label={productType === "single" ? "single SKU" : "variant family"} />
                    <BadgeLike label={templateId ? "модель найдена" : "модель не выбрана"} />
                  </div>
                </div>
              </div>
            ) : null}

            {activeStep === 1 ? (
              <div className="pnWizardFormStack">
                <div className="pnWizardSectionHead">
                  <div>
                    <strong>{productType === "single" ? "Один товарный SKU" : "Группа вариантов"}</strong>
                    <span>
                      {productType === "single"
                        ? "Один товар сразу получит SKU GT и SKU PIM."
                        : "Каждая комбинация станет отдельным SKU, а все SKU будут объединены в одну группу товара."}
                    </span>
                  </div>
                  {productType === "single" ? (
                    <button className="btn" type="button" onClick={() => void ensureSingleSkus()}>Выделить SKU</button>
                  ) : (
                    <div className="pnWizardInlineActions">
                      <button className="btn" onClick={() => setParamModalOpen(true)} type="button" disabled={!hasVariantParams}>Выбрать оси</button>
                      <button className="btn primary" onClick={onGenerateVariants} type="button" disabled={!canGenerateVariants || !hasVariantParams}>Собрать SKU</button>
                    </div>
                  )}
                </div>
                {productType === "multi" && !hasVariantParams ? (
                  <div className="pnWizardNotice">
                    В категории пока нет справочников для вариантов. Можно создать один SKU или сначала настроить инфо-модель.
                  </div>
                ) : null}
                {productType === "multi" && selectedParamLabels.length ? (
                  <div className="pnVariantRecipe">
                    {selectedParamLabels.map((param) => (
                      <div key={param.id}>
                        <span>{param.label}</span>
                        <strong>{param.values.length ? param.values.join(" / ") : "значения не выбраны"}</strong>
                      </div>
                    ))}
                  </div>
                ) : null}
                {variantErr ? <div className="pn-hint pn-hintWarn">{variantErr}</div> : null}
                {variants.length && disabledVariantCount ? (
                  <div className="pnWizardNotice">
                    В создание попадут {enabledVariantCount} из {variants.length} SKU. Исключенные комбинации можно включить обратно до создания.
                  </div>
                ) : null}
                <div
                  className="pnVariantMatrix pnVariantMatrixWide"
                  style={{
                    ["--variant-axis-count" as any]: String(variantAxisColumns.length),
                  }}
                >
                  {variants.length ? (
                    <>
                      <div className="pnVariantMatrixHead">
                        <span>Статус</span>
                        {variantAxisColumns.map((axis) => (
                          <span key={axis.id}>{axis.label}</span>
                        ))}
                        <span>Название</span>
                        <span>SKU GT</span>
                        <span>SKU PIM</span>
                        <span>Действие</span>
                      </div>
                      {variants.map((variant) => (
                        <div
                          key={variant.key}
                          className={`pnVariantMatrixRow${variant.key === activeVariantKey ? " isActive" : ""}${variant.enabled === false ? " isDisabled" : ""}`}
                          onClick={() => setActiveVariantKey(variant.key)}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              setActiveVariantKey(variant.key);
                            }
                          }}
                        >
                          <span className={`pnVariantStatus${variant.enabled === false ? " isMuted" : ""}`}>
                            {variant.enabled === false ? "исключен" : "создать"}
                          </span>
                          {variantAxisColumns.map((axis) => (
                            <span key={axis.id}>
                              {axis.id === "__variant"
                                ? Object.values(variant.params).filter(Boolean).join(" / ") || "один SKU"
                                : variant.params[axis.id] || "—"}
                            </span>
                          ))}
                          <input
                            className="pnVariantInlineInput"
                            value={variant.title}
                            onClick={(event) => event.stopPropagation()}
                            onChange={(event) => updateVariantRow(variant.key, { title: event.target.value })}
                            aria-label="Название SKU"
                          />
                          <input
                            className="pnVariantInlineInput isSku"
                            value={variant.sku_gt}
                            placeholder="будет выделен"
                            onClick={(event) => event.stopPropagation()}
                            onChange={(event) => updateVariantRow(variant.key, { sku_gt: event.target.value })}
                            aria-label="SKU GT"
                          />
                          <input
                            className="pnVariantInlineInput isSku"
                            value={variant.sku_pim}
                            placeholder="будет выделен"
                            onClick={(event) => event.stopPropagation()}
                            onChange={(event) => updateVariantRow(variant.key, { sku_pim: event.target.value })}
                            aria-label="SKU PIM"
                          />
                          <button
                            className="pnVariantToggle"
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              toggleVariantEnabled(variant.key);
                            }}
                          >
                            {variant.enabled === false ? "Включить" : "Исключить"}
                          </button>
                        </div>
                      ))}
                    </>
                  ) : (
                    <div className="pnWizardEmpty">
                      {productType === "single" ? "Нажмите «Выделить SKU»." : "Выберите параметры и нажмите «Собрать SKU»."}
                    </div>
                  )}
                </div>
              </div>
            ) : null}

            {activeStep === 2 ? (
              <div className="pnWizardFormStack">
                <div className="pnWizardSectionHead">
                  <div>
                    <strong>Подбор конкурентов после создания</strong>
                    <span>Сначала создаем реальные SKU. Один SKU откроется в карточке товара, линейка - в группе SKU с переходом к подбору конкурентов.</span>
                  </div>
                </div>
                <div className="pnWizardNotice">
                  Ручные ссылки не являются основным сценарием. После создания перейдите к источникам: там для каждого SKU будет подбор карточек,
                  подтверждение кандидата и насыщение параметрами/медиа только из подтвержденных ссылок.
                </div>
                <div className="pnVariantMatrix">
                  <div className="pnVariantMatrixHead">
                    <span>SKU</span>
                    <span>Вариант</span>
                    <span>Источники</span>
                    <span>Следующее действие</span>
                  </div>
                  {variants.filter((variant) => variant.enabled !== false).map((variant) => (
                    <div key={variant.key} className="pnVariantMatrixRow">
                      <strong>{variant.title}</strong>
                      <span>{Object.values(variant.params).filter(Boolean).join(" / ") || "один SKU"}</span>
                      <span>re-store / store77</span>
                      <span>Найти карточки</span>
                    </div>
                  ))}
                  {!enabledVariantCount ? (
                    <div className="pnWizardEmpty">Включите хотя бы один SKU на предыдущем шаге.</div>
                  ) : null}
                </div>
              </div>
            ) : null}

            {activeStep === 3 ? (
              <div className="pnWizardReview">
                <div className="pnWizardReviewHero">
                  <span>{readyToCreate ? "Можно создавать" : "Не все готово"}</span>
                  <h2>{normStr(title) || "Название не заполнено"}</h2>
                  <p>{categoryPath || "Категория не выбрана"}</p>
                </div>
                <div className="pnWizardReviewGrid">
                  <div><span>Тип</span><strong>{productType === "single" ? "Один SKU" : "С вариантами"}</strong></div>
                  <div><span>SKU к созданию</span><strong>{enabledVariantCount}</strong></div>
                  <div><span>Источники</span><strong>после создания</strong></div>
                  <div><span>Параметры</span><strong>{filledFeatures}</strong></div>
                </div>
                <div className="pnWizardNotice">
                  После создания одного SKU откроется карточка товара. После создания линейки откроется группа SKU, чтобы сначала проверить состав,
                  общие факты и отличия, а затем перейти к подбору конкурентов и выгрузке выбранных SKU.
                </div>
                <button className="btn primary pnWizardCreateButton" onClick={onSaveAll} disabled={!canSave || !readyToCreate}>
                  {saving ? "Создаем..." : productType === "single" ? "Создать SKU" : "Создать группу SKU"}
                </button>
              </div>
            ) : null}
          </section>

          <div className="pnWizardFooter">
            <button className="btn" type="button" onClick={() => setCurrentStep((step) => Math.max(0, step - 1))} disabled={activeStep === 0}>Назад</button>
            <button className="btn primary" type="button" onClick={() => setCurrentStep((step) => Math.min(wizardSteps.length - 1, step + 1))} disabled={activeStep === wizardSteps.length - 1 || !canGoNext}>Дальше</button>
          </div>
        </main>
      </div>

      <CategoryModal open={catModalOpen} roots={catalogTree} treeById={treeById} flatById={flatById} selectedId={categoryId} onPickLeaf={selectCategory} onClose={() => setCatModalOpen(false)} />
      <ParamPickerModal open={paramModalOpen} params={paramDefs} initialOrder={selectedOrder} initialValues={selectedValues} onApply={(res) => { setSelectedOrder(res.selectedOrder); setSelectedValues(res.selectedValues); }} onClose={() => setParamModalOpen(false)} />
    </div>
  );

}
