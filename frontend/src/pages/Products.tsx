import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import "../styles/products-list.css";

type ProductItem = {
  id: string;
  title?: string;
  name?: string;
  category_id: string;
  category_path?: string;
  preview_url?: string;
  sku_gt?: string;
  group_id?: string;
  group_name?: string;
  exports_enabled?: Record<string, boolean>;
  marketplace_statuses?: Record<string, { status?: string; present?: boolean }>;
  effective_template_id?: string;
  effective_template_name?: string;
  effective_template_source_category_id?: string;
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

type ProductsPageDataResp = {
  ok?: boolean;
  products: ProductItem[];
  total: number;
  page: number;
  page_size: number;
  nodes: CatalogNode[];
  groups: GroupItem[];
  templates: TemplateItem[];
};

const DEFAULT_PAGE_SIZE = 50;

function productStatusTone(status: string, present: boolean): "" | "isOn" {
  const normalized = String(status || "").trim().toLowerCase();
  if (!present) return "";
  if (normalized.includes("ошибка") || normalized.includes("отклон") || normalized.includes("нет карточки")) return "";
  return "isOn";
}

export default function ProductsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [searchDraft, setSearchDraft] = useState(searchParams.get("q") || "");
  const [products, setProducts] = useState<ProductItem[]>([]);
  const [nodes, setNodes] = useState<CatalogNode[]>([]);
  const [groups, setGroups] = useState<GroupItem[]>([]);
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const query = searchParams.get("q") || "";
  const parentCategoryId = searchParams.get("parent") || "";
  const subCategoryId = searchParams.get("sub") || "";
  const groupFilter = searchParams.get("group") || "";
  const templateFilter = searchParams.get("template") || "";
  const marketFilter = searchParams.get("ym") === "on" || searchParams.get("ym") === "off" ? (searchParams.get("ym") as "on" | "off") : "all";
  const ozonFilter = searchParams.get("oz") === "on" || searchParams.get("oz") === "off" ? (searchParams.get("oz") as "on" | "off") : "all";
  const viewFilter = ["all", "issues", "no_template", "no_ym", "no_oz"].includes(searchParams.get("view") || "")
    ? (searchParams.get("view") as "all" | "issues" | "no_template" | "no_ym" | "no_oz") || "all"
    : "all";
  const currentPage = Math.max(1, Number(searchParams.get("page") || "1") || 1);

  useEffect(() => {
    setSearchDraft(query);
  }, [query]);

  function updateFilters(
    patch: Partial<{
      q: string;
      parent: string;
      sub: string;
      group: string;
      template: string;
      ym: "all" | "on" | "off";
      oz: "all" | "on" | "off";
      view: "all" | "issues" | "no_template" | "no_ym" | "no_oz";
      page: number;
    }>,
  ) {
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
    if (patch.view !== undefined) patch.view === "all" ? next.delete("view") : next.set("view", patch.view);
    if (patch.page !== undefined) {
      if (patch.page > 1) next.set("page", String(patch.page));
      else next.delete("page");
    }
    setSearchParams(next, { replace: true });
  }

  async function load() {
    setLoading(true);
    setLoadError("");
    try {
      const params = new URLSearchParams();
      if (query) params.set("q", query);
      if (parentCategoryId) params.set("parent", parentCategoryId);
      if (subCategoryId) params.set("sub", subCategoryId);
      if (groupFilter) params.set("group", groupFilter);
      if (templateFilter) params.set("template", templateFilter);
      if (marketFilter !== "all") params.set("ym", marketFilter);
      if (ozonFilter !== "all") params.set("oz", ozonFilter);
      if (viewFilter !== "all") params.set("view", viewFilter);
      params.set("page", String(currentPage));
      params.set("page_size", String(DEFAULT_PAGE_SIZE));

      const data = await api<ProductsPageDataResp>(`/catalog/products-page-data?${params.toString()}`);
      setProducts(Array.isArray(data.products) ? data.products : []);
      setNodes(Array.isArray(data.nodes) ? data.nodes : []);
      setGroups(Array.isArray(data.groups) ? data.groups : []);
      setTemplates(Array.isArray(data.templates) ? data.templates : []);
      setTotal(Math.max(0, Number(data.total || 0)));
      setPageSize(Math.max(1, Number(data.page_size || DEFAULT_PAGE_SIZE)));
    } catch (e) {
      setLoadError((e as Error).message || "Не удалось загрузить список товаров");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [query, parentCategoryId, subCategoryId, groupFilter, templateFilter, marketFilter, ozonFilter, viewFilter, currentPage]);

  useEffect(() => {
    const next = searchDraft.trim();
    if (next === query) return;
    const t = window.setTimeout(() => {
      updateFilters({ q: next, page: 1 });
    }, 260);
    return () => window.clearTimeout(t);
  }, [searchDraft, query]);

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

  const rootCategories = useMemo(() => {
    return (childrenByParent.get("") || []).map((n) => ({ id: n.id, name: n.name }));
  }, [childrenByParent]);

  const nodeById = useMemo(() => {
    const map = new Map<string, CatalogNode>();
    for (const n of nodes || []) map.set(String(n.id || ""), n);
    return map;
  }, [nodes]);

  const subCategories = useMemo(() => {
    if (!parentCategoryId) return [] as Array<{ id: string; name: string; path: string }>;
    const pathCache = new Map<string, string>();
    const buildPath = (categoryId: string): string => {
      if (!categoryId) return "";
      if (pathCache.has(categoryId)) return pathCache.get(categoryId) || "";
      const node = nodeById.get(categoryId);
      if (!node) return "";
      const parentPath = node.parent_id ? buildPath(String(node.parent_id)) : "";
      const path = parentPath ? `${parentPath} / ${node.name}` : node.name;
      pathCache.set(categoryId, path);
      return path;
    };

    const list: Array<{ id: string; name: string; path: string }> = [];
    const stack = [...(childrenByParent.get(parentCategoryId) || [])];
    while (stack.length) {
      const n = stack.shift() as CatalogNode;
      list.push({ id: n.id, name: n.name, path: buildPath(n.id) || n.name });
      const ch = childrenByParent.get(n.id) || [];
      for (const c of ch) stack.push(c);
    }
    list.sort((a, b) => a.path.localeCompare(b.path, "ru"));
    return list;
  }, [parentCategoryId, childrenByParent, nodeById]);

  const groupOptions = useMemo(() => {
    return (groups || [])
      .map((g) => ({ id: String(g.id || ""), name: String(g.name || "") }))
      .sort((a, b) => a.name.localeCompare(b.name, "ru"));
  }, [groups]);

  const templateOptions = useMemo(() => {
    return (templates || [])
      .map((t) => ({ id: String(t.id || ""), name: String(t.name || "") }))
      .sort((a, b) => a.name.localeCompare(b.name, "ru"));
  }, [templates]);

  const totalPages = Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
  const pageFrom = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const pageTo = Math.min(total, currentPage * pageSize);
  const hasActiveFilters = Boolean(
    query || parentCategoryId || subCategoryId || groupFilter || templateFilter || marketFilter !== "all" || ozonFilter !== "all" || viewFilter !== "all",
  );
  const searchPending = searchDraft.trim() !== query;
  const listBusy = loading || searchPending;

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

      {loadError ? <div className="card" style={{ color: "#b42318", fontWeight: 700 }}>{loadError}</div> : null}

      <div className="card products-toolbar">
        <div className="products-toolbarTop">
          <div className="products-toolbarSearch">
            <input
              className={`pn-input products-filterSearch ${searchPending ? "isPending" : ""}`}
              placeholder="Поиск по товару и SKU GT..."
              value={searchDraft}
              onChange={(e) => setSearchDraft(e.target.value)}
            />
          </div>
          <div className="products-toolbarMeta">
            <div className="products-summaryChip">
              <span className="products-summaryLabel">Найдено</span>
              <strong>{total}</strong>
            </div>
            <div className="products-summaryChip">
              <span className="products-summaryLabel">Показано</span>
              <strong>{pageFrom}-{pageTo}</strong>
            </div>
            {hasActiveFilters ? (
              <button className="btn products-clearBtn" type="button" onClick={() => updateFilters({ q: "", parent: "", sub: "", group: "", template: "", ym: "all", oz: "all", view: "all", page: 1 })}>
                Сбросить
              </button>
            ) : null}
          </div>
        </div>
        <div className="products-quickFilters">
          {[
            { key: "all", label: "Все товары" },
            { key: "issues", label: "Проблемные" },
            { key: "no_template", label: "Без мастер-файла" },
            { key: "no_ym", label: "Без Я.Маркета" },
            { key: "no_oz", label: "Без Ozon" },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              className={`products-quickChip ${viewFilter === item.key ? "isActive" : ""}`}
              onClick={() => updateFilters({ view: item.key as "all" | "issues" | "no_template" | "no_ym" | "no_oz", page: 1 })}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="products-toolbarFilters">
          <select className="pn-input products-filterControl" value={parentCategoryId} onChange={(e) => updateFilters({ parent: e.target.value, sub: "", page: 1 })}>
            <option value="">Все категории</option>
            {rootCategories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <select
            className="pn-input products-filterControl"
            value={subCategoryId}
            onChange={(e) => updateFilters({ sub: e.target.value, page: 1 })}
            disabled={!parentCategoryId}
          >
            <option value="">Все подкатегории</option>
            {subCategories.map((c) => (
              <option key={c.id} value={c.id}>{c.path}</option>
            ))}
          </select>
          <select className="pn-input products-filterControl" value={groupFilter} onChange={(e) => updateFilters({ group: e.target.value, page: 1 })}>
            <option value="">Все группы</option>
            <option value="__ungrouped__">Без группы</option>
            {groupOptions.map((g) => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
          <select className="pn-input products-filterControl" value={templateFilter} onChange={(e) => updateFilters({ template: e.target.value, page: 1 })}>
            <option value="">Все мастер-файлы</option>
            <option value="__without__">Без мастер-файла</option>
            {templateOptions.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
          <select className="pn-input products-filterControl" value={marketFilter} onChange={(e) => updateFilters({ ym: e.target.value as "all" | "on" | "off", page: 1 })}>
            <option value="all">Я.Маркет: все</option>
            <option value="on">Я.Маркет: включено</option>
            <option value="off">Я.Маркет: выключено</option>
          </select>
          <select className="pn-input products-filterControl" value={ozonFilter} onChange={(e) => updateFilters({ oz: e.target.value as "all" | "on" | "off", page: 1 })}>
            <option value="all">OZON: все</option>
            <option value="on">OZON: включено</option>
            <option value="off">OZON: выключено</option>
          </select>
        </div>
      </div>

      <div className={`card products-tableWrap ${listBusy ? "isLoading" : ""}`}>
        <table className="products-table">
          <thead>
            <tr>
              <th rowSpan={2} className="products-colSku">SKU GT</th>
              <th rowSpan={2}>Товар</th>
              <th rowSpan={2} className="products-colGroup">Входит в группу</th>
              <th rowSpan={2} className="products-colTemplate">Мастер-файл</th>
              <th colSpan={2}>Площадки</th>
            </tr>
            <tr>
              <th>Я.Маркет</th>
              <th>OZON</th>
            </tr>
          </thead>
          <tbody>
            {!loading && products.map((p) => {
              const title = String(p.title || p.name || "").trim() || p.id;
              const breadcrumbs = String(p.category_path || "");
              const previewUrl = String(p.preview_url || "").trim();
              const gid = String(p.group_id || "").trim();
              const gname = String(p.group_name || "").trim();
              const skuGt = String(p.sku_gt || "").trim();
              const templateName = String(p.effective_template_name || "").trim();
              const templateSourceCategoryId = String(p.effective_template_source_category_id || "").trim();
              const ymStatus = String(p.marketplace_statuses?.yandex_market?.status || "Нет данных");
              const ymPresent = !!p.marketplace_statuses?.yandex_market?.present;
              const ozStatus = String(p.marketplace_statuses?.ozon?.status || "Нет данных");
              const ozPresent = !!p.marketplace_statuses?.ozon?.present;
              return (
                <tr key={p.id}>
                  <td className="products-colSku">
                    {skuGt ? <span className="products-sku">{skuGt}</span> : <span className="muted">-</span>}
                  </td>
                  <td>
                    <div className="products-mainCell">
                      <div className="products-thumbWrap">
                        {previewUrl ? (
                          <img className="products-thumb" src={previewUrl} alt={title} loading="lazy" />
                        ) : (
                          <div className="products-thumb products-thumbEmpty">Нет фото</div>
                        )}
                      </div>
                      <div className="products-mainMeta">
                        <Link to={`/products/${encodeURIComponent(p.id)}`} className="products-titleLink">{title}</Link>
                        <div className="products-breadcrumbs">{breadcrumbs}</div>
                      </div>
                    </div>
                  </td>
                  <td className="products-colGroup">
                    <div className="products-sideCell">
                      {gname ? <Link to={`/catalog/groups?group=${encodeURIComponent(gid)}`} className="products-cellLink">{gname}</Link> : <span className="muted">Без группы</span>}
                    </div>
                  </td>
                  <td className="products-colTemplate">
                    <div className="products-sideCell">
                      {templateName ? (
                        <Link to={`/templates/${encodeURIComponent(templateSourceCategoryId)}`} className="products-cellLink">
                          {templateName}
                        </Link>
                      ) : (
                        <span className="muted">Не назначен</span>
                      )}
                    </div>
                  </td>
                  <td>
                    <div className="products-statusCell">
                      <span className={`products-status ${productStatusTone(ymStatus, ymPresent)}`}>{ymStatus}</span>
                    </div>
                  </td>
                  <td>
                    <div className="products-statusCell">
                      <span className={`products-status ${productStatusTone(ozStatus, ozPresent)}`}>{ozStatus}</span>
                    </div>
                  </td>
                </tr>
              );
            })}
            {products.length === 0 ? (
              <tr>
                <td colSpan={6} className="products-empty">Товары не найдены</td>
              </tr>
            ) : null}
            {loading && Array.from({ length: 8 }).map((_, idx) => (
              <tr key={`sk-${idx}`} className="products-skeletonRow">
                <td className="products-colSku"><span className="products-skeleton products-skeletonSku" /></td>
                <td><div className="products-skeletonMain"><span className="products-skeleton products-skeletonThumb" /><div className="products-skeletonMeta"><span className="products-skeleton products-skeletonTitle" /><span className="products-skeleton products-skeletonCrumbs" /></div></div></td>
                <td className="products-colGroup"><span className="products-skeleton products-skeletonShort" /></td>
                <td className="products-colTemplate"><span className="products-skeleton products-skeletonMid" /></td>
                <td><span className="products-skeleton products-skeletonStatus" /></td>
                <td><span className="products-skeleton products-skeletonStatus" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card products-pager">
        <div className="products-pagerMeta">
          Показано <b>{pageFrom}-{pageTo}</b> из <b>{total}</b>
        </div>
        <div className="products-pagerActions">
          <button className="btn" type="button" onClick={() => updateFilters({ page: currentPage - 1 })} disabled={currentPage <= 1 || loading}>
            Назад
          </button>
          <div className="products-pagerNow">Страница {currentPage} / {totalPages}</div>
          <button className="btn" type="button" onClick={() => updateFilters({ page: currentPage + 1 })} disabled={currentPage >= totalPages || loading}>
            Дальше
          </button>
        </div>
      </div>
    </div>
  );
}
