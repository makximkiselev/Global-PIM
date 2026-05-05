import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../lib/api";
import "../../styles/product-groups.css";

const TAB_GROUPS = "groups" as const;
const TAB_UNGROUPED = "ungrouped" as const;

type TabKey = typeof TAB_GROUPS | typeof TAB_UNGROUPED;

type GroupItem = {
  id: string;
  name: string;
  count: number;
  variant_param_ids?: string[];
  root_category_id?: string | null;
  root_category_name?: string | null;
  root_position?: number | null;
  category_id?: string | null;
  category_path?: string | null;
};

type GroupDetails = {
  group: {
    id: string;
    name: string;
    variant_param_ids?: string[];
  };
  items: ProductItem[];
};

type ProductItem = {
  id: string;
  title?: string;
  name?: string;
  sku_pim?: string;
  sku_gt?: string;
  group_id?: string;
  category_id?: string;
};

type CatalogNode = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
};

type VariantParam = {
  id: string;
  name: string;
  code?: string;
  dict_id?: string | null;
  selected?: boolean;
};

function productLabel(p: ProductItem) {
  return (p.title || p.name || "").trim() || p.id;
}

function productSkuIds(p: ProductItem) {
  const gt = (p.sku_gt || "").trim() || "-";
  return `GT SKU: ${gt}`;
}

function qnorm(s: string) {
  return (s || "").trim().toLowerCase();
}

function uniqueIds(list: string[]) {
  return Array.from(new Set((list || []).map((x) => (x || "").trim()).filter(Boolean)));
}

