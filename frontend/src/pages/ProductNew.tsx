import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { createPortal } from "react-dom";
import "../styles/product-new.css";
import { toRenderableMediaUrl } from "../lib/media";

function apiBase() {
  return "/api";
}

const API_CATALOG_NODES = `${apiBase()}/catalog/nodes`;
const API_TEMPLATES_TREE = `${apiBase()}/templates/tree`;
const API_TEMPLATES_BY_CATEGORY = `${apiBase()}/templates/by-category`;
const API_TEMPLATE_GET = `${apiBase()}/templates`;
const API_COMP_MAPPING = `${apiBase()}/competitor-mapping/template`;
const API_COMP_CONTENT_BATCH = `${apiBase()}/competitor-mapping/competitor-content-batch`;
const API_ALLOCATE_SKUS = `${apiBase()}/products/allocate-skus`;
const API_PRODUCT_CREATE = `${apiBase()}/products/create`;
const API_PRODUCT_PATCH = `${apiBase()}/products`;
const API_VARIANTS_BULK_CREATE = `${apiBase()}/variants/bulk-create`;
const API_ATTRIBUTES = `${apiBase()}/attributes`;
const API_DICTIONARIES = `${apiBase()}/dictionaries`;
const API_DICT_GET = (dictId: string) => `${API_DICTIONARIES}/${encodeURIComponent(dictId)}`;
const API_DICT_ENSURE_VALUE = (dictId: string) =>
  `${API_DICTIONARIES}/${encodeURIComponent(dictId)}/values/ensure`;
const API_CATALOG_SEARCH = `${apiBase()}/catalog/products/search`;
const API_CATALOG_PRODUCTS = `${apiBase()}/catalog/products`;

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

