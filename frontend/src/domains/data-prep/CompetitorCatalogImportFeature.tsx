import { FormEvent, useEffect, useMemo, useState } from "react";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import PageHeader from "../../components/ui/PageHeader";
import TextInput from "../../components/ui/TextInput";
import MetricGrid from "../../components/data/MetricGrid";
import { api } from "../../lib/api";
import "../../styles/competitor-catalog-import.css";

type ImportRun = {
  id: string;
  name: string;
  start_url: string;
  host: string;
  status: string;
  created_at: string;
  updated_at: string;
  pages_scanned: number;
  products_found: number;
  errors: string[];
  product_ids: string[];
  limits: { max_pages: number; max_products: number };
};

type ImportedProduct = {
  id: string;
  url: string;
  title: string;
  description: string;
  brand: string;
  sku: string;
  price: string;
  currency: string;
  images: string[];
  specs: Record<string, string>;
  spec_count: number;
  confidence: number;
  updated_at: string;
};

type RunsResponse = {
  runs: ImportRun[];
  total_products: number;
  updated_at: string | null;
};

type RunResponse = {
  run: ImportRun;
  products: ImportedProduct[];
};

function parseApiError(error: unknown) {
  const raw = error instanceof Error ? error.message : String(error || "");
  if (raw.includes("ROBOTS_DISALLOW_ALL")) return "Сайт запретил обход в robots.txt.";
  if (raw.includes("BAD_START_URL")) return "Проверь ссылку: нужен полный URL сайта или раздела.";
  if (raw.includes("STORE_LOCKED")) return "Предыдущий запуск еще сохраняется. Повтори через несколько секунд.";
  return raw || "Не удалось запустить импорт.";
}

function runStatusLabel(status: string) {
  if (status === "completed") return "Готово";
  if (status === "running") return "Идет импорт";
  if (status === "failed") return "Ошибка";
  return status || "Черновик";
}

function ProductInspector({ product }: { product: ImportedProduct | null }) {
  if (!product) {
    return (
      <aside className="cciInspector">
        <div className="cciInspectorEmpty">Выберите карточку в таблице, чтобы проверить медиа, цену и характеристики.</div>
      </aside>
    );
  }

  const specs = Object.entries(product.specs || {}).slice(0, 16);

  return (
    <aside className="cciInspector">
      <div className="cciInspectorHead">
        <div>
          <div className="cciEyebrow">Карточка конкурента</div>
          <h2>{product.title}</h2>
        </div>
        <Badge tone={product.confidence >= 70 ? "active" : "pending"}>{product.confidence}%</Badge>
      </div>

      {product.images?.[0] ? <img className="cciPreview" src={product.images[0]} alt="" loading="lazy" /> : null}

      <div className="cciInspectorFacts">
        <div>
          <span>Бренд</span>
          <strong>{product.brand || "не найден"}</strong>
        </div>
        <div>
          <span>Цена</span>
          <strong>{product.price ? `${product.price} ${product.currency || ""}`.trim() : "не найдена"}</strong>
        </div>
        <div>
          <span>Медиа</span>
          <strong>{product.images?.length || 0}</strong>
        </div>
        <div>
          <span>Параметры</span>
          <strong>{product.spec_count || 0}</strong>
        </div>
      </div>

      <a className="cciExternalLink" href={product.url} target="_blank" rel="noreferrer">
        Открыть исходную карточку
      </a>

      <div className="cciSpecs">
        <div className="cciSectionTitle">Найденные характеристики</div>
        {specs.length ? (
          specs.map(([key, value]) => (
            <div key={key} className="cciSpecRow">
              <span>{key}</span>
              <strong>{value}</strong>
            </div>
          ))
        ) : (
          <div className="cciMuted">Характеристики не найдены.</div>
        )}
      </div>
    </aside>
  );
}

