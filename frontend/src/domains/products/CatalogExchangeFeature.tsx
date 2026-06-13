import { Link, useSearchParams } from "react-router-dom";
import { useOrgPath } from "../../app/orgRoutes";
import CatalogExportFeature from "./CatalogExportFeature";
import CatalogImportFeature from "./CatalogImportFeature";

type ExchangeTab = "import" | "export";

function normalizeTab(value: string | null): ExchangeTab {
  return value === "export" ? "export" : "import";
}

export default function CatalogExchangeFeature() {
  const [searchParams, setSearchParams] = useSearchParams();
  const orgPath = useOrgPath();
  const tab = normalizeTab(searchParams.get("tab"));

  function setTab(nextTab: ExchangeTab) {
    const next = new URLSearchParams(searchParams);
    next.set("tab", nextTab);
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="cx-exchangePage">
      <header className="cxExchangeCommandHeader">
        <div className="cxExchangeCommandContext">
          <span>Каталог / обмен</span>
          <h1>Импорт и экспорт</h1>
          <p>Одна рабочая область для загрузки данных в товары и подготовки выгрузки на площадки.</p>
        </div>
        <div className="cxExchangeCommandControls">
          <nav className="cxExchangeSegmentedTabs" aria-label="Режим обмена">
            {[
              { key: "import", label: "Импорт" },
              { key: "export", label: "Экспорт" },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                className={tab === item.key ? "active" : ""}
                onClick={() => setTab(item.key as ExchangeTab)}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <Link className="btn" to={orgPath("/catalog")}>Каталог</Link>
          <Link className="btn" to={orgPath("/products")}>Товары</Link>
        </div>
      </header>

      {tab === "export" ? <CatalogExportFeature embedded /> : <CatalogImportFeature embedded />}
    </div>
  );
}
