import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import CatalogExchangePicker, { type ExchangeNode, type ExchangeProduct } from "../components/CatalogExchangePicker";
import { api } from "../lib/api";
import "../styles/catalog-exchange.css";

type ImportRunResp = {
  ok: boolean;
  run_id: string;
  count: number;
  updated_products: number;
  import_overview?: {
    description_ready?: number;
    images_ready?: number;
    features_ready?: number;
    with_yandex_data?: number;
    with_competitor_media?: number;
    still_missing?: number;
  };
  yandex_result?: { matched_products?: number; updated_products?: number };
  products?: Array<{
    product_id: string;
    title: string;
    sku_gt?: string;
    filled_features: number;
    conflicts_count: number;
    source_summary?: {
      filled_features?: number;
      description?: { present?: boolean; from_yandex?: boolean; from_competitors?: boolean };
      media?: { images_count?: number; videos_count?: number; from_yandex?: boolean; from_competitors?: boolean };
      missing_blocks?: string[];
    };
    competitor_results?: Record<string, { ok?: boolean; images_count?: number; has_description?: boolean; mapped_specs_count?: number; error?: string }>;
  }>;
  conflicts?: Array<{
    product_id: string;
    product_title: string;
    field_code: string;
    field_name: string;
    kind: string;
    current_value: string;
    final_value: string;
    candidates: Array<{ source: string; label: string; value: string }>;
    resolved?: boolean;
  }>;
};

type ImportOverviewResp = {
  ok: boolean;
  count: number;
  import_overview?: {
    description_ready?: number;
    images_ready?: number;
    features_ready?: number;
    with_yandex_data?: number;
    with_competitor_media?: number;
    still_missing?: number;
  };
  products?: Array<{
    product_id: string;
    title: string;
    sku_gt?: string;
    filled_features: number;
    conflicts_count: number;
    source_summary?: {
      filled_features?: number;
      description?: { present?: boolean; from_yandex?: boolean; from_competitors?: boolean };
      media?: { images_count?: number; videos_count?: number; from_yandex?: boolean; from_competitors?: boolean };
      missing_blocks?: string[];
    };
  }>;
};