async function patchJson<T>(url: string, body: any): Promise<T> {
  const r = await fetch(url, {
    method: "PATCH",
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

type CatalogNodesResp = { nodes: CatalogNodeFlat[] };
type CatalogProductsResp = { items: ProductListItem[] };
type TemplateTreeNode = {
  id: string;
  parent_id: string | null;
  template_id?: string | null;
};
type TemplatesTreeResp = { nodes: TemplateTreeNode[] };

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

type AttributesListResp = {
  items: AttributeItem[];
  total: number;
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
          <div className="pn-modalTitle">Параметры вариантов</div>
          <button className="pn-iconBtn" onClick={onClose} aria-label="close" type="button">
            ✕
          </button>
        </div>

        <div className="pn-modalBody" style={{ display: "grid", gridTemplateColumns: "380px 1fr", gap: 14 }}>
          <div>
            <div className="pn-catSearchBlock">
              <div className="pn-catSearchLabel">Поиск параметра</div>
              <input
                className="pn-catSearchInput"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="например: память, цвет…"
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
              Отметьте параметры и выберите значения справа.
            </div>
          </div>

          <div>
            <div className="pn-card pn-cardInner" style={{ margin: 0 }}>
              <div className="pn-cardTitle" style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                <span>{activeParam ? activeParam.title : "Выберите параметр"} — значения</span>
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
                Ctrl/⌘ для мультивыбора.
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

// ===== product picker modal

type ProductListItem = { id: string; name: string; category_id?: string };

function CatalogProductPickerModal(props: {
  open: boolean;
  title: string;
  roots: CatalogNodeTree[];
  treeById: Map<string, CatalogNodeTree>;
  flatById: Map<string, CatalogNodeFlat>;
  initialSelected: ProductListItem[];
  onApply: (items: ProductListItem[]) => void;
  onClose: () => void;
}) {
  const { open, title, roots, treeById, flatById, initialSelected, onApply, onClose } = props;
  const [qCat, setQCat] = useState("");
  const [activeParentId, setActiveParentId] = useState<string | null>(null);
  const [activeCategoryId, setActiveCategoryId] = useState<string | null>(null);
  const [qProducts, setQProducts] = useState("");
  const [products, setProducts] = useState<ProductListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [selectedMap, setSelectedMap] = useState<Map<string, ProductListItem>>(new Map());

  useEffect(() => {
    if (!open) return;
    setQCat("");
    setQProducts("");
    setErr(null);
    const map = new Map<string, ProductListItem>();
    for (const it of initialSelected || []) {
      map.set(it.id, it);
    }
    setSelectedMap(map);
    if (roots.length) {
      setActiveParentId(null);
      setActiveCategoryId(roots[0].id);
    } else {
      setActiveParentId(null);
      setActiveCategoryId(null);
    }
  }, [open, initialSelected, roots]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const currentChildren = useMemo(() => {
    if (activeParentId === null) return roots;
    const node = treeById.get(activeParentId);
    return node?.children || [];
  }, [activeParentId, roots, treeById]);

  const searchResults = useMemo(() => {
    const qq = qCat.trim().toLowerCase();
    if (!qq) return [] as CatalogNodeTree[];
    const out: CatalogNodeTree[] = [];
    treeById.forEach((node) => {
      if (node.name.toLowerCase().includes(qq)) out.push(node);
    });
    out.sort((a, b) => a.name.localeCompare(b.name, "ru"));
    return out.slice(0, 80);
  }, [qCat, treeById]);

  useEffect(() => {
    if (!open || !activeCategoryId) return;
    (async () => {
      setLoading(true);
      setErr(null);
      try {
        const res = await getJson<CatalogProductsResp>(
          `${API_CATALOG_PRODUCTS}?category_id=${encodeURIComponent(activeCategoryId)}&include_descendants=true`
        );
        setProducts(res.items || []);
      } catch (e: any) {
        setErr(e?.message || "Не удалось загрузить товары");
        setProducts([]);
      } finally {
        setLoading(false);
      }
    })();
  }, [open, activeCategoryId]);

  function toggleSelect(item: ProductListItem) {
    setSelectedMap((prev) => {
      const next = new Map(prev);
      if (next.has(item.id)) next.delete(item.id);
      else next.set(item.id, item);
      return next;
    });
  }

  function apply() {
    onApply(Array.from(selectedMap.values()));
    onClose();
  }

  function openFolder(id: string) {
    setActiveParentId(id);
  }

  function goBack() {
    if (activeParentId === null) return;
    const node = treeById.get(activeParentId);
    if (!node?.parent_id) setActiveParentId(null);
    else setActiveParentId(node.parent_id);
  }

  const filteredProducts = useMemo(() => {
    const qq = qProducts.trim().toLowerCase();
    if (!qq) return products;
    return products.filter((p) => (p.name || "").toLowerCase().includes(qq));
  }, [qProducts, products]);

  if (!open) return null;

  return createPortal(
    <div className="pn-modalOverlay" onMouseDown={onClose} role="dialog" aria-modal="true">
      <div className="pn-modal" onMouseDown={(e) => e.stopPropagation()} style={{ maxWidth: 980 }}>
        <div className="pn-modalHead">
          <div className="pn-modalTitle">{title}</div>
          <button className="pn-iconBtn" onClick={onClose} aria-label="close" type="button">
            ✕
          </button>
        </div>
        <div className="pn-modalBody" style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: 12 }}>
          <div>
            <div className="pn-catSearchBlock">
              <div className="pn-catSearchLabel">Категории</div>
              <input
                className="pn-catSearchInput"
                value={qCat}
                onChange={(e) => setQCat(e.target.value)}
                placeholder="поиск категории"
              />
            </div>

            <div className="pn-catList" style={{ marginTop: 10 }}>
              {!qCat.trim() && activeParentId !== null && (
                <button className="pn-catRow pn-catRowBack" onClick={goBack} type="button">
                  <span className="pn-catTitle">← Назад</span>
                  <span className="pn-catChevron" aria-hidden="true" />
                </button>
              )}

              {qCat.trim() ? (
                <>
                  {searchResults.map((node) => (
                    <button
                      key={node.id}
                      className={`pn-catRow ${node.id === activeCategoryId ? "isActive" : ""}`}
                      onClick={() => setActiveCategoryId(node.id)}
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
                        className={`pn-catRow ${node.id === activeCategoryId ? "isActive" : ""}`}
                        onClick={() => (leaf ? setActiveCategoryId(node.id) : openFolder(node.id))}
                        type="button"
                        title={node.name}
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
          </div>

          <div>
            <div className="pn-catSearchBlock">
              <div className="pn-catSearchLabel">Товары</div>
              <input
                className="pn-catSearchInput"
                value={qProducts}
                onChange={(e) => setQProducts(e.target.value)}
                placeholder="поиск товара"
              />
            </div>

            {!!err && (
              <div className="pn-alert pn-alertBad" style={{ marginTop: 10 }}>
                <div className="pn-alertTitle">Ошибка</div>
                <div className="pn-alertText">{err}</div>
              </div>
            )}

            <div className="pn-catList" style={{ marginTop: 10 }}>
              {loading && <div className="pn-catEmpty">Загрузка…</div>}
              {!loading && !filteredProducts.length && <div className="pn-catEmpty">Нет товаров</div>}
              {!loading &&
                filteredProducts.map((item) => {
                  const checked = selectedMap.has(item.id);
                  return (
                    <button
                      key={item.id}
                      className={`pn-catRow ${checked ? "isActive" : ""}`}
                      onClick={() => toggleSelect(item)}
                      type="button"
                    >
                      <span className="pn-catTitle">
                        <input type="checkbox" checked={checked} readOnly /> {item.name}
                      </span>
                      <span className="pn-catMeta">ID: {item.id}</span>
                      <span className="pn-catChevron" aria-hidden="true" />
                    </button>
                  );
                })}
            </div>

            <div className="pn-variantsActions" style={{ marginTop: 12, justifyContent: "flex-end" }}>
              <button className="pn-editBtn" onClick={onClose} type="button">
                Отмена
              </button>
              <button className="pn-saveBtn" onClick={apply} type="button">
                Добавить ({selectedMap.size})
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

type MasterField = {
  code: string;
  name?: string | null;
  type?: string | null;
  scope?: string | null;
  required?: boolean;
};

type TemplateMappingResp = {
  ok: boolean;
  template_id: string;
  master_fields: MasterField[];
  data: {
    priority_site?: "restore" | "store77" | null;
    mapping_by_site?: {
      restore?: Record<string, string>;
      store77?: Record<string, string>;
    };
  };
};

type CompetitorContentResp = {
  ok: boolean;
  results: {
    restore: {
      ok: boolean;
      specs?: Record<string, string>;
      mapped_specs?: Record<string, string>;
      images?: string[];
      description?: string;
      error?: string;
      skipped?: boolean;
    };
    store77: {
      ok: boolean;
      specs?: Record<string, string>;
      mapped_specs?: Record<string, string>;
      images?: string[];
      description?: string;
      error?: string;
      skipped?: boolean;
    };
  };
};

type SkuTriplet = { sku_pim: string; sku_gt: string; sku_id: string };

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
  sku_id: string;
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

function normalizeSpecMap(specs: Record<string, string>) {
  const out = new Map<string, string>();
  for (const [k, v] of Object.entries(specs || {})) {
    out.set(_normKey(k), v);
  }
  return out;
}

function pickSpecValue(specs: Record<string, string>, fieldName: string) {
  const map = normalizeSpecMap(specs || {});
  const val = map.get(_normKey(fieldName));
  return val || "";
}

function escapeHtml(text: string) {
  return (text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function textToHtml(text: string) {
  const safe = escapeHtml(text || "").trim();
  if (!safe) return "";
  const parts = safe.split(/\n{2,}/).map((p) => p.replace(/\n/g, "<br/>"));
  return `<p>${parts.join("</p><p>")}</p>`;
}

function RichTextEditor(props: { value: string; onChange: (next: string) => void }) {
  const { value, onChange } = props;
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    if (ref.current.innerHTML !== value) {
      ref.current.innerHTML = value || "";
    }
  }, [value]);

  const exec = (cmd: string) => {
    if (document && typeof document.execCommand === "function") {
      document.execCommand(cmd, false);
    }
    ref.current?.focus();
  };

  return (
    <div className="pn-rt">
      <div className="pn-rtToolbar">
        <button className="pn-rtBtn" type="button" onClick={() => exec("bold")}>
          B
        </button>
        <button className="pn-rtBtn" type="button" onClick={() => exec("italic")}>
          I
        </button>
        <button className="pn-rtBtn" type="button" onClick={() => exec("underline")}>
          U
        </button>
        <button className="pn-rtBtn" type="button" onClick={() => exec("insertUnorderedList")}>
          •
        </button>
      </div>
      <div
        ref={ref}
        className="pn-rtEditor"
        contentEditable
        suppressContentEditableWarning
        onInput={() => onChange(ref.current?.innerHTML || "")}
      />
    </div>
  );
}

const DESC_DRAFT_KEY = "pim.productNew.descDraft.v1";

type DescDraft = {
  categoryId?: string;
  productType?: "single" | "multi";
  activeVariantKey?: string;
  variants: Record<string, { custom: string; selected: "restore" | "store77" | "custom" }>;
  updatedAt: number;
};

function canUseStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function readDescDraft(): DescDraft | null {
  if (!canUseStorage()) return null;
  try {
    const raw = window.localStorage.getItem(DESC_DRAFT_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as DescDraft;
  } catch {
    return null;
  }
}

function writeDescDraft(draft: DescDraft) {
  if (!canUseStorage()) return;
  try {
    window.localStorage.setItem(DESC_DRAFT_KEY, JSON.stringify(draft));
  } catch {
    return;
  }
}

function clearDescDraft() {
  if (!canUseStorage()) return;
  try {
    window.localStorage.removeItem(DESC_DRAFT_KEY);
  } catch {
    return;
  }
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

export default function ProductNew() {
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

  const [loadingData, setLoadingData] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  const [documents, setDocuments] = useState<ProductContent["documents"]>([]);
  const [analogs, setAnalogs] = useState<ProductContent["analogs"]>([]);
  const [related, setRelated] = useState<ProductContent["related"]>([]);

  const [pickerMode, setPickerMode] = useState<"analogs" | "related" | null>(null);

  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [created, setCreated] = useState<{ id: string; title: string } | null>(null);

  const draftAppliedRef = useRef(false);
  const draftTimerRef = useRef<number | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await getJson<CatalogNodesResp>(API_CATALOG_NODES);
        const nodes = res.nodes || [];
        const tree = buildTree(nodes);

        const mapFlat = new Map<string, CatalogNodeFlat>();
        for (const n of nodes) mapFlat.set(n.id, n);

        setCatalogTree(tree);
        setTreeById(indexTree(tree));
        setFlatById(mapFlat);
      } catch (e: any) {
        setCatalogErr(e?.message || "CATALOG_LOAD_FAILED");
      }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await getJson<TemplatesTreeResp>(API_TEMPLATES_TREE);
        const map = new Map<string, TemplateTreeNode>();
        for (const n of res.nodes || []) map.set(n.id, n);
        setTemplateTreeById(map);
      } catch {
        setTemplateTreeById(new Map());
      }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await getJson<AttributesListResp>(`${API_ATTRIBUTES}?limit=2000`);
        setGlobalAttrs(res.items || []);
      } catch {
        setGlobalAttrs([]);
      }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await getJson<{ items: DictionaryListItem[] }>(`${API_DICTIONARIES}?include_service=1`);
        setDictionaryItems(res.items || []);
      } catch {
        setDictionaryItems([]);
      }
    })();
  }, []);

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
    return (dictionaryItems || [])
      .filter((item) => !item?.meta?.service)
      .map((item) => {
        const id = (item.id || "").trim();
        const code = (item.code || id || "").trim();
        if (!id || !code) return null;
        return {
          attr_id: id,
          title: item.title || code,
          code,
          dict_id: id,
          options: [],
        } as VariantParam;
      })
      .filter(Boolean) as VariantParam[];
  }, [dictionaryItems, productType]);

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
          sku_id: "",
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
    const missing = next.filter((v) => !v.sku_pim || !v.sku_gt || !v.sku_id);
    if (!missing.length) return next;
    const triplets = await allocateSkus(missing.length);
    const tripletQueue = triplets.slice();
    return next.map((v) => {
      if (v.sku_pim && v.sku_gt && v.sku_id) return v;
      const t = tripletQueue.shift();
      if (!t) return v;
      return { ...v, sku_pim: t.sku_pim, sku_gt: t.sku_gt, sku_id: t.sku_id };
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
          sku_id: "",
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

  function updateVariantLink(key: string, idx: number, value: string) {
    setVariants((prev) =>
      prev.map((v) =>
        v.key === key ? { ...v, links: v.links.map((l, i) => (i === idx ? { ...l, url: value } : l)) } : v
      )
    );
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

  async function onLoadData() {
    setLoadErr(null);
    if (!templateId) {
      setLoadErr("Для категории нет мастер-шаблона.");
      return;
    }
    if (!variants.length) {
      setLoadErr("Сначала создайте варианты.");
      return;
    }

    setLoadingData(true);
    try {
      const mapping = await getJson<TemplateMappingResp>(`${API_COMP_MAPPING}/${encodeURIComponent(templateId)}`);
      const mapBySite = mapping.data?.mapping_by_site || { restore: {}, store77: {} };
      const priority = mapping.data?.priority_site || null;

      const results = await Promise.all(
        variants.map((v) =>
          postJson<CompetitorContentResp>(API_COMP_CONTENT_BATCH, {
            template_id: templateId,
            links: {
              restore: v.links.find((l) => l.source === "restore")?.url || "",
              store77: v.links.find((l) => l.source === "store77")?.url || "",
            },
          })
        )
      );

      setVariants((prev) =>
        prev.map((v, idx) => {
          const res = results[idx];
          const restore = res?.results?.restore || {};
          const store77 = res?.results?.store77 || {};

          const restoreSpecs = restore.specs || {};
          const storeSpecs = store77.specs || {};
          const restoreMapped = restore.mapped_specs || {};
          const storeMapped = store77.mapped_specs || {};

          const baseFields = mapping.master_fields?.length
            ? mapping.master_fields
            : templateAttrs.map((a) => ({
                code: a.code || "",
                name: a.name || a.code || "",
              }));

          const features = baseFields.reduce((acc, f) => {
            const code = (f.code || "").trim();
            if (!code) return acc;
            const rField = (mapBySite.restore || {})[code];
            const sField = (mapBySite.store77 || {})[code];
            const rVal = restoreMapped[code] || (rField ? pickSpecValue(restoreSpecs, rField) : "");
            const sVal = storeMapped[code] || (sField ? pickSpecValue(storeSpecs, sField) : "");
            const selected =
              priority === "store77"
                ? sVal
                  ? "store77"
                  : rVal
                  ? "restore"
                  : "custom"
                : rVal
                ? "restore"
                : sVal
                ? "store77"
                : "custom";
            const value = selected === "store77" ? sVal : selected === "restore" ? rVal : "";
            acc.push({
              code,
              name: f.name || code,
              restore: rVal,
              store77: sVal,
              selected,
              value,
            });
            return acc;
          }, [] as VariantContent["features"]);

          const images = uniqTrim([...(restore.images || []), ...(store77.images || [])]);
          const media = images.map((url) => ({ url }));

          const restoreDesc = restore.description || "";
          const storeDesc = store77.description || "";
          const selectedSource =
            priority === "store77"
              ? storeDesc
                ? "store77"
                : restoreDesc
                ? "restore"
                : "custom"
              : restoreDesc
              ? "restore"
              : storeDesc
              ? "store77"
              : "custom";
          const picked = selectedSource === "store77" ? storeDesc : selectedSource === "restore" ? restoreDesc : "";

          return {
            ...v,
            content: {
              features,
              media,
              description: {
                restore: restoreDesc,
                store77: storeDesc,
                selected: selectedSource,
                custom: picked || v.content.description.custom,
              },
            },
          };
        })
      );
    } catch (e: any) {
      setLoadErr(e?.message || "LOAD_FAILED");
    } finally {
      setLoadingData(false);
    }
  }

  function validateBeforeSave() {
    if (!title.trim()) return "Заполните название товара.";
    if (!categoryId.trim()) return "Выберите категорию.";
    if (!variants.length) return "Нет вариантов товара.";
    for (const v of variants) {
      const restore = v.links.find((l) => l.source === "restore")?.url || "";
      const store77 = v.links.find((l) => l.source === "store77")?.url || "";
      if (!restore || !store77) {
        return `Заполните ссылки для варианта: ${v.title}`;
      }
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
      const nextVariants = await ensureSkusForVariants(variants);
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
      setVariants(nextVariants);
      const vFirst = nextVariants[0];
      const payload: any = {
        category_id: categoryId,
        type: productType,
        title: normStr(title),
        selected_params: productType === "multi" ? selectedOrder : [],
        feature_params: [],
        exports_enabled: {},
      };
      if (productType === "single" && vFirst) {
        payload.sku_pim = vFirst.sku_pim;
        payload.sku_gt = vFirst.sku_gt;
        payload.sku_id = vFirst.sku_id;
      }

      let productId = created?.id || "";
      if (!productId) {
        const res = await postJson<{ product: { id: string; title: string } }>(API_PRODUCT_CREATE, payload);
        productId = res.product.id;
        setCreated({ id: res.product.id, title: res.product.title });
      }

      if (productId && !created) {
        await postJson(API_VARIANTS_BULK_CREATE, {
          product_id: productId,
          selected_params: selectedOrder,
          rows: nextVariants.map((v) => ({
            options: v.params,
            variant_key: v.key,
            enabled: true,
            sku: "",
            sku_pim: v.sku_pim,
            sku_gt: v.sku_gt,
            sku_id: v.sku_id,
            title: v.title,
            links: v.links,
            content: v.content,
          })),
        });
      }

      if (productId) {
        const vActive = nextVariants.find((v) => v.key === active?.key) || nextVariants[0];
        const content: ProductContent & { description?: string; media?: { url: string }[]; features?: any[] } = {
          documents,
          analogs,
          related,
        };
        if (productType === "single" && vActive) {
          content.description = vActive.content.description.custom || "";
          content.media = vActive.content.media;
          content.features = vActive.content.features.map((f) => ({ name: f.name, value: f.value }));
        }
        await patchJson(`${API_PRODUCT_PATCH}/${encodeURIComponent(productId)}`, { content });
        clearDescDraft();
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

  useEffect(() => {
    draftAppliedRef.current = false;
  }, [categoryId, productType]);

  useEffect(() => {
    if (draftAppliedRef.current) return;
    if (!variants.length || !categoryId) return;
    const draft = readDescDraft();
    if (!draft) return;
    if (draft.categoryId && draft.categoryId !== categoryId) return;
    if (draft.productType && draft.productType !== productType) return;
    setVariants((prev) =>
      prev.map((v) => {
        const d = draft.variants?.[v.key];
        if (!d) return v;
        return {
          ...v,
          content: {
            ...v.content,
            description: {
              ...v.content.description,
              custom: d.custom ?? v.content.description.custom,
              selected: d.selected ?? v.content.description.selected,
            },
          },
        };
      })
    );
    if (draft.activeVariantKey) {
      setActiveVariantKey(draft.activeVariantKey);
    }
    draftAppliedRef.current = true;
  }, [variants.length, categoryId, productType]);

  useEffect(() => {
    if (!variants.length || !categoryId) return;
    if (draftTimerRef.current) {
      window.clearTimeout(draftTimerRef.current);
    }
    draftTimerRef.current = window.setTimeout(() => {
      const variantDrafts: DescDraft["variants"] = {};
      for (const v of variants) {
        variantDrafts[v.key] = {
          custom: v.content.description.custom || "",
          selected: v.content.description.selected || "custom",
        };
      }
      writeDescDraft({
        categoryId,
        productType,
        activeVariantKey,
        variants: variantDrafts,
        updatedAt: Date.now(),
      });
    }, 500);
    return () => {
      if (draftTimerRef.current) {
        window.clearTimeout(draftTimerRef.current);
      }
    };
  }, [variants, categoryId, productType, activeVariantKey]);

  return (
    <div className="pn-wrap pn-page">
      <div className="pn-rightHeader">
        <div>
          <div className="pn-title">Создание товара</div>
          <div className="pn-sub">Полный сценарий создания карточки в PIM</div>
          {created && (
            <div className="pn-badges">
              <span className="pn-badge">ID: {created.id}</span>
            </div>
          )}
        </div>

        <div className="pn-actions">
          <Link className="pn-editBtn" to="/catalog">
            ← Каталог
          </Link>
          <button className="pn-saveBtn" onClick={onSaveAll} disabled={!canSave}>
            {saving ? <span className="pn-spinner" /> : <span className="pn-saveIcon">✓</span>}
            Сохранить товары
          </button>
        </div>
      </div>

      {catalogErr && (
        <div className="pn-card">
          <div className="pn-alert pn-alertBad">
            <div className="pn-alertTitle">Ошибка</div>
            <div className="pn-alertText">{catalogErr}</div>
          </div>
        </div>
      )}

      {saveErr && (
        <div className="pn-card">
          <div className="pn-alert pn-alertBad">
            <div className="pn-alertTitle">Ошибка сохранения</div>
            <div className="pn-alertText">{saveErr}</div>
          </div>
        </div>
      )}

      <div className="pn-section">
        <div className="pn-sectionHead">
          <div className="pn-sectionTitle">1. Категория и название</div>
          <div className="pn-sectionSub">Сначала выберите категорию и задайте название товара.</div>
        </div>
        <div className="pn-card">
          <div className="pn-form pn-formMain">
            <div className="pn-field">
              <div className="pn-label">Название товара</div>
              <input
                className="pn-input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Apple iPhone 17 Pro Max"
              />
            </div>
            <div className="pn-field">
              <div className="pn-label">Категория</div>
              <button className="pn-input pn-inputBtn" onClick={() => setCatModalOpen(true)} type="button">
                {categoryPath || "Выбрать категорию"}
              </button>
              {templateErr && <div className="pn-hint pn-hintWarn">{templateErr}</div>}
            </div>
          </div>
        </div>
      </div>

      <div className="pn-section">
        <div className="pn-sectionHead">
          <div className="pn-sectionTitle">2. Тип товара</div>
          <div className="pn-sectionSub">Одиночный товар или несколько вариантов.</div>
        </div>
        <div className="pn-card">
          <div className="pn-typeRow">
            <button
              className={`pn-pill ${productType === "single" ? "isActive" : ""}`}
              onClick={() => setProductType("single")}
              type="button"
            >
              Одиночный
            </button>
            <button
              className={`pn-pill ${productType === "multi" ? "isActive" : ""}`}
              onClick={() => setProductType("multi")}
              type="button"
            >
              С вариантами
            </button>
            <div className="pn-hint">Варианты нужны для цветов, памяти, размеров и т.д.</div>
          </div>
        </div>
      </div>

      <div className="pn-section">
        <div className="pn-sectionHead">
          <div className="pn-sectionTitle">3. Варианты</div>
          <div className="pn-sectionSub">Выбор параметров из мастер-шаблона и генерация вариантов.</div>
        </div>
        <div className="pn-card">
          {productType === "single" && (
            <div className="pn-variantSingle">
              <div className="pn-variantTitle">{variants[0]?.title || "Товар"}</div>
              <div className="pn-variantSkus">
                <span>ПИМ: {variants[0]?.sku_pim || "—"}</span>
                <span>GT: {variants[0]?.sku_gt || "—"}</span>
                <span>IDS: {variants[0]?.sku_id || "—"}</span>
              </div>
            </div>
          )}

          {productType === "multi" && (
            <>
              <div className="pn-variantActions">
                <button
                  className="pn-editBtn"
                  onClick={() => setParamModalOpen(true)}
                  type="button"
                  disabled={!templateId || !hasVariantParams}
                >
                  Выбрать параметры
                </button>
                <button
                  className="pn-saveBtn"
                  onClick={onGenerateVariants}
                  type="button"
                  disabled={!canGenerateVariants || !hasVariantParams}
                >
                  Сгенерировать варианты
                </button>
              </div>
              {!templateId && <div className="pn-hint pn-hintWarn">Сначала выберите категорию с мастер-шаблоном.</div>}
              {templateId && !hasVariantParams && (
                <div className="pn-hint pn-hintWarn">Нет доступных параметров для вариантов.</div>
              )}
              {selectedOrder.length > 0 && (
                <div className="pn-tags">
                  {selectedOrder.map((id) => (
                    <span key={id} className="pn-tag">
                      {id}
                    </span>
                  ))}
                </div>
              )}

              {variantErr && <div className="pn-hint pn-hintWarn">{variantErr}</div>}

              <div className="pn-variantGrid">
                {!variants.length && <div className="pn-muted">Варианты ещё не сгенерированы.</div>}
                {variants.map((v) => (
                  <div key={v.key} className="pn-variantCard">
                    <div className="pn-variantTitle">{v.title}</div>
                    <div className="pn-variantSkus">
                      <span>ПИМ: {v.sku_pim || "—"}</span>
                      <span>GT: {v.sku_gt || "—"}</span>
                      <span>IDS: {v.sku_id || "—"}</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="pn-section">
        <div className="pn-sectionHead">
          <div className="pn-sectionTitle">4. Ссылки конкурентов и загрузка данных</div>
          <div className="pn-sectionSub">Укажите ссылки re-store и store77, затем загрузите характеристики, медиа и описание.</div>
        </div>
        <div className="pn-card">
          {variants.map((v) => (
            <div key={v.key} className="pn-linkBlock">
              <div className="pn-linkHead">
                <div className="pn-variantTitle">{v.title}</div>
                <div className="pn-variantSkus">
                  <span>ПИМ: {v.sku_pim || "—"}</span>
                  <span>GT: {v.sku_gt || "—"}</span>
                  <span>IDS: {v.sku_id || "—"}</span>
                </div>
              </div>
              <div className="pn-form pn-formLinks">
                <div className="pn-field">
                  <div className="pn-label">re-store</div>
                  <input
                    className="pn-input"
                    value={v.links.find((l) => l.source === "restore")?.url || ""}
                    onChange={(e) => updateVariantLink(v.key, 0, e.target.value)}
                    placeholder="https://re-store.ru/..."
                  />
                </div>
                <div className="pn-field">
                  <div className="pn-label">store77</div>
                  <input
                    className="pn-input"
                    value={v.links.find((l) => l.source === "store77")?.url || ""}
                    onChange={(e) => updateVariantLink(v.key, 1, e.target.value)}
                    placeholder="https://store77.net/..."
                  />
                </div>
              </div>
            </div>
          ))}

          {loadErr && (
            <div className="pn-alert pn-alertBad" style={{ marginTop: 12 }}>
              <div className="pn-alertTitle">Ошибка</div>
              <div className="pn-alertText">{loadErr}</div>
            </div>
          )}
          <div style={{ marginTop: 12 }}>
            <button className="pn-saveBtn" onClick={onLoadData} type="button" disabled={loadingData}>
              {loadingData ? <span className="pn-spinner" /> : <span className="pn-saveIcon">⇩</span>}
              Загрузить данные
            </button>
            <div className="pn-hint">Нужен настроенный мэппинг мастер-шаблона.</div>
          </div>
        </div>
      </div>

      <div className="pn-section">
        <div className="pn-sectionHead">
          <div className="pn-sectionTitle">5. Характеристики</div>
          <div className="pn-sectionSub">Заполненные характеристики по мэппингу.</div>
        </div>
        <div className="pn-card">
          {variants.length > 1 && (
            <div className="pn-variantPicker">
              <div className="pn-label">Вариант</div>
              <select
                className="pn-select"
                value={active?.key || ""}
                onChange={(e) => setActiveVariantKey(e.target.value)}
              >
                {variants.map((v) => (
                  <option key={v.key} value={v.key}>
                    {v.title}
                  </option>
                ))}
              </select>
            </div>
          )}

          {!active?.content.features.length && <div className="pn-muted">Пока нет характеристик.</div>}
          {!!active?.content.features.length && (
            <div className="pn-featureTable">
              <div className="pn-featureHeader">
                <div>Параметр</div>
                <div>Re-Store</div>
                <div>Store77</div>
                <div>Выбор</div>
                <div>PIM</div>
              </div>
              {active.content.features.map((f, idx) => (
                <div key={`${f.code}-${idx}`} className="pn-featureRow">
                  <div className="pn-featureName">
                    <span>{f.name}</span>
                    {!!f?.conflict?.active && (
                      <span
                        className="pn-conflictBadge"
                        title={`Расхождение значений между магазинами Я.Маркета: ${((f?.conflict?.variants || []) as Array<any>).map((x) => `${x.store_title || x.store_id}: ${x.value}`).join(" | ")}`}
                      >
                        !
                      </span>
                    )}
                  </div>
                  <div className="pn-featureVal">{f.restore || "—"}</div>
                  <div className="pn-featureVal">{f.store77 || "—"}</div>
                  <div className="pn-featurePick">
                    <label>
                      <input
                        type="checkbox"
                        checked={f.selected === "restore"}
                        onChange={() => {
                          const next = active.content.features.map((row, i) =>
                            i === idx
                              ? { ...row, selected: "restore", value: row.restore || row.value }
                              : row
                          );
                          updateActiveVariantContent({ features: next });
                        }}
                      />
                      Re-Store
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={f.selected === "store77"}
                        onChange={() => {
                          const next = active.content.features.map((row, i) =>
                            i === idx
                              ? { ...row, selected: "store77", value: row.store77 || row.value }
                              : row
                          );
                          updateActiveVariantContent({ features: next });
                        }}
                      />
                      Store77
                    </label>
                  </div>
                  <input
                    className="pn-input"
                    value={f.value}
                    onChange={(e) => {
                      const next = active.content.features.map((row, i) =>
                        i === idx ? { ...row, selected: "custom", value: e.target.value } : row
                      );
                      updateActiveVariantContent({ features: next });
                    }}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="pn-section">
        <div className="pn-sectionHead">
          <div className="pn-sectionTitle">6. Медиа</div>
          <div className="pn-sectionSub">Все изображения из источников.</div>
        </div>
        <div className="pn-card">
          {!active?.content.media.length && <div className="pn-muted">Пока нет изображений.</div>}
          {!!active?.content.media.length && (
            <div className="pn-mediaGrid">
              {active.content.media.map((m, idx) => (
                <div key={`${m.url}-${idx}`} className="pn-mediaCard">
                  <img src={toRenderableMediaUrl(m.url)} alt="" />
                  <button
                    className="pn-iconBtn"
                    type="button"
                    onClick={() => {
                      const next = active.content.media.filter((_, i) => i !== idx);
                      updateActiveVariantContent({ media: next });
                    }}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="pn-hint">Можно удалить лишние изображения перед сохранением.</div>
        </div>
      </div>

      <div className="pn-section">
        <div className="pn-sectionHead">
          <div className="pn-sectionTitle">7. Описание</div>
          <div className="pn-sectionSub">Выберите источник и при необходимости отредактируйте.</div>
        </div>
        <div className="pn-card">
          {active && (
            <>
              <div className="pn-descSources">
                <button
                  className={`pn-pill ${active.content.description.selected === "restore" ? "isActive" : ""}`}
                  type="button"
                  onClick={() =>
                    updateActiveDescription({
                      selected: "restore",
                      custom: textToHtml(active.content.description.restore || ""),
                    })
                  }
                  disabled={!active.content.description.restore}
                >
                  re-store
                </button>
                <button
                  className={`pn-pill ${active.content.description.selected === "store77" ? "isActive" : ""}`}
                  type="button"
                  onClick={() =>
                    updateActiveDescription({
                      selected: "store77",
                      custom: textToHtml(active.content.description.store77 || ""),
                    })
                  }
                  disabled={!active.content.description.store77}
                >
                  store77
                </button>
                <button
                  className={`pn-pill ${active.content.description.selected === "custom" ? "isActive" : ""}`}
                  type="button"
                  onClick={() => updateActiveDescription({ selected: "custom" })}
                >
                  Своё
                </button>
              </div>
              <RichTextEditor
                value={active.content.description.custom}
                onChange={(next) =>
                  updateActiveDescription({
                    selected: "custom",
                    custom: next,
                  })
                }
              />
            </>
          )}
        </div>
      </div>

      <div className="pn-section">
        <div className="pn-sectionHead">
          <div className="pn-sectionTitle">8. Документы</div>
          <div className="pn-sectionSub">Инструкции, сертификаты, гарантия.</div>
        </div>
        <div className="pn-card">
          {documents.map((d, idx) => (
            <div key={idx} className="pn-docRow">
              <input
                className="pn-input"
                value={d.name}
                onChange={(e) => {
                  const next = documents.slice();
                  next[idx] = { ...next[idx], name: e.target.value };
                  setDocuments(next);
                }}
                placeholder="Название документа"
              />
              <input
                className="pn-input"
                value={d.url}
                onChange={(e) => {
                  const next = documents.slice();
                  next[idx] = { ...next[idx], url: e.target.value };
                  setDocuments(next);
                }}
                placeholder="https://..."
              />
              <button
                className="pn-iconBtn"
                type="button"
                onClick={() => setDocuments((prev) => prev.filter((_, i) => i !== idx))}
              >
                ✕
              </button>
            </div>
          ))}
          <button
            className="pn-editBtn"
            type="button"
            onClick={() => setDocuments((prev) => [...prev, { name: "", url: "" }])}
          >
            ＋ Добавить документ
          </button>
        </div>
      </div>

      <div className="pn-section">
        <div className="pn-sectionHead">
          <div className="pn-sectionTitle">9. Аналоги</div>
          <div className="pn-sectionSub">Подберите аналоги из каталога.</div>
        </div>
        <div className="pn-card">
          {!analogs.length && <div className="pn-muted">Аналоги не выбраны.</div>}
          {analogs.map((a, idx) => (
            <div key={`${a.sku}-${idx}`} className="pn-relRow">
              <div>
                <div className="pn-relName">{a.name}</div>
                <div className="pn-relMeta">ID: {a.sku}</div>
              </div>
              <button
                className="pn-iconBtn"
                type="button"
                onClick={() => setAnalogs((prev) => prev.filter((_, i) => i !== idx))}
              >
                ✕
              </button>
            </div>
          ))}
          <button className="pn-editBtn" type="button" onClick={() => setPickerMode("analogs")}>
            ＋ Добавить аналог
          </button>
        </div>
      </div>

      <div className="pn-section">
        <div className="pn-sectionHead">
          <div className="pn-sectionTitle">10. Сопутствующие товары</div>
          <div className="pn-sectionSub">Cross-sell — аксессуары и доп. товары.</div>
        </div>
        <div className="pn-card">
          {!related.length && <div className="pn-muted">Сопутствующие товары не выбраны.</div>}
          {related.map((r, idx) => (
            <div key={`${r.sku}-${idx}`} className="pn-relRow">
              <div>
                <div className="pn-relName">{r.name}</div>
                <div className="pn-relMeta">ID: {r.sku}</div>
              </div>
              <button
                className="pn-iconBtn"
                type="button"
                onClick={() => setRelated((prev) => prev.filter((_, i) => i !== idx))}
              >
                ✕
              </button>
            </div>
          ))}
          <button className="pn-editBtn" type="button" onClick={() => setPickerMode("related")}>
            ＋ Добавить сопутствующий
          </button>
        </div>
      </div>

      <div className="pn-footerActions">
        <button className="pn-saveBtn" onClick={onSaveAll} disabled={!canSave}>
          {saving ? <span className="pn-spinner" /> : <span className="pn-saveIcon">✓</span>}
          Сохранить товары
        </button>
        {created && (
          <Link className="pn-editBtn" to={`/product/${created.id}`}>
            Перейти к товару
          </Link>
        )}
      </div>

      <CategoryModal
        open={catModalOpen}
        roots={catalogTree}
        treeById={treeById}
        flatById={flatById}
        selectedId={categoryId}
        onPickLeaf={selectCategory}
        onClose={() => setCatModalOpen(false)}
      />

      <ParamPickerModal
        open={paramModalOpen}
        params={paramDefs}
        initialOrder={selectedOrder}
        initialValues={selectedValues}
        onApply={(res) => {
          setSelectedOrder(res.selectedOrder);
          setSelectedValues(res.selectedValues);
        }}
        onClose={() => setParamModalOpen(false)}
      />

      <CatalogProductPickerModal
        open={pickerMode !== null}
        title={pickerMode === "analogs" ? "Добавить аналоги" : "Добавить сопутствующие товары"}
        roots={catalogTree}
        treeById={treeById}
        flatById={flatById}
        initialSelected={
          pickerMode === "analogs"
            ? analogs.map((a) => ({ id: a.sku, name: a.name }))
            : related.map((r) => ({ id: r.sku, name: r.name }))
        }
        onApply={(items) => {
          if (pickerMode === "analogs") {
            setAnalogs(items.map((i) => ({ sku: i.id, name: i.name })));
          } else if (pickerMode === "related") {
            setRelated(items.map((i) => ({ sku: i.id, name: i.name })));
          }
        }}
        onClose={() => setPickerMode(null)}
      />
    </div>
  );
}
