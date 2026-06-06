import { useEffect, useMemo, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import SourcesMarketplaceSection from "./SourcesMarketplaceSection";
import SourcesParamsWorkspaceSection from "./SourcesParamsWorkspaceSection";
import SourcesValueMappingSection from "./SourcesValueMappingSection";
import WorkspaceHeader from "../../components/layout/WorkspaceHeader";
import WorkspaceTaskQueue from "../../components/layout/WorkspaceTaskQueue";
import { api } from "../../lib/api";
import "../../styles/product-groups.css";
import "../../styles/competitor-mapping.css";
import "../../styles/sources-mapping-modern.css";

type SourcesTab = "sources" | "params" | "values";

type MappingBootstrapResp = {
  catalog_nodes?: Array<{ id: string; parent_id: string | null; name: string }>;
  catalog_items?: Array<{ id: string; name: string; path?: string }>;
  mappings?: Record<string, Record<string, string>>;
};
const MAPPING_BOOTSTRAP_CACHE_KEY = "sources_mapping_feature_bootstrap_v2";
const PRODUCT_CONTEXT_CACHE_KEY = "smartpim_last_product_context_v1";
let mappingBootstrapCache: MappingBootstrapResp | null = null;

const TAB_ITEMS: Array<{ key: SourcesTab; label: string; hint: string }> = [
  { key: "sources", label: "Категории", hint: "Площадки и конкурентные источники" },
  { key: "params", label: "Черновик параметров", hint: "Источники -> поля PIM" },
  { key: "values", label: "Значения", hint: "Написания для выгрузки" },
];

function readStoredProductContext(): { productId: string; categoryId: string; categoryName: string } {
  if (typeof window === "undefined") return { productId: "", categoryId: "", categoryName: "" };
  try {
    const parsed = JSON.parse(window.localStorage.getItem(PRODUCT_CONTEXT_CACHE_KEY) || "{}");
    return {
      productId: String(parsed?.productId || "").trim(),
      categoryId: String(parsed?.categoryId || "").trim(),
      categoryName: String(parsed?.categoryName || "").trim(),
    };
  } catch {
    return { productId: "", categoryId: "", categoryName: "" };
  }
}

function sourcesHref(tab: SourcesTab, categoryId: string, productId: string) {
  const params = new URLSearchParams();
  params.set("tab", tab);
  if (categoryId) params.set("category", categoryId);
  if (productId) params.set("product", productId);
  return `/sources?${params.toString()}`;
}

function exportHref(categoryId: string, productId: string) {
  if (productId) return `/catalog/exchange?tab=export&product=${encodeURIComponent(productId)}`;
  if (categoryId) return `/catalog/exchange?tab=export&category=${encodeURIComponent(categoryId)}`;
  return "/catalog/exchange?tab=export";
}

function sourcesNextAction(tab: SourcesTab, categoryId: string, productId: string) {
  if (!categoryId) {
    return {
      title: "Выберите категорию",
      detail: "Сначала выберите рабочую ветку каталога, чтобы видеть привязки площадок, параметры и значения в одном контексте.",
      label: "Категории",
      href: sourcesHref("sources", "", productId),
      tone: "pending",
    };
  }
  if (tab === "sources") {
    return {
      title: "Собрать параметры",
      detail: "Когда категория площадки и конкурентные карточки выбраны, переходите к черновику PIM-параметров.",
      label: "К параметрам",
      href: sourcesHref("params", categoryId, productId),
      tone: "pending",
    };
  }
  if (tab === "params") {
    return {
      title: "Нормализовать значения",
      detail: "После связки полей проверьте справочники, boolean/enum значения и provider-specific output.",
      label: "К значениям",
      href: sourcesHref("values", categoryId, productId),
      tone: "pending",
    };
  }
  return {
    title: productId ? "Проверить экспорт SKU" : "Проверить экспорт категории",
    detail: productId
      ? "После значений запустите readiness batch по исходному SKU."
      : "После значений запустите readiness batch. Для финальной проверки лучше выбрать отдельный SKU.",
    label: productId ? "Экспорт SKU" : "Проверить экспорт",
    href: exportHref(categoryId, productId),
    tone: "active",
  };
}

function normalizeTab(value: string | null): SourcesTab {
  if (value === "mp_categories" || value === "marketplace_categories") return "sources";
  if (value === "params") return "params";
  if (value === "mp_attributes" || value === "attributes") return "params";
  if (value === "values") return "values";
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
  const data = await api<MappingBootstrapResp>("/marketplaces/mapping/import/categories/bootstrap");
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
  const rawTab = searchParams.get("tab");
  const initialTab = normalizeTab(searchParams.get("tab"));
  const storedContext = useMemo(() => readStoredProductContext(), []);
  const categoryParam = String(searchParams.get("category") || "").trim();
  const explicitProductParam = String(searchParams.get("product") || "").trim();
  const storedMatchesExplicitProduct = !!explicitProductParam && storedContext.productId === explicitProductParam;
  const initialCategoryId = categoryParam || (!explicitProductParam || storedMatchesExplicitProduct ? storedContext.categoryId : "") || "";
  const providerParam = String(searchParams.get("provider") || "").trim();
  const providerCategoryParam = String(searchParams.get("provider_category") || "").trim();
  const parameterParam = String(searchParams.get("parameter") || "").trim();
  const productParam = explicitProductParam || (!categoryParam ? storedContext.productId : "");
  const [tab, setTabState] = useState<SourcesTab>(initialTab);
  const [selectedCategoryId, setSelectedCategoryId] = useState(initialCategoryId);
  const [selectedCategoryName, setSelectedCategoryName] = useState(storedContext.categoryName);
  const activeCategoryId = selectedCategoryId || categoryParam;
  const [categoryResolving, setCategoryResolving] = useState(
    (initialTab === "params" && !initialCategoryId) || !!providerCategoryParam,
  );
  const tabDescription = useMemo(
    () =>
      tab === "sources"
        ? "Выберите PIM-категорию, сопоставьте площадки и подтвердите конкурентные карточки для насыщения товаров."
        : tab === "params"
          ? "Соберите черновик PIM-параметров из площадок, конкурентов и товарных данных, затем утверждайте модель."
          : "Контроль значений PIM, справочников площадок и написаний для выгрузки по каждому параметру.",
    [tab],
  );
  const nextAction = useMemo(() => sourcesNextAction(tab, activeCategoryId, productParam), [productParam, activeCategoryId, tab]);

  useEffect(() => {
    const nextTab = normalizeTab(searchParams.get("tab"));
    const nextCategoryParam = String(searchParams.get("category") || "").trim();
    const nextProductParam = String(searchParams.get("product") || "").trim();
    const nextStoredMatchesProduct = !!nextProductParam && storedContext.productId === nextProductParam;
    const nextCategoryId = nextCategoryParam || (!nextProductParam || nextStoredMatchesProduct ? storedContext.categoryId : "") || "";
    const nextProviderCategoryId = String(searchParams.get("provider_category") || "").trim();
    setTabState((prev) => (prev === nextTab ? prev : nextTab));
    setSelectedCategoryId(nextCategoryId);
    setSelectedCategoryName((prev) => (nextCategoryId ? prev : ""));
    setCategoryResolving((nextTab === "params" && !nextCategoryId) || !!nextProviderCategoryId);
  }, [searchParams, storedContext.categoryId]);

  useEffect(() => {
    if (!productParam && !activeCategoryId) return;
    try {
      window.localStorage.setItem(PRODUCT_CONTEXT_CACHE_KEY, JSON.stringify({
        productId: productParam,
        categoryId: activeCategoryId,
        categoryName: selectedCategoryName,
        updatedAt: new Date().toISOString(),
      }));
    } catch {
      // Context persistence is optional; explicit URL params remain authoritative.
    }
  }, [productParam, activeCategoryId, selectedCategoryName]);

  useEffect(() => {
    if (!activeCategoryId || selectedCategoryName) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await loadMappingBootstrap();
        if (cancelled) return;
        const currentItem = (data.catalog_items || []).find((item) => item.id === activeCategoryId);
        const currentNode = (data.catalog_nodes || []).find((item) => item.id === activeCategoryId);
        const nextName = currentItem?.name || currentItem?.path || currentNode?.name || "";
        if (nextName) setSelectedCategoryName((prev) => (prev === nextName ? prev : nextName));
      } catch {
        // The id is still enough to keep links/actions correct; the name can resolve on the next successful bootstrap.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeCategoryId, selectedCategoryName]);

  useEffect(() => {
    if (!providerParam || !providerCategoryParam) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await loadMappingBootstrap();
        if (cancelled) return;
        const mappings = data.mappings || {};
        const matched = (data.catalog_items || []).find(
          (item) => String(mappings[item.id]?.[providerParam] || "").trim() === providerCategoryParam,
        );
        if (matched) {
          setSelectedCategory(matched.id, matched.name || matched.path || matched.id);
        }
      } finally {
        if (!cancelled) setCategoryResolving(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [providerParam, providerCategoryParam, searchParams]);

  useEffect(() => {
    if (tab !== "params") return;
    let cancelled = false;
    (async () => {
      try {
        const data = await loadMappingBootstrap();
        if (cancelled) return;
        const mappings = data.mappings || {};
        if (!selectedCategoryId) {
          const mappedItem = [...(data.catalog_items || [])]
            .sort((a, b) => String(a.path || a.name || "").localeCompare(String(b.path || b.name || ""), "ru"))
            .find((item) => Object.values(mappings[item.id] || {}).some((value) => !!String(value || "").trim()));
          if (mappedItem) {
            setSelectedCategory(mappedItem.id, mappedItem.name || mappedItem.path || mappedItem.id);
            return;
          }
          return;
        }
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

  if (rawTab === "competitors" || rawTab === "competitor" || rawTab === "competitor_links" || rawTab === "discovery") {
    const categoryParam = activeCategoryId ? `?category=${encodeURIComponent(activeCategoryId)}` : "";
    return <Navigate to={`/data-prep/competitors${categoryParam}`} replace />;
  }

  return (
    <div className="page-shell sourcesMappingPage">
      <WorkspaceHeader
        eyebrow="Инфо-модели"
        title="Сопоставления"
        context={selectedCategoryName || undefined}
        subtitle={tabDescription}
        tabs={TAB_ITEMS}
        activeTab={tab}
        onTabChange={(nextTab) => setTab(nextTab as SourcesTab)}
      />

      <WorkspaceTaskQueue
        title="Маршрут сопоставления"
        items={[
          {
            key: "sources",
            label: "Категории и конкурентные карточки",
            description: "Сначала свяжи PIM-ветку с площадками, затем подтверди точные карточки re-store/store77 для SKU.",
            href: activeCategoryId ? sourcesHref("sources", activeCategoryId, productParam) : undefined,
            actionLabel: "Открыть",
            status: tab === "sources" ? "active" : "done",
          },
          {
            key: "params",
            label: "Черновик PIM-параметров",
            description: "Создается из данных площадок, конкурентов и товаров. Одни только площадки не являются финальной моделью.",
            href: activeCategoryId ? sourcesHref("params", activeCategoryId, productParam) : undefined,
            actionLabel: "Черновик",
            status: tab === "params" ? "active" : tab === "values" ? "done" : "todo",
          },
          {
            key: "values",
            label: "Значения для выгрузки",
            description: "Нормализуй написания: 256 ГБ, eSIM, цвета и справочники площадок.",
            href: activeCategoryId ? sourcesHref("values", activeCategoryId, productParam) : undefined,
            actionLabel: "Значения",
            status: tab === "values" ? "active" : "todo",
          },
          {
            key: "export",
            label: "Проверить экспорт",
            description: "Когда категории, поля и значения закрыты, проверь готовность выгрузки.",
            href: activeCategoryId ? exportHref(activeCategoryId, productParam) : undefined,
            actionLabel: "Экспорт",
            status: "todo",
          },
        ]}
      />

      <div className="sourcesMappingContextCard">
        <div>
          <span>Рабочий контекст</span>
          <strong>{selectedCategoryName || "Категория не выбрана"}</strong>
          <p>
            {productParam
              ? `Переход из SKU ${productParam}: правки применяются к категории, а проверку результата лучше запускать по этому SKU.`
              : "Все вкладки ниже работают в одной категории: источники, поля, значения и проверка экспорта."}
          </p>
        </div>
        <div className="sourcesMappingContextActions">
          {productParam ? <a className="btn" href={`/products/${encodeURIComponent(productParam)}`}>Открыть SKU</a> : null}
          <a className="btn" href={exportHref(activeCategoryId, productParam)}>{productParam ? "Экспорт SKU" : "Экспорт категории"}</a>
          <a className="btn primary" href={nextAction.href}>{nextAction.label}</a>
        </div>
      </div>

      <div className="sourcesMappingCanvas">
        {tab === "params" && categoryResolving ? (
          <div className="sourcesMappingCanvasIntro">
            <div className="sourcesMappingCanvasTitle">Подбираем рабочую категорию</div>
            <div className="sourcesMappingCanvasSub">
              Для сопоставления параметров открываем ближайшую дочернюю категорию, где уже есть привязка к каналам.
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
            selectedCategoryId={activeCategoryId}
            onSelectedCategoryChange={(categoryId, categoryName) => {
              setSelectedCategory(categoryId, categoryName);
            }}
          />
        )}

        {tab === "params" && !categoryResolving && (
          <SourcesParamsWorkspaceSection
            selectedCategoryId={activeCategoryId}
            focusParameter={parameterParam}
            onSelectedCategoryChange={(categoryId, categoryName) => {
              setSelectedCategory(categoryId, categoryName);
            }}
          />
        )}

        {tab === "values" && (
          <SourcesValueMappingSection
            selectedCategoryId={activeCategoryId}
            focusParameter={parameterParam}
            onSelectedCategoryChange={(categoryId, categoryName) => {
              setSelectedCategory(categoryId, categoryName);
            }}
          />
        )}
      </div>
    </div>
  );
}
