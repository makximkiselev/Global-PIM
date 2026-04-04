import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import "../styles/catalog-fresh.css";
import { api } from "../lib/api";
import ProductRegistry from "../components/ProductRegistry";
import CategorySidebar from "../components/CategorySidebar";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";

type NodeT = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
  template_id: string | null;
  products_count?: number;
};

type NodesResp = { nodes: NodeT[] };

type ProductHit = {
  id: string;
  name: string;
  category_id: string;
};

function buildChildrenMap(nodes: NodeT[]) {
  const map = new Map<string | null, NodeT[]>();
  for (const n of nodes) {
    const k = n.parent_id ?? null;
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(n);
  }
  for (const [k, arr] of map.entries()) {
    arr.sort(
      (a, b) =>
        (a.position ?? 0) - (b.position ?? 0) || a.name.localeCompare(b.name)
    );
    map.set(k, arr);
  }
  return map;
}

function collectPath(nodesById: Map<string, NodeT>, id: string) {
  const parts: string[] = [];
  let cur: NodeT | undefined = nodesById.get(id);
  while (cur) {
    parts.unshift(cur.name);
    cur = cur.parent_id ? nodesById.get(cur.parent_id) : undefined;
  }
  return parts.join(" / ");
}

function computeAggregatedCounts(nodes: NodeT[]) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const children = buildChildrenMap(nodes);
  const memo = new Map<string, number>();

  const dfs = (id: string): number => {
    if (memo.has(id)) return memo.get(id)!;
    const self = byId.get(id)?.products_count ?? 0;
    const kids = children.get(id) ?? [];
    const total = self + kids.reduce((sum, k) => sum + dfs(k.id), 0);
    memo.set(id, total);
    return total;
  };

  const out = new Map<string, number>();
  for (const n of nodes) out.set(n.id, dfs(n.id));
  return out;
}

function Modal({
  title,
  open,
  children,
  onClose,
  onEnter,
}: {
  title: string;
  open: boolean;
  children: React.ReactNode;
  onClose: () => void;
  onEnter?: () => void;
}) {
  useEffect(() => {
    if (!open) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "Enter" && onEnter) {
        const target = e.target as HTMLElement | null;
        const tag = (target?.tagName || "").toLowerCase();
        if (tag === "textarea") return;

        e.preventDefault();
        onEnter();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose, onEnter]);

  if (!open) return null;

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div className="modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title">{title}</div>
          <button className="btn" onClick={onClose} type="button">
            ✕
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

/** Drop line must be interactive (before/after sorting depends on it). */
function Dropline({ id }: { id: string }) {
  const { isOver, setNodeRef } = useDroppable({ id });
  return (
    <div
      ref={setNodeRef}
      className={`cf-dropLine ${isOver ? "is-over" : ""}`}
    />
  );
}

/** Drop inside is ONLY highlight; it must not intercept clicks. */
function DropInside({ id }: { id: string }) {
  const { isOver, setNodeRef } = useDroppable({ id });
  return (
    <div
      ref={setNodeRef}
      className={`cf-dropInside ${isOver ? "is-over" : ""}`}
    />
  );
}

function DraggableRow({
  node,
  depth,
  isSelected,
  isExpanded,
  hasKids,
  count,
  sortMode,
  onSelect,
  onToggle,
}: {
  node: NodeT;
  depth: number;
  isSelected: boolean;
  isExpanded: boolean;
  hasKids: boolean;
  count: number;
  sortMode: boolean;
  onSelect: () => void;
  onToggle: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({ id: node.id });

  const style: React.CSSProperties = {
    transform: CSS.Translate.toString(transform),
  };

  return (
    <div
      className="cf-treeRow"
      style={{ ["--depth" as any]: depth }}
      data-depth={String(depth)}
    >
      {sortMode ? <Dropline id={`before:${node.id}`} /> : null}

      <div
        ref={setNodeRef}
        style={style}
        className={`cf-treeRowInner ${isDragging ? "is-dragging" : ""}`}
      >
        {sortMode ? <DropInside id={`inside:${node.id}`} /> : null}

        <div
          className={`cf-treeNode ${isSelected ? "is-active" : ""}`}
          role="button"
          tabIndex={0}
          onClick={onSelect}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onSelect();
            }
          }}
        >
          {sortMode ? (
            <div
              className="cf-drag"
              title="Перетащить"
              onClick={(e) => e.stopPropagation()}
              {...listeners}
              {...attributes}
            >
              <span className="cf-dragDots">⠿</span>
            </div>
          ) : (
            <div className="cf-dragPlaceholder" aria-hidden />
          )}

          {hasKids ? (
            <span
              className="cf-caret"
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation();
                onToggle();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onToggle();
                }
              }}
              title={isExpanded ? "Свернуть" : "Развернуть"}
            >
              {isExpanded ? "▾" : "▸"}
            </span>
          ) : (
            <div className="cf-caretSpacer" aria-hidden />
          )}

          <div className="cf-treeName" title={node.name}>
            {node.name}
          </div>

          <span
            className="cf-count"
            title="Товаров в категории (включая подкатегории)"
          >
            {count}
          </span>
        </div>
      </div>

      {sortMode ? <Dropline id={`after:${node.id}`} /> : null}
    </div>
  );
}

