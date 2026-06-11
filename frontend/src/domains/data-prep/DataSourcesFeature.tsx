import { Link, useSearchParams } from "react-router-dom";
import { useOrgPath } from "../../app/orgRoutes";
import ConnectorsStatusFeature from "../channels/ConnectorsStatusFeature";
import PageHeader from "../../components/ui/PageHeader";
import PageTabs from "../../components/ui/PageTabs";
import CompetitorSourcesFeature from "./CompetitorSourcesFeature";

type DataSourcesTab = "overview" | "marketplaces" | "stores" | "competitors";

function normalizeTab(value: string | null): DataSourcesTab {
  if (value === "marketplaces" || value === "stores" || value === "competitors") return value;
  return "overview";
}

export default function DataSourcesFeature() {
  const [searchParams, setSearchParams] = useSearchParams();
  const orgPath = useOrgPath();
  const tab = normalizeTab(searchParams.get("tab"));

  function setTab(nextTab: DataSourcesTab) {
    const next = new URLSearchParams(searchParams);
    next.set("tab", nextTab);
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="dataSourcesPage">
      <PageHeader
        title="Источники данных"
        subtitle="Сначала подключаем магазины, площадки и конкурентов. Затем эти источники питают импорт, инфо-модели, насыщение и экспорт."
        actions={
          <>
            <Link className="btn" to={orgPath("/sources?tab=sources")}>К сопоставлениям</Link>
            <Link className="btn" to={orgPath("/templates")}>К инфо-моделям</Link>
          </>
        }
      />

      <PageTabs
        activeKey={tab}
        onChange={(key) => setTab(key as DataSourcesTab)}
        items={[
          { key: "overview", label: "Готовность" },
          { key: "marketplaces", label: "Площадки" },
          { key: "stores", label: "Магазины" },
          { key: "competitors", label: "Конкуренты" },
        ]}
      />

      {tab === "competitors" ? <CompetitorSourcesFeature embedded /> : <ConnectorsStatusFeature embedded view={tab} />}
    </div>
  );
}
