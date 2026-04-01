import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import "../styles/products-list.css";

type ProductItem = {
  id: string;
  title?: string;
  name?: string;
  category_id: string;
  sku_gt?: string;
  sku_id?: string;
  group_id?: string;
  exports_enabled?: Record<string, boolean>;
};

type CatalogNode = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
};

type GroupItem = {
  id: string;
  name: string;
};

type TemplateItem = {
  id: string;
  category_id?: string | null;
  name: string;
};

type TemplateNode = {
  id: string;
  parent_id: string | null;
  template_id?: string | null;
};

function qnorm(s: string) {
  return (s || "").trim().toLowerCase();
}

function gtSortKey(value?: string) {
  const v = String(value || "").trim();
  if (!v) return [1, Number.MAX_SAFE_INTEGER, ""] as const;
  if (v.match(/^\d+$/)) return [0, Number(v), v] as const;
  return [0, Number.MAX_SAFE_INTEGER, v.toLowerCase()] as const;
}

export default function ProductsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [products, setProducts] = useState<ProductItem[]>([]);
  const [nodes, setNodes] = useState<CatalogNode[]>([]);
  const [groups, setGroups] = useState<GroupItem[]>([]);
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [templateNodes, setTemplateNodes] = useState<TemplateNode[]>([]);

  const [query, setQueryState] = useState(searchParams.get("q") || "");
  const [parentCategoryId, setParentCategoryIdState] = useState(searchParams.get("parent") || "");
  const [subCategoryId, setSubCategoryIdState] = useState(searchParams.get("sub") || "");
  const [groupFilter, setGroupFilterState] = useState(searchParams.get("group") || "");
  const [templateFilter, setTemplateFilterState] = useState(searchParams.get("template") || "");
  const [marketFilter, setMarketFilterState] = useState<"all" | "on" | "off">(
    searchParams.get("ym") === "on" || searchParams.get("ym") === "off" ? (searchParams.get("ym") as "on" | "off") : "all"
  );
  const [ozonFilter, setOzonFilterState] = useState<"all" | "on" | "off">(
    searchParams.get("oz") === "on" || searchParams.get("oz") === "off" ? (searchParams.get("oz") as "on" | "off") : "all"
  );

  useEffect(() => {
    setQueryState(searchParams.get("q") || "");
    setParentCategoryIdState(searchParams.get("parent") || "");
    setSubCategoryIdState(searchParams.get("sub") || "");
    setGroupFilterState(searchParams.get("group") || "");
    setTemplateFilterState(searchParams.get("template") || "");
    setMarketFilterState(
      searchParams.get("ym") === "on" || searchParams.get("ym") === "off" ? (searchParams.get("ym") as "on" | "off") : "all"
    );
    setOzonFilterState(
      searchParams.get("oz") === "on" || searchParams.get("oz") === "off" ? (searchParams.get("oz") as "on" | "off") : "all"
    );
  }, [searchParams]);

  function updateFilters(patch: Partial<{
    q: string;
    parent: string;
    sub: string;
    group: string;
    template: string;
    ym: "all" | "on" | "off";
    oz: "all" | "on" | "off";
  }>) {
    const next = new URLSearchParams(searchParams);
    const apply = (key: string, value: string) => {
      if (value) next.set(key, value);
      else next.delete(key);
    };
    if (patch.q !== undefined) apply("q", patch.q);
    if (patch.parent !== undefined) apply("parent", patch.parent);
    if (patch.sub !== undefined) apply("sub", patch.sub);
    if (patch.group !== undefined) apply("group", patch.group);
    if (patch.template !== undefined) apply("template", patch.template);
    if (patch.ym !== undefined) patch.ym === "all" ? next.delete("ym") : next.set("ym", patch.ym);
    if (patch.oz !== undefined) patch.oz === "all" ? next.delete("oz") : next.set("oz", patch.oz);
    setSearchParams(next, { replace: true });
  }

  function setQuery(value: string) {
    setQueryState(value);
    updateFilters({ q: value });
  }

  function setParentCategoryId(value: string) {
    setParentCategoryIdState(value);
    setSubCategoryIdState("");
    updateFilters({ parent: value, sub: "" });
  }

  function setSubCategoryId(value: string) {
    setSubCategoryIdState(value);
    updateFilters({ sub: value });
  }

  function setGroupFilter(value: string) {
    setGroupFilterState(value);
    updateFilters({ group: value });
  }

  function setTemplateFilter(value: string) {
    setTemplateFilterState(value);
    updateFilters({ template: value });
  }

  function setMarketFilter(value: "all" | "on" | "off") {
    setMarketFilterState(value);
    updateFilters({ ym: value });
  }

  function setOzonFilter(value: "all" | "on" | "off") {
    setOzonFilterState(value);
    updateFilters({ oz: value });
  }

  async function load() {
    setLoading(true);
    setLoadError("");
    try {
      const [p, n, g, t, tt] = await Promise.allSettled([
        api<{ items: ProductItem[] }>("/catalog/products"),
        api<{ nodes: CatalogNode[] }>("/catalog/nodes"),
        api<{ items: GroupItem[] }>("/product-groups"),
        api<{ ok?: boolean; items: TemplateItem[] }>("/templates/list"),
        api<{ nodes: TemplateNode[] }>("/templates/tree"),
      ]);
      setProducts(p.status === "fulfilled" ? (p.value.items || []) : []);
      setNodes(n.status === "fulfilled" ? (n.value.nodes || []) : []);
      setGroups(g.status === "fulfilled" ? (g.value.items || []) : []);
      setTemplates(t.status === "fulfilled" ? (t.value.items || []) : []);
      setTemplateNodes(tt.status === "fulfilled" ? (tt.value.nodes || []) : []);
      const failed = [p, n, g, t, tt].filter((x) => x.status === "rejected").length;
      if (failed > 0) setLoadError(`Часть данных не загрузилась (${failed}).`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const nodeById = useMemo(() => {
    const m = new Map<string, CatalogNode>();
    for (const n of nodes || []) m.set(n.id, n);
    return m;
  }, [nodes]);

  const childrenByParent = useMemo(() => {
    const m = new Map<string, CatalogNode[]>();
    for (const n of nodes || []) {
      const pid = n.parent_id || "";
      const arr = m.get(pid) || [];
      arr.push(n);
      m.set(pid, arr);
    }
    for (const arr of m.values()) {
      arr.sort((a, b) => {
        if ((a.position || 0) !== (b.position || 0)) return (a.position || 0) - (b.position || 0);
        return (a.name || "").localeCompare(b.name || "", "ru");
      });
    }
    return m;
  }, [nodes]);

  const groupNameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const g of groups || []) m.set(String(g.id || ""), String(g.name || ""));
    return m;
  }, [groups]);

  const templateNameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const t of templates || []) m.set(String(t.id || ""), String(t.name || ""));
    return m;
  }, [templates]);

  const templateIdByCategory = useMemo(() => {
    const m = new Map<string, string>();
    for (const n of templateNodes || []) {
      const cid = String(n.id || "");
      const tid = String(n.template_id || "");
      if (cid && tid) m.set(cid, tid);
    }
    return m;
  }, [templateNodes]);

  function categoryBreadcrumbs(categoryId: string) {
    const chain: string[] = [];
    const seen = new Set<string>();
    let cur = nodeById.get(categoryId);
    while (cur && !seen.has(cur.id)) {
      seen.add(cur.id);
      chain.push(cur.name || cur.id);
      cur = cur.parent_id ? nodeById.get(cur.parent_id) : undefined;
    }
    return chain.reverse().join(" / ");
  }

  function collectSubtreeIds(rootId: string) {
    if (!rootId) return null;
    const out = new Set<string>();
    const stack = [rootId];
    while (stack.length) {
      const cid = stack.pop() as string;
      if (!cid || out.has(cid)) continue;
      out.add(cid);
      const children = childrenByParent.get(cid) || [];
      for (const ch of children) stack.push(ch.id);
    }
    return out;
  }

  function effectiveTemplateRef(categoryId: string): { templateId: string; templateName: string; sourceCategoryId: string } {
    let curId = String(categoryId || "");
    const seen = new Set<string>();
    while (curId && !seen.has(curId)) {
      seen.add(curId);
      const tid = templateIdByCategory.get(curId);
      if (tid) {
        return {
          templateId: tid,
          templateName: templateNameById.get(tid) || tid,
          sourceCategoryId: curId,
        };
      }
      const node = nodeById.get(curId);
      curId = node?.parent_id || "";
    }
    return { templateId: "", templateName: "", sourceCategoryId: "" };
  }

  const rootCategories = useMemo(() => {
    return (childrenByParent.get("") || []).map((n) => ({ id: n.id, name: n.name }));
  }, [childrenByParent]);

  const subCategories = useMemo(() => {
    if (!parentCategoryId) return [] as Array<{ id: string; name: string; path: string }>;
    const list: Array<{ id: string; name: string; path: string }> = [];
    const stack = [...(childrenByParent.get(parentCategoryId) || [])];
    while (stack.length) {
      const n = stack.shift() as CatalogNode;
      list.push({ id: n.id, name: n.name, path: categoryBreadcrumbs(n.id) });
      const ch = childrenByParent.get(n.id) || [];
      for (const c of ch) stack.push(c);
    }
    list.sort((a, b) => a.path.localeCompare(b.path, "ru"));
    return list;
  }, [parentCategoryId, childrenByParent, nodeById]);

  const filtered = useMemo(() => {
    const q = qnorm(query);
    const byParent = collectSubtreeIds(parentCategoryId);
    const bySub = collectSubtreeIds(subCategoryId);
    return (products || [])
      .filter((p) => {
        const cid = String(p.category_id || "");
        if (byParent && !byParent.has(cid)) return false;
        if (bySub && !bySub.has(cid)) return false;
        const gid = String(p.group_id || "").trim();
        if (groupFilter === "__ungrouped__" && gid) return false;
        if (groupFilter && groupFilter !== "__ungrouped__" && gid !== groupFilter) return false;
        const tref = effectiveTemplateRef(cid);
        if (templateFilter === "__without__" && tref.templateId) return false;
        if (templateFilter && templateFilter !== "__without__" && tref.templateId !== templateFilter) return false;
        const ym = !!p.exports_enabled?.yandex_market;
        const oz = !!p.exports_enabled?.ozon;
        if (marketFilter === "on" && !ym) return false;
        if (marketFilter === "off" && ym) return false;
        if (ozonFilter === "on" && !oz) return false;
        if (ozonFilter === "off" && oz) return false;
        if (!q) return true;
        return [p.title || p.name || "", p.sku_gt || "", p.sku_id || "", categoryBreadcrumbs(cid)]
          .join(" ")
          .toLowerCase()
          .includes(q);
      })
      .sort((a, b) => {
        const ka = gtSortKey(a.sku_gt);
        const kb = gtSortKey(b.sku_gt);
        if (ka[0] !== kb[0]) return ka[0] - kb[0];
        if (ka[1] !== kb[1]) return ka[1] - kb[1];
        if (ka[2] !== kb[2]) return ka[2].localeCompare(kb[2], "ru");
        return String(a.title || a.name || "").localeCompare(String(b.title || b.name || ""), "ru");
      });
  }, [products, query, parentCategoryId, subCategoryId, groupFilter, templateFilter, marketFilter, ozonFilter, childrenByParent, nodeById, templateIdByCategory, templateNameById]);

  const groupOptions = useMemo(() => {
    const ids = new Set((products || []).map((p) => String(p.group_id || "").trim()).filter(Boolean));
    const out = (groups || [])
      .filter((g) => ids.has(String(g.id || "")))
      .map((g) => ({ id: String(g.id || ""), name: String(g.name || "") }))
      .sort((a, b) => a.name.localeCompare(b.name, "ru"));
    return out;
  }, [groups, products]);

  const templateOptions = useMemo(() => {
    const ids = new Set<string>();
    for (const p of products || []) {
      const tref = effectiveTemplateRef(String(p.category_id || ""));
      if (tref.templateId) ids.add(tref.templateId);
    }
    return (templates || [])
      .filter((t) => ids.has(String(t.id || "")))
      .map((t) => ({ id: String(t.id || ""), name: String(t.name || "") }))
      .sort((a, b) => a.name.localeCompare(b.name, "ru"));
  }, [templates, products, templateIdByCategory, templateNameById, nodeById]);

  return (
    <div className="products-page page-shell">
      <div className="page-header">
        <div className="page-header-main">
          <div className="page-title">Товары</div>
          <div className="page-subtitle">Список товаров и статусы подготовки к выгрузке.</div>
        </div>
        <div className="page-header-actions">
          <Link className="btn primary" to="/products/new">Добавить товар</Link>
          <button className="btn" type="button" onClick={() => void load()} disabled={loading}>
            {loading ? "Обновляю..." : "Обновить"}
          </button>
        </div>
      </div>

      {loadError ? (
        <div className="card" style={{ color: "#b42318", fontWeight: 700 }}>{loadError}</div>
      ) : null}

      <div className="card products-filters">
        <input
          className="pn-input"
          placeholder="Поиск по товару, GT ID, IDs ID..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select className="pn-input" value={parentCategoryId} onChange={(e) => setParentCategoryId(e.target.value)}>
          <option value="">Все категории</option>
          {rootCategories.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <select
          className="pn-input"
          value={subCategoryId}
          onChange={(e) => setSubCategoryId(e.target.value)}
          disabled={!parentCategoryId}
        >
          <option value="">Все подкатегории</option>
          {subCategories.map((c) => (
            <option key={c.id} value={c.id}>{c.path}</option>
          ))}
        </select>
        <select className="pn-input" value={groupFilter} onChange={(e) => setGroupFilter(e.target.value)}>
          <option value="">Все группы</option>
          <option value="__ungrouped__">Без группы</option>
          {groupOptions.map((g) => (
            <option key={g.id} value={g.id}>{g.name}</option>
          ))}
        </select>
        <select className="pn-input" value={templateFilter} onChange={(e) => setTemplateFilter(e.target.value)}>
          <option value="">Все мастер-файлы</option>
          <option value="__without__">Без мастер-файла</option>
          {templateOptions.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
        <select className="pn-input" value={marketFilter} onChange={(e) => setMarketFilter(e.target.value as "all" | "on" | "off")}>
          <option value="all">Я.Маркет: все</option>
          <option value="on">Я.Маркет: включено</option>
          <option value="off">Я.Маркет: выключено</option>
        </select>
        <select className="pn-input" value={ozonFilter} onChange={(e) => setOzonFilter(e.target.value as "all" | "on" | "off")}>
          <option value="all">OZON: все</option>
          <option value="on">OZON: включено</option>
          <option value="off">OZON: выключено</option>
        </select>
        <div className="muted">Найдено: <b>{filtered.length}</b></div>
      </div>

      <div className="card products-tableWrap">
        <table className="products-table">
          <thead>
            <tr>
              <th rowSpan={2}>Наименование товара</th>
              <th rowSpan={2}>Входит в группу</th>
              <th rowSpan={2}>Мастер-файл</th>
              <th colSpan={2}>Площадки</th>
            </tr>
            <tr>
              <th>Я.Маркет</th>
              <th>OZON</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => {
              const title = String(p.title || p.name || "").trim() || p.id;
              const breadcrumbs = categoryBreadcrumbs(String(p.category_id || ""));
              const gid = String(p.group_id || "").trim();
              const gname = gid ? (groupNameById.get(gid) || gid) : "";
              const tref = effectiveTemplateRef(String(p.category_id || ""));
              const exportYM = !!p.exports_enabled?.yandex_market;
              const exportOzon = !!p.exports_enabled?.ozon;
              return (
                <tr key={p.id}>
                  <td>
                    <Link to={`/products/${encodeURIComponent(p.id)}`} className="products-titleLink">{title}</Link>
                    <div className="products-breadcrumbs">{breadcrumbs}</div>
                  </td>
                  <td>
                    {gname ? <Link to={`/catalog/groups?group=${encodeURIComponent(gid)}`} className="products-cellLink">{gname}</Link> : <span className="muted">Без группы</span>}
                  </td>
                  <td>
                    {tref.templateName ? (
                      <Link to={`/templates/${encodeURIComponent(tref.sourceCategoryId)}`} className="products-cellLink">
                        {tref.templateName}
                      </Link>
                    ) : (
                      <span className="muted">Не назначен</span>
                    )}
                  </td>
                  <td>
                    <span className={`products-status ${exportYM ? "isOn" : ""}`}>{exportYM ? "Да" : "Нет"}</span>
                  </td>
                  <td>
                    <span className={`products-status ${exportOzon ? "isOn" : ""}`}>{exportOzon ? "Да" : "Нет"}</span>
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={5} className="products-empty">Товары не найдены</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
