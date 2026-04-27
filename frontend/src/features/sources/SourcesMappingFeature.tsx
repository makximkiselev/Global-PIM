import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import SourcesMarketplaceSection from "./SourcesMarketplaceSection";
import SourcesValueMappingSection from "./SourcesValueMappingSection";
import CompetitorMappingFeature from "./CompetitorMappingFeature";
import CompetitorDiscoveryPanel from "./CompetitorDiscoveryPanel";
import PageTabs from "../../components/ui/PageTabs";
import Badge from "../../components/ui/Badge";
import { api } from "../../lib/api";
import "../../styles/product-groups.css";
import "../../styles/competitor-mapping.css";
import "../../styles/sources-mapping-modern.css";

type SourcesTab = "sources" | "params" | "values" | "competitors";

type MappingBootstrapResp = {
  catalog_nodes?: Array<{ id: string; parent_id: string | null; name: string }>;
  catalog_items?: Array<{ id: string; name: string; path?: string }>;
  mappings?: Record<string, Record<string, string>>;
};

const MAPPING_BOOTSTRAP_CACHE_KEY = "sources_mapping_feature_bootstrap_v1";
let mappingBootstrapCache: MappingBootstrapResp | null = null;

function normalizeTab(value: string | null): SourcesTab {
  if (value === "params") return "params";
  if (value === "values") return "values";
  if (value === "competitors") return "competitors";
  return "sources";
}

async function loadMappingBootstrap() {
  if (mappingBootstrapCache) return mappingBootstrapCache;
  if (typeof window !== "undefined") {
    try {
      const raw = window.localStorage.getItem(MAPPING_BOOTSTRAP_CACHE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as MappingBootstrapResp;
        mappingBootstrapCache = parsed;
        return parsed;
      }
    } catch {
      // ignore cache read errors
    }
  }
  const data = await api<MappingBootstrapResp>("/marketplaces/mapping/import/categories");
  mappingBootstrapCache = data;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(MAPPING_BOOTSTRAP_CACHE_KEY, JSON.stringify(data));
    } catch {
      // ignore cache write errors
    }
  }
  return data;
}

