import { Link, useSearchParams } from "react-router-dom";
import PageHeader from "../../components/ui/PageHeader";
import PageTabs from "../../components/ui/PageTabs";
import CatalogExportFeature from "./CatalogExportFeature";
import CatalogImportFeature from "./CatalogImportFeature";

type ExchangeTab = "import" | "export";

function normalizeTab(value: string | null): ExchangeTab {
  return value === "export" ? "export" : "import";
}

export default function CatalogExchangeFeature() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = normalizeTab(searchParams.get("tab"));

  function setTab(nextTab: ExchangeTab) {
    const next = new URLSearchParams(searchParams);
    next.set("tab", nextTab);
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="cx-exchangePage">
      <PageHeader
        title="Импорт / Экспорт"
        subtitle="Одна рабочая область для загрузки данных в товары и подготовки выгрузки на площадки."
        actions={
          <>
            <Link className="btn" to="/catalog">К каталогу</Link>
            <Link className="btn" to="/products">К товарам</Link>
          </>
        }
      />

      <PageTabs
        className="cx-exchangeTabs"
        activeKey={tab}
        onChange={(key) => setTab(key as ExchangeTab)}
        items={[
          { key: "import", label: "Импорт товаров" },
          { key: "export", label: "Экспорт товаров" },
        ]}
      />

      {tab === "export" ? <CatalogExportFeature embedded /> : <CatalogImportFeature embedded />}
    </div>
  );
}
