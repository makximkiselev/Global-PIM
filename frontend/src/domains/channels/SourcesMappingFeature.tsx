import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useOrgPath } from "../../app/orgRoutes";
import SourcesMarketplaceSection from "./SourcesMarketplaceSection";
import SourcesParamsWorkspaceSection from "./SourcesParamsWorkspaceSection";
import SourcesValueMappingSection from "./SourcesValueMappingSection";
import { api } from "../../lib/api";
import "../../styles/product-groups.css";
import "../../styles/competitor-mapping.css";
import "../../styles/sources-mapping-modern.css";

type SourcesTab = "sources" | "competitors" | "params" | "values";

type MappingBootstrapResp = {
  catalog_nodes?: Array<{ id: string; parent_id: string | null; name: string }>;
  catalog_items?: Array<{ id: string; name: string; path?: string }>;
  mappings?: Record<string, Record<string, string>>;
};
const MAPPING_BOOTSTRAP_CACHE_KEY = "sources_mapping_feature_bootstrap_v2";
const PRODUCT_CONTEXT_CACHE_KEY = "smartpim_last_product_context_v1";
let mappingBootstrapCache: MappingBootstrapResp | null = null;

const STEP_ITEMS: Array<{ key: SourcesTab | "export"; label: string; hint: string }> = [
  { key: "sources", label: "Площадки", hint: "Категории Я.Маркет и Ozon" },
  { key: "competitors", label: "Конкуренты", hint: "Точные карточки товаров" },
  { key: "params", label: "Параметры", hint: "Поля категории и источников" },
  { key: "values", label: "Значения", hint: "Справочники и написания" },
  { key: "export", label: "Экспорт", hint: "Проверка готовности" },
];

function stepIndex(key: SourcesTab | "export") {
  return STEP_ITEMS.findIndex((item) => item.key === key);
}

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
      title: "Подобрать конкурентов",
      detail: "После привязки категорий площадок выберите точные карточки конкурентов для насыщения товаров.",
      label: "К конкурентам",
      href: sourcesHref("competitors", categoryId, productId),
      tone: "pending",
    };
  }
  if (tab === "competitors") {
    return {
      title: "Собрать параметры",
      detail: "Когда категории площадок и конкурентные карточки выбраны, переходите к предложениям параметров категории.",
      label: "К параметрам",
      href: sourcesHref("params", categoryId, productId),
      tone: "pending",
    };
  }
  if (tab === "params") {
    return {
      title: "Нормализовать значения",
      detail: "После связки полей проверьте справочники, значения да/нет, списки и написания для каждой площадки.",
      label: "К значениям",
      href: sourcesHref("values", categoryId, productId),
      tone: "pending",
    };
  }
  return {
    title: productId ? "Проверить экспорт SKU" : "Проверить экспорт категории",
    detail: productId
      ? "После значений запустите проверку выгрузки по исходному SKU."
      : "После значений запустите проверку выгрузки. Для финальной проверки лучше выбрать отдельный SKU.",
    label: productId ? "Экспорт SKU" : "Проверить экспорт",
    href: exportHref(categoryId, productId),
    tone: "active",
  };
}

