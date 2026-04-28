import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../../styles/templates.css";
import { api } from "../../lib/api";
import Alert from "../../components/ui/Alert";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import EmptyState from "../../components/ui/EmptyState";
import PageHeader from "../../components/ui/PageHeader";
import DataToolbar from "../../components/data/DataToolbar";
import InspectorPanel from "../../components/data/InspectorPanel";
import MetricGrid from "../../components/data/MetricGrid";
import WorkspaceFrame from "../../components/layout/WorkspaceFrame";

type NodeT = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
  template_id: string | null;
  effective_template_id?: string | null;
  effective_from_id?: string | null;
  can_have_own_template?: boolean;
  lock_reason?: string | null;
};

type AttrT = {
  id?: string;
  attribute_id?: string;
  name: string;
  code?: string;
  type: string;
  required: boolean;
  scope: string;
  options?: Record<string, unknown>;
  position?: number;
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
    row_count?: number;
    confirmed_count?: number;
  };
  status?: "draft" | "in_progress" | "ready";
  sources?: Record<string, any>;
};

type CategoryMappingItem = {
  id?: string;
  category_id?: string;
  name?: string;
  title?: string;
  linked?: boolean;
  category_name?: string;
};

type ProductPreviewItem = {
  id?: string;
  sku?: string;
  name?: string;
  title?: string;
  category_id?: string | null;
  updated_at?: string | null;
  status?: string | null;
};

const TYPE_LABEL: Record<string, string> = {
  text: "Текст",
  number: "Число",
  select: "Список",
  bool: "Да/Нет",
  date: "Дата",
  json: "JSON",
};

const SCOPE_LABEL: Record<string, string> = {
  common: "Товар",
  variant: "SKU",
};

function buildChildrenMap(nodes: NodeT[]) {
  const map = new Map<string | null, NodeT[]>();
  for (const n of nodes) {
    const key = n.parent_id ?? null;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(n);
  }
  for (const [key, arr] of map.entries()) {
    arr.sort((a, b) => (a.position ?? 0) - (b.position ?? 0) || a.name.localeCompare(b.name, "ru"));
    map.set(key, arr);
  }
  return map;
}

function buildById(nodes: NodeT[]) {
  const map = new Map<string, NodeT>();
  for (const node of nodes) map.set(node.id, node);
  return map;
}

function hasTemplateInSubtree(
  nodeId: string,
  childrenMap: Map<string | null, NodeT[]>,
  visited = new Set<string>(),
): boolean {
  if (visited.has(nodeId)) return false;
  visited.add(nodeId);
  const children = childrenMap.get(nodeId) || [];
  for (const child of children) {
    if (child.template_id) return true;
    if (hasTemplateInSubtree(child.id, childrenMap, visited)) return true;
  }
  return false;
}

function computeEffectiveAndLocks(nodes: NodeT[]) {
  const byId = buildById(nodes);
  const childrenMap = buildChildrenMap(nodes);

  const findNearestAncestorTemplate = (node: NodeT) => {
    let current = node.parent_id ? byId.get(node.parent_id) : null;
    while (current) {
      if (current.template_id) return { tpl: current.template_id, fromId: current.id };
      current = current.parent_id ? byId.get(current.parent_id) : null;
    }
    return { tpl: null as string | null, fromId: null as string | null };
  };

  return nodes.map((node) => {
    const ownTemplate = node.template_id || null;
    const ancestor = findNearestAncestorTemplate(node);
    const hasAncestorTemplate = !!ancestor.tpl;
    const hasDescendantTemplate = hasTemplateInSubtree(node.id, childrenMap);
    const hasOwnTemplate = !!ownTemplate;

    let canHaveOwnTemplate = true;
    let lockReason: string | null = null;
    if (!hasOwnTemplate) {
      if (hasAncestorTemplate) {
        canHaveOwnTemplate = false;
        lockReason = "Шаблон наследуется от категории выше.";
      } else if (hasDescendantTemplate) {
        canHaveOwnTemplate = false;
        lockReason = "В подкатегориях уже есть шаблон. Выше по ветке его задавать нельзя.";
      }
    }

    return {
      ...node,
      effective_template_id: ownTemplate ?? ancestor.tpl ?? null,
      effective_from_id: ownTemplate ? node.id : ancestor.fromId,
      can_have_own_template: canHaveOwnTemplate,
      lock_reason: lockReason,
    };
  });
}

