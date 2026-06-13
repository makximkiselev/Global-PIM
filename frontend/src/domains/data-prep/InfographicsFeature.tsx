import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useOrgPath } from "../../app/orgRoutes";
import { api } from "../../lib/api";
import Alert from "../../components/ui/Alert";
import MetricGrid from "../../components/data/MetricGrid";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";

type MediaItem = { url?: string; selected?: boolean };
type ProductRow = {
  id: string;
  title?: string;
  name?: string;
  sku?: string;
  sku_gt?: string;
  category_path?: string;
  category_name?: string;
  content?: {
    media?: MediaItem[];
    media_images?: MediaItem[];
    documents?: MediaItem[];
  };
};
type ProductsPageDataResp = {
  products?: ProductRow[];
  total?: number;
};

type MediaFilter = "all" | "missing" | "review" | "ready";

const MEDIA_WORKFLOW = [
  {
    key: "select",
    title: "Проверить состав",
    text: "Откройте SKU и убедитесь, что в карточке есть импортированные изображения, документы и PDF из площадок или конкурентов.",
    status: "В карточке SKU",
  },
  {
    key: "order",
    title: "Выбрать для экспорта",
    text: "Контент-менеджер задает главное фото, порядок галереи и исключает файлы, которые не должны возвращаться автоматически.",
    status: "Требует выбора",
  },
  {
    key: "export",
    title: "Проверить выгрузку",
    text: "Экспорт должен брать только утвержденный набор медиа, без повторного насыщения удаленных пользователем файлов.",
    status: "Перед отправкой",
  },
];

const MEDIA_QUEUE = [
  {
    key: "missing",
    label: "Без медиа",
    value: "открыть SKU",
    detail: "если карточка пустая, сначала проверьте импорт площадок и карточки конкурентов",
  },
  {
    key: "order",
    label: "Без порядка",
    value: "задать вручную",
    detail: "главное фото и последовательность галереи не должны угадываться при экспорте",
  },
  {
    key: "docs",
    label: "Документы",
    value: "PDF отдельно",
    detail: "инструкции и сертификаты живут в документах товара, не в параметрах",
  },
];

