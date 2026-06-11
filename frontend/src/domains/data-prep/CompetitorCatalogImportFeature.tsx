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
  link?: ProductLink | null;
};

type ProductLink = {
  status: "linked" | "ignored" | "unlinked";
  pim_product_id: string;
  pim_title?: string;
  sku_gt?: string;
  sku_pim?: string;
  updated_at: string;
  last_applied_at?: string;
};

type ProductCandidate = {
  product_id: string;
  title: string;
  sku_gt: string;
  sku_pim: string;
  category_id: string;
  group_id?: string;
  score: number;
  reasons: string[];
};

type CatalogSearchItem = {
  id: string;
  title?: string;
  name?: string;
  sku_gt?: string;
  sku_pim?: string;
  category_id?: string;
  group_id?: string;
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

type SuggestionsResponse = {
  product: ImportedProduct;
  candidates: ProductCandidate[];
};

type LinkResponse = {
  product: ImportedProduct;
};

type ApplyPlan = {
  summary: {
    media_to_add: number;
    description_ready: boolean;
    specs_to_fill: number;
    specs_to_create: number;
  };
  media_to_add: Array<{ url: string; caption?: string }>;
  description_to_apply: string;
  description_skipped_reason?: string;
  specs_to_fill: Array<{ name: string; value: string }>;
  specs_to_create: Array<{ name: string; value: string }>;
};

type ApplyPreviewResponse = {
  competitor_product: ImportedProduct;
  pim_product: { id: string; title: string; sku_gt: string; sku_pim: string };
  plan: ApplyPlan;
};

type ApplyResponse = {
  competitor_product: ImportedProduct;
  applied: { media: number; description: boolean; specs: number };
  plan: ApplyPlan;
};

type ProductQueueFilter = "all" | "unlinked" | "ready" | "applied" | "ignored";

type ProductSearchResponse = {
  items: CatalogSearchItem[];
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

function linkLabel(link?: ProductLink | null) {
  if (!link) return "Не связана";
  if (link.status === "ignored") return "Не использовать";
  if (link.status === "linked") return "Связана";
  return "Не связана";
}

function queueFilterLabel(filter: ProductQueueFilter) {
  if (filter === "unlinked") return "Не связаны";
  if (filter === "ready") return "К применению";
  if (filter === "applied") return "Применены";
  if (filter === "ignored") return "Игнор";
  return "Все";
}

function queueStatus(product: ImportedProduct): ProductQueueFilter {
  if (product.link?.status === "ignored") return "ignored";
  if (product.link?.status === "linked" && product.link.last_applied_at) return "applied";
  if (product.link?.status === "linked") return "ready";
  return "unlinked";
}

function ProductInspector({
  product,
  candidates,
  applyPlan,
  loadingCandidates,
  loadingPlan,
  applying,
  onLink,
  onIgnore,
  onUnlink,
  onApply,
}: {
  product: ImportedProduct | null;
  candidates: ProductCandidate[];
  applyPlan: ApplyPlan | null;
  loadingCandidates: boolean;
  loadingPlan: boolean;
  applying: boolean;
  onLink: (candidate: ProductCandidate) => void;
  onIgnore: () => void;
  onUnlink: () => void;
  onApply: () => void;
}) {
  const [manualQuery, setManualQuery] = useState("");
  const [manualResults, setManualResults] = useState<ProductCandidate[]>([]);
  const [manualLoading, setManualLoading] = useState(false);

  useEffect(() => {
    if (!product?.id || product.link?.status === "linked" || product.link?.status === "ignored") {
      setManualResults([]);
      return;
    }
    const q = manualQuery.trim();
    if (q.length < 2) {
      setManualResults([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setManualLoading(true);
      api<ProductSearchResponse>(`/catalog/products/search?q=${encodeURIComponent(q)}&limit=20`)
        .then((data) => {
          if (cancelled) return;
          setManualResults(
            (data.items || []).map((item) => ({
              product_id: item.id,
              title: item.title || item.name || item.id,
              sku_gt: item.sku_gt || "",
              sku_pim: item.sku_pim || "",
              category_id: item.category_id || "",
              group_id: item.group_id,
              score: 0,
              reasons: ["ручной поиск"],
            })),
          );
        })
        .catch(() => {
          if (!cancelled) setManualResults([]);
        })
        .finally(() => {
          if (!cancelled) setManualLoading(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [manualQuery, product?.id, product?.link?.status]);

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
        <Badge tone={product.link?.status === "linked" ? "active" : product.link?.status === "ignored" ? "neutral" : "pending"}>
          {linkLabel(product.link)}
        </Badge>
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

      <div className="cciLinkBlock">
        <div className="cciSectionTitle">Связь с PIM</div>
        {product.link?.status === "linked" ? (
          <div className="cciLinkedProduct">
            <span>Связана с SKU</span>
            <strong>{product.link.pim_title || product.link.pim_product_id}</strong>
            <small>{product.link.sku_gt || product.link.sku_pim || product.link.pim_product_id}</small>
            <Button onClick={onUnlink}>Снять связь</Button>
          </div>
        ) : product.link?.status === "ignored" ? (
          <div className="cciLinkedProduct">
            <span>Эта карточка исключена</span>
            <strong>Не использовать для насыщения</strong>
            <Button onClick={onUnlink}>Вернуть в работу</Button>
          </div>
        ) : (
          <>
            <div className="cciCandidateList">
              {loadingCandidates ? (
                <div className="cciMuted">Подбираю кандидатов...</div>
              ) : candidates.length ? (
                candidates.map((candidate) => (
                  <button key={candidate.product_id} type="button" className="cciCandidate" onClick={() => onLink(candidate)}>
                    <span>
                      <strong>{candidate.title}</strong>
                      <small>{candidate.sku_gt || candidate.sku_pim || candidate.product_id}</small>
                    </span>
                    <Badge tone={candidate.score >= 70 ? "active" : "pending"}>{candidate.score}%</Badge>
                  </button>
                ))
              ) : (
                <div className="cciMuted">Похожие SKU не найдены. Используйте ручной поиск ниже.</div>
              )}
            </div>
            <div className="cciManualSearch">
              <TextInput
                value={manualQuery}
                onChange={(event) => setManualQuery(event.target.value)}
                placeholder="Ручной поиск SKU: название, GT SKU, PIM SKU"
              />
              {manualLoading ? <div className="cciMuted">Ищу товары...</div> : null}
              {manualResults.length ? (
                <div className="cciCandidateList">
                  {manualResults.map((candidate) => (
                    <button key={candidate.product_id} type="button" className="cciCandidate" onClick={() => onLink(candidate)}>
                      <span>
                        <strong>{candidate.title}</strong>
                        <small>{candidate.sku_gt || candidate.sku_pim || candidate.product_id}</small>
                      </span>
                      <Badge tone="neutral">ручной</Badge>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
            <Button onClick={onIgnore}>Не использовать карточку</Button>
          </>
        )}
      </div>

      {product.link?.status === "linked" ? (
        <div className="cciApplyBlock">
          <div className="cciSectionTitle">Предложения к товару</div>
          {loadingPlan ? (
            <div className="cciMuted">Собираю план применения...</div>
          ) : applyPlan ? (
            <>
              <div className="cciApplyGrid">
                <div>
                  <span>Медиа</span>
                  <strong>{applyPlan.summary.media_to_add}</strong>
                </div>
                <div>
                  <span>Описание</span>
                  <strong>{applyPlan.summary.description_ready ? "есть" : "нет"}</strong>
                </div>
                <div>
                  <span>Заполнить</span>
                  <strong>{applyPlan.summary.specs_to_fill}</strong>
                </div>
                <div>
                  <span>Новые поля</span>
                  <strong>{applyPlan.summary.specs_to_create}</strong>
                </div>
              </div>
              <div className="cciApplyPreview">
                {applyPlan.media_to_add.slice(0, 4).map((item) => (
                  <img key={item.url} src={item.url} alt="" loading="lazy" />
                ))}
                {applyPlan.description_to_apply ? <p>{applyPlan.description_to_apply}</p> : null}
                {[...applyPlan.specs_to_fill, ...applyPlan.specs_to_create].slice(0, 6).map((item) => (
                  <div key={`${item.name}:${item.value}`} className="cciSpecRow">
                    <span>{item.name}</span>
                    <strong>{item.value}</strong>
                  </div>
                ))}
              </div>
              <Button variant="primary" onClick={onApply} disabled={applying}>
                {applying ? "Применяю..." : "Применить к SKU"}
              </Button>
            </>
          ) : (
            <div className="cciMuted">Нет данных для применения.</div>
          )}
        </div>
      ) : null}

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
  const [candidates, setCandidates] = useState<ProductCandidate[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [applyPlan, setApplyPlan] = useState<ApplyPlan | null>(null);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [applying, setApplying] = useState(false);
  const [queueFilter, setQueueFilter] = useState<ProductQueueFilter>("all");

  const lastRun = runs[0] || null;
  const queueCounts = useMemo(() => {
    const counts: Record<ProductQueueFilter, number> = { all: products.length, unlinked: 0, ready: 0, applied: 0, ignored: 0 };
    for (const product of products) {
      counts[queueStatus(product)] += 1;
    }
    return counts;
  }, [products]);
  const filteredProducts = useMemo(
    () => products.filter((product) => queueFilter === "all" || queueStatus(product) === queueFilter),
    [products, queueFilter],
  );
  const selectedProduct = filteredProducts.find((product) => product.id === selectedId) || filteredProducts[0] || null;

  const metrics = useMemo(
    () => [
      { label: "Найдено карточек", value: lastRun?.products_found || 0, meta: lastRun?.host || "последний прогон" },
      { label: "Не связаны", value: queueCounts.unlinked, meta: "нужен SKU" },
      { label: "К применению", value: queueCounts.ready, meta: "связаны с SKU" },
      { label: "Применены", value: queueCounts.applied, meta: `${totalProducts} всего` },
    ],
    [lastRun, queueCounts, totalProducts],
  );

  useEffect(() => {
    if (!filteredProducts.length) return;
    if (!filteredProducts.some((product) => product.id === selectedId)) {
      setSelectedId(filteredProducts[0].id);
    }
  }, [filteredProducts, selectedId]);

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

  useEffect(() => {
    if (!selectedProduct?.id || selectedProduct.link?.status === "linked" || selectedProduct.link?.status === "ignored") {
      setCandidates([]);
      return;
    }
    let cancelled = false;
    setLoadingCandidates(true);
    api<SuggestionsResponse>(`/competitor-catalog/products/${selectedProduct.id}/suggestions`)
      .then((data) => {
        if (cancelled) return;
        setCandidates(data.candidates || []);
      })
      .catch(() => {
        if (!cancelled) setCandidates([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingCandidates(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedProduct?.id, selectedProduct?.link?.status]);

  useEffect(() => {
    if (!selectedProduct?.id || selectedProduct.link?.status !== "linked") {
      setApplyPlan(null);
      return;
    }
    let cancelled = false;
    setLoadingPlan(true);
    api<ApplyPreviewResponse>(`/competitor-catalog/products/${selectedProduct.id}/apply-preview`)
      .then((data) => {
        if (!cancelled) setApplyPlan(data.plan || null);
      })
      .catch(() => {
        if (!cancelled) setApplyPlan(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingPlan(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedProduct?.id, selectedProduct?.link?.status, selectedProduct?.link?.last_applied_at]);

  function replaceProduct(next: ImportedProduct) {
    setProducts((items) => items.map((item) => (item.id === next.id ? next : item)));
  }

  async function saveLink(status: "linked" | "ignored" | "unlinked", pimProductId = "") {
    if (!selectedProduct) return;
    setError("");
    try {
      const data = await api<LinkResponse>(`/competitor-catalog/products/${selectedProduct.id}/link`, {
        method: "POST",
        body: JSON.stringify({ product_id: selectedProduct.id, pim_product_id: pimProductId, status }),
      });
      replaceProduct(data.product);
    } catch (err) {
      setError(parseApiError(err));
    }
  }

  async function applySelectedProduct() {
    if (!selectedProduct) return;
    setApplying(true);
    setError("");
    try {
      const data = await api<ApplyResponse>(`/competitor-catalog/products/${selectedProduct.id}/apply`, {
        method: "POST",
        body: JSON.stringify({ apply_media: true, apply_description: true, apply_specs: true }),
      });
      replaceProduct(data.competitor_product);
      setApplyPlan(data.plan || null);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setApplying(false);
    }
  }

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
              {loading ? <Badge tone="provisioning">Загрузка</Badge> : <Badge tone="neutral">{filteredProducts.length} из {products.length}</Badge>}
            </div>

            {products.length ? (
              <div className="cciQueueFilters">
                {(["all", "unlinked", "ready", "applied", "ignored"] as ProductQueueFilter[]).map((filter) => (
                  <button
                    key={filter}
                    type="button"
                    className={queueFilter === filter ? "isActive" : ""}
                    onClick={() => setQueueFilter(filter)}
                  >
                    <span>{queueFilterLabel(filter)}</span>
                    <strong>{queueCounts[filter]}</strong>
                  </button>
                ))}
              </div>
            ) : null}

            {filteredProducts.length ? (
              <div className="cciTable">
                <div className="cciTableHead">
                  <span>Товар</span>
                  <span>Связь</span>
                  <span>Цена</span>
                  <span>Медиа</span>
                  <span>Параметры</span>
                  <span>Уверенность</span>
                </div>
                {filteredProducts.map((product) => (
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
                    <span>
                      <Badge tone={product.link?.status === "linked" ? "active" : product.link?.status === "ignored" ? "neutral" : "pending"}>
                        {linkLabel(product.link)}
                      </Badge>
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
                {loading
                  ? "Загружаю последние результаты..."
                  : products.length
                    ? "В выбранном состоянии нет карточек."
                    : "Пока нет импортированных карточек. Запусти первый обход сайта конкурента."}
              </div>
            )}
          </section>
        </main>

        <ProductInspector
          product={selectedProduct}
          candidates={candidates}
          applyPlan={applyPlan}
          loadingCandidates={loadingCandidates}
          loadingPlan={loadingPlan}
          applying={applying}
          onLink={(candidate) => saveLink("linked", candidate.product_id)}
          onIgnore={() => saveLink("ignored")}
          onUnlink={() => saveLink("unlinked")}
          onApply={applySelectedProduct}
        />
      </section>
    </div>
  );
}
