import { useEffect, useMemo, useState } from "react";
import CategorySidebar from "./CategorySidebar";
import CategoryScopeSelector, { type CategoryScopeMode } from "./catalog/CategoryScopeSelector";
import { api } from "../lib/api";

export type ExchangeNode = {
  id: string;
  parent_id: string | null;
  name: string;
  position?: number;
};

export type ExchangeProduct = {
  id: string;
  title?: string;
  name?: string;
  category_id?: string;
  sku_gt?: string;
};

type Props = {
  nodes: ExchangeNode[];
  productCountsByCategory: Record<string, number>;
  selectedNodeIds: string[];
  selectedProductIds: string[];
  onSelectedNodeIdsChange: (ids: string[]) => void;
  onSelectedProductIdsChange: (ids: string[]) => void;
  includeDescendants: boolean;
  onIncludeDescendantsChange: (value: boolean) => void;
  embedded?: boolean;
};

function qnorm(s: string) {
  return (s || "").trim().toLowerCase();
}

function buildPath(nodeById: Map<string, ExchangeNode>, categoryId: string) {
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

export default function CatalogExchangePicker(props: Props) {
  const {
    nodes,
    productCountsByCategory,
    selectedNodeIds,
    selectedProductIds,
    onSelectedNodeIdsChange,
    onSelectedProductIdsChange,
    includeDescendants,
    onIncludeDescendantsChange,
    embedded = false,
  } = props;

  const [nodeQuery, setNodeQuery] = useState("");
  const [productQuery, setProductQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [productItems, setProductItems] = useState<ExchangeProduct[]>([]);
  const [productsLoading, setProductsLoading] = useState(false);

  const nodeById = useMemo(() => new Map((nodes || []).map((n) => [n.id, n])), [nodes]);
  const childrenByParent = useMemo(() => {
    const m = new Map<string, ExchangeNode[]>();
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

  const selectedNodeSet = useMemo(() => new Set(selectedNodeIds || []), [selectedNodeIds]);
  const selectedProductSet = useMemo(() => new Set(selectedProductIds || []), [selectedProductIds]);
  const directCounts = useMemo(() => {
    const map = new Map<string, number>();
    for (const [categoryId, count] of Object.entries(productCountsByCategory || {})) {
      if (!categoryId) continue;
      map.set(categoryId, Number(count) || 0);
    }
    return map;
  }, [productCountsByCategory]);
  const aggregatedCounts = useMemo(() => {
    const memo = new Map<string, number>();
    const walk = (id: string) => {
      if (memo.has(id)) return memo.get(id)!;
      const own = directCounts.get(id) || 0;
      const kids = childrenByParent.get(id) || [];
      const total = own + kids.reduce((sum, child) => sum + walk(child.id), 0);
      memo.set(id, total);
      return total;
    };
    for (const node of nodes || []) walk(node.id);
    return memo;
  }, [childrenByParent, directCounts, nodes]);

  const filteredNodeIds = useMemo(() => {
    const q = qnorm(nodeQuery);
    if (!q) return null;
    const hits = new Set<string>();
    for (const n of nodes || []) {
      const path = buildPath(nodeById, n.id);
      if ([n.name || "", path].join(" ").toLowerCase().includes(q)) {
        hits.add(n.id);
        let cur = n.parent_id ? nodeById.get(n.parent_id) : undefined;
        while (cur) {
          hits.add(cur.id);
          cur = cur.parent_id ? nodeById.get(cur.parent_id) : undefined;
        }
      }
    }
    return hits;
  }, [nodeQuery, nodes, nodeById]);
  const hasExpandedNodes = useMemo(
    () =>
      Object.entries(expanded).some(
        ([id, value]) => value && (childrenByParent.get(id) || []).length > 0
      ),
    [childrenByParent, expanded]
  );

  const selectedTreeCategoryIds = useMemo(() => {
    if (!selectedNodeIds.length) return null;
    const out = new Set<string>();
    const stack = [...selectedNodeIds];
    while (stack.length) {
      const id = stack.pop() as string;
      if (!id || out.has(id)) continue;
      out.add(id);
      if (includeDescendants) {
        for (const child of childrenByParent.get(id) || []) stack.push(child.id);
      }
    }
    return out;
  }, [selectedNodeIds, includeDescendants, childrenByParent]);

  const hasProductScope = !!selectedTreeCategoryIds || !!qnorm(productQuery);
  const visibleProducts = productItems;
  const hasSelectedCategoryScope = selectedNodeIds.length > 0;
  const categoryScopeMode: CategoryScopeMode = !hasSelectedCategoryScope && selectedProductIds.length === 0
    ? "all"
    : includeDescendants
      ? "branch"
      : "category";

  useEffect(() => {
    const exactIds = selectedProductIds.filter(Boolean);
    if (!exactIds.length) return;
    let cancelled = false;
    void (async () => {
      try {
        const res = await api<{ items: ExchangeProduct[] }>(
          `/catalog/products/search?ids=${encodeURIComponent(exactIds.join(","))}&limit=${encodeURIComponent(String(Math.max(exactIds.length, 50)))}`
        );
        if (cancelled) return;
        setProductItems((prev) => {
          const merged = new Map<string, ExchangeProduct>();
          for (const item of prev) merged.set(item.id, item);
          for (const item of res.items || []) merged.set(item.id, item);
          return Array.from(merged.values());
        });
      } catch {
        // no-op: selected ids will stay selected even if labels are not loaded yet
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedProductIds]);

  useEffect(() => {
    let cancelled = false;
    const q = qnorm(productQuery);
    const nodeIds = selectedNodeIds.filter(Boolean);
    if (!q && !nodeIds.length) {
      setProductItems((prev) => prev.filter((item) => selectedProductSet.has(item.id)));
      setProductsLoading(false);
      return;
    }

    const timer = window.setTimeout(() => {
      setProductsLoading(true);
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (nodeIds.length) params.set("category_ids", nodeIds.join(","));
      params.set("include_descendants", includeDescendants ? "1" : "0");
      params.set("limit", "80");
      void (async () => {
        try {
          const res = await api<{ items: ExchangeProduct[] }>(`/catalog/products/search?${params.toString()}`);
          if (cancelled) return;
          setProductItems((prev) => {
            const merged = new Map<string, ExchangeProduct>();
            for (const item of res.items || []) merged.set(item.id, item);
            for (const item of prev) {
              if (selectedProductSet.has(item.id)) merged.set(item.id, item);
            }
            return Array.from(merged.values());
          });
        } finally {
          if (!cancelled) setProductsLoading(false);
        }
      })();
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [includeDescendants, productQuery, selectedNodeIds, selectedProductSet]);

  function toggleNode(id: string, checked: boolean) {
    const next = new Set(selectedNodeIds || []);
    if (checked) next.add(id);
    else next.delete(id);
    onSelectedNodeIdsChange(Array.from(next));
  }

  function toggleProduct(id: string, checked: boolean) {
    const next = new Set(selectedProductIds || []);
    if (checked) next.add(id);
    else next.delete(id);
    onSelectedProductIdsChange(Array.from(next));
  }

  function toggleNodeExpand(id: string) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  function expandAll() {
    const next: Record<string, boolean> = {};
    for (const node of nodes || []) {
      if ((childrenByParent.get(node.id) || []).length > 0) next[node.id] = true;
    }
    setExpanded(next);
  }

  function collapseAll() {
    setExpanded({});
  }

  function changeCategoryScope(mode: CategoryScopeMode) {
    if (mode === "all") {
      onSelectedNodeIdsChange([]);
      onSelectedProductIdsChange([]);
      return;
    }
    if (!hasSelectedCategoryScope) return;
    onIncludeDescendantsChange(mode === "branch");
  }

  function renderTree(parentId: string | null, depth = 0): JSX.Element[] {
    const items = childrenByParent.get(parentId || "") || [];
    const q = filteredNodeIds;
    return items.flatMap((node) => {
      if (q && !q.has(node.id)) return [];
      const checked = selectedNodeSet.has(node.id);
      const kids = childrenByParent.get(node.id) || [];
      const hasKids = kids.length > 0;
      const isExpanded = q ? true : !!expanded[node.id];
      return [
        <div key={node.id}>
          <div className="csb-treeRow" style={{ ["--depth" as any]: depth }}>
            <label className={`csb-treeNode csb-treeNodeCheck ${checked ? "is-active" : ""}`}>
              {hasKids ? (
                <button
                  className="csb-caretBtn"
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    toggleNodeExpand(node.id);
                  }}
                  title={isExpanded ? "Свернуть" : "Развернуть"}
                >
                  {isExpanded ? "▾" : "▸"}
                </button>
              ) : (
                <span className="csb-caretSpacer" aria-hidden="true" />
              )}
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => toggleNode(node.id, e.target.checked)}
              />
              <span className="csb-treeName" title={node.name}>{node.name}</span>
              <span className="csb-treeCount">{aggregatedCounts.get(node.id) || 0}</span>
            </label>
          </div>
          {hasKids && isExpanded ? renderTree(node.id, depth + 1) : null}
        </div>,
      ];
    });
  }

  return (
    <div className={`cx-pickerGrid${embedded ? " isEmbedded" : ""}`}>
      <CategorySidebar
        className="cx-pane cx-paneSidebar cx-importCategoryPanel"
        title="Категории"
        hint={`${nodes.length} узлов в каталоге`}
        searchValue={nodeQuery}
        onSearchChange={setNodeQuery}
        searchPlaceholder="Поиск категории"
        controls={
          <>
            <CategoryScopeSelector
              mode={categoryScopeMode}
              categorySelected={hasSelectedCategoryScope}
              onModeChange={changeCategoryScope}
            />
            <button className="btn sm" type="button" onClick={expandAll}>
              Развернуть
            </button>
            <button className="btn sm" type="button" onClick={collapseAll} disabled={!hasExpandedNodes}>
              Свернуть
            </button>
          </>
        }
      >
        <div className="csb-tree">{renderTree(null)}</div>
      </CategorySidebar>

      <section className="card cx-pane">
        <div className="cx-paneHead">
          <div>
            <div className="cx-paneTitle">Товары</div>
            <div className="cx-paneSub">Точный выбор товаров по уже прогретым backend-данным</div>
          </div>
          <div className="cx-count">{productsLoading ? "…" : visibleProducts.length}</div>
        </div>
        <input className="pn-input" placeholder="Поиск по товарам..." value={productQuery} onChange={(e) => setProductQuery(e.target.value)} />
        <div className="cx-productsList">
          {visibleProducts.map((p) => {
            const title = String(p.title || p.name || p.id);
            const cid = String(p.category_id || "");
            return (
              <label key={p.id} className="cx-productRow">
                <input type="checkbox" checked={selectedProductSet.has(p.id)} onChange={(e) => toggleProduct(p.id, e.target.checked)} />
                <span className="cx-productMain">
                  <span className="cx-productTitle">{title}</span>
                  <span className="cx-productMeta">{buildPath(nodeById, cid)} · GT {p.sku_gt || "-"}</span>
                </span>
              </label>
            );
          })}
          {!hasProductScope ? <div className="cx-empty">Сначала выбери раздел каталога или начни поиск по товарам.</div> : productsLoading ? <div className="cx-empty">Загружаю товары…</div> : visibleProducts.length === 0 ? <div className="cx-empty">Ничего не найдено</div> : null}
        </div>
      </section>
    </div>
  );
}
