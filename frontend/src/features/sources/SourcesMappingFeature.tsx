import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import SourcesMarketplaceSection from "./SourcesMarketplaceSection";
import SourcesValueMappingSection from "./SourcesValueMappingSection";
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
type CompetitorSourceSuggestion = {
  id: string;
  type: "observed" | "search" | string;
  label: string;
  url: string;
  confidence?: number;
  products_count?: number;
  evidence?: string;
  examples?: string[];
};
type CompetitorCategorySource = {
  id: "restore" | "store77" | string;
  name: string;
  domain: string;
  status: string;
  products_count: number;
  confirmed_count: number;
  candidates_count: number;
  needs_review_count: number;
  suggestions: CompetitorSourceSuggestion[];
};
type CompetitorCategoryResp = {
  ok: boolean;
  category: { id: string; name: string; products_count: number; scanned_product_ids?: string[] };
  sources: CompetitorCategorySource[];
};

const MAPPING_BOOTSTRAP_CACHE_KEY = "sources_mapping_feature_bootstrap_v1";
let mappingBootstrapCache: MappingBootstrapResp | null = null;

function normalizeTab(value: string | null): SourcesTab {
  if (value === "mp_categories" || value === "marketplace_categories") return "sources";
  if (value === "params") return "params";
  if (value === "mp_attributes" || value === "attributes") return "params";
  if (value === "values") return "values";
  if (value === "competitor_links" || value === "competitor" || value === "discovery") return "competitors";
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

function confidenceLabel(value?: number) {
  const raw = Number(value || 0);
  if (!Number.isFinite(raw) || raw <= 0) return "нет score";
  return `${Math.round(raw * 100)}%`;
}

function CategoryCompetitorSourcesPanel({ categoryId, categoryName }: { categoryId: string; categoryName: string }) {
  const [data, setData] = useState<CompetitorCategoryResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!categoryId) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    api<CompetitorCategoryResp>(`/competitor-mapping/discovery/categories/${encodeURIComponent(categoryId)}`)
      .then((response) => {
        if (!cancelled) setData(response);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Не удалось загрузить competitors");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [categoryId]);

  return (
    <div className="sourcesCategoryCompetitors">
      <div className="sourcesCategoryCompetitorsHead">
        <div>
          <div className="sourcesCategoryCompetitorsKicker">Конкурентные источники</div>
          <div className="sourcesCategoryCompetitorsTitle">re-store / store77</div>
        </div>
        <Badge tone={data?.category?.products_count ? "active" : "neutral"}>
          {loading ? "loading" : `${data?.category?.products_count || 0} SKU`}
        </Badge>
      </div>
      <p className="sourcesCategoryCompetitorsText">
        Здесь должны жить не параметры и не карточки товара, а привязка ветки PIM к конкурентным разделам/поиску. Дальше эти источники питают discovery и enrichment.
      </p>

      {error ? <div className="sourcesCategoryCompetitorsError">{error}</div> : null}
      {loading ? <div className="sourcesCategoryCompetitorsEmpty">Загружаем источники для “{categoryName}”...</div> : null}

      {!loading && data?.sources?.length ? (
        <div className="sourcesCategoryCompetitorsList">
          {data.sources.map((source) => (
            <div className="sourcesCategoryCompetitorCard" key={source.id}>
              <div className="sourcesCategoryCompetitorCardHead">
                <div>
                  <strong>{source.name}</strong>
                  <span>{source.domain}</span>
                </div>
                <Badge tone={source.needs_review_count ? "pending" : source.confirmed_count ? "active" : "neutral"}>
                  {source.confirmed_count ? `${source.confirmed_count} confirmed` : source.needs_review_count ? `${source.needs_review_count} review` : "нет связей"}
                </Badge>
              </div>
              <div className="sourcesCategoryCompetitorStats">
                <span>{source.candidates_count} candidates</span>
                <span>{source.confirmed_count} links</span>
              </div>
              <div className="sourcesCategoryCompetitorSuggestions">
                {(source.suggestions || []).map((suggestion) => (
                  <a className="sourcesCategoryCompetitorSuggestion" href={suggestion.url} target="_blank" rel="noreferrer" key={suggestion.id}>
                    <span>{suggestion.label}</span>
                    <em>
                      {suggestion.type === "search" ? "поиск" : "найдено"} · {confidenceLabel(suggestion.confidence)}
                    </em>
                  </a>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
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
        ? "Маркетплейсы — куда выгружаем товары. Конкуренты — откуда берем evidence для enrichment. Параметры и значения живут на следующих вкладках."
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
              Слева дерево PIM, в центре категории Я.Маркета/Ozon, справа competitor context по re-store/store77 для выбранной ветки.
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
              <CategoryCompetitorSourcesPanel categoryId={categoryId} categoryName={categoryName} />
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