export default function ProductGroupsFeature() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTabState] = useState<TabKey>(searchParams.get("tab") === TAB_UNGROUPED ? TAB_UNGROUPED : TAB_GROUPS);
  const [groups, setGroups] = useState<GroupItem[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [groupsQuery, setGroupsQuery] = useState("");
  const [groupsTreeExpanded, setGroupsTreeExpanded] = useState<Record<string, boolean>>({});

  const [selectedGroupId, setSelectedGroupIdState] = useState<string>(searchParams.get("group") || "");
  const [groupDetails, setGroupDetails] = useState<GroupDetails | null>(null);
  const [groupLoading, setGroupLoading] = useState(false);

  const [ungrouped, setUngrouped] = useState<ProductItem[]>([]);
  const [ungroupedLoading, setUngroupedLoading] = useState(false);

  const [catalogNodes, setCatalogNodes] = useState<CatalogNode[]>([]);

  const [createName, setCreateName] = useState("");
  const [createNameTouched, setCreateNameTouched] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editName, setEditName] = useState("");

  const [addQuery, setAddQuery] = useState("");
  const [addSelected, setAddSelected] = useState<string[]>([]);
  const [addCategoryId, setAddCategoryId] = useState("");
  const [addCategoryQuery, setAddCategoryQuery] = useState("");
  const [addTreeExpanded, setAddTreeExpanded] = useState<Record<string, boolean>>({});
  const [addModalOpen, setAddModalOpen] = useState(false);

  const [ungroupedQuery, setUngroupedQuery] = useState("");
  const [ungroupedSelected, setUngroupedSelected] = useState<string[]>([]);
  const [ungroupedCategoryId, setUngroupedCategoryId] = useState("");
  const [assignGroupId, setAssignGroupId] = useState("");
  const [assignCreateName, setAssignCreateName] = useState("");
  const [assignCreateTouched, setAssignCreateTouched] = useState(false);
  const [groupCreatedToast, setGroupCreatedToast] = useState("");
  const [softRefreshing, setSoftRefreshing] = useState(false);

  const [variantModalOpen, setVariantModalOpen] = useState(false);
  const [variantLoading, setVariantLoading] = useState(false);
  const [variantOptions, setVariantOptions] = useState<VariantParam[]>([]);
  const [variantSelected, setVariantSelected] = useState<string[]>([]);

  useEffect(() => {
    setTabState(searchParams.get("tab") === TAB_UNGROUPED ? TAB_UNGROUPED : TAB_GROUPS);
    setSelectedGroupIdState(searchParams.get("group") || "");
  }, [searchParams]);

  function setTab(nextTab: TabKey) {
    setTabState(nextTab);
    const next = new URLSearchParams(searchParams);
    next.set("tab", nextTab);
    setSearchParams(next, { replace: true });
  }

  function setSelectedGroupId(nextGroupId: string) {
    setSelectedGroupIdState(nextGroupId);
    const next = new URLSearchParams(searchParams);
    if (nextGroupId) next.set("group", nextGroupId);
    else next.delete("group");
    setSearchParams(next, { replace: true });
  }

  async function loadGroups() {
    setGroupsLoading(true);
    try {
      const data = await api<{ items: GroupItem[] }>("/product-groups");
      setGroups(data.items || []);
    } finally {
      setGroupsLoading(false);
    }
  }

  async function loadGroupDetails(groupId: string) {
    if (!groupId) {
      setGroupDetails(null);
      return;
    }
    setGroupLoading(true);
    try {
      const data = await api<GroupDetails>(`/product-groups/${encodeURIComponent(groupId)}`);
      setGroupDetails(data || null);
      setEditName(data?.group?.name || "");
    } finally {
      setGroupLoading(false);
    }
  }

  async function loadUngrouped() {
    setUngroupedLoading(true);
    try {
      const data = await api<{ items: ProductItem[] }>("/product-groups/ungrouped");
      setUngrouped(data.items || []);
    } finally {
      setUngroupedLoading(false);
    }
  }

  async function loadCatalogNodes() {
    const data = await api<{ nodes: CatalogNode[] }>("/catalog/nodes");
    setCatalogNodes(data.nodes || []);
  }

  async function refreshGroupsView() {
    await loadGroups();
    if (selectedGroupId) {
      await loadGroupDetails(selectedGroupId);
    }
  }

  async function refreshUngroupedView() {
    await loadUngrouped();
  }

  async function refreshCurrentTab() {
    if (tab === TAB_UNGROUPED) {
      await refreshUngroupedView();
      return;
    }
    await refreshGroupsView();
  }

  async function refreshAfterGroupMutation() {
    await Promise.all([loadGroups(), loadUngrouped()]);
    if (selectedGroupId) {
      await loadGroupDetails(selectedGroupId);
    }
  }

  useEffect(() => {
    loadCatalogNodes();
    if (tab === TAB_UNGROUPED) {
      refreshUngroupedView();
    } else {
      refreshGroupsView();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (tab === TAB_UNGROUPED) {
      if (!ungrouped.length && !ungroupedLoading) loadUngrouped();
      return;
    }
    if (!groups.length && !groupsLoading) loadGroups();
    if (selectedGroupId) loadGroupDetails(selectedGroupId);
  }, [tab]);

  useEffect(() => {
    if (!selectedGroupId || tab !== TAB_GROUPS) return;
    loadGroupDetails(selectedGroupId);
  }, [selectedGroupId, tab]);

  useEffect(() => {
    if (!addModalOpen) return;
    if (!ungrouped.length && !ungroupedLoading) loadUngrouped();
  }, [addModalOpen]);

  const nodeById = useMemo(() => {
    const map = new Map<string, CatalogNode>();
    for (const n of catalogNodes || []) map.set(n.id, n);
    return map;
  }, [catalogNodes]);

  const childrenByParent = useMemo(() => {
    const map = new Map<string, CatalogNode[]>();
    for (const n of catalogNodes || []) {
      const pid = n.parent_id || "";
      const arr = map.get(pid) || [];
      arr.push(n);
      map.set(pid, arr);
    }
    for (const arr of map.values()) {
      arr.sort((a, b) => {
        if ((a.position || 0) !== (b.position || 0)) return (a.position || 0) - (b.position || 0);
        return (a.name || "").localeCompare(b.name || "", "ru");
      });
    }
    return map;
  }, [catalogNodes]);

  function categoryPathLabel(categoryId: string) {
    const chain: string[] = [];
    const guard = new Set<string>();
    let cur = nodeById.get(categoryId);
    while (cur && !guard.has(cur.id)) {
      guard.add(cur.id);
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
      const id = stack.pop() as string;
      if (!id || out.has(id)) continue;
      out.add(id);
      const children = childrenByParent.get(id) || [];
      for (const ch of children) stack.push(ch.id);
    }
    return out;
  }

  const treeSearchVisible = useMemo(() => {
    const q = qnorm(addCategoryQuery);
    if (!q) return null;

    const visible = new Set<string>();
    const markParents = (id: string) => {
      let cur = nodeById.get(id);
      const guard = new Set<string>();
      while (cur && !guard.has(cur.id)) {
        guard.add(cur.id);
        visible.add(cur.id);
        cur = cur.parent_id ? nodeById.get(cur.parent_id) : undefined;
      }
    };

    for (const n of catalogNodes || []) {
      if ((n.name || "").toLowerCase().includes(q)) {
        markParents(n.id);
      }
    }
    return visible;
  }, [addCategoryQuery, catalogNodes, nodeById]);

  const filteredUngrouped = useMemo(() => {
    const q = qnorm(ungroupedQuery);
    const subtree = collectSubtreeIds(ungroupedCategoryId);
    return (ungrouped || []).filter((p) => {
      if (subtree && !subtree.has(String(p.category_id || ""))) return false;
      if (!q) return true;
      return [productLabel(p), p.sku_gt || ""]
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
  }, [ungrouped, ungroupedQuery, ungroupedCategoryId, childrenByParent]);

  const categoryOptionsForUngrouped = useMemo(() => {
    const q = qnorm(ungroupedQuery);
    if (!q) {
      return (catalogNodes || [])
        .slice()
        .sort((a, b) => categoryPathLabel(a.id).localeCompare(categoryPathLabel(b.id), "ru"));
    }

    const matchedProducts = (ungrouped || []).filter((p) =>
      [productLabel(p), p.sku_gt || ""]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );

    const visibleCategoryIds = new Set<string>();
    for (const p of matchedProducts) {
      let cur = String(p.category_id || "").trim();
      const guard = new Set<string>();
      while (cur && !guard.has(cur)) {
        guard.add(cur);
        visibleCategoryIds.add(cur);
        const node = nodeById.get(cur);
        cur = node?.parent_id ? String(node.parent_id) : "";
      }
    }

    return (catalogNodes || [])
      .filter((n) => visibleCategoryIds.has(String(n.id || "")))
      .sort((a, b) => categoryPathLabel(a.id).localeCompare(categoryPathLabel(b.id), "ru"));
  }, [ungroupedQuery, catalogNodes, ungrouped, nodeById]);

  useEffect(() => {
    if (!ungroupedCategoryId) return;
    if (!qnorm(ungroupedQuery)) return;
    const exists = categoryOptionsForUngrouped.some((n) => n.id === ungroupedCategoryId);
    if (!exists) setUngroupedCategoryId("");
  }, [ungroupedCategoryId, ungroupedQuery, categoryOptionsForUngrouped]);

  const filteredGroups = useMemo(() => {
    const q = qnorm(groupsQuery);
    if (!q) return groups || [];
    return (groups || []).filter((g) => String(g.name || "").toLowerCase().includes(q));
  }, [groups, groupsQuery]);

  const groupsByRoot = useMemo(() => {
    const categoryOrderKey = (categoryId?: string | null) => {
      const id = String(categoryId || "").trim();
      if (!id) return [10 ** 9] as number[];
      const chain: CatalogNode[] = [];
      const guard = new Set<string>();
      let cur = nodeById.get(id);
      while (cur && !guard.has(cur.id)) {
        guard.add(cur.id);
        chain.push(cur);
        cur = cur.parent_id ? nodeById.get(cur.parent_id) : undefined;
      }
      chain.reverse();
      return chain.map((n) => Number(n.position || 0));
    };

    const compareOrderKey = (a: number[], b: number[]) => {
      const maxLen = Math.max(a.length, b.length);
      for (let i = 0; i < maxLen; i += 1) {
        const av = a[i] ?? -1;
        const bv = b[i] ?? -1;
        if (av !== bv) return av - bv;
      }
      return 0;
    };

    const buckets: Record<string, { key: string; label: string; items: GroupItem[] }> = {};
    for (const g of filteredGroups || []) {
      const key = String(g.root_category_id || "__uncategorized__");
      const label = String(g.root_category_name || "Без категории");
      if (!buckets[key]) buckets[key] = { key, label, items: [] };
      buckets[key].items.push(g);
    }
    return Object.values(buckets)
      .map((b) => ({
        ...b,
        items: [...b.items].sort((a, z) => {
          const keyA = categoryOrderKey(a.category_id);
          const keyZ = categoryOrderKey(z.category_id);
          const byCatalogOrder = compareOrderKey(keyA, keyZ);
          if (byCatalogOrder !== 0) return byCatalogOrder;
          const pA = String(a.category_path || "");
          const pZ = String(z.category_path || "");
          if (pA !== pZ) return pA.localeCompare(pZ, "ru");
          return String(a.name || "").localeCompare(String(z.name || ""), "ru");
        }),
      }))
      .sort((a, z) => {
        const rootA = a.key === "__uncategorized__" ? undefined : nodeById.get(a.key);
        const rootZ = z.key === "__uncategorized__" ? undefined : nodeById.get(z.key);
        const posA = Math.max(0, Number(rootA?.position ?? (a.items[0]?.root_position as number) ?? 10 ** 9));
        const posZ = Math.max(0, Number(rootZ?.position ?? (z.items[0]?.root_position as number) ?? 10 ** 9));
        if (posA !== posZ) return posA - posZ;
        return a.label.localeCompare(z.label, "ru");
      });
  }, [filteredGroups, nodeById]);

  const hasExpandedGroups = useMemo(
    () => groupsByRoot.some((b) => !!groupsTreeExpanded[b.key]),
    [groupsByRoot, groupsTreeExpanded]
  );

  useEffect(() => {
    setGroupsTreeExpanded((prev) => {
      const next = { ...prev };
      for (const b of groupsByRoot) {
        if (typeof next[b.key] === "undefined") next[b.key] = false;
      }
      return next;
    });
  }, [groupsByRoot]);

  const groupNameSet = useMemo(() => {
    return new Set((groups || []).map((g) => qnorm(g.name || "")).filter(Boolean));
  }, [groups]);

  const createNameNorm = qnorm(createName);
  const assignCreateNorm = qnorm(assignCreateName);
  const createNameDuplicate = !!createNameNorm && groupNameSet.has(createNameNorm);
  const assignCreateDuplicate = !!assignCreateNorm && groupNameSet.has(assignCreateNorm);

  const createNameHints = useMemo(() => {
    const q = qnorm(createName);
    if (!q) return [] as string[];
    return (groups || [])
      .map((g) => String(g.name || "").trim())
      .filter((name) => qnorm(name).includes(q))
      .slice(0, 4);
  }, [groups, createName]);

  const assignCreateHints = useMemo(() => {
    const q = qnorm(assignCreateName);
    if (!q) return [] as string[];
    return (groups || [])
      .map((g) => String(g.name || "").trim())
      .filter((name) => qnorm(name).includes(q))
      .slice(0, 4);
  }, [groups, assignCreateName]);

  const filteredAdd = useMemo(() => {
    const q = qnorm(addQuery);
    const subtree = collectSubtreeIds(addCategoryId);
    return (ungrouped || []).filter((p) => {
      if (subtree && !subtree.has(String(p.category_id || ""))) return false;
      if (!q) return true;
      return [productLabel(p), p.sku_gt || ""]
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
  }, [ungrouped, addQuery, addCategoryId, childrenByParent]);

  async function createGroup() {
    const name = createName.trim();
    if (!name || createNameDuplicate) return;
    const data = await api<{ group: { id: string } }>("/product-groups", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    setCreateName("");
    setCreateNameTouched(false);
    setGroupCreatedToast(`Группа "${name}" создана`);
    await loadGroups();
    if (data.group?.id) {
      setSelectedGroupId(data.group.id);
    }
  }

  async function saveGroupName() {
    if (!selectedGroupId) return;
    const name = editName.trim();
    if (!name) return;
    await api(`/product-groups/${encodeURIComponent(selectedGroupId)}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    });
    setEditMode(false);
    await loadGroups();
    await loadGroupDetails(selectedGroupId);
  }

  async function patchGroupItems(add: string[] = [], remove: string[] = []) {
    if (!selectedGroupId) return;
    const keepY = window.scrollY;
    setSoftRefreshing(true);
    try {
      await api(`/product-groups/${encodeURIComponent(selectedGroupId)}/items`, {
        method: "POST",
        body: JSON.stringify({ add, remove }),
      });
      setAddSelected([]);
      await refreshAfterGroupMutation();
      requestAnimationFrame(() => window.scrollTo({ top: keepY, left: 0, behavior: "auto" }));
    } finally {
      setSoftRefreshing(false);
    }
  }

  async function assignUngroupedToGroup() {
    if (!assignGroupId || ungroupedSelected.length === 0) return;
    const keepY = window.scrollY;
    setSoftRefreshing(true);
    try {
      await api(`/product-groups/${encodeURIComponent(assignGroupId)}/items`, {
        method: "POST",
        body: JSON.stringify({ add: ungroupedSelected }),
      });
      setUngroupedSelected([]);
      await refreshAfterGroupMutation();
      requestAnimationFrame(() => window.scrollTo({ top: keepY, left: 0, behavior: "auto" }));
    } finally {
      setSoftRefreshing(false);
    }
  }

  async function createAndAssignUngroupedToNewGroup() {
    const name = assignCreateName.trim();
    if (!name || ungroupedSelected.length === 0 || assignCreateDuplicate) return;
    const keepY = window.scrollY;
    setSoftRefreshing(true);
    try {
      const data = await api<{ group: { id: string } }>("/product-groups", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      const newGroupId = String(data.group?.id || "").trim();
      if (!newGroupId) return;
      await api(`/product-groups/${encodeURIComponent(newGroupId)}/items`, {
        method: "POST",
        body: JSON.stringify({ add: ungroupedSelected }),
      });
      setAssignCreateName("");
      setAssignCreateTouched(false);
      setAssignGroupId("");
      setUngroupedSelected([]);
      setGroupCreatedToast(`Группа "${name}" создана`);
      await refreshAfterGroupMutation();
      setSelectedGroupId(newGroupId);
      requestAnimationFrame(() => window.scrollTo({ top: keepY, left: 0, behavior: "auto" }));
    } finally {
      setSoftRefreshing(false);
    }
  }

  useEffect(() => {
    if (!groupCreatedToast) return;
    const t = window.setTimeout(() => setGroupCreatedToast(""), 2600);
    return () => window.clearTimeout(t);
  }, [groupCreatedToast]);

  async function openVariantModal() {
    if (!selectedGroupId) return;
    setVariantModalOpen(true);
    setVariantLoading(true);
    try {
      const data = await api<{ items: VariantParam[]; selected_ids?: string[] }>(
        `/product-groups/${encodeURIComponent(selectedGroupId)}/variant-params`
      );
      const selected = uniqueIds(data.selected_ids || groupDetails?.group?.variant_param_ids || []);
      setVariantOptions(data.items || []);
      setVariantSelected(selected);
    } finally {
      setVariantLoading(false);
    }
  }

  async function saveVariantParams() {
    if (!selectedGroupId) return;
    await api(`/product-groups/${encodeURIComponent(selectedGroupId)}`, {
      method: "PATCH",
      body: JSON.stringify({ variant_param_ids: uniqueIds(variantSelected) }),
    });
    setVariantModalOpen(false);
    await loadGroups();
    await loadGroupDetails(selectedGroupId);
  }

  function toggleAddSelection(productId: string, checked: boolean) {
    setAddSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(productId);
      else next.delete(productId);
      return Array.from(next);
    });
  }

  function toggleUngroupedSelection(productId: string, checked: boolean) {
    setUngroupedSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(productId);
      else next.delete(productId);
      return Array.from(next);
    });
  }

  function selectAllAddInCategory() {
    const ids = (ungrouped || [])
      .filter((p) => {
        if (!addCategoryId) return true;
        const subtree = collectSubtreeIds(addCategoryId);
        return !!subtree?.has(String(p.category_id || ""));
      })
      .map((p) => p.id);
    setAddSelected((prev) => uniqueIds([...prev, ...ids]));
  }

  function clearAllAddInCategory() {
    const subtree = addCategoryId ? collectSubtreeIds(addCategoryId) : null;
    setAddSelected((prev) =>
      prev.filter((id) => {
        const p = (ungrouped || []).find((x) => x.id === id);
        if (!p) return false;
        if (!subtree) return false;
        return !subtree.has(String(p.category_id || ""));
      })
    );
  }

  const selectedVariantNames = useMemo(() => {
    const byId = new Map<string, string>();
    for (const v of variantOptions) byId.set(v.id, v.name || v.code || v.id);
    return (groupDetails?.group?.variant_param_ids || []).map((id) => byId.get(id) || id);
  }, [groupDetails?.group?.variant_param_ids, variantOptions]);

  function toggleTreeNode(nodeId: string) {
    setAddTreeExpanded((prev) => ({ ...prev, [nodeId]: !prev[nodeId] }));
  }

  function isNodeVisibleBySearch(nodeId: string) {
    if (!treeSearchVisible) return true;
    return treeSearchVisible.has(nodeId);
  }

  function renderTreeNode(node: CatalogNode, level: number) {
    if (!isNodeVisibleBySearch(node.id)) return null;

    const children = (childrenByParent.get(node.id) || []).filter((x) => isNodeVisibleBySearch(x.id));
    const hasChildren = children.length > 0;
    const q = qnorm(addCategoryQuery);
    const expanded = q ? true : !!addTreeExpanded[node.id];

    return (
      <div key={node.id} className="pg-treeRowWrap">
        <div className={`pg-treeNodeLine ${addCategoryId === node.id ? "active" : ""}`} style={{ paddingLeft: 8 + level * 14 }}>
          <button
            type="button"
            className={`pg-treeCaret ${hasChildren ? "" : "empty"}`}
            onClick={() => hasChildren && toggleTreeNode(node.id)}
          >
            {hasChildren ? (expanded ? "▾" : "▸") : "•"}
          </button>
          <button type="button" className="pg-treeLabel" onClick={() => setAddCategoryId(node.id)}>
            {node.name}
          </button>
        </div>
        {hasChildren && expanded ? children.map((child) => renderTreeNode(child, level + 1)) : null}
      </div>
    );
  }

  function renderAddSelector() {
    const rootNodes = (childrenByParent.get("") || []).filter((x) => isNodeVisibleBySearch(x.id));

    return (
      <div className="pg-addPanel">
        <div className="pg-addGrid">
          <div className="pg-treeBox">
            <div className="pg-treeHead">
              <div>Категории</div>
              <input
                value={addCategoryQuery}
                onChange={(e) => setAddCategoryQuery(e.target.value)}
                placeholder="Поиск по категориям…"
                className="pg-treeSearch"
              />
            </div>

            <div className="pg-treeBody">
              <div className={`pg-treeNodeLine ${!addCategoryId ? "active" : ""}`}>
                <button type="button" className="pg-treeCaret empty">
                  •
                </button>
                <button type="button" className="pg-treeLabel" onClick={() => setAddCategoryId("")}>Все категории</button>
              </div>
              {rootNodes.map((n) => renderTreeNode(n, 0))}
            </div>
          </div>

          <div className="pg-productsSide">
            <div className="pg-selectedCatBox">
              <div className="muted">Выбранная категория</div>
              <div className="pg-selectedCatName">{addCategoryId ? categoryPathLabel(addCategoryId) : "Все категории"}</div>
            </div>

            <div className="pg-productsBox">
              <input
                value={addQuery}
                onChange={(e) => setAddQuery(e.target.value)}
                placeholder="Поиск по товарам без группы…"
              />
              <div className="pg-addActions pg-addActionsTop">
                <div className="muted">Найдено: {filteredAdd.length}</div>
                <div className="btn-group">
                  <button className="btn" type="button" onClick={selectAllAddInCategory}>
                    Выбрать подкатегорию
                  </button>
                  <button className="btn" type="button" onClick={clearAllAddInCategory}>
                    Снять подкатегорию
                  </button>
                </div>
              </div>

              <div className="pg-addList">
                <div className={`pg-listArea ${softRefreshing ? "isBusy" : ""}`}>
                {ungroupedLoading ? (
                  <div className="muted">Загрузка…</div>
                ) : filteredAdd.length === 0 ? (
                  <div className="muted">Нет товаров без группы.</div>
                ) : (
                  filteredAdd.map((p) => {
                    const checked = addSelected.includes(p.id);
                    return (
                      <div
                        key={p.id}
                        className={`pg-itemRow pg-itemRowSelectable ${checked ? "active" : ""}`}
                        role="button"
                        tabIndex={0}
                        onClick={() => toggleAddSelection(p.id, !checked)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggleAddSelection(p.id, !checked);
                          }
                        }}
                      >
                        <div className="pg-checkRow pg-checkRowWide">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) => toggleAddSelection(p.id, e.target.checked)}
                            onClick={(e) => e.stopPropagation()}
                          />
                          <span>
                            <div>{productLabel(p)}</div>
                            <div className="muted">{productSkuIds(p)}</div>
                          </span>
                        </div>
                      </div>
                    );
                  })
                )}
                  {softRefreshing ? (
                    <div className="pg-listOverlay">
                      <span className="pg-spinner" />
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="pg-addActions">
                <div className="muted">Выбрано: {addSelected.length}</div>
                <button
                  className="btn primary"
                  type="button"
                  disabled={addSelected.length === 0}
                  onClick={() => patchGroupItems(addSelected, [])}
                >
                  Добавить в группу
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="pg-page page-shell">
      <div className="page-header">
        <div className="page-header-main">
          <div className="page-title">Группы товаров</div>
          <div className="page-subtitle">Объединяйте товары в группы и управляйте вариантами.</div>
        </div>
        <div className="page-header-actions">
          <Link className="btn" to="/catalog">
            ← В каталог
          </Link>
          <button className="btn" type="button" onClick={refreshCurrentTab} disabled={groupsLoading || ungroupedLoading}>
            {groupsLoading || ungroupedLoading ? "Обновляю…" : "Обновить"}
          </button>
        </div>
      </div>

      <div className="page-tabs">
        <button className={`page-tab ${tab === TAB_GROUPS ? "active" : ""}`} onClick={() => setTab(TAB_GROUPS)}>
          Группы товаров
        </button>
        <button className={`page-tab ${tab === TAB_UNGROUPED ? "active" : ""}`} onClick={() => setTab(TAB_UNGROUPED)}>
          Товары без группы
        </button>
      </div>

      {tab === TAB_GROUPS ? (
        <div className="pg-grid">
          <div className="card pg-left">
            <div className="pg-leftHead">
              <div className="pg-leftHeadMain">
                <div className="card-title">Группы</div>
                <div className="muted">{groups.length} шт.</div>
              </div>
            </div>

            <div className="pg-sectionLabel">Поиск групп</div>
            <div className="pg-groupsSearch">
              <input
                value={groupsQuery}
                onChange={(e) => setGroupsQuery(e.target.value)}
                placeholder="Поиск по группам…"
              />
            </div>

            <div className="pg-sectionLabel">Создание группы</div>
            <div className="pg-create">
              <input
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                onBlur={() => setCreateNameTouched(true)}
                placeholder="Наименование группы"
                list={createName.trim() ? "pg-group-name-hints-create" : undefined}
              />
              <button
                className="btn primary"
                type="button"
                onClick={createGroup}
                disabled={!createName.trim() || createNameDuplicate}
              >
                Добавить
              </button>
            </div>
            {createNameTouched && createNameDuplicate ? (
              <div className="pg-inlineWarn">Группа с таким названием уже существует.</div>
            ) : createNameHints.length > 0 ? (
              <div className="pg-inlineHint">Похожие: {createNameHints.join(", ")}</div>
            ) : null}

            <div className="pg-sectionHead">
              <div className="pg-sectionLabel">Список групп</div>
              {groupsByRoot.length > 0 ? (
                <button
                  className="btn pg-miniBtn"
                  type="button"
                  onClick={() => {
                    const next: Record<string, boolean> = {};
                    for (const b of groupsByRoot) next[b.key] = !hasExpandedGroups;
                    setGroupsTreeExpanded(next);
                  }}
                >
                  {hasExpandedGroups ? "Свернуть все" : "Развернуть все"}
                </button>
              ) : null}
            </div>

            <div className="pg-groupList">
              {groupsLoading ? (
                <div className="muted">Загрузка…</div>
              ) : filteredGroups.length === 0 ? (
                <div className="muted">Пока нет групп. Создайте первую.</div>
              ) : (
                groupsByRoot.map((bucket) => (
                  <div key={bucket.key} className="pg-groupRoot">
                    <button
                      type="button"
                      className={`pg-groupRootHead ${groupsTreeExpanded[bucket.key] ? "active" : ""}`}
                      onClick={() =>
                        setGroupsTreeExpanded((prev) => ({ ...prev, [bucket.key]: !prev[bucket.key] }))
                      }
                    >
                      <span className="pg-groupRootLabel">
                        <span className="pg-groupRootCaret">{groupsTreeExpanded[bucket.key] ? "▾" : "▸"}</span>
                        <span>{bucket.label}</span>
                      </span>
                      <span className="pg-groupRootCount">{bucket.items.length}</span>
                    </button>

                    {groupsTreeExpanded[bucket.key] ? (
                      <div className="pg-groupRootItems">
                        {bucket.items.map((g) => (
                          <button
                            key={g.id}
                            type="button"
                            className={`pg-group ${selectedGroupId === g.id ? "active" : ""}`}
                            onClick={() => setSelectedGroupId(g.id)}
                          >
                            <span className="pg-groupName">{g.name}</span>
                            <span className="pg-groupCount">{g.count}</span>
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="pg-rightStack">
            {!selectedGroupId ? (
              <div className="card pg-right">
                <div className="muted">Выберите группу, чтобы увидеть товары.</div>
              </div>
            ) : (
              <>
                <div className="card pg-right">
                  {groupLoading ? (
                <div className="muted">Загрузка группы…</div>
              ) : !groupDetails ? (
                <div className="muted">Группа не найдена.</div>
              ) : (
                <>
                  <div className="pg-groupHeader">
                    <div>
                      {editMode ? (
                        <input value={editName} onChange={(e) => setEditName(e.target.value)} />
                      ) : (
                        <div className="pg-groupTitle">{groupDetails.group.name}</div>
                      )}
                      <div className="muted">{groupDetails.items.length} товаров</div>
                    </div>
                    <div className="pg-groupActions">
                      <button
                        className="btn"
                        type="button"
                        onClick={() => {
                          if (groupDetails.items.length > 0) setAddModalOpen(true);
                        }}
                        disabled={groupDetails.items.length === 0}
                        title={groupDetails.items.length > 0 ? "Добавить товары через модальное окно" : "Добавление ниже в блоке"}
                      >
                        Добавить товары
                      </button>
                      <button className="btn" type="button" onClick={openVariantModal}>
                        Параметры вариантов
                      </button>
                      {editMode ? (
                        <>
                          <button className="btn primary" type="button" onClick={saveGroupName}>
                            Сохранить
                          </button>
                          <button className="btn" type="button" onClick={() => setEditMode(false)}>
                            Отмена
                          </button>
                        </>
                      ) : (
                        <button className="btn" type="button" onClick={() => setEditMode(true)}>
                          Редактировать
                        </button>
                      )}
                    </div>
                  </div>

                  {selectedVariantNames.length > 0 ? (
                    <div className="pg-pills">
                      {selectedVariantNames.map((x) => (
                        <span key={x} className="pg-pill">
                          {x}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="muted">Параметры вариантов для группы не выбраны.</div>
                  )}

                  {groupDetails.items.length === 0 ? (
                    <div className="pg-inlineAddWrap">
                      <div className="card-title">Добавить товары</div>
                      {renderAddSelector()}
                    </div>
                  ) : null}
                </>
              )}
                </div>

                <div className="card pg-productsCard">
                  {groupLoading ? (
                <div className="muted">Загрузка товаров…</div>
              ) : !groupDetails || groupDetails.items.length === 0 ? (
                <div className="empty-state">В этой группе пока нет товаров.</div>
              ) : (
                <>
                  <div className="card-title">Товары группы</div>
                  <div className={`pg-items pg-listArea ${softRefreshing ? "isBusy" : ""}`}>
                    {groupDetails.items.map((p) => (
                      <div key={p.id} className="pg-itemRow">
                        <div>
                          <Link to={`/products/${p.id}`} className="pg-itemTitle">
                            {productLabel(p)}
                          </Link>
                          <div className="muted">{productSkuIds(p)}</div>
                          {!!p.category_id && <div className="muted">{categoryPathLabel(p.category_id)}</div>}
                        </div>
                        <button className="btn danger" type="button" onClick={() => patchGroupItems([], [p.id])}>
                          Убрать
                        </button>
                      </div>
                    ))}
                    {softRefreshing ? (
                      <div className="pg-listOverlay">
                        <span className="pg-spinner" />
                      </div>
                    ) : null}
                  </div>
                </>
              )}
                </div>
              </>
            )}
          </div>
        </div>
      ) : (
        <div className="card pg-ungrouped">
          <div className="pg-ungroupedHead">
            <div>
              <div className="card-title">Товары без группы</div>
              <div className="muted">{filteredUngrouped.length} товаров</div>
            </div>
          </div>

          <div className="pg-filters">
            <input
              value={ungroupedQuery}
              onChange={(e) => setUngroupedQuery(e.target.value)}
              placeholder="Поиск по товарам и артикулам…"
            />
            <select value={ungroupedCategoryId} onChange={(e) => setUngroupedCategoryId(e.target.value)}>
              <option value="">Все категории</option>
              {categoryOptionsForUngrouped.map((n) => (
                  <option key={n.id} value={n.id}>
                    {categoryPathLabel(n.id)}
                  </option>
                ))}
            </select>
          </div>

          <div className="pg-filtersActions">
            <button className="btn" type="button" onClick={() => setUngroupedSelected(filteredUngrouped.map((p) => p.id))}>
              Выбрать всё
            </button>
            <button className="btn" type="button" onClick={() => setUngroupedSelected([])}>
              Снять всё
            </button>
          </div>

          <div className={`pg-ungroupedList pg-listArea ${softRefreshing ? "isBusy" : ""}`}>
            {ungroupedLoading ? (
              <div className="muted">Загрузка…</div>
            ) : filteredUngrouped.length === 0 ? (
              <div className="empty-state">Товары без группы не найдены.</div>
            ) : (
              filteredUngrouped.map((p) => {
                const checked = ungroupedSelected.includes(p.id);
                return (
                  <div
                    key={p.id}
                    className={`pg-itemRow pg-itemRowSelectable ${checked ? "active" : ""}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => toggleUngroupedSelection(p.id, !checked)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        toggleUngroupedSelection(p.id, !checked);
                      }
                    }}
                  >
                    <div className="pg-checkRow pg-checkRowWide">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => toggleUngroupedSelection(p.id, e.target.checked)}
                        onClick={(e) => e.stopPropagation()}
                      />
                      <span>
                        <div>{productLabel(p)}</div>
                        {!!p.category_id && <div className="muted">{categoryPathLabel(p.category_id)}</div>}
                      </span>
                    </div>
                    <Link to={`/products/${p.id}`} className="pg-itemSku" onClick={(e) => e.stopPropagation()}>
                      {productSkuIds(p)}
                    </Link>
                  </div>
                );
              })
            )}
            {softRefreshing ? (
              <div className="pg-listOverlay">
                <span className="pg-spinner" />
              </div>
            ) : null}
          </div>

          {ungroupedSelected.length > 0 && (
            <div className="pg-selectionBar">
              <div className="pg-selectionCount">Выбрано: {ungroupedSelected.length}</div>
              <div className="pg-selectionControls">
                <select value={assignGroupId} onChange={(e) => setAssignGroupId(e.target.value)}>
                  <option value="">Выберите группу</option>
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
                <button
                  className="btn primary"
                  type="button"
                  disabled={!assignGroupId}
                  onClick={assignUngroupedToGroup}
                >
                  Добавить
                </button>
                <input
                  value={assignCreateName}
                  onChange={(e) => setAssignCreateName(e.target.value)}
                  onBlur={() => setAssignCreateTouched(true)}
                  placeholder="Введите наименование"
                  list={assignCreateName.trim() ? "pg-group-name-hints-assign" : undefined}
                />
                <button
                  className="btn primary"
                  type="button"
                  disabled={!assignCreateName.trim() || assignCreateDuplicate}
                  onClick={createAndAssignUngroupedToNewGroup}
                >
                  Создать
                </button>
              </div>
              {assignCreateTouched && assignCreateDuplicate ? (
                <div className="pg-inlineWarn">Группа с таким названием уже существует.</div>
              ) : assignCreateHints.length > 0 ? (
                <div className="pg-inlineHint">Похожие: {assignCreateHints.join(", ")}</div>
              ) : null}
            </div>
          )}
        </div>
      )}

      <datalist id="pg-group-name-hints-create">
        {createNameHints.map((name) => (
          <option key={`hint-create-${name}`} value={name} />
        ))}
      </datalist>
      <datalist id="pg-group-name-hints-assign">
        {assignCreateHints.map((name) => (
          <option key={`hint-assign-${name}`} value={name} />
        ))}
      </datalist>

      {groupCreatedToast ? (
        <div className="pg-createdToast" role="status" aria-live="polite">
          <span className="pg-createdToastIcon">✓</span>
          <span>{groupCreatedToast}</span>
        </div>
      ) : null}

      {addModalOpen ? (
        <div className="pg-modalBackdrop" onClick={() => setAddModalOpen(false)}>
          <div className="pg-modal pg-modalWide" onClick={(e) => e.stopPropagation()}>
            <div className="pg-modalHead">
              <div>
                <div className="card-title">Добавить товары в группу</div>
                <div className="muted">Поиск по категориям и товарам без группы.</div>
              </div>
              <button className="btn" type="button" onClick={() => setAddModalOpen(false)}>
                Закрыть
              </button>
            </div>
            <div className="pg-modalBody">{renderAddSelector()}</div>
          </div>
        </div>
      ) : null}

      {variantModalOpen ? (
        <div className="pg-modalBackdrop" onClick={() => setVariantModalOpen(false)}>
          <div className="pg-modal" onClick={(e) => e.stopPropagation()}>
            <div className="pg-modalHead">
              <div>
                <div className="card-title">Параметры вариантов группы</div>
                <div className="muted">Берутся из мастер-шаблонов, сервисные поля скрыты.</div>
              </div>
              <button className="btn" type="button" onClick={() => setVariantModalOpen(false)}>
                Закрыть
              </button>
            </div>

            <div className="pg-modalBody">
              {variantLoading ? (
                <div className="muted">Загрузка…</div>
              ) : variantOptions.length === 0 ? (
                <div className="empty-state">Нет доступных параметров. Добавьте товары в группу и настройте шаблон.</div>
              ) : (
                <div className="pg-paramList">
                  {variantOptions.map((p) => {
                    const checked = variantSelected.includes(p.id);
                    return (
                      <label key={p.id} className="pg-checkRow pg-checkRowWide pg-paramRow">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => {
                            const on = e.target.checked;
                            setVariantSelected((prev) => {
                              const next = new Set(prev);
                              if (on) next.add(p.id);
                              else next.delete(p.id);
                              return Array.from(next);
                            });
                          }}
                        />
                        <span>
                          <div>{p.name}</div>
                          <div className="muted">{p.code || p.id}</div>
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="pg-modalActions">
              <div className="muted">Выбрано: {variantSelected.length}</div>
              <button className="btn primary" type="button" onClick={saveVariantParams} disabled={variantLoading}>
                Сохранить
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