export default function Infographics() {
  const orgPath = useOrgPath();
  const [products, setProducts] = useState<ProductRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<MediaFilter>("all");

  async function loadProducts() {
    setLoading(true);
    setError("");
    try {
      const page = await api<ProductsPageDataResp>("/catalog/products-page-data?page=1&page_size=40");
      const pageProducts = Array.isArray(page.products) ? page.products : [];
      const ids = pageProducts.map((product) => String(product.id || "").trim()).filter(Boolean);
      if (!ids.length) {
        setProducts([]);
        return;
      }
      const full = await api<{ items?: ProductRow[] }>(`/products/bulk?ids=${encodeURIComponent(ids.join(","))}`);
      const fullById = new Map((full.items || []).map((product) => [String(product.id || "").trim(), product]));
      setProducts(pageProducts.map((product) => ({ ...product, ...(fullById.get(String(product.id || "").trim()) || {}) })));
    } catch (e) {
      setError((e as Error).message || "Не удалось загрузить очередь медиа");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadProducts();
  }, []);

  const queue = useMemo(() => {
    return products.map((product) => {
      const content = product.content || {};
      const media = Array.isArray(content.media_images) && content.media_images.length
        ? content.media_images
        : Array.isArray(content.media) ? content.media : [];
      const docs = Array.isArray(content.documents) ? content.documents : [];
      const selectedCount = media.filter((item) => item.selected !== false).length;
      const status: MediaFilter = media.length === 0 ? "missing" : selectedCount !== media.length ? "review" : "ready";
      return {
        product,
        mediaCount: media.length,
        selectedCount,
        docsCount: docs.length,
        status,
      };
    });
  }, [products]);

  const filteredQueue = useMemo(
    () => queue.filter((row) => filter === "all" || row.status === filter),
    [filter, queue],
  );

  const missingCount = queue.filter((row) => row.status === "missing").length;
  const reviewCount = queue.filter((row) => row.status === "review").length;
  const readyCount = queue.filter((row) => row.status === "ready").length;

  return (
    <div className="page page-shell mediaOpsPage">
      <header className="mediaOpsCommandHeader">
        <div className="mediaOpsCommandContext">
          <span>Контент / медиа</span>
          <h1>Медиа и документы</h1>
          <p>Рабочая область для проверки изображений, PDF и порядка выгрузки. Источники собираются из импорта площадок и конкурентов, но финальный состав утверждает пользователь.</p>
        </div>
        <div className="mediaOpsActions">
          <Badge tone="pending">Очередь проверки</Badge>
          <Link className="btn" to={orgPath("/products")}>К товарам</Link>
          <Link className="btn primary" to={orgPath("/catalog/exchange?tab=export")}>К экспорту</Link>
        </div>
      </header>

      <MetricGrid
        className="mediaOpsMetrics"
        items={[
          { label: "В очереди", value: String(queue.length), meta: loading ? "загружаю SKU" : "товары в контрольной выборке" },
          { label: "Без медиа", value: String(missingCount), meta: "нужно проверить импорт или конкурентов" },
          { label: "Готово", value: String(readyCount), meta: "есть утвержденный набор для экспорта" },
        ]}
      />

      <section className="mediaOpsWorkspace" aria-label="Рабочий процесс медиа">
        <div className="mediaOpsBoard">
          {MEDIA_WORKFLOW.map((item, index) => (
            <article key={item.key} className="mediaOpsStep">
              <div className="mediaOpsStepNumber">{String(index + 1).padStart(2, "0")}</div>
              <div className="mediaOpsStepBody">
                <div className="mediaOpsStepHead">
                  <h2>{item.title}</h2>
                  <Badge tone={index === 0 ? "active" : "pending"}>{item.status}</Badge>
                </div>
                <p>{item.text}</p>
              </div>
            </article>
          ))}
        </div>

        <aside className="mediaOpsQueuePanel">
          <div className="mediaOpsQueueHead">
            <span>Контроль перед экспортом</span>
            <strong>Что нельзя пропустить</strong>
          </div>
          <div className="mediaOpsQueueList">
            {MEDIA_QUEUE.map((item) => (
              <div key={item.key} className="mediaOpsQueueItem">
                <div>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
                <p>{item.detail}</p>
              </div>
            ))}
          </div>
        </aside>
      </section>

      <section className="mediaOpsTableCard" aria-label="Очередь медиа SKU">
        <div className="mediaOpsTableHeader">
          <div>
            <span>Очередь медиа</span>
            <h2>SKU для проверки перед экспортом</h2>
            <p>Открывайте карточку товара, выбирайте фото для экспорта и фиксируйте порядок галереи. Экспорт берет только выбранный набор.</p>
          </div>
          <div className="mediaOpsTableActions">
            <Button onClick={() => void loadProducts()} disabled={loading}>{loading ? "Обновляю" : "Обновить"}</Button>
            <Link className="btn primary" to={orgPath("/catalog/exchange?tab=export")}>К экспорту</Link>
          </div>
        </div>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="mediaOpsFilters" role="tablist" aria-label="Фильтр очереди медиа">
          {[
            { key: "all", label: "Все", count: queue.length },
            { key: "missing", label: "Без медиа", count: missingCount },
            { key: "review", label: "Проверить выбор", count: reviewCount },
            { key: "ready", label: "Готово", count: readyCount },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              className={filter === item.key ? "isActive" : ""}
              onClick={() => setFilter(item.key as MediaFilter)}
            >
              {item.label}<span>{item.count}</span>
            </button>
          ))}
        </div>
        <div className="mediaOpsTable" role="table">
          <div className="mediaOpsTableRow isHead" role="row">
            <span>SKU / товар</span>
            <span>Категория</span>
            <span>Медиа</span>
            <span>Документы</span>
            <span>Статус</span>
            <span>Действие</span>
          </div>
          {loading ? (
            <div className="mediaOpsTableEmpty">Загружаю очередь медиа...</div>
          ) : filteredQueue.length ? filteredQueue.map((row) => {
            const product = row.product;
            const title = product.title || product.name || product.id;
            const sku = product.sku_gt || product.sku || product.id;
            const statusTone = row.status === "ready" ? "active" : row.status === "review" ? "pending" : "danger";
            const statusLabel = row.status === "ready" ? "Готово" : row.status === "review" ? "Проверить выбор" : "Нет медиа";
            return (
              <div key={product.id} className="mediaOpsTableRow" role="row">
                <div className="mediaOpsSkuCell">
                  <strong>{title}</strong>
                  <span>{sku}</span>
                </div>
                <span>{product.category_path || product.category_name || "Без категории"}</span>
                <span>{row.mediaCount ? `${row.selectedCount}/${row.mediaCount} выбрано` : "0 фото"}</span>
                <span>{row.docsCount ? `${row.docsCount} файлов` : "нет PDF"}</span>
                <Badge tone={statusTone}>{statusLabel}</Badge>
                <Link className="btn sm" to={orgPath(`/products/${encodeURIComponent(product.id)}?tab=media`)}>
                  Открыть SKU
                </Link>
              </div>
            );
          }) : (
            <div className="mediaOpsTableEmpty">По выбранному фильтру нет SKU.</div>
          )}
        </div>
      </section>
    </div>
  );
}