export default function CompetitorCatalogImportFeature() {
  const [runs, setRuns] = useState<ImportRun[]>([]);
  const [totalProducts, setTotalProducts] = useState(0);
  const [products, setProducts] = useState<ImportedProduct[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [name, setName] = useState("");
  const [startUrl, setStartUrl] = useState("");
  const [maxPages, setMaxPages] = useState(35);
  const [maxProducts, setMaxProducts] = useState(60);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const selectedProduct = products.find((product) => product.id === selectedId) || products[0] || null;
  const lastRun = runs[0] || null;

  const metrics = useMemo(
    () => [
      { label: "Найдено карточек", value: lastRun?.products_found || 0, meta: lastRun?.host || "последний прогон" },
      { label: "Просканировано страниц", value: lastRun?.pages_scanned || 0, meta: lastRun ? `лимит ${lastRun.limits?.max_pages || "-"}` : "ограниченный обход" },
      { label: "Всего во внешнем каталоге", value: totalProducts, meta: "по текущей организации" },
      { label: "Ошибки обхода", value: lastRun?.errors?.length || 0, meta: "часть страниц могла не открыться" },
    ],
    [lastRun, totalProducts],
  );

  async function loadRuns() {
    const data = await api<RunsResponse>("/competitor-catalog/runs");
    setRuns(data.runs || []);
    setTotalProducts(data.total_products || 0);
    if (data.runs?.[0]) {
      const detail = await api<RunResponse>(`/competitor-catalog/runs/${data.runs[0].id}`);
      setProducts(detail.products || []);
      setSelectedId(detail.products?.[0]?.id || "");
    }
  }

  useEffect(() => {
    setLoading(true);
    setError("");
    loadRuns()
      .catch((err) => setError(parseApiError(err)))
      .finally(() => setLoading(false));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setRunning(true);
    setError("");
    try {
      const data = await api<RunResponse>("/competitor-catalog/runs", {
        method: "POST",
        body: JSON.stringify({ name, start_url: startUrl, max_pages: maxPages, max_products: maxProducts }),
      });
      setProducts(data.products || []);
      setSelectedId(data.products?.[0]?.id || "");
      await loadRuns();
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="page-shell cciPage">
      <PageHeader
        title="Импорт каталога конкурента"
        subtitle="Сканирование сайта конкурента в отдельный внешний каталог. Найденные карточки не попадают в PIM, пока их не сопоставят с нашими SKU."
        actions={<Badge tone="pending">MVP crawler</Badge>}
      />

      <MetricGrid items={metrics} className="cciMetrics" />

      <section className="cciLayout">
        <main className="cciMain">
          <form className="cciRunPanel" onSubmit={submit}>
            <div>
              <div className="cciEyebrow">Новый прогон</div>
              <h2>Укажи сайт или раздел конкурента</h2>
              <p>Система попробует sitemap, затем ссылки внутри этого домена. Обход ограничен страницами и товарами.</p>
            </div>
            <div className="cciFormGrid">
              <label>
                <span>Название источника</span>
                <TextInput value={name} onChange={(event) => setName(event.target.value)} placeholder="re-store, store77, локальный конкурент" />
              </label>
              <label className="cciWideField">
                <span>Ссылка</span>
                <TextInput value={startUrl} onChange={(event) => setStartUrl(event.target.value)} placeholder="https://example.ru/catalog/smartphones" required />
              </label>
              <label>
                <span>Лимит страниц</span>
                <TextInput type="number" value={maxPages} min={1} max={80} onChange={(event) => setMaxPages(Number(event.target.value) || 1)} />
              </label>
              <label>
                <span>Лимит товаров</span>
                <TextInput type="number" value={maxProducts} min={1} max={120} onChange={(event) => setMaxProducts(Number(event.target.value) || 1)} />
              </label>
            </div>
            <div className="cciRunActions">
              <Button variant="primary" type="submit" disabled={running || !startUrl.trim()}>
                {running ? "Сканирую..." : "Запустить импорт"}
              </Button>
              {lastRun ? <span>Последний прогон: {runStatusLabel(lastRun.status)} · {lastRun.host}</span> : null}
            </div>
            {error ? <div className="cciError">{error}</div> : null}
          </form>

          <section className="cciTablePanel">
            <div className="cciPanelHead">
              <div>
                <div className="cciEyebrow">Внешний каталог</div>
                <h2>Найденные карточки</h2>
              </div>
              {loading ? <Badge tone="provisioning">Загрузка</Badge> : <Badge tone="neutral">{products.length} товаров</Badge>}
            </div>

            {products.length ? (
              <div className="cciTable">
                <div className="cciTableHead">
                  <span>Товар</span>
                  <span>Цена</span>
                  <span>Медиа</span>
                  <span>Параметры</span>
                  <span>Уверенность</span>
                </div>
                {products.map((product) => (
                  <button
                    key={product.id}
                    type="button"
                    className={`cciTableRow${selectedProduct?.id === product.id ? " isActive" : ""}`}
                    onClick={() => setSelectedId(product.id)}
                  >
                    <span>
                      <strong>{product.title}</strong>
                      <small>{product.url}</small>
                    </span>
                    <span>{product.price ? `${product.price} ${product.currency || ""}`.trim() : "-"}</span>
                    <span>{product.images?.length || 0}</span>
                    <span>{product.spec_count || 0}</span>
                    <span>{product.confidence}%</span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="cciEmpty">
                {loading ? "Загружаю последние результаты..." : "Пока нет импортированных карточек. Запусти первый обход сайта конкурента."}
              </div>
            )}
          </section>
        </main>

        <ProductInspector product={selectedProduct} />
      </section>
    </div>
  );
}