export default function CatalogImportPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [nodes, setNodes] = useState<ExchangeNode[]>([]);
  const [productCountsByCategory, setProductCountsByCategory] = useState<Record<string, number>>({});
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);
  const [includeDescendants, setIncludeDescendants] = useState(true);
  const [useYandex, setUseYandex] = useState(true);
  const [useCompetitors, setUseCompetitors] = useState(true);
  const [loading, setLoading] = useState(false);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overview, setOverview] = useState<ImportOverviewResp | null>(null);
  const [run, setRun] = useState<ImportRunResp | null>(null);
  const [err, setErr] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [bootstrappedFromUrl, setBootstrappedFromUrl] = useState(false);

  useEffect(() => {
    const load = async () => {
      const [n, counts] = await Promise.all([
        api<{ nodes: ExchangeNode[] }>("/catalog/nodes"),
        api<{ counts: Record<string, number> }>("/catalog/products/counts"),
      ]);
      setNodes(n.nodes || []);
      setProductCountsByCategory(counts.counts || {});
    };
    void load();
  }, []);

  useEffect(() => {
    if (bootstrappedFromUrl) return;
    if (!nodes.length) return;
    const categoryId = String(searchParams.get("category") || "").trim();
    const productId = String(searchParams.get("product") || "").trim();
    const nextNodeIds = categoryId && nodes.some((node) => node.id === categoryId) ? [categoryId] : [];
    const nextProductIds = productId ? [productId] : [];
    if (nextNodeIds.length) setSelectedNodeIds(nextNodeIds);
    if (nextProductIds.length) setSelectedProductIds(nextProductIds);
    setBootstrappedFromUrl(true);
  }, [bootstrappedFromUrl, nodes, searchParams]);

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (selectedNodeIds[0]) next.set("category", selectedNodeIds[0]);
    else next.delete("category");
    if (selectedProductIds[0]) next.set("product", selectedProductIds[0]);
    else next.delete("product");
    const serialized = next.toString();
    if (serialized !== searchParams.toString()) {
      setSearchParams(next, { replace: true });
    }
  }, [selectedNodeIds, selectedProductIds, searchParams, setSearchParams]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedNodeIds.length && !selectedProductIds.length) {
      setOverview(null);
      setOverviewLoading(false);
      return;
    }
    const timer = window.setTimeout(() => {
      setOverviewLoading(true);
      const params = new URLSearchParams();
      if (selectedNodeIds.length) params.set("node_ids", selectedNodeIds.join(","));
      if (selectedProductIds.length) params.set("product_ids", selectedProductIds.join(","));
      params.set("include_descendants", includeDescendants ? "1" : "0");
      params.set("limit", "50");
      void (async () => {
        try {
          const resp = await api<ImportOverviewResp>(`/catalog/exchange/import/overview?${params.toString()}`);
          if (!cancelled) setOverview(resp);
        } catch (e) {
          if (!cancelled) setErr((e as Error).message || "Ошибка загрузки обзора");
        } finally {
          if (!cancelled) setOverviewLoading(false);
        }
      })();
    }, 150);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [includeDescendants, selectedNodeIds, selectedProductIds]);

  const unresolved = useMemo(() => (run?.conflicts || []).filter((x) => !x.resolved), [run]);
  const selectedScope = useMemo(() => {
    if (!selectedNodeIds.length && !selectedProductIds.length) return "Весь каталог";
    if (selectedProductIds.length && !selectedNodeIds.length) return `Товары: ${selectedProductIds.length}`;
    if (selectedNodeIds.length && !selectedProductIds.length) return `Разделы: ${selectedNodeIds.length}`;
    return `Разделы: ${selectedNodeIds.length} · Товары: ${selectedProductIds.length}`;
  }, [selectedNodeIds, selectedProductIds]);
  const runProducts = run?.products || [];
  const runOverview = run?.import_overview || {};
  const baselineProducts = overview?.products || [];
  const baselineOverview = overview?.import_overview || {};
  const sourceMode = useMemo(() => {
    if (useYandex && useCompetitors) return "Маркет -> конкуренты";
    if (useYandex) return "Только Яндекс.Маркет";
    if (useCompetitors) return "Только конкуренты";
    return "Источники не выбраны";
  }, [useCompetitors, useYandex]);

  async function startImport() {
    setLoading(true);
    setErr("");
    try {
      const res = await api<ImportRunResp>("/catalog/exchange/import/run", {
        method: "POST",
        body: JSON.stringify({
          selection: {
            mode: selectedNodeIds.length || selectedProductIds.length ? "mixed" : "all",
            node_ids: selectedNodeIds,
            product_ids: selectedProductIds,
            include_descendants: includeDescendants,
          },
          use_yandex_market: useYandex,
          use_competitors: useCompetitors,
        }),
      });
      setRun(res);
      const nextDrafts: Record<string, string> = {};
      for (const row of res.conflicts || []) {
        nextDrafts[`${row.product_id}:${row.field_code}`] = row.final_value || row.current_value || "";
      }
      setDrafts(nextDrafts);
    } catch (e) {
      setErr((e as Error).message || "Ошибка импорта");
    } finally {
      setLoading(false);
    }
  }

  async function saveResolutions() {
    if (!run?.run_id) return;
    const items = (run.conflicts || [])
      .filter((x) => !x.resolved)
      .map((x) => ({
        product_id: x.product_id,
        field_code: x.field_code,
        field_name: x.field_name,
        kind: x.kind,
        value: drafts[`${x.product_id}:${x.field_code}`] || "",
      }))
      .filter((x) => x.value.trim());
    if (!items.length) return;
    setSaving(true);
    setErr("");
    try {
      await api("/catalog/exchange/import/resolve", {
        method: "POST",
        body: JSON.stringify({ run_id: run.run_id, items }),
      });
      const fresh = await api<{ ok: boolean; run: ImportRunResp }>(`/catalog/exchange/import/runs/${encodeURIComponent(run.run_id)}`);
      setRun(fresh.run);
    } catch (e) {
      setErr((e as Error).message || "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="cx-page">
      <div className="cx-head">
        <div>
          <div className="cx-headEyebrow">Заполнение данных</div>
          <h1>Импорт контента</h1>
          <p>Выбираем ветку каталога, тянем контент из Яндекс.Маркета, затем добиваем пробелы конкурентами и отдельно закрываем конфликты значений.</p>
        </div>
        <div className="cx-headActions">
          <Link className="btn" to="/catalog">К каталогу</Link>
          <button className="btn primary" onClick={() => void startImport()} disabled={loading || (!useYandex && !useCompetitors)}>
            {loading ? "Заполняю…" : "Запустить заполнение"}
          </button>
        </div>
      </div>

      <section className="cx-runway card">
        <div className="cx-runwayMain">
          <div className="cx-runwayTitle">Пайплайн</div>
          <div className="cx-runwaySteps">
            <div className="cx-runwayStep"><span>1</span><b>Область</b><small>Каталог или точечные товары</small></div>
            <div className="cx-runwayStep"><span>2</span><b>Маркет</b><small>Описание, медиа, часть характеристик</small></div>
            <div className="cx-runwayStep"><span>3</span><b>Конкуренты</b><small>Добивка пробелов и конфликты</small></div>
          </div>
        </div>
        <div className="cx-runwayAside">
          <div className="cx-kpi">
            <span className="cx-kpiLabel">Область</span>
            <span className="cx-kpiValue">{selectedScope}</span>
          </div>
          <div className="cx-kpi">
            <span className="cx-kpiLabel">Режим</span>
            <span className="cx-kpiValue">{sourceMode}</span>
          </div>
        </div>
      </section>

      <section className="cx-importTopGrid">
        <div className="card cx-sourceShell">
          <div className="cx-sectionHeadline">
            <div>
              <div className="cx-paneTitle">Источники заполнения</div>
              <div className="cx-paneSub">Маркет даем как основной источник. Конкурентов включаем для добивки и конфликтов.</div>
            </div>
          </div>
          <div className="cx-sourceList">
            <label className={`cx-sourceToggle ${useYandex ? "isActive" : ""}`}>
              <input type="checkbox" checked={useYandex} onChange={(e) => setUseYandex(e.target.checked)} />
              <span className="cx-sourceTitle">Яндекс.Маркет</span>
              <span className="cx-sourceMeta">Приоритет для описания, медиа и характеристик по мастер-шаблону.</span>
            </label>
            <label className={`cx-sourceToggle ${useCompetitors ? "isActive" : ""}`}>
              <input type="checkbox" checked={useCompetitors} onChange={(e) => setUseCompetitors(e.target.checked)} />
              <span className="cx-sourceTitle">Конкуренты</span>
              <span className="cx-sourceMeta">Добивают пробелы после Маркета и дают варианты для разрешения конфликтов.</span>
            </label>
          </div>
        </div>
        <div className="card cx-runInfoCard">
          <div className="cx-sectionHeadline">
            <div>
              <div className="cx-paneTitle">Что произойдет</div>
              <div className="cx-paneSub">Заполнение идет в 1 прогон и сохраняет run c итогами и нерешенными конфликтами.</div>
            </div>
          </div>
          <div className="cx-bulletList">
            <div>Выбранные товары будут синхронизированы с Маркетом.</div>
            <div>Конкуренты не затирают вслепую, а создают варианты выбора.</div>
            <div>Пустые блоки после прогона остаются видимыми отдельным списком.</div>
          </div>
        </div>
      </section>

      <CatalogExchangePicker
        nodes={nodes}
        productCountsByCategory={productCountsByCategory}
        selectedNodeIds={selectedNodeIds}
        selectedProductIds={selectedProductIds}
        onSelectedNodeIdsChange={setSelectedNodeIds}
        onSelectedProductIdsChange={setSelectedProductIds}
        includeDescendants={includeDescendants}
        onIncludeDescendantsChange={setIncludeDescendants}
      />

      {err ? <div className="card cx-error">{err}</div> : null}

      {overview || overviewLoading ? (
        <>
          <section className="cx-summaryGrid cx-summaryGridPrimary">
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Товаров в области</div><div className="cx-summaryValue">{overviewLoading && !overview ? "…" : overview?.count || 0}</div></div>
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Описания готовы</div><div className="cx-summaryValue">{baselineOverview.description_ready || 0}</div></div>
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Фото готовы</div><div className="cx-summaryValue">{baselineOverview.images_ready || 0}</div></div>
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Ждут добивки</div><div className="cx-summaryValue">{baselineOverview.still_missing || 0}</div></div>
          </section>

          <section className="cx-summaryStrip card">
            <div className="cx-stripMetric"><span>Характеристики</span><b>{baselineOverview.features_ready || 0}</b></div>
            <div className="cx-stripMetric"><span>С Маркетом</span><b>{baselineOverview.with_yandex_data || 0}</b></div>
            <div className="cx-stripMetric"><span>С медиа конкурентов</span><b>{baselineOverview.with_competitor_media || 0}</b></div>
          </section>

          <section className="card cx-pane">
            <div className="cx-paneHead">
              <div>
                <div className="cx-paneTitle">Текущая готовность ветки</div>
                <div className="cx-paneSub">Это уже прогретые backend-данные. Здесь видно текущий факт до запуска нового заполнения.</div>
              </div>
            </div>
            <div className="cx-resultsTableWrap">
              <table className="cx-resultsTable">
                <thead>
                  <tr>
                    <th>Товар</th>
                    <th>Характеристики</th>
                    <th>Контент</th>
                    <th>Источники</th>
                    <th>Пробелы</th>
                  </tr>
                </thead>
                <tbody>
                  {baselineProducts.map((row) => (
                    <tr key={row.product_id}>
                      <td>
                        <div className="cx-resultProduct">
                          <Link to={`/products/${encodeURIComponent(row.product_id)}`}>{row.title}</Link>
                          <span>GT SKU {row.sku_gt || "—"}</span>
                        </div>
                      </td>
                      <td><div className="cx-resultValue">{row.source_summary?.filled_features ?? row.filled_features}</div></td>
                      <td>
                        <div className="cx-cellStack">
                          <span className={`cx-statusDot ${(row.source_summary?.description?.present) ? "isOk" : ""}`}>Описание</span>
                          <span className={`cx-statusDot ${((row.source_summary?.media?.images_count || 0) > 0) ? "isOk" : ""}`}>Фото {row.source_summary?.media?.images_count || 0}</span>
                          <span className={`cx-statusDot ${((row.source_summary?.media?.videos_count || 0) > 0) ? "isOk" : ""}`}>Видео {row.source_summary?.media?.videos_count || 0}</span>
                        </div>
                      </td>
                      <td>
                        <div className="cx-cellStack">
                          <span className={`cx-sourcePill ${(row.source_summary?.description?.from_yandex || row.source_summary?.media?.from_yandex) ? "isOn" : ""}`}>Маркет</span>
                          <span className={`cx-sourcePill ${row.source_summary?.media?.from_competitors ? "isOn" : ""}`}>Конкуренты</span>
                        </div>
                      </td>
                      <td>{(row.source_summary?.missing_blocks || []).length ? (row.source_summary?.missing_blocks || []).join(", ") : "—"}</td>
                    </tr>
                  ))}
                  {!baselineProducts.length && !overviewLoading ? (
                    <tr><td colSpan={5} className="cx-empty">Выбери ветку каталога или конкретные товары.</td></tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}

      {run ? (
        <>
          <section className="cx-summaryGrid cx-summaryGridPrimary">
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Товаров в прогоне</div><div className="cx-summaryValue">{run.count}</div></div>
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Обновлено</div><div className="cx-summaryValue">{run.updated_products}</div></div>
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Яндекс нашел</div><div className="cx-summaryValue">{run.yandex_result?.matched_products || 0}</div></div>
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Конфликтов</div><div className="cx-summaryValue">{unresolved.length}</div></div>
          </section>

          <section className="cx-summaryStrip card">
            <div className="cx-stripMetric"><span>Описания готовы</span><b>{runOverview.description_ready || 0}</b></div>
            <div className="cx-stripMetric"><span>Фото готовы</span><b>{runOverview.images_ready || 0}</b></div>
            <div className="cx-stripMetric"><span>Характеристики</span><b>{runOverview.features_ready || 0}</b></div>
            <div className="cx-stripMetric"><span>С Маркетом</span><b>{runOverview.with_yandex_data || 0}</b></div>
            <div className="cx-stripMetric"><span>С медиа конкурентов</span><b>{runOverview.with_competitor_media || 0}</b></div>
            <div className="cx-stripMetric isAlert"><span>Ждут добивки</span><b>{runOverview.still_missing || 0}</b></div>
          </section>

          <section className="card cx-pane">
            <div className="cx-paneHead">
              <div>
                <div className="cx-paneTitle">Результат прогона</div>
                <div className="cx-paneSub">Видно, чем товар насытился после Маркета и конкурентов, и какие блоки остались пустыми.</div>
              </div>
            </div>
            <div className="cx-resultsTableWrap">
              <table className="cx-resultsTable">
                <thead>
                  <tr>
                    <th>Товар</th>
                    <th>Характеристики</th>
                    <th>Контент</th>
                    <th>Источники</th>
                    <th>Пробелы</th>
                    <th>Конфликты</th>
                  </tr>
                </thead>
                <tbody>
                  {runProducts.map((row) => (
                    <tr key={row.product_id}>
                      <td>
                        <div className="cx-resultProduct">
                          <Link to={`/products/${encodeURIComponent(row.product_id)}`}>{row.title}</Link>
                          <span>GT SKU {row.sku_gt || "—"}</span>
                        </div>
                      </td>
                      <td>
                        <div className="cx-resultValue">{row.source_summary?.filled_features ?? row.filled_features}</div>
                      </td>
                      <td>
                        <div className="cx-cellStack">
                          <span className={`cx-statusDot ${(row.source_summary?.description?.present) ? "isOk" : ""}`}>Описание</span>
                          <span className={`cx-statusDot ${((row.source_summary?.media?.images_count || 0) > 0) ? "isOk" : ""}`}>Фото {row.source_summary?.media?.images_count || 0}</span>
                          <span className={`cx-statusDot ${((row.source_summary?.media?.videos_count || 0) > 0) ? "isOk" : ""}`}>Видео {row.source_summary?.media?.videos_count || 0}</span>
                        </div>
                      </td>
                      <td>
                        <div className="cx-cellStack">
                          <span className={`cx-sourcePill ${(row.source_summary?.description?.from_yandex || row.source_summary?.media?.from_yandex) ? "isOn" : ""}`}>Маркет</span>
                          <span className={`cx-sourcePill ${row.source_summary?.media?.from_competitors ? "isOn" : ""}`}>Конкуренты</span>
                        </div>
                      </td>
                      <td>{(row.source_summary?.missing_blocks || []).length ? (row.source_summary?.missing_blocks || []).join(", ") : "—"}</td>
                      <td>{row.conflicts_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card cx-pane">
            <div className="cx-paneHead">
              <div>
                <div className="cx-paneTitle">Конфликты данных</div>
                <div className="cx-paneSub">Выбери одно из значений или задай свое финальное. Без этого конфликт не закроется.</div>
              </div>
              <button className="btn primary" onClick={() => void saveResolutions()} disabled={saving || unresolved.length === 0}>{saving ? "Сохраняю…" : "Применить выбранные значения"}</button>
            </div>
            <div className="cx-conflicts">
              {unresolved.map((row) => {
                const key = `${row.product_id}:${row.field_code}`;
                return (
                  <div key={key} className="cx-conflictCard">
                    <div className="cx-conflictHead">
                      <div>
                        <div className="cx-conflictTitle">{row.field_name}</div>
                        <div className="cx-conflictMeta"><Link to={`/products/${encodeURIComponent(row.product_id)}`}>{row.product_title}</Link></div>
                      </div>
                    </div>
                    <div className="cx-candidates">
                      {row.candidates.map((candidate, idx) => (
                        <button key={`${key}:${idx}`} className="cx-candidateBtn" onClick={() => setDrafts((prev) => ({ ...prev, [key]: candidate.value || "" }))}>
                          <span className="cx-candidateLabel">{candidate.label}</span>
                          <span className="cx-candidateValue">{candidate.value || "—"}</span>
                        </button>
                      ))}
                    </div>
                    {row.kind === "description" ? (
                      <textarea className="pn-input cx-textarea" value={drafts[key] || ""} onChange={(e) => setDrafts((prev) => ({ ...prev, [key]: e.target.value }))} />
                    ) : (
                      <input className="pn-input" value={drafts[key] || ""} onChange={(e) => setDrafts((prev) => ({ ...prev, [key]: e.target.value }))} />
                    )}
                  </div>
                );
              })}
              {unresolved.length === 0 ? <div className="cx-empty">Конфликтов нет. Импорт можно считать завершенным.</div> : null}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
