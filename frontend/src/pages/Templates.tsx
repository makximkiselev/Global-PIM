import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../styles/catalog.css";
import "../styles/templates.css";
import { api } from "../lib/api";
import CategorySidebar from "../components/CategorySidebar";

type NodeT = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
  template_id: string | null;

  // computed (frontend)
  effective_template_id?: string | null; // либо свой, либо у ближайшего предка
  effective_from_id?: string | null;     // чья категория дала effective_template_id
  can_have_own_template?: boolean;       // можно ли ставить шаблон на этой ноде (по правилам)
  lock_reason?: string | null;           // почему нельзя
};

type AttrT = {
  id?: string;
  attribute_id?: string;
  name: string;
  code?: string;
  type: string;
  required: boolean;
  scope: string;
  options?: any;
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
  variant: "Вариант",
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

function buildById(nodes: NodeT[]) {
  const map = new Map<string, NodeT>();
  for (const n of nodes) map.set(n.id, n);
  return map;
}

// ======= правила шаблонов =======
// В одном пути root -> leaf допустим только ОДИН template_id
// Значит:
// - если у предка есть template_id -> этот узел не может иметь свой
// - если у потомка есть template_id -> этот узел не может иметь свой (иначе конфликты по ветке)

function hasTemplateInSubtree(
  nodeId: string,
  childrenMap: Map<string | null, NodeT[]>,
  visited = new Set<string>()
): boolean {
  if (visited.has(nodeId)) return false;
  visited.add(nodeId);

  const kids = childrenMap.get(nodeId) || [];
  for (const k of kids) {
    if (k.template_id) return true;
    if (hasTemplateInSubtree(k.id, childrenMap, visited)) return true;
  }
  return false;
}

function computeEffectiveAndLocks(nodes: NodeT[]) {
  const byId = buildById(nodes);
  const childrenMap = buildChildrenMap(nodes);

  // helper: найти ближайшего предка с template_id
  const findNearestAncestorTemplate = (node: NodeT) => {
    let cur = node.parent_id ? byId.get(node.parent_id) : null;
    while (cur) {
      if (cur.template_id) return { tpl: cur.template_id, fromId: cur.id, fromName: cur.name };
      cur = cur.parent_id ? byId.get(cur.parent_id) : null;
    }
    return { tpl: null as string | null, fromId: null as string | null, fromName: null as string | null };
  };

  const out: NodeT[] = nodes.map((n) => {
    const ownTpl = n.template_id ? n.template_id : null;
    const anc = findNearestAncestorTemplate(n);

    const effective_template_id = ownTpl ?? anc.tpl ?? null;
    const effective_from_id = ownTpl ? n.id : anc.fromId;

    // блокировки:
    const hasAncestorTpl = !!anc.tpl;
    const hasDescendantTpl = hasTemplateInSubtree(n.id, childrenMap);
    const hasOwnTpl = !!ownTpl;

    // если у самой ноды уже есть шаблон — мы разрешаем открывать, но запрещаем на предках/потомках
    let can_have_own_template = true;
    let lock_reason: string | null = null;

    if (!hasOwnTpl) {
      if (hasAncestorTpl) {
        can_have_own_template = false;
        lock_reason = `Шаблон наследуется от категории выше`;
      } else if (hasDescendantTpl) {
        can_have_own_template = false;
        lock_reason = `В подкатегориях уже есть шаблон — нельзя ставить выше, чтобы не было конфликта`;
      }
    }

    return {
      ...n,
      effective_template_id,
      effective_from_id,
      can_have_own_template,
      lock_reason,
    };
  });

  return out;
}

export default function TemplatesCatalog() {
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
  const treeRef = useRef<HTMLDivElement | null>(null);

  const nodes = useMemo(() => computeEffectiveAndLocks(nodesRaw), [nodesRaw]);
  const childrenMap = useMemo(() => buildChildrenMap(nodes), [nodes]);
  const roots = childrenMap.get(null) || [];
  const byId = useMemo(() => buildById(nodes), [nodes]);
  const visibleSet = useMemo(() => {
    const q = treeQuery.trim().toLowerCase();
    if (!q) return null;
    const set = new Set<string>();
    for (const n of nodes) {
      if (n.name.toLowerCase().includes(q)) {
        set.add(n.id);
        let cur = n.parent_id ? byId.get(n.parent_id) : undefined;
        while (cur) {
          set.add(cur.id);
          cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
        }
      }
    }
    return set;
  }, [treeQuery, nodes, byId]);

  function preserveViewport(run: () => void) {
    const pageY = window.scrollY;
    const treeY = treeRef.current?.scrollTop ?? 0;
    run();
    window.requestAnimationFrame(() => {
      window.scrollTo({ top: pageY });
      if (treeRef.current) treeRef.current.scrollTop = treeY;
    });
  }

  const toggle = (id: string) =>
    preserveViewport(() => setExpanded((p) => ({ ...p, [id]: !p[id] })));
  const expandAll = () => {
    const next: Record<string, boolean> = {};
    for (const n of nodes) {
      if ((childrenMap.get(n.id) || []).length > 0) next[n.id] = true;
    }
    setExpanded(next);
  };
  const collapseAll = () => setExpanded({});

  async function refreshTree() {
    setLoading(true);
    try {
      const r = await api<{ nodes: NodeT[] }>("/templates/tree");
      setNodesRaw(r.nodes || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshTree();
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    const node = byId.get(selectedId);
    if (!node) return;
    const targetId =
      node.template_id || node.effective_from_id ? (node.template_id ? node.id : node.effective_from_id!) : node.id;

    const run = async () => {
      setPreviewLoading(true);
      setPreviewErr(null);
      try {
        const r = await api<{ template: TemplateT | null; attributes: AttrT[]; master?: TemplateMaster }>(
          `/templates/by-category/${encodeURIComponent(targetId)}`
        );
        setPreviewTemplate(r.template || null);
        setPreviewAttrs(r.attributes || []);
        setPreviewMaster(r.master || null);
      } catch (e) {
        setPreviewErr((e as Error).message || "Ошибка загрузки");
        setPreviewTemplate(null);
        setPreviewAttrs([]);
        setPreviewMaster(null);
      } finally {
        setPreviewLoading(false);
      }
    };
    run();
  }, [selectedId, byId]);

  const selectedNode = selectedId ? byId.get(selectedId) : null;
  const canCreateTemplate =
    !!selectedNode && !selectedNode.template_id && selectedNode.can_have_own_template !== false;
  const canDeleteTemplate = !!selectedNode?.template_id;
  const previewStatus = previewMaster?.status || (previewTemplate ? "draft" : "");
  const yandexSource = previewMaster?.sources?.yandex_market || null;
  const ozonSource = previewMaster?.sources?.ozon || null;
  const sourceCards = [
    yandexSource
      ? { key: "yandex_market", title: "Я.Маркет", source: yandexSource }
      : null,
    ozonSource
      ? { key: "ozon", title: "Ozon", source: ozonSource }
      : null,
  ].filter(Boolean) as Array<{ key: string; title: string; source: any }>;

  async function createTemplateForSelected() {
    if (!selectedNode) return;
    if (!canCreateTemplate) return;
    const defName = selectedNode?.name ? `Мастер-шаблон: ${selectedNode.name}` : "Мастер-шаблон";
    const name = window.prompt("Название мастер-шаблона", defName) || "";
    if (!name.trim()) return;
    setActionLoading(true);
    try {
      await api(`/templates/by-category/${encodeURIComponent(selectedNode.id)}`, {
        method: "POST",
        body: JSON.stringify({ name: name.trim() }),
      });
      await refreshTree();
    } finally {
      setActionLoading(false);
    }
  }

  async function deleteTemplateForSelected() {
    if (!selectedNode?.template_id) return;
    const label = previewTemplate?.name || selectedNode.name;
    if (!window.confirm(`Удалить мастер-шаблон "${label}"?\n\nПараметры будут удалены без возможности восстановления.`)) {
      return;
    }
    setActionLoading(true);
    try {
      await api(`/templates/${encodeURIComponent(selectedNode.template_id)}`, { method: "DELETE" });
      await refreshTree();
    } finally {
      setActionLoading(false);
    }
  }

  const TreeNode = ({ node, depth }: { node: NodeT; depth: number }) => {
    if (visibleSet && !visibleSet.has(node.id)) return null;
    const kids = childrenMap.get(node.id) || [];
    const visibleKids = visibleSet ? kids.filter((k) => visibleSet.has(k.id)) : kids;
    const hasKids = visibleSet ? visibleKids.length > 0 : kids.length > 0;
    const isExpanded = visibleSet ? true : !!expanded[node.id];

    const hasOwnTpl = !!node.template_id;
    const hasEffectiveTpl = !!node.effective_template_id;
    const isInherited = !hasOwnTpl && hasEffectiveTpl;

    // переход:
    // - если свой шаблон: открываем редактор
    // - если наследуемый: открываем страницу редактора “родителя-источника” (чтобы было понятно где править)
    // - если нет никакого: открываем этот узел (там можно создать)
    const openEditor = () => {
      if (!hasOwnTpl && node.effective_from_id) {
        nav(`/templates/${node.effective_from_id}`);
        return;
      }
      nav(`/templates/${node.id}`);
    };

    const onSelect = () => {
      preserveViewport(() => setSelectedId(node.id));
    };

    // кликабельность строки: если узел заблокирован и у него нет шаблона вообще — всё равно можно открыть,
    // но если он наследуется — мы ведём к источнику (выше), это нормально
    const disabledOwn = node.can_have_own_template === false && !hasOwnTpl;
    const hint = disabledOwn
      ? (node.lock_reason || "Нельзя создать шаблон на этом уровне")
      : hasOwnTpl
      ? "Открыть мастер-шаблон"
      : isInherited
      ? "Шаблон наследуется — открою категорию, где он задан"
      : "Открыть (можно создать мастер-шаблон)";

    // путь (для title): показываем откуда наследуется
    let inheritFromName = "";
    if (isInherited && node.effective_from_id) {
      const fromNode = byId.get(node.effective_from_id);
      if (fromNode) inheritFromName = fromNode.name;
    }

    return (
      <div>
        <div className="tree-row tpl-row" style={{ ["--depth" as any]: depth }}>
          <div
            className={`tpl-item ${disabledOwn ? "is-locked" : ""} ${selectedId === node.id ? "is-selected" : ""} ${hasOwnTpl ? "is-own" : isInherited ? "is-inherit" : "is-empty"}`}
            role="button"
            tabIndex={0}
            onClick={onSelect}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect();
              }
            }}
            aria-label={`Открыть шаблон категории: ${node.name}`}
            title={hint}
          >
            <button
              className="caret-btn"
              type="button"
              disabled={!hasKids}
              title={hasKids ? (isExpanded ? "Свернуть" : "Развернуть") : ""}
              onMouseDown={(e) => e.preventDefault()}
              onClick={(e) => {
                e.stopPropagation();
                if (hasKids) toggle(node.id);
              }}
              onKeyDown={(e) => {
                e.stopPropagation();
              }}
              aria-label={
                hasKids
                  ? isExpanded
                    ? "Свернуть ветку"
                    : "Развернуть ветку"
                  : "Нет вложенных категорий"
              }
            >
              {hasKids ? (isExpanded ? "▾" : "▸") : "•"}
            </button>

            <div className="tpl-main">
              <div className="tpl-title" title={node.name}>
                {node.name}
              </div>
              <div className="tpl-sub">
                {hasOwnTpl
                  ? "Шаблон задан на категории"
                  : isInherited
                  ? `Наследуется от: ${inheritFromName || "родителя"}`
                  : "Шаблон не задан"}
                {disabledOwn ? ` · ${node.lock_reason}` : ""}
              </div>
            </div>

            <div className="tpl-meta" onClick={(e) => e.stopPropagation()}>
              {hasOwnTpl ? (
                <span className="tpl-pill is-own">Своя</span>
              ) : isInherited ? (
                <span className="tpl-pill is-inherit">Наследуется</span>
              ) : (
                <span className="tpl-pill">Пусто</span>
              )}
              {hasOwnTpl ? (
                <button className="btn sm" type="button" onClick={openEditor}>
                  Открыть
                </button>
              ) : null}
            </div>
          </div>
        </div>

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

  return (
    <div className="templates-page page-shell">
      <div className="page-header">
        <div className="page-header-main">
          <div className="page-title">Мастер-шаблоны</div>
          <div className="page-subtitle">
            Своя — шаблон задан на категории • Наследуется — редактировать нужно “выше”
          </div>
        </div>
      </div>

      <div className="templates-grid">
        <CategorySidebar
          className="templates-panel"
          title="Категории"
          hint={`Наследование и выбор шаблона · ${nodes.length}`}
          searchValue={treeQuery}
          onSearchChange={setTreeQuery}
          searchPlaceholder="Поиск категории…"
          controls={
            <>
              <button className="btn sm" type="button" onClick={expandAll}>
                Развернуть
              </button>
              <button className="btn sm" type="button" onClick={collapseAll}>
                Свернуть
              </button>
            </>
          }
        >
          <div className="tree" ref={treeRef}>
            {loading ? (
              <div className="muted">Загрузка…</div>
            ) : roots.length === 0 ? (
              <div className="muted">Категорий пока нет.</div>
            ) : (
              roots.map((r) => <TreeNode key={r.id} node={r} depth={0} />)
            )}
          </div>
        </CategorySidebar>

        <div className="card templates-preview">
          {!selectedId ? (
            <div className="muted">Выберите категорию слева, чтобы увидеть параметры.</div>
          ) : previewLoading ? (
            <div className="muted">Загрузка параметров…</div>
          ) : previewErr ? (
            <div className="muted">{previewErr}</div>
          ) : (
            <>
              <div className="templates-previewHead">
                <div>
                  <div className="card-title">
                    {previewTemplate ? previewTemplate.name : "Мастер-шаблон не задан"}
                  </div>
                  <div className="muted">
                    {previewTemplate
                      ? `Параметров: ${previewAttrs.length}`
                      : "Можно создать шаблон в редакторе"}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  {previewStatus ? (
                    <span className={`tpl-pill ${previewStatus === "ready" ? "is-own" : previewStatus === "in_progress" ? "is-inherit" : ""}`}>
                      {previewStatus === "ready" ? "Готов" : previewStatus === "in_progress" ? "В работе" : "Черновик"}
                    </span>
                  ) : null}
                  {canCreateTemplate ? (
                    <button className="btn" type="button" onClick={createTemplateForSelected} disabled={actionLoading}>
                      + Шаблон
                    </button>
                  ) : null}
                  {canDeleteTemplate ? (
                    <button
                      className="btn danger"
                      type="button"
                      onClick={deleteTemplateForSelected}
                      disabled={actionLoading}
                    >
                      Удалить
                    </button>
                  ) : null}
                  {(() => {
                    const node = byId.get(selectedId);
                    const hasOwn = !!node?.template_id;
                    if (!hasOwn) return null;
                    return (
                      <button
                        className="btn primary"
                        type="button"
                        onClick={() => nav(`/templates/${node!.id}`)}
                        disabled={actionLoading}
                      >
                        Редактировать
                      </button>
                    );
                  })()}
                </div>
              </div>

              {previewAttrs.length === 0 ? (
                <div className="muted">Параметров нет.</div>
              ) : (
                <>
                  {previewMaster?.stats ? (
                    <div className="stats-grid" style={{ marginBottom: 12 }}>
                      <div className="tile">
                        <div className="muted">Основа товара</div>
                        <div className="num">{previewMaster.stats.base_count}</div>
                      </div>
                      <div className="tile">
                        <div className="muted">Параметры категории</div>
                        <div className="num">{previewMaster.stats.category_count}</div>
                      </div>
                      <div className="tile">
                        <div className="muted">Подтверждено</div>
                        <div className="num">
                          {Number(previewMaster.stats.confirmed_count || 0)} / {Number(previewMaster.stats.row_count || 0)}
                        </div>
                      </div>
                    </div>
                  ) : null}

                  {sourceCards.length ? (
                    <div className="tpl-sourceStrip">
                      {sourceCards.map(({ key, title, source }) => (
                        <div key={key} className="tpl-sourceCard">
                          <div className="tpl-sourceTop">
                            <div>
                              <div className="tpl-sourceTitle">{title}</div>
                              <div className="tpl-sourcePath">{String(source.category_name || "Категория не привязана")}</div>
                            </div>
                            <span className="tpl-pill">{source.mode === "structure_source" ? "Структура" : "Источник"}</span>
                          </div>
                          <div className="tpl-sourceStats">
                            <div className="tpl-sourceStat">
                              <span className="muted">Параметров</span>
                              <strong>{Number(source.params_count || 0)}</strong>
                            </div>
                            <div className="tpl-sourceStat">
                              <span className="muted">Обязательных</span>
                              <strong>{Number(source.required_params_count || 0)}</strong>
                            </div>
                            <div className="tpl-sourceStat">
                              <span className="muted">Сопоставлено</span>
                              <strong>{Number(source.mapped_rows || 0)}</strong>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}

                  <div className="tpl-attrs">
                  {previewAttrs.map((a, idx) => (
                    <div key={`${a.id || a.code || idx}`} className="tpl-attrRow">
                      <div className="tpl-attrMain">
                        <div className="tpl-attrName">
                          {a.name}
                          {a.required ? <span className="tpl-attrReq">Обязательный</span> : null}
                          <span className="tpl-pill">{TYPE_LABEL[a.type] || a.type}</span>
                          <span className="tpl-pill">{SCOPE_LABEL[a.scope] || a.scope}</span>
                        </div>
                        {/* код скрыт по запросу */}
                      </div>
                      {a.type === "select" && (a.options?.dict_id || a.options?.dictId) ? (
                        <button
                          className="btn sm"
                          type="button"
                          onClick={() =>
                            nav(`/dictionaries/${encodeURIComponent(a.options?.dict_id || a.options?.dictId)}`, {
                              state: { backTo: "/templates", backLabel: "К мастер-шаблонам" },
                            })
                          }
                        >
                          Посмотреть значения
                        </button>
                      ) : null}
                    </div>
                  ))}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
