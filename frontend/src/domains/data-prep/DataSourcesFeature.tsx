import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useOrgPath } from "../../app/orgRoutes";
import ConnectorsStatusFeature from "../channels/ConnectorsStatusFeature";
import CompetitorSourcesFeature from "./CompetitorSourcesFeature";

type DataSourcesTab = "overview" | "marketplaces" | "stores" | "competitors";

function normalizeTab(value: string | null): DataSourcesTab {
  if (value === "categories") return "marketplaces";
  if (value === "marketplaces" || value === "stores" || value === "competitors") return value;
  return "overview";
}

export default function DataSourcesFeature() {
  const [searchParams, setSearchParams] = useSearchParams();
  const orgPath = useOrgPath();
  const tab = normalizeTab(searchParams.get("tab"));

  useEffect(() => {
    if (searchParams.get("tab") !== "categories") return;
    const next = new URLSearchParams(searchParams);
    next.set("tab", "marketplaces");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  function setTab(nextTab: DataSourcesTab) {
    const next = new URLSearchParams(searchParams);
    next.set("tab", nextTab);
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="dataSourcesPage">
      <header className="dataSourcesCommandHeader">
        <div className="dataSourcesCommandContext">
          <span>Данные / подключения</span>
          <h1>Источники данных</h1>
          <p>Подключайте площадки, магазины и конкурентов. Эти источники питают импорт, сопоставления, насыщение и экспорт.</p>
        </div>
        <div className="dataSourcesCommandControls">
          <nav className="dataSourcesSegmentedTabs" aria-label="Раздел источников данных">
            {[
              { key: "overview", label: "Готовность" },
              { key: "marketplaces", label: "Площадки" },
              { key: "stores", label: "Магазины" },
              { key: "competitors", label: "Конкуренты" },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                className={tab === item.key ? "active" : ""}
                onClick={() => setTab(item.key as DataSourcesTab)}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <Link className="btn" to={orgPath("/sources?tab=sources")}>Сопоставления</Link>
          <Link className="btn" to={orgPath("/catalog")}>Каталог</Link>
        </div>
      </header>

      {tab === "competitors" ? <CompetitorSourcesFeature embedded /> : <ConnectorsStatusFeature embedded view={tab} />}
    </div>
  );
}
