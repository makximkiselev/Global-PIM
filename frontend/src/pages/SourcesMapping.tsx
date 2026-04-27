import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import SourcesMarketplaceSection from "./SourcesMarketplaceSection";
import CompetitorMapping from "./CompetitorMapping";
import PageHeader from "../components/ui/PageHeader";
import PageTabs from "../components/ui/PageTabs";
import "../styles/product-groups.css";
import "../styles/competitor-mapping.css";

type SourcesTab = "sources" | "params";

function normalizeTab(value: string | null): SourcesTab {
  if (value === "params") return "params";
  return "sources";
}

export default function SourcesMapping() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTabState] = useState<SourcesTab>(normalizeTab(searchParams.get("tab")));
  const [selectedCategoryId, setSelectedCategoryId] = useState(searchParams.get("category") || "");
  const [selectedCategoryName, setSelectedCategoryName] = useState("");

  useEffect(() => {
    const nextTab = normalizeTab(searchParams.get("tab"));
    setTabState((prev) => (prev === nextTab ? prev : nextTab));
    setSelectedCategoryId(searchParams.get("category") || "");
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

  return (
    <div className="dashboard-page page-shell sm-pageRoot" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <PageHeader
        title="Маппинг источников"
        subtitle="Единый блок сопоставления категорий и параметров по маркетплейсам и конкурентам."
        actions={<Link className="btn" to="/">На главную</Link>}
      />
      <PageTabs
        activeKey={tab}
        onChange={(key) => setTab(key as SourcesTab)}
        items={[
          { key: "sources", label: "Категории и источники" },
          { key: "params", label: "Сопоставление параметров" },
        ]}
      />

      <div className="card sm-shell">
        {tab === "sources" ? (
          <div className="sm-shellHead">
            <div>
              <div className="sm-shellTitle">Категории и источники</div>
              <div className="sm-shellSub">Единое дерево категорий для привязок маркетплейсов и ссылок конкурентов.</div>
            </div>
          </div>
        ) : null}

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
        />
      )}
      </div>
    </div>
  );
}
