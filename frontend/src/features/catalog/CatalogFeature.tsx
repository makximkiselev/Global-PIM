import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
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
import WorkspaceFrame from "../../components/layout/WorkspaceFrame";
import PageHeader from "../../components/ui/PageHeader";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import Alert from "../../components/ui/Alert";
import EmptyState from "../../components/ui/EmptyState";
import DataToolbar from "../../components/data/DataToolbar";
import ProductRegistry from "../../components/ProductRegistry";
import { api } from "../../lib/api";
import "../../styles/catalog-fresh.css";

type NodeT = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
  template_id: string | null;
  template_ids?: string[];
  products_count?: number;
};

type ProductPreviewItem = {
  id: string;
  name?: string;
  title?: string;
  category_id?: string;
  sku_gt?: string;
  group_id?: string;
  preview_url?: string;
};

type CatalogTreeFilter = "all" | "with_products" | "empty";

function buildChildrenMap(nodes: NodeT[]) {
  const map = new Map<string | null, NodeT[]>();
  for (const n of nodes) {
    const key = n.parent_id ?? null;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(n);
  }
  for (const [key, arr] of map.entries()) {
    arr.sort(
      (a, b) =>
        (a.position ?? 0) - (b.position ?? 0) || a.name.localeCompare(b.name, "ru"),
    );
    map.set(key, arr);
  }
  return map;
}

function collectPath(nodesById: Map<string, NodeT>, id: string) {
  const parts: string[] = [];
  const seen = new Set<string>();
  let current = nodesById.get(id);
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    parts.unshift(current.name);
    current = current.parent_id ? nodesById.get(current.parent_id) : undefined;
  }
  return parts.join(" / ");
}

function computeAggregatedCounts(nodes: NodeT[]) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const childrenMap = buildChildrenMap(nodes);
  const memo = new Map<string, number>();

  const dfs = (id: string): number => {
    if (memo.has(id)) return memo.get(id)!;
    const selfCount = byId.get(id)?.products_count ?? 0;
    const children = childrenMap.get(id) ?? [];
    const total = selfCount + children.reduce((sum, child) => sum + dfs(child.id), 0);
    memo.set(id, total);
    return total;
  };

  const out = new Map<string, number>();
  for (const node of nodes) out.set(node.id, dfs(node.id));
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
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === "Enter" && onEnter) {
        const target = event.target as HTMLElement | null;
        const tag = (target?.tagName || "").toLowerCase();
        if (tag === "textarea") return;
        event.preventDefault();
        onEnter();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose, onEnter]);

  if (!open) return null;

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div className="modal" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title">{title}</div>
          <button className="btn" onClick={onClose} type="button">
            Закрыть
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

function Dropline({ id }: { id: string }) {
  const { isOver, setNodeRef } = useDroppable({ id });
  return <div ref={setNodeRef} className={`catalogTreeDropLine${isOver ? " isOver" : ""}`} />;
}

function DropInside({ id }: { id: string }) {
  const { isOver, setNodeRef } = useDroppable({ id });
  return <div ref={setNodeRef} className={`catalogTreeDropInside${isOver ? " isOver" : ""}`} />;
}