export default function Catalog() {
  const [loading, setLoading] = useState(true);
  const [nodes, setNodes] = useState<NodeT[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [treeQuery, setTreeQuery] = useState("");
  const [sortMode, setSortMode] = useState(false);

  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem("catalog.expanded") || "{}");
    } catch {
      return {};
    }
  });

  // modals: category
  const [createOpen, setCreateOpen] = useState(false);
  const [createParentId, setCreateParentId] = useState<string | null>(null);
  const [createName, setCreateName] = useState("");

  const [renameOpen, setRenameOpen] = useState(false);
  const [renameName, setRenameName] = useState("");
  const [renamePosition, setRenamePosition] = useState("0");
  const [categoryMenuOpen, setCategoryMenuOpen] = useState(false);

  const [deleteOpen, setDeleteOpen] = useState(false);

  // search (topbar)
  const [pq, setPq] = useState("");
  const [pHits, setPHits] = useState<ProductHit[]>([]);
  const [pLoading, setPLoading] = useState(false);
  const topbarRef = useRef<HTMLDivElement | null>(null);

  // bulk import
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkCategoryId, setBulkCategoryId] = useState<string>("");
  const [bulkFile, setBulkFile] = useState<File | null>(null);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkErr, setBulkErr] = useState<string | null>(null);
  const [bulkResult, setBulkResult] = useState<string | null>(null);
  const [bulkQuery, setBulkQuery] = useState("");
  const [templateCategoryIds, setTemplateCategoryIds] = useState<Set<string>>(new Set());

  // dnd
  const [activeId, setActiveId] = useState<string | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 12 },
    })
  );

  const nodesById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const childrenMap = useMemo(() => buildChildrenMap(nodes), [nodes]);
  const aggCounts = useMemo(() => computeAggregatedCounts(nodes), [nodes]);
  const hasExpandedNodes = useMemo(() => {
    return nodes.some((n) => !!expanded[n.id] && (childrenMap.get(n.id) || []).length > 0);
  }, [nodes, expanded, childrenMap]);
  const leafNodes = useMemo(() => nodes.filter((n) => !(childrenMap.get(n.id) || []).length), [nodes, childrenMap]);
  const visibleSet = useMemo(() => {
    const q = treeQuery.trim().toLowerCase();
    if (!q) return null;
    const set = new Set<string>();
    for (const n of nodes) {
      if (n.name.toLowerCase().includes(q)) {
        set.add(n.id);
        let cur = n.parent_id ? nodesById.get(n.parent_id) : undefined;
        while (cur) {
          set.add(cur.id);
          cur = cur.parent_id ? nodesById.get(cur.parent_id) : undefined;
        }
      }
    }
    return set;
  }, [treeQuery, nodes, nodesById]);

  const bulkSearchResults = useMemo(() => {
    const q = bulkQuery.trim().toLowerCase();
    if (!q) return [] as NodeT[];
    const out: NodeT[] = [];
    for (const n of nodes) {
      if (!templateCategoryIds.has(n.id)) continue;
      const path = collectPath(nodesById, n.id).toLowerCase();
      if (n.name.toLowerCase().includes(q) || path.includes(q)) out.push(n);
    }
    out.sort((a, b) => a.name.localeCompare(b.name, "ru"));
    return out.slice(0, 80);
  }, [bulkQuery, nodes, nodesById, templateCategoryIds]);

  const templateCategories = useMemo(() => {
    const list = nodes.filter((n) => templateCategoryIds.has(n.id));
    list.sort((a, b) => a.name.localeCompare(b.name, "ru"));
    return list;
  }, [nodes, templateCategoryIds]);

  useEffect(() => {
    localStorage.setItem("catalog.expanded", JSON.stringify(expanded));
  }, [expanded]);

  useEffect(() => {
    if (!categoryMenuOpen) return;
    const onDown = () => setCategoryMenuOpen(false);
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [categoryMenuOpen]);

  function expandTo(id: string) {
    setExpanded((prev) => {
      const next = { ...prev };
      let cur = nodesById.get(id);
      while (cur?.parent_id) {
        next[cur.parent_id] = true;
        cur = nodesById.get(cur.parent_id);
      }
      return next;
    });
  }

  async function refresh() {
    setLoading(true);
    try {
      const [nodesRes, templatesRes] = await Promise.allSettled([
        api<NodesResp>("/catalog/nodes"),
        api<{ nodes: NodeT[] }>("/templates/tree"),
      ]);

      if (nodesRes.status === "fulfilled") {
        const data = nodesRes.value;
        setNodes(data.nodes || []);
        if (!selectedId) {
          const roots = (data.nodes || []).filter((n) => !n.parent_id);
          if (roots[0]) setSelectedId(roots[0].id);
        }
      }

      const tset = new Set<string>();
      if (templatesRes.status === "fulfilled") {
        const templates = templatesRes.value;
        for (const n of templates.nodes || []) {
          if (n.template_id || (n as any).template_ids?.length) {
            tset.add(n.id);
          }
        }
      }
      setTemplateCategoryIds(tset);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!bulkOpen) return;
    if (!templateCategories.length) return;
    let nextId = bulkCategoryId;
    if (selectedId) {
      let cur = nodesById.get(selectedId);
      while (cur) {
        if (templateCategoryIds.has(cur.id)) {
          nextId = cur.id;
          break;
        }
        cur = cur.parent_id ? nodesById.get(cur.parent_id) : undefined;
      }
    }
    if (!nextId || !templateCategoryIds.has(nextId)) {
      nextId = templateCategories[0].id;
    }
    setBulkCategoryId(nextId || "");
  }, [bulkOpen, selectedId, bulkCategoryId, nodesById, templateCategories, templateCategoryIds]);

  // search (debounced)
  useEffect(() => {
    const q = pq.trim();
    if (!q) {
      setPHits([]);
      return;
    }

    const t = window.setTimeout(async () => {
      setPLoading(true);
      try {
        const r = await api<{ items: ProductHit[] }>(
          `/catalog/products/search?q=${encodeURIComponent(q)}`
        );
        setPHits(r.items || []);
      } catch (e) {
        console.error(e);
        setPHits([]);
      } finally {
        setPLoading(false);
      }
    }, 220);

    return () => window.clearTimeout(t);
  }, [pq]);

  // close dropdown outside click
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!pq.trim()) return;
      const root = topbarRef.current;
      if (!root) return;
      if (!root.contains(e.target as Node)) setPHits([]);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [pq]);

  const toggle = (id: string) => setExpanded((s) => ({ ...s, [id]: !s[id] }));
  const expandAll = () => {
    const next: Record<string, boolean> = {};
    for (const n of nodes) {
      if ((childrenMap.get(n.id) || []).length > 0) next[n.id] = true;
    }
    setExpanded(next);
  };
  const collapseAll = () => setExpanded({});

  const openCreateRoot = () => {
    setCreateParentId(null);
    setCreateName("");
    setCreateOpen(true);
  };

  const openCreateChild = (parentId: string) => {
    setCreateParentId(parentId);
    setCreateName("");
    setExpanded((s) => ({ ...s, [parentId]: true }));
    setCreateOpen(true);
    setCategoryMenuOpen(false);
  };

  const openRename = (id: string) => {
    const n = nodesById.get(id);
    if (!n) return;
    setSelectedId(id);
    expandTo(id);
    setRenameName(n.name);
    setRenamePosition(String(Math.max(0, Number(n.position ?? 0))));
    setRenameOpen(true);
    setCategoryMenuOpen(false);
  };

  const openDelete = (id: string) => {
    setSelectedId(id);
    expandTo(id);
    setDeleteOpen(true);
    setCategoryMenuOpen(false);
  };

  async function doCreate() {
    const name = createName.trim();
    if (!name) return;

    await api<NodeT>("/catalog/nodes", {
      method: "POST",
      body: JSON.stringify({ name, parent_id: createParentId }),
    });

    setCreateOpen(false);
    await refresh();
  }

  async function doRename() {
    if (!selectedId) return;
    const name = renameName.trim();
    if (!name) return;
    const parsedPosition = Number.parseInt(renamePosition, 10);

    await api<NodeT>(`/catalog/nodes/${selectedId}`, {
      method: "PATCH",
      body: JSON.stringify({
        name,
        position: Number.isFinite(parsedPosition) ? Math.max(0, parsedPosition) : 0,
      }),
    });

    setRenameOpen(false);
    await refresh();
  }

  async function doDeleteBranch() {
    if (!selectedId) return;

    await api<{ ok: boolean }>(`/catalog/nodes/${selectedId}`, {
      method: "DELETE",
    });

    setDeleteOpen(false);
    setSelectedId(null);
    await refresh();
  }

  async function moveNode(nodeId: string, newParentId: string | null, newPosition: number) {
    await api<{ ok: boolean }>(`/catalog/nodes/${nodeId}/move`, {
      method: "PATCH",
      body: JSON.stringify({ new_parent_id: newParentId, new_position: newPosition }),
    });
    await refresh();
  }

  function getSiblings(parentId: string | null) {
    return (childrenMap.get(parentId ?? null) || [])
      .slice()
      .sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
  }

  function onDragStart(e: DragStartEvent) {
    setActiveId(String(e.active.id));
  }

  async function onDragEnd(e: DragEndEvent) {
    setActiveId(null);

    const draggedId = String(e.active.id);
    const overIdRaw = e.over?.id ? String(e.over.id) : null;
    if (!overIdRaw) return;

    // prevent self drops
    if (overIdRaw.endsWith(`:${draggedId}`) || overIdRaw === draggedId) return;

    const dragged = nodesById.get(draggedId);
    if (!dragged) return;

    // drop INSIDE
    if (overIdRaw.startsWith("inside:")) {
      const targetId = overIdRaw.split(":")[1];
      if (!targetId) return;

      const targetChildren = getSiblings(targetId);
      const pos = targetChildren.length;

      try {
        await moveNode(draggedId, targetId, pos);
        setExpanded((s) => ({ ...s, [targetId]: true }));
      } catch (err) {
        console.error(err);
      }
      return;
    }

    // drop BEFORE/AFTER
    if (overIdRaw.startsWith("before:") || overIdRaw.startsWith("after:")) {
      const [kind, targetId] = overIdRaw.split(":");
      const target = nodesById.get(targetId);
      if (!target) return;

      const parentId = target.parent_id ?? null;
      const siblings = getSiblings(parentId).filter((n) => n.id !== draggedId);

      const targetIndex = siblings.findIndex((n) => n.id === targetId);
      if (targetIndex === -1) return;

      const pos = kind === "before" ? targetIndex : targetIndex + 1;

      try {
        await moveNode(draggedId, parentId, pos);
      } catch (err) {
        console.error(err);
      }
      return;
    }
  }

  const selected = selectedId ? nodesById.get(selectedId) : null;
  const selectedPath = selected ? collectPath(nodesById, selected.id) : "";
  const crumbsArr = selectedPath ? selectedPath.split(" / ") : [];
  const breadcrumbLabel = selected
    ? (crumbsArr.length > 1 ? crumbsArr.slice(0, -1).join(" / ") : "Каталог")
    : "";
  const roots = childrenMap.get(null) || [];
  const totalProductsCount = roots.reduce((sum, root) => sum + (aggCounts.get(root.id) ?? 0), 0);
  const selectedCount = selected ? (aggCounts.get(selected.id) ?? 0) : 0;
  const prefetchCategoryIds = useMemo(() => {
    if (!selected) return [] as string[];
    const siblings = childrenMap.get(selected.parent_id ?? null) || [];
    const children = childrenMap.get(selected.id) || [];
    return [...siblings, ...children].map((node) => node.id);
  }, [childrenMap, selected]);
  const TreeNode = ({ node, depth }: { node: NodeT; depth: number }) => {
    if (visibleSet && !visibleSet.has(node.id)) return null;
    const kids = childrenMap.get(node.id) || [];
    const visibleKids = visibleSet ? kids.filter((k) => visibleSet.has(k.id)) : kids;
    const hasKids = visibleSet ? visibleKids.length > 0 : kids.length > 0;
    const isExpanded = visibleSet ? true : !!expanded[node.id];
    const isSelected = node.id === selectedId;
    const count = aggCounts.get(node.id) ?? 0;

    return (
      <div>
        <DraggableRow
          node={node}
          depth={depth}
          isSelected={isSelected}
          isExpanded={isExpanded}
          hasKids={hasKids}
          count={count}
          sortMode={sortMode}
          onSelect={() => {
            setSelectedId(node.id);
            expandTo(node.id);
          }}
          onToggle={() => toggle(node.id)}
        />

        {hasKids && isExpanded && (
          <div className="tree-children">
            {visibleKids.map((k) => (
              <TreeNode key={k.id} node={k} depth={depth + 1} />
            ))}
          </div>
        )}
      </div>
    );
  };

  const activeNode = activeId ? nodesById.get(activeId) : null;

  const createCrumbs =
    createParentId && nodesById.get(createParentId)
      ? collectPath(nodesById, createParentId)
      : "Корень";

  const goCreateProduct = () => {
    if (!selectedId) return;
    window.location.href = `/products/new?category_id=${encodeURIComponent(selectedId)}`;
  };

  const isBulkLeaf = (node: NodeT) => !(childrenMap.get(node.id) || []).length;

  const downloadBulkTemplate = async () => {
    if (!bulkCategoryId) return;
    setBulkErr(null);
    setBulkResult(null);
    try {
      const res = await fetch(
        `/api/catalog/products/template.xlsx?category_id=${encodeURIComponent(bulkCategoryId)}`
      );
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(text || `HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `products_${bulkCategoryId}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setBulkErr(e?.message || "TEMPLATE_DOWNLOAD_FAILED");
    }
  };

  const importBulkExcel = async () => {
    if (!bulkFile || !bulkCategoryId) return;
    setBulkErr(null);
    setBulkResult(null);
    setBulkLoading(true);
    try {
      const form = new FormData();
      form.append("file", bulkFile);
      const res = await fetch(
        `/api/catalog/products/import.xlsx?category_id=${encodeURIComponent(bulkCategoryId)}`,
        { method: "POST", body: form }
      );
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setBulkResult(`Импортировано товаров: ${data.created || 0}`);
      setBulkFile(null);
      if (selectedId) {
        const r = await api<{ items: ProductT[] }>(
          `/catalog/products?category_id=${encodeURIComponent(selectedId)}&include_descendants=1`
        );
        setProducts(r.items || []);
      }
    } catch (e: any) {
      setBulkErr(e?.message || "IMPORT_FAILED");
    } finally {
      setBulkLoading(false);
    }
  };

  return (
    <div className="catalog-fresh-page page-shell">
      <div className="page-header catalog-topbar" ref={topbarRef}>
        <div className="page-header-main">
          <div className="page-title">Каталог</div>
          <div className="page-subtitle">
            Перетаскивай: между (сортировка) или внутрь (сделать подкатегорией).
          </div>
        </div>
      </div>

      <div className="cf-commandBar" ref={topbarRef}>
        <div className="cf-commandSearch">
          <div className="search cf-pageSearch">
            <span style={{ color: "var(--muted)" }}>🔎</span>
            <input
              value={pq}
              onChange={(e) => setPq(e.target.value)}
              placeholder="Поиск товара или категории"
            />
          </div>

          {(pLoading || pHits.length > 0) && pq.trim() && (
            <div className="dropdown cf-pageDropdown">
              {pLoading ? (
                <div style={{ padding: 10, color: "var(--muted)", fontSize: 13 }}>
                  Ищу…
                </div>
              ) : (
                pHits.slice(0, 8).map((h) => (
                  <button
                    key={h.id}
                    type="button"
                    className="dropdown-item"
                    onClick={() => {
                      setSelectedId(h.category_id);
                      expandTo(h.category_id);
                      setPq("");
                      setPHits([]);
                    }}
                    title="Показать в дереве"
                  >
                    <div className="dd-title">{h.name}</div>
                    <div className="dd-sub">Показать в дереве</div>
                  </button>
                ))
              )}
            </div>
            )}
        </div>
        <div className="cf-commandStats">
          <div className="cf-stat">
            <span className="cf-statLabel">Категорий</span>
            <span className="cf-statValue">{nodes.length}</span>
          </div>
          <div className="cf-stat">
            <span className="cf-statLabel">Товаров</span>
            <span className="cf-statValue">{totalProductsCount}</span>
          </div>
        </div>
      </div>

      <Modal
        title="Массовая загрузка"
        open={bulkOpen}
        onClose={() => {
          setBulkOpen(false);
          setBulkErr(null);
          setBulkResult(null);
          setBulkFile(null);
          setBulkQuery("");
        }}
      >
        <div className="form">
          <div className="field">
            <div className="field-label">Подкатегория (последний уровень)</div>
            <div className="pn-catSearchBlock">
              <div className="pn-catSearchLabel">Категории</div>
              <input
                className="pn-catSearchInput"
                value={bulkQuery}
                onChange={(e) => setBulkQuery(e.target.value)}
                placeholder="поиск категории"
              />
            </div>

            <div className="pn-catList" style={{ marginTop: 10, maxHeight: 240 }}>
              {loading ? (
                <div className="pn-catEmpty">Загрузка…</div>
              ) : !templateCategories.length ? (
                <div className="pn-catEmpty">Шаблоны для категорий не найдены.</div>
              ) : bulkQuery.trim() ? (
                <>
                  {bulkSearchResults.map((node) => {
                    const leaf = isBulkLeaf(node);
                    return (
                      <button
                        key={node.id}
                        className={`pn-catRow ${node.id === bulkCategoryId ? "isActive" : ""}`}
                        onClick={() => {
                          if (leaf || templateCategoryIds.has(node.id)) setBulkCategoryId(node.id);
                          setBulkQuery("");
                        }}
                        type="button"
                        title={collectPath(nodesById, node.id)}
                      >
                        <span className="pn-catTitle">{node.name}</span>
                        <span className="pn-catMeta">{collectPath(nodesById, node.id)}</span>
                        <span className="pn-catChevron" aria-hidden="true" />
                      </button>
                    );
                  })}
                  {!bulkSearchResults.length && <div className="pn-catEmpty">Ничего не найдено</div>}
                </>
              ) : (
                <>
                  {templateCategories.map((node) => {
                    const leaf = isBulkLeaf(node);
                    return (
                      <button
                        key={node.id}
                        className={`pn-catRow ${node.id === bulkCategoryId ? "isActive" : ""}`}
                        onClick={() => (leaf || templateCategoryIds.has(node.id) ? setBulkCategoryId(node.id) : null)}
                        type="button"
                        title={collectPath(nodesById, node.id)}
                      >
                        <span className="pn-catTitle">{node.name}</span>
                        <span className="pn-catMeta">{collectPath(nodesById, node.id)}</span>
                        <span className="pn-catChevron" aria-hidden="true">
                          {leaf ? "" : "›"}
                        </span>
                      </button>
                    );
                  })}
                  {!templateCategories.length && <div className="pn-catEmpty">На этом уровне ничего нет</div>}
                </>
              )}
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <button className="btn" type="button" onClick={downloadBulkTemplate} disabled={!bulkCategoryId}>
              ⬇️ Скачать шаблон
            </button>
            <div className="muted" style={{ fontSize: 12 }}>
              Достаточно заполнить только название товара.
            </div>
          </div>

          <div className="field" style={{ marginTop: 10 }}>
            <div className="field-label">Загрузка Excel</div>
            <input
              type="file"
              accept=".xlsx"
              onChange={(e) => setBulkFile(e.target.files?.[0] || null)}
            />
          </div>

          {bulkErr ? (
            <div className="muted" style={{ color: "rgba(239,68,68,.90)", fontSize: 12 }}>
              {bulkErr}
            </div>
          ) : null}
          {bulkResult ? (
            <div className="muted" style={{ fontSize: 12 }}>
              {bulkResult}
            </div>
          ) : null}

          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 8 }}>
            <button className="btn" type="button" onClick={() => setBulkOpen(false)}>
              Закрыть
            </button>
            <button
              className="btn primary"
              type="button"
              onClick={importBulkExcel}
              disabled={!bulkFile || bulkLoading}
            >
              {bulkLoading ? "Импортирую…" : "Импортировать"}
            </button>
          </div>
        </div>
      </Modal>

      <div className="cf-workspace">
        <CategorySidebar
          className="cf-sidebar"
          title="Категории"
          hint="Структура каталога"
          primaryAction={{ label: "Новая", onClick: openCreateRoot, kind: "primary" }}
          searchValue={treeQuery}
          onSearchChange={setTreeQuery}
          searchPlaceholder="Быстрый поиск"
          controls={
            <>
              <button
                className={`btn sm ${sortMode ? "primary" : ""}`}
                type="button"
                onClick={() => setSortMode((v) => !v)}
              >
                {sortMode ? "Готово" : "Сортировка"}
              </button>
              <button
                className="btn sm"
                type="button"
                onClick={hasExpandedNodes ? collapseAll : expandAll}
              >
                {hasExpandedNodes ? "Свернуть" : "Развернуть"}
              </button>
            </>
          }
        >
          <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
            <div className="cf-tree">
              {loading ? (
                <div className="muted">Загрузка…</div>
              ) : roots.length === 0 ? (
                <div className="muted">
                  Пусто. Нажми <b>“+”</b>, чтобы создать первую категорию.
                </div>
              ) : (
                roots.map((r) => <TreeNode key={r.id} node={r} depth={0} />)
              )}
            </div>

            <DragOverlay>
              {activeNode ? <div className="drag-overlay">{activeNode.name}</div> : null}
            </DragOverlay>
          </DndContext>
        </CategorySidebar>

        <section className="cf-main">
          <div className="cf-hero">
            <div className="cf-heroMain">
              {selected && breadcrumbLabel ? (
                <div className="cf-heroPath">{breadcrumbLabel}</div>
              ) : null}
              <div className="cf-heroTitle">
                {selected ? selected.name : "Выберите категорию"}
              </div>
              {selected ? (
                <div className="cf-metaLine">
                  <span>{selectedCount} товаров</span>
                  <span>Приоритет {selected.position ?? 0}</span>
                </div>
              ) : null}
            </div>
            <div className="cf-heroActions">
              <div className="cf-actionGroup cf-actionGroupMain">
                <button
                  className="btn primary"
                  onClick={goCreateProduct}
                  type="button"
                  disabled={!selectedId}
                  title={!selectedId ? "Сначала выбери категорию" : "Добавить товар"}
                >
                  + Товар
                </button>
                <Link className="btn" to="/catalog/groups">
                  Группы товаров
                </Link>
                {selected ? (
                  <div
                    className="cf-moreMenu"
                    onMouseDown={(e) => e.stopPropagation()}
                  >
                    <button
                      className={`btn cf-moreBtn${categoryMenuOpen ? " is-open" : ""}`}
                      type="button"
                      onClick={() => setCategoryMenuOpen((v) => !v)}
                      aria-haspopup="menu"
                      aria-expanded={categoryMenuOpen}
                      title="Действия с категорией"
                    >
                      ⋯
                    </button>
                    {categoryMenuOpen ? (
                      <div className="cf-moreDropdown" role="menu">
                        <button className="cf-moreItem" type="button" onClick={() => setBulkOpen(true)}>
                          Массовая загрузка
                        </button>
                        <Link className="cf-moreItem" to={selectedId ? `/catalog/import?category=${encodeURIComponent(selectedId)}` : "/catalog/import"}>
                          Заполнение данных
                        </Link>
                        <button className="cf-moreItem" type="button" onClick={() => openCreateChild(selected.id)}>
                          Создать подкатегорию
                        </button>
                        <button className="cf-moreItem" type="button" onClick={() => openRename(selected.id)}>
                          Изменить категорию
                        </button>
                        <button className="cf-moreItem is-danger" type="button" onClick={() => openDelete(selected.id)}>
                          Удалить категорию
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          </div>

          {!selected ? null : (
            <div className="cf-section">
              <ProductRegistry
                mode="embedded"
                scopeCategoryId={selected.id}
                scopeTitle={`Товары: ${selected.name}`}
                paramPrefix="cat_"
                showHeader={false}
                prefetchCategoryIds={prefetchCategoryIds}
              />
            </div>
          )}
        </section>
      </div>

      {/* Create category */}
      <Modal
        title={createParentId ? "Новая подкатегория" : "Новая категория"}
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onEnter={doCreate}
      >
        <div className="form">
          <div className="cf-modalNote">
            <b>Куда:</b> {createCrumbs}
          </div>

          <div className="field">
            <div className="field-label">Название</div>
            <input
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              placeholder="Например: Смартфоны"
              autoFocus
            />
          </div>

          <div className="cf-modalActions">
            <button className="btn" onClick={() => setCreateOpen(false)} type="button">
              Отмена
            </button>
            <button className="btn primary" onClick={doCreate} type="button">
              Создать
            </button>
          </div>
        </div>
      </Modal>

      {/* Rename */}
      <Modal
        title="Изменить категорию"
        open={renameOpen}
        onClose={() => setRenameOpen(false)}
        onEnter={doRename}
      >
        <div className="form">
          <div className="field">
            <div className="field-label">Новое название</div>
            <input
              value={renameName}
              onChange={(e) => setRenameName(e.target.value)}
              autoFocus
            />
          </div>

          <div className="field">
            <div className="field-label">Приоритет</div>
            <input
              type="number"
              min={0}
              step={1}
              value={renamePosition}
              onChange={(e) => setRenamePosition(e.target.value)}
            />
          </div>

          <div className="cf-modalHint">
            Меньшее число поднимает категорию выше среди соседних категорий.
          </div>

          <div className="cf-modalActions">
            <button className="btn" onClick={() => setRenameOpen(false)} type="button">
              Отмена
            </button>
            <button className="btn primary" onClick={doRename} type="button">
              Сохранить
            </button>
          </div>
        </div>
      </Modal>

      {/* Delete */}
      <Modal title="Удалить ветку" open={deleteOpen} onClose={() => setDeleteOpen(false)}>
        <div className="form">
          <div className="cf-modalDangerText">
            Будет удалена <b>вся ветка</b> (категория и все подкатегории).
          </div>
          <div className="cf-modalActions">
            <button className="btn" onClick={() => setDeleteOpen(false)} type="button">
              Отмена
            </button>
            <button className="btn danger" onClick={doDeleteBranch} type="button">
              Удалить
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