function buildCategoryPath(nodeId: string | null, byId: Map<string, NodeT>) {
  if (!nodeId) return [];
  const path: NodeT[] = [];
  const visited = new Set<string>();
  let current = byId.get(nodeId);
  while (current && !visited.has(current.id)) {
    visited.add(current.id);
    path.push(current);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }
  return path.reverse();
}

function formatDateTime(value?: string | null) {
  if (!value) return "Недавно";
  try {
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return "Недавно";
  }
}

export default function TemplatesCatalogFeature() {
  const nav = useNavigate();

  const [loading, setLoading] = useState(true);
  const [nodesRaw, setNodesRaw] = useState<NodeT[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [treeQuery, setTreeQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [previewTemplate, setPreviewTemplate] = useState<TemplateT | null>(null);
  const [previewAttrs, setPreviewAttrs] = useState<AttrT[]>([]);
  const [previewMaster, setPreviewMaster] = useState<TemplateMaster | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [mappingItems, setMappingItems] = useState<CategoryMappingItem[]>([]);
  const [mappingLoading, setMappingLoading] = useState(false);
  const [productPreview, setProductPreview] = useState<ProductPreviewItem[]>([]);
  const [productPreviewLoading, setProductPreviewLoading] = useState(false);
  const treeRef = useRef<HTMLDivElement | null>(null);

  const nodes = useMemo(() => computeEffectiveAndLocks(nodesRaw), [nodesRaw]);
  const childrenMap = useMemo(() => buildChildrenMap(nodes), [nodes]);
  const roots = childrenMap.get(null) || [];
  const byId = useMemo(() => buildById(nodes), [nodes]);

  const visibleSet = useMemo(() => {
    const query = treeQuery.trim().toLowerCase();
    if (!query) return null;
    const set = new Set<string>();
    for (const node of nodes) {
      if (node.name.toLowerCase().includes(query)) {
        set.add(node.id);
        let current = node.parent_id ? byId.get(node.parent_id) : undefined;
        while (current) {
          set.add(current.id);
          current = current.parent_id ? byId.get(current.parent_id) : undefined;
        }
      }
    }
    return set;
  }, [treeQuery, nodes, byId]);

  const selectedNode = selectedId ? byId.get(selectedId) : null;
  const selectedPath = useMemo(() => buildCategoryPath(selectedId, byId), [selectedId, byId]);
  const inheritedFromNode = selectedNode?.effective_from_id ? byId.get(selectedNode.effective_from_id) : null;

  const baseAttrs = previewMaster?.base_attributes || [];
  const categoryAttrs = previewMaster?.category_attributes || [];
  const totalAttrs = previewAttrs.length;
  const requiredAttrs = previewMaster?.stats?.required_count || previewAttrs.filter((attr) => attr.required).length;
  const sourceCards = useMemo(
    () =>
      Object.entries(previewMaster?.sources || {})
        .map(([key, source]) => {
          if (!source || typeof source !== "object") return null;
          const title =
            key === "yandex_market" ? "Я.Маркет" : key === "ozon" ? "Ozon" : String((source as any).title || key);
          return { key, title, source: source as Record<string, unknown> };
        })
        .filter(Boolean) as Array<{ key: string; title: string; source: Record<string, unknown> }>,
    [previewMaster],
  );

  const linkedMappings = useMemo(() => {
    if (!selectedId) return [];
    return mappingItems.filter((item) => item.category_id === selectedId || item.id === selectedId);
  }, [mappingItems, selectedId]);

  const canCreateTemplate = !!selectedNode && !selectedNode.template_id && selectedNode.can_have_own_template !== false;
  const canDeleteTemplate = !!selectedNode?.template_id;

  function preserveViewport(run: () => void) {
    const pageY = window.scrollY;
    const treeY = treeRef.current?.scrollTop ?? 0;
    run();
    window.requestAnimationFrame(() => {
      window.scrollTo({ top: pageY });
      if (treeRef.current) treeRef.current.scrollTop = treeY;
    });
  }

  async function refreshTree() {
    setLoading(true);
    try {
      const response = await api<{ nodes: NodeT[] }>("/templates/tree");
      const nextNodes = response.nodes || [];
      setNodesRaw(nextNodes);
      setSelectedId((current) => current || nextNodes[0]?.id || null);
      const nextExpanded: Record<string, boolean> = {};
      for (const node of nextNodes) {
        if (node.parent_id === null) nextExpanded[node.id] = true;
      }
      setExpanded((prev) => ({ ...nextExpanded, ...prev }));
    } finally {
      setLoading(false);
    }
  }

  async function refreshMappings() {
    setMappingLoading(true);
    try {
      const response = await api<{ items?: CategoryMappingItem[] }>("/marketplaces/mapping/import/categories");
      setMappingItems(Array.isArray(response?.items) ? response.items : []);
    } catch {
      setMappingItems([]);
    } finally {
      setMappingLoading(false);
    }
  }

  useEffect(() => {
    void refreshTree();
    void refreshMappings();
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setPreviewTemplate(null);
      setPreviewAttrs([]);
      setPreviewMaster(null);
      setProductPreview([]);
      setPreviewErr(null);
      return;
    }

    const selected = byId.get(selectedId);
    if (!selected) return;
    const targetId = selected.template_id
      ? selected.id
      : selected.effective_from_id
        ? selected.effective_from_id
        : selected.id;

    let cancelled = false;

    const loadPreview = async () => {
      setPreviewLoading(true);
      setPreviewErr(null);
      try {
        const [templateResponse, productsResponse] = await Promise.all([
          api<{ template: TemplateT | null; attributes: AttrT[]; master?: TemplateMaster }>(
            `/templates/by-category/${encodeURIComponent(targetId)}`,
          ),
          api<{ items?: ProductPreviewItem[] }>(
            `/catalog/products/search?category_ids=${encodeURIComponent(selectedId)}&include_descendants=1&limit=8`,
          ).catch(() => ({ items: [] })),
        ]);

        if (cancelled) return;
        setPreviewTemplate(templateResponse.template || null);
        setPreviewAttrs(templateResponse.attributes || []);
        setPreviewMaster(templateResponse.master || null);
        setProductPreview(Array.isArray(productsResponse?.items) ? productsResponse.items : []);
      } catch (error) {
        if (cancelled) return;
        setPreviewErr((error as Error).message || "Не удалось загрузить модель.");
        setPreviewTemplate(null);
        setPreviewAttrs([]);
        setPreviewMaster(null);
        setProductPreview([]);
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    };

    void loadPreview();
    return () => {
      cancelled = true;
    };
  }, [selectedId, byId]);

  const expandAll = () => {
    const next: Record<string, boolean> = {};
    for (const node of nodes) {
      if ((childrenMap.get(node.id) || []).length > 0) next[node.id] = true;
    }
    setExpanded(next);
  };

  const collapseAll = () => {
    const next: Record<string, boolean> = {};
    for (const root of roots) next[root.id] = true;
    setExpanded(next);
  };

  const toggle = (id: string) => {
    preserveViewport(() => setExpanded((prev) => ({ ...prev, [id]: !prev[id] })));
  };

  async function createTemplateForSelected() {
    if (!selectedNode || !canCreateTemplate) return;
    const defaultName = selectedNode.name ? `Мастер-шаблон: ${selectedNode.name}` : "Мастер-шаблон";
    const name = window.prompt("Название мастер-шаблона", defaultName) || "";
    if (!name.trim()) return;
    setActionLoading(true);
    try {
      await api(`/templates/by-category/${encodeURIComponent(selectedNode.id)}`, {
        method: "POST",
        body: JSON.stringify({ name: name.trim() }),
      });
      await refreshTree();
      setSelectedId(selectedNode.id);
    } finally {
      setActionLoading(false);
    }
  }

  async function deleteTemplateForSelected() {
    if (!selectedNode?.template_id) return;
    const label = previewTemplate?.name || selectedNode.name;
    const confirmed = window.confirm(
      `Удалить мастер-шаблон "${label}"?\n\nПоля модели будут удалены без возможности восстановления.`,
    );
    if (!confirmed) return;
    setActionLoading(true);
    try {
      await api(`/templates/${encodeURIComponent(selectedNode.template_id)}`, { method: "DELETE" });
      await refreshTree();
      setSelectedId(selectedNode.id);
    } finally {
      setActionLoading(false);
    }
  }

  function openEditorForNode(node: NodeT) {
    if (!node.template_id && node.effective_from_id) {
      nav(`/templates/${node.effective_from_id}`);
      return;
    }
    nav(`/templates/${node.id}`);
  }

  function TreeNode({ node, depth }: { node: NodeT; depth: number }) {
    if (visibleSet && !visibleSet.has(node.id)) return null;
    const kids = childrenMap.get(node.id) || [];
    const visibleKids = visibleSet ? kids.filter((kid) => visibleSet.has(kid.id)) : kids;
    const hasKids = visibleKids.length > 0;
    const isExpanded = visibleSet ? true : !!expanded[node.id];
    const hasOwnTemplate = !!node.template_id;
    const isInherited = !hasOwnTemplate && !!node.effective_template_id;
    const selected = selectedId === node.id;
    const statusText = hasOwnTemplate ? "Своя" : isInherited ? "Наследуется" : "Пусто";
    const hint = hasOwnTemplate
      ? "Открыть модель"
      : isInherited
        ? "Открыть категорию, откуда наследуется модель"
        : node.lock_reason || "Модель на категории еще не задана";

    return (
      <div className="tplTreeNode">
        <div
          className={`tplTreeRow${selected ? " is-selected" : ""}${hasOwnTemplate ? " is-own" : isInherited ? " is-inherited" : ""}`}
          style={{ ["--depth" as any]: depth }}
        >
          <button
            className="tplTreeCaret"
            type="button"
            disabled={!hasKids}
            onClick={() => hasKids && toggle(node.id)}
            aria-label={hasKids ? (isExpanded ? "Свернуть ветку" : "Развернуть ветку") : "Нет вложенных категорий"}
          >
            {hasKids ? (isExpanded ? "▾" : "▸") : "•"}
          </button>
          <button
            type="button"
            className="tplTreeMain"
            onClick={() => preserveViewport(() => setSelectedId(node.id))}
            title={hint}
          >
            <span className="tplTreeTitle">{node.name}</span>
            <span className="tplTreeMeta">
              {hasOwnTemplate
                ? "Модель задана на категории"
                : isInherited
                  ? `Наследуется от ${byId.get(node.effective_from_id || "")?.name || "родителя"}`
                  : node.lock_reason || "Модель не задана"}
            </span>
          </button>
          <div className="tplTreeActions">
            <span className={`tplModePill${hasOwnTemplate ? " is-own" : isInherited ? " is-inherited" : ""}`}>{statusText}</span>
            {(hasOwnTemplate || isInherited) ? (
              <Button className="sm" type="button" onClick={() => openEditorForNode(node)}>
                Открыть
              </Button>
            ) : null}
          </div>
        </div>
        {hasKids && isExpanded ? (
          <div className="tplTreeChildren">
            {visibleKids.map((kid) => (
              <TreeNode key={kid.id} node={kid} depth={depth + 1} />
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="templates-page page-shell">
      <PageHeader
        title="Инфо-модели"
        subtitle="Категории наследуют модель по ветке. Отдельная модель создается только там, где это действительно нужно."
        actions={
          <>
            <Button onClick={expandAll}>Развернуть</Button>
            <Button onClick={collapseAll}>Свернуть</Button>
            <Button onClick={createTemplateForSelected} disabled={!canCreateTemplate || actionLoading}>
              Создать модель
            </Button>
            <Button onClick={() => selectedNode && openEditorForNode(selectedNode)} disabled={!selectedNode || actionLoading}>
              Открыть редактор
            </Button>
            <Button variant="danger" onClick={deleteTemplateForSelected} disabled={!canDeleteTemplate || actionLoading}>
              Удалить
            </Button>
          </>
        }
      />

      <WorkspaceFrame
        className="templatesCatalogFrame"
        sidebar={
          <Card className="tplSidebarCard">
            <DataToolbar
              title="Дерево моделей"
              subtitle={`${nodes.length} категорий в модельном контуре`}
              actions={<Badge tone={treeQuery ? "active" : "neutral"}>{treeQuery ? "Фильтр" : "Вся структура"}</Badge>}
            />
            <div className="tplSidebarSearch">
              <input
                value={treeQuery}
                onChange={(event) => setTreeQuery(event.target.value)}
                placeholder="Поиск категории или модели"
              />
            </div>
            <div className="tplSidebarLegend">
              <span><span className="tplLegendDot is-own" />Своя модель</span>
              <span><span className="tplLegendDot is-inherited" />Наследование</span>
              <span><span className="tplLegendDot" />Пусто</span>
            </div>
            <div className="tplTreePanel" ref={treeRef}>
              {loading ? (
                <div className="muted">Загружаю дерево моделей…</div>
              ) : roots.length === 0 ? (
                <EmptyState title="Категорий пока нет" body="Сначала собери каталог, затем вернись к моделям." />
              ) : (
                roots.map((root) => <TreeNode key={root.id} node={root} depth={0} />)
              )}
            </div>
          </Card>
        }
        main={
          <div className="tplCanvasStack">
            <Card className="tplCanvasCard tplCanvasSummary">
              {!selectedNode ? (
                <EmptyState title="Выбери категорию" body="Слева выбери ветку каталога, чтобы увидеть структуру инфо-модели." />
              ) : previewLoading ? (
                <div className="muted">Загружаю модель категории…</div>
              ) : previewErr ? (
                <Alert tone="error">{previewErr}</Alert>
              ) : (
                <>
                  <div className="tplSummaryHeader">
                    <div className="tplSummaryTitleBlock">
                      <div className="tplSectionEyebrow">Поля товара</div>
                      <h2>{previewTemplate?.name || `Модель для «${selectedNode.name}» не задана`}</h2>
                      <p>
                        {previewTemplate
                          ? "Здесь задаются поля, обязательность и наследование для товаров выбранной ветки."
                          : "У этой категории нет собственной модели. Можно создать отдельный набор полей или оставить наследование выше по дереву."}
                      </p>
                      <div className="tplPathChips" aria-label="Путь категории">
                        {selectedPath.map((node) => (
                          <span key={node.id} className="tplPathChip">
                            {node.name}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="tplSummaryStateCard">
                      <span className="tplSummaryStatusLabel">Состояние</span>
                      <strong>
                        {selectedNode.template_id ? "Своя модель" : selectedNode.effective_template_id ? "Наследуется" : "Не задана"}
                      </strong>
                      <span>
                        {selectedNode.template_id
                          ? "Можно редактировать прямо здесь."
                          : selectedNode.effective_template_id
                            ? `Источник: ${inheritedFromNode?.name || "родительская категория"}.`
                            : selectedNode.lock_reason || "Создайте модель, если категории нужны отдельные поля."}
                      </span>
                    </div>
                  </div>

                  <MetricGrid
                    className="tplSummaryMetrics"
                    items={[
                      { label: "Всего полей", value: totalAttrs || "—" },
                      { label: "Обязательных", value: requiredAttrs || "—" },
                      {
                        label: "Подтверждено",
                        value: previewMaster?.stats
                          ? `${Number(previewMaster.stats.confirmed_count || 0)} / ${Number(previewMaster.stats.row_count || 0)}`
                          : "—",
                      },
                    ]}
                  />
                </>
              )}
            </Card>

            {selectedNode && !previewLoading && !previewErr ? (
              <div className="tplCanvasGrid">
                <Card className="tplCanvasCard">
                  <DataToolbar
                    title="Структура модели"
                    subtitle={
                      previewTemplate
                        ? "Основа товара и категорийные поля живут в одном рабочем кадре."
                        : "Собственной модели нет. После создания здесь появятся группы полей."
                    }
                  />
                  {previewTemplate ? (
                    <div className="tplModelSections">
                      <section className="tplSectionCard">
                        <div className="tplSectionHead">
                          <div>
                            <h3>Основа товара</h3>
                            <p>Глобальные поля, которые повторяются во всех SKU этой модели.</p>
                          </div>
                          <span className="tplSectionCount">{baseAttrs.length}</span>
                        </div>
                        {baseAttrs.length ? (
                          <div className="tplFieldList">
                            {baseAttrs.slice(0, 8).map((attr, index) => (
                              <div key={`${attr.id || attr.code || index}-base`} className="tplFieldPreview">
                                <div className="tplFieldCopy">
                                  <strong>{attr.name}</strong>
                                  <span>{TYPE_LABEL[attr.type] || attr.type} · {SCOPE_LABEL[attr.scope] || attr.scope}</span>
                                </div>
                                <div className="tplFieldMeta">
                                  {attr.required ? <span className="tplModePill is-own">Обяз.</span> : null}
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <EmptyState title="Базовых полей пока нет" body="После создания модели сюда попадут системные и общие поля товара." />
                        )}
                      </section>

                      <section className="tplSectionCard">
                        <div className="tplSectionHead">
                          <div>
                            <h3>Поля категории</h3>
                            <p>Часть модели, которая отличает эту ветку каталога от остальных.</p>
                          </div>
                          <span className="tplSectionCount">{categoryAttrs.length}</span>
                        </div>
                        {categoryAttrs.length ? (
                          <div className="tplFieldList">
                            {categoryAttrs.slice(0, 12).map((attr, index) => (
                              <div key={`${attr.id || attr.code || index}-category`} className="tplFieldPreview">
                                <div className="tplFieldCopy">
                                  <strong>{attr.name}</strong>
                                  <span>{TYPE_LABEL[attr.type] || attr.type} · {SCOPE_LABEL[attr.scope] || attr.scope}</span>
                                </div>
                                <div className="tplFieldMeta">
                                  {attr.required ? <span className="tplModePill is-own">Обяз.</span> : null}
                                  {attr.type === "select" ? <span className="tplModePill is-inherited">Список</span> : null}
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <EmptyState title="Полей категории пока нет" body="Категория может жить только на базовом наборе полей до детальной настройки." />
                        )}
                      </section>
                    </div>
                  ) : (
                    <EmptyState
                      title="Модель не задана"
                      body="Создай отдельную модель на категории или открой источник наследования выше по дереву."
                      action={
                        canCreateTemplate ? (
                          <Button variant="primary" onClick={createTemplateForSelected} disabled={actionLoading}>
                            Создать модель
                          </Button>
                        ) : undefined
                      }
                    />
                  )}
                </Card>

                <Card className="tplCanvasCard">
                  <DataToolbar
                    title="Использование модели"
                    subtitle="Текущее состояние категории, каналов и товаров, которые живут на этой модели."
                  />
                  <div className="tplUsageGrid">
                    <section className="tplSectionCard">
                      <div className="tplSectionHead">
                        <div>
                          <h3>Каналы и источники</h3>
                          <p>Все площадки и источники структуры, которые уже связаны с категорией.</p>
                        </div>
                        <span className="tplSectionCount">{sourceCards.length + linkedMappings.length}</span>
                      </div>
                      {sourceCards.length || linkedMappings.length ? (
                        <div className="tplUsageList">
                          {sourceCards.map(({ key, title, source }) => (
                            <div key={key} className="tplUsageRow">
                              <div className="tplUsageCopy">
                                <strong>{title}</strong>
                                <span>{String(source.category_name || "Категория канала не выбрана")}</span>
                              </div>
                              <div className="tplUsageStats">
                                <span>{Number(source.params_count || 0)} полей</span>
                                <span>{Number(source.mapped_rows || 0)} сопоставлено</span>
                              </div>
                            </div>
                          ))}
                          {linkedMappings.map((item, index) => (
                            <div key={`${item.id || item.category_id || index}-mapping`} className="tplUsageRow">
                              <div className="tplUsageCopy">
                                <strong>{item.name || item.title || item.category_name || "Связанный канал"}</strong>
                                <span>Контур category mapping уже связан с этой категорией.</span>
                              </div>
                              <div className="tplUsageStats">
                                <span>{item.linked ? "Связано" : "Черновик"}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <EmptyState title="Связей пока нет" body="После канального маппинга здесь появятся площадки и источники структуры." />
                      )}
                    </section>

                    <section className="tplSectionCard">
                      <div className="tplSectionHead">
                        <div>
                          <h3>Товары по категории</h3>
                          <p>Быстрый preview SKU, которые уже живут в этой ветке каталога.</p>
                        </div>
                        <span className="tplSectionCount">{productPreview.length}</span>
                      </div>
                      {productPreviewLoading ? (
                        <div className="muted">Загружаю SKU…</div>
                      ) : productPreview.length ? (
                        <div className="tplProductPreviewList">
                          {productPreview.map((item, index) => (
                            <button
                              key={item.id || item.sku || index}
                              type="button"
                              className="tplProductPreview"
                              onClick={() => item.id && nav(`/products/${item.id}`)}
                            >
                              <div className="tplProductPreviewCopy">
                                <strong>{item.name || item.title || item.sku || "SKU"}</strong>
                                <span>{item.sku || "Без SKU"} · {formatDateTime(item.updated_at)}</span>
                              </div>
                              <span className="tplModePill">{item.status || "В работе"}</span>
                            </button>
                          ))}
                        </div>
                      ) : (
                        <EmptyState title="Товаров пока нет" body="Как только SKU попадут в категорию, они появятся здесь." />
                      )}
                    </section>
                  </div>
                </Card>
              </div>
            ) : null}
          </div>
        }
        inspector={
          <InspectorPanel
            className="tplInspector"
            title="Сводка модели"
            subtitle={selectedNode ? "Текущий узел и ближайшие действия." : "Выбери категорию слева."}
            actions={selectedNode ? <Badge tone={selectedNode.template_id ? "active" : selectedNode.effective_template_id ? "pending" : "neutral"}>{selectedNode.template_id ? "Своя" : selectedNode.effective_template_id ? "Наследование" : "Пусто"}</Badge> : undefined}
          >
            {selectedNode ? (
              <div className="tplInspectorStack">
                <div className="tplInspectorMetric">
                  <span className="tplInspectorLabel">Категория</span>
                  <strong>{selectedNode.name}</strong>
                  <span>{selectedPath.map((item) => item.name).join(" / ")}</span>
                </div>
                <div className="tplInspectorMetric">
                  <span className="tplInspectorLabel">Источник модели</span>
                  <strong>
                    {selectedNode.template_id
                      ? "Эта категория"
                      : inheritedFromNode?.name || "Модель не задана"}
                  </strong>
                  <span>{selectedNode.lock_reason || "Ограничений по ветке сейчас нет."}</span>
                </div>
                <div className="tplInspectorMetric">
                  <span className="tplInspectorLabel">Готовность</span>
                  <strong>
                    {previewMaster?.stats
                      ? `${Number(previewMaster.stats.confirmed_count || 0)} / ${Number(previewMaster.stats.row_count || 0)}`
                      : "—"}
                  </strong>
                  <span>Подтвержденные строки модели и готовность к маппингу.</span>
                </div>
                <div className="tplInspectorActions">
                  <Button variant="primary" onClick={() => openEditorForNode(selectedNode)}>
                    Открыть редактор
                  </Button>
                  <Button onClick={() => nav(`/catalog?selected=${encodeURIComponent(selectedNode.id)}`)}>Открыть категорию</Button>
                  <Button onClick={() => nav(`/products?parent=${encodeURIComponent(selectedNode.id)}`)}>Открыть товары</Button>
                  <Button onClick={() => nav(`/sources?category=${encodeURIComponent(selectedNode.id)}`)}>К каналам</Button>
                </div>
                {mappingLoading ? <div className="muted">Обновляю канальный контур…</div> : null}
              </div>
            ) : (
              <EmptyState title="Нет активной категории" body="Выбери категорию в дереве, чтобы увидеть контекст модели." />
            )}
          </InspectorPanel>
        }
      />
    </div>
  );
}