function CatalogTreeRow({
  node,
  depth,
  count,
  isSelected,
  isExpanded,
  hasKids,
  sortMode,
  onSelect,
  onToggle,
}: {
  node: NodeT;
  depth: number;
  count: number;
  isSelected: boolean;
  isExpanded: boolean;
  hasKids: boolean;
  sortMode: boolean;
  onSelect: () => void;
  onToggle: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: node.id });

  const style: React.CSSProperties = {
    transform: CSS.Translate.toString(transform),
  };

  return (
    <div className="catalogTreeRow" style={{ ["--depth" as never]: depth }}>
      {sortMode ? <Dropline id={`before:${node.id}`} /> : null}
      <div
        ref={setNodeRef}
        style={style}
        className={`catalogTreeRowInner${isDragging ? " isDragging" : ""}`}
      >
        {sortMode ? <DropInside id={`inside:${node.id}`} /> : null}
        <div
          className={`catalogTreeNode${isSelected ? " isActive" : ""}`}
          role="button"
          tabIndex={0}
          onClick={onSelect}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onSelect();
            }
          }}
        >
          {sortMode ? (
            <button
              className="catalogTreeDrag"
              type="button"
              title="Перетащить"
              onClick={(event) => event.stopPropagation()}
              {...listeners}
              {...attributes}
            >
              ⠿
            </button>
          ) : (
            <span className="catalogTreeDragPlaceholder" aria-hidden />
          )}

          {hasKids ? (
            <button
              className="catalogTreeCaret"
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onToggle();
              }}
              title={isExpanded ? "Свернуть" : "Развернуть"}
            >
              {isExpanded ? "▾" : "▸"}
            </button>
          ) : (
            <span className="catalogTreeCaretPlaceholder" aria-hidden />
          )}

          <div className="catalogTreeContent">
            <div className="catalogTreePrimary">
              <span className="catalogTreeName" title={node.name}>
                {node.name}
              </span>
              <span className="catalogTreeCount">{count}</span>
            </div>
          </div>
        </div>
      </div>
      {sortMode ? <Dropline id={`after:${node.id}`} /> : null}
    </div>
  );
}

function CatalogProductPreview({
  products,
  loading,
  selectedId,
}: {
  products: ProductPreviewItem[];
  loading: boolean;
  selectedId: string;
}) {
  if (loading) {
    return (
      <div className="catalogPreviewList">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={`sk-${index}`} className="catalogPreviewSkeleton" />
        ))}
      </div>
    );
  }

  if (!products.length) {
    return (
      <EmptyState
        title="В этой ветке пока нет товаров"
        description="Категория настроена, но SKU в нее еще не загружены."
        action={
          <div className="catalogEmptyActions">
            <Link className="btn primary" to={`/products/new?category_id=${encodeURIComponent(selectedId)}`}>
              Добавить SKU
            </Link>
            <Link className="btn" to={`/catalog/import?category=${encodeURIComponent(selectedId)}`}>
              Импорт Excel
            </Link>
          </div>
        }
      />
    );
  }

  return (
    <div className="catalogPreviewList">
      {products.map((product) => {
        const title = String(product.title || product.name || "").trim() || product.id;
        const sku = String(product.sku_gt || "").trim() || "Без SKU";
        const group = String(product.group_id || "").trim();
        return (
          <Link key={product.id} className="catalogPreviewRow" to={`/products/${encodeURIComponent(product.id)}`}>
            <div className="catalogPreviewCopy">
              <strong>{title}</strong>
              <span>{sku}</span>
            </div>
            <div className="catalogPreviewMeta">
              {group ? <Badge tone="neutral">Группа</Badge> : null}
              <span>Открыть</span>
            </div>
          </Link>
        );
      })}
    </div>
  );
}