export default function SourcesMappingFeature() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = normalizeTab(searchParams.get("tab"));
  const initialCategoryId = searchParams.get("category") || "";
  const [tab, setTabState] = useState<SourcesTab>(initialTab);
  const [selectedCategoryId, setSelectedCategoryId] = useState(initialCategoryId);
  const [selectedCategoryName, setSelectedCategoryName] = useState("");
  const [categoryResolving, setCategoryResolving] = useState(initialTab === "params" && !initialCategoryId);
  const tabLabel =
    tab === "sources"
      ? "Категории и источники"
      : tab === "params"
        ? "Сопоставление параметров"
        : tab === "values"
          ? "Значения параметров"
          : "Конкуренты";

  const tabDescription = useMemo(
    () =>
      tab === "sources"
        ? "Рабочий экран для связки категорий PIM с маркетплейсами и конкурентными источниками."
        : tab === "params"
          ? "Рабочий экран для связи параметров инфо-модели с полями каналов и конкурентных площадок."
          : tab === "values"
            ? "Контроль канонических значений, allowed values площадок и export-написаний для каждого параметра."
          : "Очередь найденных конкурентных карточек re-store/store77, matching score и модерация контент-менеджером.",
    [tab],
  );

  useEffect(() => {
    const nextTab = normalizeTab(searchParams.get("tab"));
    const nextCategoryId = searchParams.get("category") || "";
    setTabState((prev) => (prev === nextTab ? prev : nextTab));
    setSelectedCategoryId(nextCategoryId);
    setSelectedCategoryName((prev) => (nextCategoryId ? prev : ""));
    setCategoryResolving(nextTab === "params" && !nextCategoryId);
  }, [searchParams]);

  useEffect(() => {
    if (tab !== "params" || !selectedCategoryId) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await loadMappingBootstrap();
        if (cancelled) return;
        const mappings = data.mappings || {};
        const currentItem = (data.catalog_items || []).find((item) => item.id === selectedCategoryId);
        if (currentItem?.name) {
          setSelectedCategoryName((prev) => (prev === currentItem.name ? prev : currentItem.name));
        }
        const hasDirectMapping = Object.values(mappings[selectedCategoryId] || {}).some((value) => !!String(value || "").trim());
        if (hasDirectMapping) return;

        const nodes = data.catalog_nodes || [];
        const itemsById = new Map((data.catalog_items || []).map((item) => [item.id, item]));
        const childrenByParent = new Map<string, Array<{ id: string; parent_id: string | null; name: string }>>();
        for (const node of nodes) {
          const parentId = node.parent_id || "";
          const bucket = childrenByParent.get(parentId) || [];
          bucket.push(node);
          childrenByParent.set(parentId, bucket);
        }

        const descendants: Array<{ id: string; name: string; path: string }> = [];
        const stack = [...(childrenByParent.get(selectedCategoryId) || [])];
        const seen = new Set<string>();
        while (stack.length) {
          const node = stack.pop();
          if (!node || seen.has(node.id)) continue;
          seen.add(node.id);
          stack.push(...(childrenByParent.get(node.id) || []));
          const mapped = Object.values(mappings[node.id] || {}).some((value) => !!String(value || "").trim());
          if (!mapped) continue;
          const item = itemsById.get(node.id);
          descendants.push({
            id: node.id,
            name: item?.name || node.name,
            path: item?.path || item?.name || node.name,
          });
        }
        descendants.sort((a, b) => a.path.localeCompare(b.path, "ru"));
        if (!descendants.length) return;
        setCategoryResolving(true);
        const nextCategory = descendants[0];
        setSelectedCategory(nextCategory.id, nextCategory.name);
      } finally {
        if (!cancelled) setCategoryResolving(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, selectedCategoryId, searchParams]);

  function setTab(nextTab: SourcesTab) {
    setTabState(nextTab);
    setCategoryResolving(nextTab === "params");
    const next = new URLSearchParams(searchParams);
    next.set("tab", nextTab);
    setSearchParams(next, { replace: true });
  }

  function setSelectedCategory(nextCategoryId: string, nextCategoryName: string) {
    setSelectedCategoryId((prev) => (prev === nextCategoryId ? prev : nextCategoryId));
    setSelectedCategoryName((prev) => (prev === nextCategoryName ? prev : nextCategoryName));
    const currentCategoryId = searchParams.get("category") || "";
    if (currentCategoryId === nextCategoryId) return;
    const next = new URLSearchParams(searchParams);
    if (nextCategoryId) next.set("category", nextCategoryId);
    else next.delete("category");
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="page-shell sourcesMappingPage">
      <div className="sourcesMappingTopbar">
        <div className="sourcesMappingTopbarMain">
          <div className="sourcesMappingEyebrow">Рабочий контур</div>
          <div className="sourcesMappingTitleRow">
            <h1 className="sourcesMappingTitle">Каналы и источники</h1>
            <Badge tone="active">{tabLabel}</Badge>
          </div>
          <p className="sourcesMappingSubtitle">{tabDescription}</p>
        </div>
        <div className="sourcesMappingTopbarMeta">
          <div className="sourcesMappingMetaLabel">Текущий контур</div>
          <div className="sourcesMappingMetaValue">{selectedCategoryName || "Выбери категорию в дереве"}</div>
        </div>
      </div>

      <PageTabs
        className="sourcesMappingTabs"
        activeKey={tab}
        onChange={(key) => setTab(key as SourcesTab)}
        items={[
          { key: "sources", label: "Категории и источники" },
          { key: "params", label: "Сопоставление параметров" },
          { key: "values", label: "Значения" },
          { key: "competitors", label: "Конкуренты" },
        ]}
      />

      <div className="sourcesMappingCanvas">
        {tab === "params" && categoryResolving ? (
          <div className="sourcesMappingCanvasIntro">
            <div className="sourcesMappingCanvasTitle">Подбираем рабочую категорию</div>
            <div className="sourcesMappingCanvasSub">
              Для сопоставления параметров открываем ближайшую дочернюю категорию, где уже есть привязка к каналам.
            </div>
          </div>
        ) : null}

        {tab === "sources" ? (
          <div className="sourcesMappingCanvasIntro">
            <div className="sourcesMappingCanvasTitle">Категории и источники</div>
            <div className="sourcesMappingCanvasSub">
              Единое дерево категорий для привязок маркетплейсов и ссылок конкурентов без переходов между отдельными экранами.
            </div>
          </div>
        ) : null}

        {tab === "sources" && (
          <SourcesMarketplaceSection
            key="sources-workspace"
            embedded
            forcedMainTab="import"
            forcedImportTab="categories"
            hideMainTabs
            hideImportTabs
            selectedCategoryId={selectedCategoryId}
            onSelectedCategoryChange={(categoryId, categoryName) => {
              setSelectedCategory(categoryId, categoryName);
            }}
            renderCategoryDetailExtra={(categoryId, categoryName) => (
              <div className="sm-section sm-sectionBordered">
                <CompetitorMappingFeature embedded view="links" categoryId={categoryId} categoryName={categoryName} />
              </div>
            )}
          />
        )}

        {tab === "params" && !categoryResolving && (
          <SourcesMarketplaceSection
            key="params-workspace"
            embedded
            forcedMainTab="import"
            forcedImportTab="features"
            hideMainTabs
            hideImportTabs
            selectedCategoryId={selectedCategoryId}
            onSelectedCategoryChange={(categoryId, categoryName) => {
              setSelectedCategory(categoryId, categoryName);
            }}
            useCatalogTreeForFeatures
          />
        )}

        {tab === "values" && (
          <SourcesValueMappingSection
            selectedCategoryId={selectedCategoryId}
            onSelectedCategoryChange={(categoryId, categoryName) => {
              setSelectedCategory(categoryId, categoryName);
            }}
          />
        )}

        {tab === "competitors" && <CompetitorDiscoveryPanel />}
      </div>
    </div>
  );
}