function normalizeTab(value: string | null): SourcesTab {
  if (value === "mp_categories" || value === "marketplace_categories") return "sources";
  if (value === "competitors" || value === "competitor" || value === "competitor_links" || value === "discovery") return "competitors";
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
  const orgPath = useOrgPath();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = normalizeTab(searchParams.get("tab"));
  const storedContext = useMemo(() => readStoredProductContext(), []);
  const categoryParam = String(searchParams.get("category") || "").trim();
  const explicitProductParam = String(searchParams.get("product") || "").trim();
  const storedMatchesExplicitProduct = !!explicitProductParam && storedContext.productId === explicitProductParam;
  const initialCategoryId = categoryParam || (!explicitProductParam || storedMatchesExplicitProduct ? storedContext.categoryId : "") || "";
  const providerParam = String(searchParams.get("provider") || "").trim();
  const providerCategoryParam = String(searchParams.get("provider_category") || "").trim();
  const productParam = explicitProductParam || (!categoryParam ? storedContext.productId : "");
  const [tab, setTabState] = useState<SourcesTab>(initialTab);
  const [selectedCategoryId, setSelectedCategoryId] = useState(initialCategoryId);
  const [selectedCategoryName, setSelectedCategoryName] = useState(storedContext.categoryName);
  const [marketplaceReady, setMarketplaceReady] = useState(false);
  const [categoryResolving, setCategoryResolving] = useState(
    (initialTab === "params" && !initialCategoryId) || !!providerCategoryParam,
  );
  const tabDescription = useMemo(
    () =>
      tab === "sources"
        ? "Сопоставьте категорию каталога с категориями Я.Маркета и Ozon. Конкуренты вынесены в следующий шаг."
        : tab === "competitors"
          ? "Выберите точные карточки конкурентов для SKU: из них система заберет параметры, описание и медиа."
        : tab === "params"
          ? "Соберите предложения параметров категории из площадок, конкурентов и товарных данных, затем утверждайте модель."
          : "Контроль значений, справочников площадок и написаний для выгрузки по каждому параметру.",
    [tab],
  );
  const nextAction = useMemo(() => {
    if (tab === "sources" && selectedCategoryId && !marketplaceReady) {
      return {
        title: "Сопоставьте площадки",
        detail: "Выберите категории Я.Маркета и Ozon для текущей ветки. После этого откроются конкуренты, параметры и значения.",
        label: "Сопоставить площадки",
        href: sourcesHref("sources", selectedCategoryId, productParam),
        tone: "pending",
      };
    }
    if ((tab === "params" || tab === "values") && selectedCategoryId && !marketplaceReady) {
      return {
        title: "Сначала сопоставьте площадки",
        detail: "Без связки с категориями маркетплейсов нельзя собрать обязательные поля, значения и готовую выгрузку.",
        label: "Открыть площадки",
        href: sourcesHref("sources", selectedCategoryId, productParam),
        tone: "pending",
      };
    }
    return sourcesNextAction(tab, selectedCategoryId, productParam);
  }, [marketplaceReady, productParam, selectedCategoryId, tab]);
  const activeStepIndex = stepIndex(tab);
  const categoryLabel = selectedCategoryName || (selectedCategoryId ? `ID ${selectedCategoryId}` : "Категория не выбрана");
  const workModeLabel = productParam ? "SKU" : "Категория";
  const workModeDetail = productParam
    ? `Контроль по ${productParam}, модель и значения применяются к категории.`
    : selectedCategoryId
      ? "Работа идет по выбранной ветке каталога."
      : "Выберите ветку каталога, чтобы открыть источники.";
  const currentStepLabel = STEP_ITEMS[activeStepIndex]?.label || "Источники";

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
    if (!productParam && !selectedCategoryId) return;
    try {
      window.localStorage.setItem(PRODUCT_CONTEXT_CACHE_KEY, JSON.stringify({
        productId: productParam,
        categoryId: selectedCategoryId,
        categoryName: selectedCategoryName,
        updatedAt: new Date().toISOString(),
      }));
    } catch {
      // Context persistence is optional; explicit URL params remain authoritative.
    }
  }, [productParam, selectedCategoryId, selectedCategoryName]);

  useEffect(() => {
    if (!selectedCategoryId || selectedCategoryName) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await loadMappingBootstrap();
        if (cancelled) return;
        const currentItem = (data.catalog_items || []).find((item) => item.id === selectedCategoryId);
        const currentNode = (data.catalog_nodes || []).find((item) => item.id === selectedCategoryId);
        const nextName = currentItem?.name || currentItem?.path || currentNode?.name || "";
        if (nextName) setSelectedCategoryName((prev) => (prev === nextName ? prev : nextName));
      } catch {
        // The id is still enough to keep links/actions correct; the name can resolve on the next successful bootstrap.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedCategoryId, selectedCategoryName]);

  useEffect(() => {
    if (!selectedCategoryId) {
      setMarketplaceReady(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await loadMappingBootstrap();
        if (cancelled) return;
        const mappings = data.mappings || {};
        const hasMapping = Object.values(mappings[selectedCategoryId] || {}).some((value) => !!String(value || "").trim());
        setMarketplaceReady(hasMapping);
      } catch {
        if (!cancelled) setMarketplaceReady(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedCategoryId]);

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

  return (
    <div className="page-shell sourcesMappingPage sourcesCommandPage">
      <section className="sourcesCommandHeader" aria-labelledby="sources-mapping-title">
        <div className="sourcesCommandTitleBlock">
          <div className="sourcesCommandBreadcrumb">Каталог / Подготовка данных</div>
          <div className="sourcesCommandTitleRow">
            <h1 id="sources-mapping-title">Сопоставления</h1>
            <span className="sourcesCommandContext">{categoryLabel}</span>
          </div>
          <p>{tabDescription}</p>
        </div>
        <div className="sourcesCommandActions">
          <div className="sourcesCommandStatus" title={tabDescription}>
            <span>Этап</span>
            <strong>{currentStepLabel}</strong>
          </div>
          {productParam ? <Link className="btn" to={orgPath(`/products/${encodeURIComponent(productParam)}`)}>Открыть SKU</Link> : null}
          <Link className="btn primary" to={orgPath(nextAction.href)}>{nextAction.label}</Link>
        </div>
      </section>

      <nav className="sourcesCommandStepper" aria-label="Маршрут сопоставления">
        {STEP_ITEMS.map((step, index) => {
          const isActive = step.key === tab;
          const isDone = index < activeStepIndex;
          const isDisabled = step.key !== "sources" && !selectedCategoryId;
          const href = step.key === "export"
            ? exportHref(selectedCategoryId, productParam)
            : sourcesHref(step.key, selectedCategoryId, productParam);
          const className = [
            "sourcesCommandStep",
            isActive ? "isActive" : "",
            isDone ? "isDone" : "",
            isDisabled ? "isDisabled" : "",
          ].filter(Boolean).join(" ");
          const content = (
            <>
              <span className="sourcesCommandStepIndex">{String(index + 1).padStart(2, "0")}</span>
              <span className="sourcesCommandStepMain">
                <strong>{step.label}</strong>
                <span>{step.hint}</span>
              </span>
            </>
          );
          if (isDisabled) {
            return (
              <button className={className} disabled key={step.key} type="button">
                {content}
              </button>
            );
          }
          if (step.key === "export") {
            return <Link className={className} key={step.key} to={orgPath(href)}>{content}</Link>;
          }
          return (
            <button className={className} key={step.key} type="button" onClick={() => setTab(step.key)}>
              {content}
            </button>
          );
        })}
      </nav>

      <section className="sourcesCommandContextBar" aria-label="Контекст сопоставления">
        <div className="sourcesCommandContextItem">
          <span>Контекст</span>
          <strong>{workModeLabel}</strong>
          <p>{workModeDetail}</p>
        </div>
        <div className="sourcesCommandContextItem isWide">
          <span>Категория</span>
          <strong>{categoryLabel}</strong>
          <p>{selectedCategoryId ? `ID ${selectedCategoryId}` : "Выберите ветку каталога слева"}</p>
        </div>
        <div className="sourcesCommandContextItem">
          <span>Дальше</span>
          <strong>{nextAction.label}</strong>
          <p>{nextAction.detail}</p>
        </div>
      </section>

      <section className="sourcesCommandWorkbench">
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
            hideCompetitors
            selectedCategoryId={selectedCategoryId}
            onSelectedCategoryChange={(categoryId, categoryName) => {
              setSelectedCategory(categoryId, categoryName);
            }}
          />
        )}

        {tab === "competitors" && (
          <SourcesMarketplaceSection
            key="competitors-workspace"
            embedded
            forcedMainTab="import"
            forcedImportTab="categories"
            hideMainTabs
            hideImportTabs
            showOnlyCompetitors
            focusedProductId={productParam}
            selectedCategoryId={selectedCategoryId}
            onSelectedCategoryChange={(categoryId, categoryName) => {
              setSelectedCategory(categoryId, categoryName);
            }}
          />
        )}

        {tab === "params" && !categoryResolving && (
          <SourcesParamsWorkspaceSection
            selectedCategoryId={selectedCategoryId}
            onSelectedCategoryChange={(categoryId, categoryName) => {
              setSelectedCategory(categoryId, categoryName);
            }}
          />
        )}

        {tab === "values" && selectedCategoryId && !marketplaceReady ? (
          <div className="paramsInfoModelSetup sourcesStepBlocked">
            <div>
              <span>Нужен предыдущий шаг</span>
              <h3>Сначала сопоставьте площадки</h3>
              <p>
                Значения можно нормализовать только после того, как категория связана с Я.Маркетом и Ozon.
                Откройте шаг «Площадки», выберите категории площадок, затем вернитесь к значениям.
              </p>
            </div>
            <div className="paramsInfoModelSetupActions">
              <Link className="btn btn-primary" to={orgPath(sourcesHref("sources", selectedCategoryId, productParam))}>Открыть площадки</Link>
              <Link className="btn" to={orgPath(sourcesHref("params", selectedCategoryId, productParam))}>К параметрам</Link>
            </div>
          </div>
        ) : tab === "values" && (
          <SourcesValueMappingSection
            selectedCategoryId={selectedCategoryId}
            onSelectedCategoryChange={(categoryId, categoryName) => {
              setSelectedCategory(categoryId, categoryName);
            }}
          />
        )}
      </section>
    </div>
  );
}