export default function CatalogFeature() {
  const [loading, setLoading] = useState(true);
  const [refreshError, setRefreshError] = useState("");
  const [nodes, setNodes] = useState<NodeT[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [treeQuery, setTreeQuery] = useState("");
  const [treeFilter, setTreeFilter] = useState<CatalogTreeFilter>("all");
  const [sortMode, setSortMode] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem("catalog.expanded") || "{}");
    } catch {
      return {};
    }
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [createParentId, setCreateParentId] = useState<string | null>(null);
  const [createName, setCreateName] = useState("");

  const [renameOpen, setRenameOpen] = useState(false);
  const [renameName, setRenameName] = useState("");
  const [renamePosition, setRenamePosition] = useState("0");

  const [deleteOpen, setDeleteOpen] = useState(false);

  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkCategoryId, setBulkCategoryId] = useState<string>("");
  const [bulkFile, setBulkFile] = useState<File | null>(null);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkErr, setBulkErr] = useState<string | null>(null);
  const [bulkResult, setBulkResult] = useState<string | null>(null);
  const [bulkQuery, setBulkQuery] = useState("");

  const [activeId, setActiveId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 12 },
    }),
  );

  const nodesById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const childrenMap = useMemo(() => buildChildrenMap(nodes), [nodes]);
  const aggCounts = useMemo(() => computeAggregatedCounts(nodes), [nodes]);
  const roots = childrenMap.get(null) || [];
  const totalProductsCount = roots.reduce((sum, root) => sum + (aggCounts.get(root.id) ?? 0), 0);
  const visibleSet = useMemo(() => {
    const q = treeQuery.trim().toLowerCase();
    const hasFilter = treeFilter !== "all";
    if (!q && !hasFilter) return null;

    const matchesFilter = (node: NodeT) => {
      if (treeFilter === "all") return true;
      const count = aggCounts.get(node.id) ?? 0;
      if (treeFilter === "with_products") return count > 0;
      if (treeFilter === "empty") return count === 0;
      return true;
    };

    const set = new Set<string>();
    for (const node of nodes) {
      const matchesQuery = !q || node.name.toLowerCase().includes(q);
      if (matchesQuery && matchesFilter(node)) {
        set.add(node.id);
        let current = node.parent_id ? nodesById.get(node.parent_id) : undefined;
        while (current) {
          set.add(current.id);
          current = current.parent_id ? nodesById.get(current.parent_id) : undefined;
        }
      }
    }
    return set;
  }, [treeQuery, treeFilter, nodes, nodesById, aggCounts]);

  const selected = selectedId ? nodesById.get(selectedId) || null : null;
  const selectedPath = selected ? collectPath(nodesById, selected.id) : "";
  const selectedChildrenCount = selected ? (childrenMap.get(selected.id) || []).length : 0;
  const selectedCount = selected ? aggCounts.get(selected.id) ?? 0 : 0;
  const templateCategoryIds = useMemo(
    () =>
      new Set(
        nodes
          .filter(
            (node) => !!node.template_id || !!(node.template_ids && node.template_ids.length),
          )
          .map((node) => node.id),
      ),
    [nodes],
  );
  const templateCategories = useMemo(() => {
    const list = nodes.filter((node) => templateCategoryIds.has(node.id));
    list.sort((left, right) => left.name.localeCompare(right.name, "ru"));
    return list;
  }, [nodes, templateCategoryIds]);
  const bulkSearchResults = useMemo(() => {
    const q = bulkQuery.trim().toLowerCase();
    if (!q) return [] as NodeT[];
    return templateCategories
      .filter((node) => collectPath(nodesById, node.id).toLowerCase().includes(q))
      .slice(0, 80);
  }, [bulkQuery, templateCategories, nodesById]);

  useEffect(() => {
    localStorage.setItem("catalog.expanded", JSON.stringify(expanded));
  }, [expanded]);

  function expandTo(id: string) {
    setExpanded((prev) => {
      const next = { ...prev };
      let current = nodesById.get(id);
      while (current?.parent_id) {
        next[current.parent_id] = true;
        current = nodesById.get(current.parent_id);
      }
      return next;
    });
  }

  async function refresh() {
    setLoading(true);
    setRefreshError("");
    try {
      const [treeResult, countsResult] = await Promise.all([
        api<{ nodes: NodeT[] }>("/templates/tree"),
        api<{ counts?: Record<string, number> }>("/catalog/products/counts").catch(() => ({ counts: {} })),
      ]);
      const counts = countsResult.counts || {};
      const nextNodes = (Array.isArray(treeResult.nodes) ? treeResult.nodes : []).map((node) => ({
        ...node,
        products_count: Number(counts[node.id] ?? node.products_count ?? 0),
      }));
      setNodes(nextNodes);

      setSelectedId((current) => {
        if (current && nextNodes.some((node) => node.id === current)) return current;
        return nextNodes.find((node) => !node.parent_id)?.id || null;
      });
    } catch (error) {
      setRefreshError((error as Error).message || "Не удалось загрузить каталог");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!bulkOpen) return;
    if (!templateCategories.length) return;
    let nextId = bulkCategoryId;
    if (selectedId) {
      let current = nodesById.get(selectedId);
      while (current) {
        if (templateCategoryIds.has(current.id)) {
          nextId = current.id;
          break;
        }
        current = current.parent_id ? nodesById.get(current.parent_id) : undefined;
      }
    }
    if (!nextId || !templateCategoryIds.has(nextId)) {
      nextId = templateCategories[0]?.id || "";
    }
    setBulkCategoryId(nextId);
  }, [bulkOpen, bulkCategoryId, selectedId, nodesById, templateCategoryIds, templateCategories]);

  const toggle = (id: string) => setExpanded((state) => ({ ...state, [id]: !state[id] }));

  const expandAll = () => {
    const next: Record<string, boolean> = {};
    for (const node of nodes) {
      if ((childrenMap.get(node.id) || []).length > 0) next[node.id] = true;
    }
    setExpanded(next);
  };

  const collapseAll = () => {
    const next: Record<string, boolean> = {};
    let current = selectedId ? nodesById.get(selectedId) : null;
    while (current?.parent_id) {
      next[current.parent_id] = true;
      current = nodesById.get(current.parent_id) || null;
    }
    setExpanded(next);
  };

  const openCreateRoot = () => {
    setCreateParentId(null);
    setCreateName("");
    setCreateOpen(true);
  };

  const openCreateChild = (parentId: string) => {
    setCreateParentId(parentId);
    setCreateName("");
    setExpanded((state) => ({ ...state, [parentId]: true }));
    setCreateOpen(true);
  };

  const openRename = (id: string) => {
    const node = nodesById.get(id);
    if (!node) return;
    setSelectedId(id);
    expandTo(id);
    setRenameName(node.name);
    setRenamePosition(String(Math.max(0, Number(node.position ?? 0))));
    setRenameOpen(true);
  };

  const openDelete = (id: string) => {
    setSelectedId(id);
    expandTo(id);
    setDeleteOpen(true);
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
    await api<{ ok: boolean }>(`/catalog/nodes/${selectedId}`, { method: "DELETE" });
    setDeleteOpen(false);
    setSelectedId(null);
    await refresh();
  }

  function getSiblings(parentId: string | null) {
    return (childrenMap.get(parentId ?? null) || [])
      .slice()
      .sort((left, right) => (left.position ?? 0) - (right.position ?? 0));
  }

  async function moveNode(nodeId: string, newParentId: string | null, newPosition: number) {
    await api<{ ok: boolean }>(`/catalog/nodes/${nodeId}/move`, {
      method: "PATCH",
      body: JSON.stringify({ new_parent_id: newParentId, new_position: newPosition }),
    });
    await refresh();
  }

  function onDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id));
  }

  async function onDragEnd(event: DragEndEvent) {
    setActiveId(null);
    const draggedId = String(event.active.id);
    const overIdRaw = event.over?.id ? String(event.over.id) : null;
    if (!overIdRaw) return;
    if (overIdRaw.endsWith(`:${draggedId}`) || overIdRaw === draggedId) return;

    const dragged = nodesById.get(draggedId);
    if (!dragged) return;

    if (overIdRaw.startsWith("inside:")) {
      const targetId = overIdRaw.split(":")[1];
      if (!targetId) return;
      const targetChildren = getSiblings(targetId);
      try {
        await moveNode(draggedId, targetId, targetChildren.length);
        setExpanded((state) => ({ ...state, [targetId]: true }));
      } catch (error) {
        console.error(error);
      }
      return;
    }

    if (overIdRaw.startsWith("before:") || overIdRaw.startsWith("after:")) {
      const [kind, targetId] = overIdRaw.split(":");
      const target = nodesById.get(targetId);
      if (!target) return;
      const parentId = target.parent_id ?? null;
      const siblings = getSiblings(parentId).filter((node) => node.id !== draggedId);
      const targetIndex = siblings.findIndex((node) => node.id === targetId);
      if (targetIndex === -1) return;
      const nextPosition = kind === "before" ? targetIndex : targetIndex + 1;
      try {
        await moveNode(draggedId, parentId, nextPosition);
      } catch (error) {
        console.error(error);
      }
    }
  }

  const TreeNode = ({ node, depth }: { node: NodeT; depth: number }) => {
    if (visibleSet && !visibleSet.has(node.id)) return null;
    const children = childrenMap.get(node.id) || [];
    const visibleChildren = visibleSet
      ? children.filter((child) => visibleSet.has(child.id))
      : children;
    const hasKids = visibleChildren.length > 0;
    const isExpanded = visibleSet ? true : !!expanded[node.id];
    return (
      <div key={node.id}>
        <CatalogTreeRow
          node={node}
          depth={depth}
          count={aggCounts.get(node.id) ?? 0}
          isSelected={node.id === selectedId}
          isExpanded={isExpanded}
          hasKids={hasKids}
          sortMode={sortMode}
          onSelect={() => {
            setSelectedId(node.id);
            expandTo(node.id);
          }}
          onToggle={() => toggle(node.id)}
        />
        {hasKids && isExpanded ? (
          <div>
            {visibleChildren.map((child) => (
              <TreeNode key={child.id} node={child} depth={depth + 1} />
            ))}
          </div>
        ) : null}
      </div>
    );
  };

  const activeNode = activeId ? nodesById.get(activeId) || null : null;
  const createCrumbs =
    createParentId && nodesById.get(createParentId)
      ? collectPath(nodesById, createParentId)
      : "Корень";

  const openProductsHref = selected
    ? `/products?parent=${encodeURIComponent(selected.id)}`
    : "/products";

  async function downloadBulkTemplate() {
    if (!bulkCategoryId) return;
    setBulkErr(null);
    setBulkResult(null);
    try {
      const response = await fetch(
        `/api/catalog/products/template.xlsx?category_id=${encodeURIComponent(bulkCategoryId)}`,
      );
      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(text || `HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `products_${bulkCategoryId}.xlsx`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setBulkErr((error as Error).message || "TEMPLATE_DOWNLOAD_FAILED");
    }
  }

  async function importBulkExcel() {
    if (!bulkFile || !bulkCategoryId) return;
    setBulkErr(null);
    setBulkResult(null);
    setBulkLoading(true);
    try {
      const form = new FormData();
      form.append("file", bulkFile);
      const response = await fetch(
        `/api/catalog/products/import.xlsx?category_id=${encodeURIComponent(bulkCategoryId)}`,
        { method: "POST", body: form },
      );
      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(text || `HTTP ${response.status}`);
      }
      const data = await response.json();
      setBulkResult(`Импортировано товаров: ${data.created || 0}`);
      setBulkFile(null);
      await refresh();
    } catch (error) {
      setBulkErr((error as Error).message || "IMPORT_FAILED");
    } finally {
      setBulkLoading(false);
    }
  }

  return (
    <div className="catalog-fresh-page catalogWorkspacePage page-shell">
      <PageHeader
        title="Каталог"
        subtitle="Чистая структура категорий и товары внутри выбранной ветки."
        actions={
          <>
            <Link className="btn" to="/catalog/groups">
              Группы
            </Link>
            <Button variant="primary" onClick={openCreateRoot}>
              Новая категория
            </Button>
          </>
        }
      />

      {refreshError ? <Alert tone="error">{refreshError}</Alert> : null}

      <WorkspaceFrame
        className="catalogWorkspaceFrame"
        sidebar={
          <Card className="catalogTreePanel">
            <DataToolbar
              title="Категории"
              subtitle={loading ? "Загружаю структуру…" : `${nodes.length} узлов в каталоге`}
              actions={
                <div className="catalogTreeToolbarActions">
                  <Button
                    className="sm"
                    onClick={() => setSortMode((value) => !value)}
                    variant={sortMode ? "primary" : "default"}
                  >
                    {sortMode ? "Готово" : "Сортировка"}
                  </Button>
                  <Button className="sm" onClick={expandAll}>
                    Развернуть
                  </Button>
                  <Button className="sm" onClick={collapseAll}>
                    Свернуть
                  </Button>
                </div>
              }
            />

            <div className="catalogTreeSearch">
              <span aria-hidden="true">🔎</span>
              <input
                value={treeQuery}
                onChange={(event) => setTreeQuery(event.target.value)}
                placeholder="Поиск категории"
              />
            </div>

            <div className="catalogTreeFilters" aria-label="Фильтры категорий">
              {[
                { key: "all", label: "Все" },
                { key: "with_products", label: "С товарами" },
                { key: "empty", label: "Пустые" },
              ].map((item) => (
                <button
                  key={item.key}
                  className={`catalogTreeFilter${treeFilter === item.key ? " isActive" : ""}`}
                  type="button"
                  onClick={() => setTreeFilter(item.key as CatalogTreeFilter)}
                >
                  {item.label}
                </button>
              ))}
            </div>

            <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
              <div className="catalogTree">
                {loading ? (
                  <div className="catalogTreeEmpty">Загрузка каталога…</div>
                ) : !roots.length ? (
                  <EmptyState
                    title="Каталог пуст"
                    description="Создай первую категорию и начни собирать структуру каталога."
                    action={
                      <Button variant="primary" onClick={openCreateRoot}>
                        Создать первую категорию
                      </Button>
                    }
                  />
                ) : (
                  roots.map((root) => <TreeNode key={root.id} node={root} depth={0} />)
                )}
              </div>
              <DragOverlay>
                {activeNode ? <div className="catalogTreeDragOverlay">{activeNode.name}</div> : null}
              </DragOverlay>
            </DndContext>
          </Card>
        }
        main={
          selected ? (
            <div className="catalogCanvas isProductsMode">
              <Card className="catalogWorkHeader">
                <div className="catalogWorkTitleBlock">
                  <div className="catalogSectionEyebrow">Выбранная категория</div>
                  <div className="catalogWorkTitleRow">
                    <h1>{selected.name}</h1>
                    <Badge tone={selectedCount > 0 ? "active" : "neutral"}>
                      {selectedCount > 0 ? "Есть товары" : "Пустая ветка"}
                    </Badge>
                  </div>
                  <div className="catalogWorkMeta">
                    <span>{selectedCount} SKU в ветке</span>
                    <span>{selectedChildrenCount} подкатегорий</span>
                    {selectedPath ? <span>{selectedPath}</span> : null}
                  </div>
                </div>
                <div className="catalogWorkActionPanel">
                  <div className="catalogWorkQuickStats">
                    <span><strong>{selectedCount}</strong> SKU в ветке</span>
                    <span><strong>{selectedChildrenCount}</strong> подкатегорий</span>
                    <span><strong>{selected ? selected.products_count ?? 0 : 0}</strong> прямо здесь</span>
                  </div>
                  <div className="catalogCanvasActions">
                    <Link className="btn primary" to={`/products/new?category_id=${encodeURIComponent(selected.id)}`}>
                      Добавить SKU
                    </Link>
                    <Button onClick={() => openCreateChild(selected.id)}>
                      Подкатегория
                    </Button>
                    <Button onClick={() => openRename(selected.id)}>Переименовать</Button>
                    <Button variant="danger" onClick={() => openDelete(selected.id)}>
                      Удалить ветку
                    </Button>
                  </div>
                </div>
              </Card>

              <Card className="catalogProductsWorkspace">
                <div className="catalogProductsHead">
                  <div>
                    <div className="catalogProductsKicker">{selectedPath}</div>
                    <div className="catalogProductsTitleRow">
                      <h2>Товары в категории</h2>
                    </div>
                    <div className="catalogProductsMeta">
                      <span>{selectedCount} SKU</span>
                      <span>{selectedChildrenCount} подкатегорий</span>
                      <span>перемещение и просмотр</span>
                    </div>
                  </div>
                  <div className="catalogProductsCommandActions">
                    <Link className="btn" to={openProductsHref}>Полный список</Link>
                  </div>
                </div>
                <ProductRegistry
                  mode="embedded"
                  variant="catalogClean"
                  scopeCategoryId={selected.id}
                  scopeTitle={`Товары: ${selected.name}`}
                  paramPrefix="cat_"
                  showHeader={false}
                  prefetchCategoryIds={(childrenMap.get(selected.id) || []).map((node) => node.id)}
                  onProductMoved={refresh}
                />
              </Card>
            </div>
          ) : (
            <EmptyState
              title="Выбери категорию слева"
              description="После выбора откроется список SKU и действия с веткой каталога."
            />
          )
        }
      />

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
            <div className="field-label">Категория с набором полей</div>
            <div className="catalogBulkSearch">
              <input
                value={bulkQuery}
                onChange={(event) => setBulkQuery(event.target.value)}
                placeholder="Поиск категории"
              />
            </div>
            <div className="catalogBulkList">
              {loading ? (
                <div className="catalogBulkEmpty">Загрузка…</div>
              ) : !templateCategories.length ? (
                <div className="catalogBulkEmpty">Категории с набором полей не найдены.</div>
              ) : (bulkQuery.trim() ? bulkSearchResults : templateCategories).length ? (
                (bulkQuery.trim() ? bulkSearchResults : templateCategories).map((node) => (
                  <button
                    key={node.id}
                    className={`catalogBulkRow${node.id === bulkCategoryId ? " isActive" : ""}`}
                    type="button"
                    onClick={() => setBulkCategoryId(node.id)}
                    title={collectPath(nodesById, node.id)}
                  >
                    <span>{node.name}</span>
                    <small>{collectPath(nodesById, node.id)}</small>
                  </button>
                ))
              ) : (
                <div className="catalogBulkEmpty">Ничего не найдено</div>
              )}
            </div>
          </div>

          <div className="catalogBulkActionsRow">
            <Button onClick={downloadBulkTemplate} disabled={!bulkCategoryId}>
              Скачать шаблон
            </Button>
            <span>Шаблон строится по набору полей выбранной категории.</span>
          </div>

          <div className="field">
            <div className="field-label">Файл Excel</div>
            <input type="file" accept=".xlsx" onChange={(event) => setBulkFile(event.target.files?.[0] || null)} />
          </div>

          {bulkErr ? <Alert tone="error">{bulkErr}</Alert> : null}
          {bulkResult ? <Alert tone="success">{bulkResult}</Alert> : null}

          <div className="catalogModalActions">
            <Button onClick={() => setBulkOpen(false)}>Закрыть</Button>
            <Button variant="primary" onClick={importBulkExcel} disabled={!bulkFile || bulkLoading}>
              {bulkLoading ? "Импортирую…" : "Импортировать"}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        title={createParentId ? "Новая подкатегория" : "Новая категория"}
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onEnter={doCreate}
      >
        <div className="form">
          <div className="catalogModalNote">
            <b>Куда:</b> {createCrumbs}
          </div>
          <div className="field">
            <div className="field-label">Название</div>
            <input
              value={createName}
              onChange={(event) => setCreateName(event.target.value)}
              placeholder="Например: Смартфоны"
              autoFocus
            />
          </div>
          <div className="catalogModalActions">
            <Button onClick={() => setCreateOpen(false)}>Отмена</Button>
            <Button variant="primary" onClick={doCreate}>
              Создать
            </Button>
          </div>
        </div>
      </Modal>

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
              onChange={(event) => setRenameName(event.target.value)}
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
              onChange={(event) => setRenamePosition(event.target.value)}
            />
          </div>
          <div className="catalogModalHint">
            Меньшее число поднимает категорию выше среди соседних узлов.
          </div>
          <div className="catalogModalActions">
            <Button onClick={() => setRenameOpen(false)}>Отмена</Button>
            <Button variant="primary" onClick={doRename}>
              Сохранить
            </Button>
          </div>
        </div>
      </Modal>

      <Modal title="Удалить ветку" open={deleteOpen} onClose={() => setDeleteOpen(false)}>
        <div className="form">
          <div className="catalogModalDanger">
            Будет удалена вся ветка: текущая категория, подкатегории и связанные товары этой ветки.
          </div>
          <div className="catalogModalActions">
            <Button onClick={() => setDeleteOpen(false)}>Отмена</Button>
            <Button variant="danger" onClick={doDeleteBranch}>
              Удалить
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
