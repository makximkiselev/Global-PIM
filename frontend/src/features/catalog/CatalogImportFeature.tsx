import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import CatalogExchangePicker, { type ExchangeNode } from "../../components/CatalogExchangePicker";
import DataToolbar from "../../components/data/DataToolbar";
import InspectorPanel from "../../components/data/InspectorPanel";
import WorkspaceFrame from "../../components/layout/WorkspaceFrame";
import { api } from "../../lib/api";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import EmptyState from "../../components/ui/EmptyState";
import PageHeader from "../../components/ui/PageHeader";
import Textarea from "../../components/ui/Textarea";
import "../../styles/catalog-exchange.css";

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

type MetricItem = {
  label: string;
  value: number | string;
  accent?: boolean;
};

function SummaryMetricRow({ items }: { items: MetricItem[] }) {
  return (
    <section className="cx-summaryStrip card">
      {items.map((item) => (
        <div key={item.label} className={`cx-stripMetric${item.accent ? " isAlert" : ""}`}>
          <span>{item.label}</span>
          <b>{item.value}</b>
        </div>
      ))}
    </section>
  );
}

function ProductsResultsTable({
  title,
  subtitle,
  rows,
  loading,
  showConflicts = false,
}: {
  title: string;
  subtitle: string;
  rows: ImportOverviewResp["products"] | ImportRunResp["products"];
  loading?: boolean;
  showConflicts?: boolean;
}) {
  return (
    <section className="card cx-pane">
      <div className="cx-paneHead">
        <div>
          <div className="cx-paneTitle">{title}</div>
          <div className="cx-paneSub">{subtitle}</div>
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
              {showConflicts ? <th>Конфликты</th> : null}
            </tr>
          </thead>
          <tbody>
            {(rows || []).map((row) => (
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
                    <span className={`cx-statusDot ${row.source_summary?.description?.present ? "isOk" : ""}`}>Описание</span>
                    <span className={`cx-statusDot ${((row.source_summary?.media?.images_count || 0) > 0) ? "isOk" : ""}`}>
                      Фото {row.source_summary?.media?.images_count || 0}
                    </span>
                    <span className={`cx-statusDot ${((row.source_summary?.media?.videos_count || 0) > 0) ? "isOk" : ""}`}>
                      Видео {row.source_summary?.media?.videos_count || 0}
                    </span>
                  </div>
                </td>
                <td>
                  <div className="cx-cellStack">
                    <span className={`cx-sourcePill ${(row.source_summary?.description?.from_yandex || row.source_summary?.media?.from_yandex) ? "isOn" : ""}`}>Маркет</span>
                    <span className={`cx-sourcePill ${row.source_summary?.media?.from_competitors ? "isOn" : ""}`}>Конкуренты</span>
                  </div>
                </td>
                <td>{(row.source_summary?.missing_blocks || []).length ? (row.source_summary?.missing_blocks || []).join(", ") : "—"}</td>
                {showConflicts ? <td>{"conflicts_count" in row ? row.conflicts_count : 0}</td> : null}
              </tr>
            ))}
            {!(rows || []).length ? (
              <tr>
                <td colSpan={showConflicts ? 6 : 5} className="cx-empty">
                  {loading ? "Загружаю данные..." : "Нет данных по выбранной области."}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function CatalogImportFeature() {
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
    if (bootstrappedFromUrl || !nodes.length) return;
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

  const baselineMetrics: MetricItem[] = [
    { label: "Товаров в области", value: overviewLoading && !overview ? "…" : overview?.count || 0 },
    { label: "Описания готовы", value: baselineOverview.description_ready || 0 },
    { label: "Фото готовы", value: baselineOverview.images_ready || 0 },
    { label: "Ждут добивки", value: baselineOverview.still_missing || 0, accent: true },
  ];

  const runMetrics: MetricItem[] = [
    { label: "Товаров в прогоне", value: run?.count || 0 },
    { label: "Обновлено", value: run?.updated_products || 0 },
    { label: "Яндекс нашел", value: run?.yandex_result?.matched_products || 0 },
    { label: "Конфликтов", value: unresolved.length, accent: unresolved.length > 0 },
  ];

  const inspector = (
    <div className="cx-workspaceInspector">
      <InspectorPanel title="Область" subtitle="Что именно попадет в прогон">
        <div className="cx-inspectorList">
          <div className="cx-inspectorRow"><span>Выбрано</span><strong>{selectedScope}</strong></div>
          <div className="cx-inspectorRow"><span>Режим</span><strong>{sourceMode}</strong></div>
          {selectedNodeIds.length ? (
            <div className="cx-inspectorRow"><span>Глубина</span><strong>{includeDescendants ? "Вся ветка" : "Только категория"}</strong></div>
          ) : null}
        </div>
      </InspectorPanel>

      <InspectorPanel title="Источники" subtitle="Источник данных для enrichment">
        <div className="cx-inspectorStack">
          <div className="cx-sourceInspectorCard">
            <div>
              <strong>Яндекс.Маркет</strong>
              <p>Главный источник описания, медиа и части характеристик.</p>
            </div>
            <Badge tone={useYandex ? "active" : "neutral"}>{useYandex ? "Включен" : "Выключен"}</Badge>
          </div>
          <div className="cx-sourceInspectorCard">
            <div>
              <strong>Конкуренты</strong>
              <p>Закрывают пробелы и дают кандидатов для конфликтов.</p>
            </div>
            <Badge tone={useCompetitors ? "active" : "neutral"}>{useCompetitors ? "Включен" : "Выключен"}</Badge>
          </div>
        </div>
      </InspectorPanel>

      <InspectorPanel title="Сейчас по ветке" subtitle="Текущий факт до нового запуска">
        <div className="cx-inspectorList">
          <div className="cx-inspectorRow"><span>Характеристики</span><strong>{baselineOverview.features_ready || 0}</strong></div>
          <div className="cx-inspectorRow"><span>С Маркетом</span><strong>{baselineOverview.with_yandex_data || 0}</strong></div>
          <div className="cx-inspectorRow"><span>С медиа конкурентов</span><strong>{baselineOverview.with_competitor_media || 0}</strong></div>
          <div className="cx-inspectorRow"><span>Нерешенных конфликтов</span><strong>{unresolved.length}</strong></div>
        </div>
      </InspectorPanel>
    </div>
  );

  return (
    <div className="cx-page cx-pageModern">
      <PageHeader
        title="Импорт контента"
        subtitle="Заполняй товары через Яндекс.Маркет и конкурентные источники без переходов между отдельными экранами."
        actions={(
          <>
            <Link className="btn" to="/catalog">К каталогу</Link>
            <Button variant="primary" onClick={() => void startImport()} disabled={loading || (!useYandex && !useCompetitors)}>
              {loading ? "Заполняю…" : "Запустить заполнение"}
            </Button>
          </>
        )}
      />

      {err ? <div className="card cx-error">{err}</div> : null}

      <WorkspaceFrame
        className="cx-workspaceFrame"
        sidebar={(
          <CatalogExchangePicker
            embedded
            nodes={nodes}
            productCountsByCategory={productCountsByCategory}
            selectedNodeIds={selectedNodeIds}
            selectedProductIds={selectedProductIds}
            onSelectedNodeIdsChange={setSelectedNodeIds}
            onSelectedProductIdsChange={setSelectedProductIds}
            includeDescendants={includeDescendants}
            onIncludeDescendantsChange={setIncludeDescendants}
          />
        )}
        main={(
          <div className="cx-workspaceMain">
            <DataToolbar
              title="Источники заполнения"
              subtitle="Маркет идет первым, конкуренты закрывают пробелы и конфликты. Область можно ограничить категорией или конкретными SKU."
              className="cx-workspaceToolbar"
              actions={(
                <div className="cx-toolbarActions">
                  <Badge tone={useYandex || useCompetitors ? "active" : "neutral"}>{sourceMode}</Badge>
                  <Button variant="primary" onClick={() => void startImport()} disabled={loading || (!useYandex && !useCompetitors)}>
                    {loading ? "Заполняю…" : "Запустить"}
                  </Button>
                </div>
              )}
            >
              <div className="cx-sourceBoard">
                <label className={`cx-sourceToggle ${useYandex ? "isActive" : ""}`}>
                  <input type="checkbox" checked={useYandex} onChange={(e) => setUseYandex(e.target.checked)} />
                  <span className="cx-sourceTitle">Яндекс.Маркет</span>
                  <span className="cx-sourceMeta">Приоритетный источник описания, медиа и части характеристик по шаблону.</span>
                </label>
                <label className={`cx-sourceToggle ${useCompetitors ? "isActive" : ""}`}>
                  <input type="checkbox" checked={useCompetitors} onChange={(e) => setUseCompetitors(e.target.checked)} />
                  <span className="cx-sourceTitle">Конкуренты</span>
                  <span className="cx-sourceMeta">Добивают пробелы после Маркета и создают кандидатов для конфликтов.</span>
                </label>
              </div>
            </DataToolbar>

            {(overview || overviewLoading) ? (
              <>
                <SummaryMetricRow items={baselineMetrics} />
                <SummaryMetricRow
                  items={[
                    { label: "Характеристики", value: baselineOverview.features_ready || 0 },
                    { label: "С Маркетом", value: baselineOverview.with_yandex_data || 0 },
                    { label: "С медиа конкурентов", value: baselineOverview.with_competitor_media || 0 },
                  ]}
                />
                <ProductsResultsTable
                  title="Текущая готовность ветки"
                  subtitle="Прогретые backend-данные до нового запуска."
                  rows={baselineProducts}
                  loading={overviewLoading}
                />
              </>
            ) : (
              <EmptyState
                title="Выбери ветку или SKU"
                description="Слева можно ограничить импорт категорией, отдельными товарами или оставить весь каталог."
                action={<Button variant="primary" onClick={() => void startImport()} disabled={loading || (!useYandex && !useCompetitors)}>{loading ? "Заполняю…" : "Запустить заполнение"}</Button>}
              />
            )}

            {run ? (
              <>
                <SummaryMetricRow items={runMetrics} />
                <SummaryMetricRow
                  items={[
                    { label: "Описания готовы", value: runOverview.description_ready || 0 },
                    { label: "Фото готовы", value: runOverview.images_ready || 0 },
                    { label: "Характеристики", value: runOverview.features_ready || 0 },
                    { label: "С Маркетом", value: runOverview.with_yandex_data || 0 },
                    { label: "С медиа конкурентов", value: runOverview.with_competitor_media || 0 },
                    { label: "Ждут добивки", value: runOverview.still_missing || 0, accent: true },
                  ]}
                />
                <ProductsResultsTable
                  title="Результат прогона"
                  subtitle="Срез после enrichment из Маркета и конкурентных источников."
                  rows={runProducts}
                  showConflicts
                />
                <section className="card cx-pane">
                  <div className="cx-paneHead">
                    <div>
                      <div className="cx-paneTitle">Конфликты данных</div>
                      <div className="cx-paneSub">Выбери итоговое значение или задай свое. Пока конфликты не закрыты, run считается незавершенным.</div>
                    </div>
                    <Button variant="primary" onClick={() => void saveResolutions()} disabled={saving || unresolved.length === 0}>
                      {saving ? "Сохраняю…" : "Применить выбранные значения"}
                    </Button>
                  </div>
                  <div className="cx-conflicts">
                    {unresolved.map((row) => {
                      const key = `${row.product_id}:${row.field_code}`;
                      return (
                        <div key={key} className="cx-conflictCard">
                          <div className="cx-conflictHead">
                            <div>
                              <div className="cx-conflictTitle">{row.field_name}</div>
                              <div className="cx-conflictMeta">
                                <Link to={`/products/${encodeURIComponent(row.product_id)}`}>{row.product_title}</Link>
                              </div>
                            </div>
                            <Badge tone="pending">{row.kind}</Badge>
                          </div>
                          <div className="cx-candidates">
                            {row.candidates.map((candidate, idx) => (
                              <button
                                key={`${key}:${idx}`}
                                className="cx-candidateBtn"
                                onClick={() => setDrafts((prev) => ({ ...prev, [key]: candidate.value || "" }))}
                              >
                                <span className="cx-candidateLabel">{candidate.label}</span>
                                <span className="cx-candidateValue">{candidate.value || "—"}</span>
                              </button>
                            ))}
                          </div>
                          {row.kind === "description" ? (
                            <Textarea className="pn-input cx-textarea" value={drafts[key] || ""} onChange={(e) => setDrafts((prev) => ({ ...prev, [key]: e.target.value }))} />
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
        )}
        inspector={inspector}
      />
    </div>
  );
}
