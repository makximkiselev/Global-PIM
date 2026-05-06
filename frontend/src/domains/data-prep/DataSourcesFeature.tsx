import { Link, useSearchParams } from "react-router-dom";
import ConnectorsStatusFeature from "../channels/ConnectorsStatusFeature";
import PageHeader from "../../components/ui/PageHeader";
import PageTabs from "../../components/ui/PageTabs";
import CompetitorSourcesFeature from "./CompetitorSourcesFeature";

type DataSourcesTab = "marketplaces" | "competitors";

function normalizeTab(value: string | null): DataSourcesTab {
  return value === "competitors" ? "competitors" : "marketplaces";
}

export default function DataSourcesFeature() {
  const [searchParams, setSearchParams] = useSearchParams();
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
        subtitle="Подключения площадок, магазины, конкуренты и проверки источников в одном рабочем месте."
        actions={
          <>
            <Link className="btn" to="/sources?tab=sources">К сопоставлениям</Link>
            <Link className="btn" to="/templates">К инфо-моделям</Link>
          </>
        }
      />

      <PageTabs
        activeKey={tab}
        onChange={(key) => setTab(key as DataSourcesTab)}
        items={[
          { key: "marketplaces", label: "Площадки и магазины" },
          { key: "competitors", label: "Конкуренты" },
        ]}
      />

      {tab === "competitors" ? <CompetitorSourcesFeature embedded /> : <ConnectorsStatusFeature embedded />}
    </div>
  );
}
