import { useMemo, useState } from "react";

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
  products: ExchangeProduct[];
  selectedNodeIds: string[];
  selectedProductIds: string[];
  onSelectedNodeIdsChange: (ids: string[]) => void;
  onSelectedProductIdsChange: (ids: string[]) => void;
  includeDescendants: boolean;
  onIncludeDescendantsChange: (value: boolean) => void;
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
    products,
    selectedNodeIds,
    selectedProductIds,
    onSelectedNodeIdsChange,
    onSelectedProductIdsChange,
    includeDescendants,
    onIncludeDescendantsChange,
  } = props;

  const [nodeQuery, setNodeQuery] = useState("");
  const [productQuery, setProductQuery] = useState("");

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
  const visibleProducts = useMemo(() => {
    const q = qnorm(productQuery);
    if (!selectedTreeCategoryIds && !q) return [] as ExchangeProduct[];
    return (products || [])
      .filter((p) => {
        const cid = String(p.category_id || "");
        if (selectedTreeCategoryIds && !selectedTreeCategoryIds.has(cid)) return false;
        if (!q) return true;
        const title = String(p.title || p.name || "");
        const path = buildPath(nodeById, cid);
        return [title, p.sku_gt || "", path].join(" ").toLowerCase().includes(q);
      })
      .sort((a, b) => String(a.title || a.name || "").localeCompare(String(b.title || b.name || ""), "ru"))
      .slice(0, 400);
  }, [products, selectedTreeCategoryIds, productQuery, nodeById]);

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

  function renderTree(parentId: string | null, depth = 0): JSX.Element[] {
    const items = childrenByParent.get(parentId || "") || [];
    const q = filteredNodeIds;
    return items.flatMap((node) => {
      if (q && !q.has(node.id)) return [];
      const checked = selectedNodeSet.has(node.id);
      return [
        <label key={node.id} className="cx-treeRow" style={{ paddingLeft: 14 + depth * 18 }}>
          <input type="checkbox" checked={checked} onChange={(e) => toggleNode(node.id, e.target.checked)} />
          <span>{node.name}</span>
        </label>,
        ...renderTree(node.id, depth + 1),
      ];
    });
  }

  return (
    <div className="cx-pickerGrid">
      <section className="card cx-pane">
        <div className="cx-paneHead">
          <div>
            <div className="cx-paneTitle">Каталог</div>
            <div className="cx-paneSub">Выбор веток и разделов каталога</div>
          </div>
          <label className="cx-inlineCheck">
            <input
              type="checkbox"
              checked={selectedNodeIds.length === 0 && selectedProductIds.length === 0}
              onChange={(e) => {
                if (e.target.checked) {
                  onSelectedNodeIdsChange([]);
                  onSelectedProductIdsChange([]);
                }
              }}
            />
            <span>Весь каталог</span>
          </label>
        </div>
        <input className="pn-input" placeholder="Поиск по дереву..." value={nodeQuery} onChange={(e) => setNodeQuery(e.target.value)} />
        <label className="cx-inlineCheck cx-inlineCheckMuted">
          <input type="checkbox" checked={includeDescendants} onChange={(e) => onIncludeDescendantsChange(e.target.checked)} />
          <span>Включая дочерние разделы</span>
        </label>
        <div className="cx-tree">{renderTree(null)}</div>
      </section>

      <section className="card cx-pane">
        <div className="cx-paneHead">
          <div>
            <div className="cx-paneTitle">Товары</div>
            <div className="cx-paneSub">Можно дополнительно выбрать конкретные товары</div>
          </div>
          <div className="cx-count">{visibleProducts.length}</div>
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
          {!hasProductScope ? <div className="cx-empty">Сначала выбери раздел каталога или начни поиск по товарам.</div> : visibleProducts.length === 0 ? <div className="cx-empty">Ничего не найдено</div> : null}
        </div>
      </section>
    </div>
  );
}
