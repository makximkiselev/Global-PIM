import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import SourcesMarketplaceSection from "./SourcesMarketplaceSection";
import CompetitorMapping from "./CompetitorMapping";
import SourcesValueMappingSection from "./SourcesValueMappingSection";
import "../styles/product-groups.css";
import "../styles/competitor-mapping.css";

type SourcesTab = "sources" | "params" | "values";
type ParamsView = "marketplaces" | "competitors";

function normalizeTab(value: string | null): SourcesTab {
  if (value === "params") return "params";
  if (value === "values") return "values";
  return "sources";
}

function normalizeParamsView(value: string | null): ParamsView {
  if (value === "competitors") return "competitors";
  return "marketplaces";
}

export default function SourcesMapping() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTabState] = useState<SourcesTab>(normalizeTab(searchParams.get("tab")));
  const [selectedCategoryId, setSelectedCategoryId] = useState(searchParams.get("category") || "");
  const [selectedCategoryName, setSelectedCategoryName] = useState("");
  const [paramsView, setParamsViewState] = useState<ParamsView>(normalizeParamsView(searchParams.get("params_view")));

  useEffect(() => {
    const nextTab = normalizeTab(searchParams.get("tab"));
    setTabState((prev) => (prev === nextTab ? prev : nextTab));
    setSelectedCategoryId(searchParams.get("category") || "");
    setParamsViewState((prev) => {
      const nextView = normalizeParamsView(searchParams.get("params_view"));
      return prev === nextView ? prev : nextView;
    });
  }, [searchParams]);

  function setTab(nextTab: SourcesTab) {
    setTabState(nextTab);
    const next = new URLSearchParams(searchParams);
    next.set("tab", nextTab);
    setSearchParams(next, { replace: true });
  }

  function setSelectedCategory(nextCategoryId: string, nextCategoryName: string) {
    setSelectedCategoryId(nextCategoryId);
    setSelectedCategoryName(nextCategoryName);
    const next = new URLSearchParams(searchParams);
    if (nextCategoryId) next.set("category", nextCategoryId);
    else next.delete("category");
    setSearchParams(next, { replace: true });
  }

  function setParamsView(nextView: ParamsView) {
    setParamsViewState(nextView);
    const next = new URLSearchParams(searchParams);
    next.set("params_view", nextView);
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="dashboard-page page-shell sm-pageRoot" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="page-header sm-pageHeader">
        <div className="page-header-main">
          <div className="page-title">Маппинг источников</div>
          <div className="page-subtitle">Единый блок сопоставления категорий и параметров по маркетплейсам и конкурентам.</div>
        </div>
        <div className="page-header-actions">
          <Link className="btn" to="/">← На главную</Link>
        </div>
      </div>
      <div className="page-tabs sm-pageTabs">
        <button className={`page-tab ${tab === "sources" ? "active" : ""}`} onClick={() => setTab("sources")}>
          Категории и источники
        </button>
        <button className={`page-tab ${tab === "params" ? "active" : ""}`} onClick={() => setTab("params")}>
          Сопоставление параметров
        </button>
        <button className={`page-tab ${tab === "values" ? "active" : ""}`} onClick={() => setTab("values")}>
          Сопоставление значений
        </button>
      </div>

      <div className="card sm-shell">
        <div className="sm-shellHead">
          <div>
            <div className="sm-shellTitle">
              {tab === "sources"
                ? "Категории и источники"
                : tab === "params"
                  ? "Сопоставление параметров"
                  : "Сопоставление значений"}
            </div>
            <div className="sm-shellSub">
              {tab === "sources"
                ? "Единое дерево категорий для привязок маркетплейсов и ссылок конкурентов."
                : tab === "params"
                  ? "Одна выбранная категория, один мастер-шаблон и сразу два слоя маппинга: маркетплейсы и конкуренты."
                  : "Отдельный workflow для словарей значений: выбираешь категорию, поле и дружишь значения площадок с нашими каноническими значениями."}
            </div>
          </div>
        </div>

      {tab === "sources" && (
        <SourcesMarketplaceSection
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
              <CompetitorMapping embedded view="links" categoryId={categoryId} categoryName={categoryName} />
            </div>
          )}
        />
      )}

      {tab === "params" && (
        <div className="sm-stack">
          <div className="sm-section sm-sectionBordered">
            <div className="sm-sectionHead">
              <div>
                <div className="sm-sectionTitle">Сопоставление параметров</div>
                <div className="sm-sectionSub">Одна выбранная категория, один мастер-шаблон и сразу два слоя маппинга: маркетплейсы и конкуренты.</div>
              </div>
            </div>
            <SourcesMarketplaceSection
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
              featureView={paramsView}
              onFeatureViewChange={setParamsView}
              renderFeatureDetailExtra={(categoryId, categoryName) => (
                <div className="sm-section sm-sectionBordered">
                  <div className="sm-sectionHead">
                    <div>
                      <div className="sm-sectionTitle">Параметры конкурентов</div>
                      <div className="sm-sectionSub">Сопоставление полей конкурентов с тем же шаблоном выбранной категории.</div>
                    </div>
                  </div>
                  <CompetitorMapping embedded view="mapping" categoryId={categoryId} categoryName={categoryName} />
                </div>
              )}
            />
          </div>
        </div>
      )}

      {tab === "values" && (
        <div className="sm-stack">
          <div className="sm-section sm-sectionBordered">
            <div className="sm-sectionHead">
              <div>
                <div className="sm-sectionTitle">Сопоставление значений</div>
                <div className="sm-sectionSub">Отдельный пул для value-mapping. Здесь больше нет сопоставления параметров, только словари значений и соответствия площадок.</div>
              </div>
            </div>
            <SourcesValueMappingSection
              selectedCategoryId={selectedCategoryId}
              onSelectedCategoryChange={(categoryId, categoryName) => {
                setSelectedCategory(categoryId, categoryName);
              }}
            />
          </div>
        </div>
      )}
      </div>
    </div>
  );
}
