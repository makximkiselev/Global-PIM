import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useSearchParams } from "react-router-dom";
import CatalogExchangePicker, { type ExchangeNode } from "../../components/CatalogExchangePicker";
import DataToolbar from "../../components/data/DataToolbar";
import InspectorPanel from "../../components/data/InspectorPanel";
import WorkspaceFrame from "../../components/layout/WorkspaceFrame";
import { api } from "../../lib/api";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import EmptyState from "../../components/ui/EmptyState";
import PageHeader from "../../components/ui/PageHeader";
import "../../styles/catalog-exchange.css";

type Store = { id: string; title: string; enabled?: boolean };
type ProviderRow = { code: string; title: string; import_stores?: Store[] };
type ConnectorsResp = { providers?: ProviderRow[] };
type ExportRunResp = {
  ok: boolean;
  run_id: string;
  count: number;
  summary?: {
    product_count?: number;
    target_count?: number;
    batch_count?: number;
    ready_batches?: number;
    blocked_batches?: number;
    ready_target_items?: number;
    blocked_target_items?: number;
    blockers_count?: number;
    status?: "ready" | "blocked" | string;
  };
  batches: Array<{
    provider: string;
    store_id: string;
    store_title: string;
    status: "ready" | "blocked" | string;
    ready_count: number;
    not_ready_count?: number;
    blockers_count?: number;
    count: number;
    blockers?: Array<{ product_id: string; offer_id?: string; product_title?: string; category_id?: string; missing: string[] }>;
  }>;
};

type ExportBlocker = {
  provider: string;
  providerTitle: string;
  product_id: string;
  offer_id?: string;
  product_title?: string;
  category_id?: string;
  missing: string[];
};

type MetricItem = {
  label: string;
  value: number | string;
  accent?: boolean;
};

const EXPORT_PROVIDER_CODE = "yandex_market";
const EXPORT_STORE_TITLE = "GT USD";

function isAllowedExportStore(store: Store): boolean {
  return String(store.title || "").trim().toLowerCase() === EXPORT_STORE_TITLE.toLowerCase();
}

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

function providerTitle(provider: string): string {
  if (provider === "yandex_market") return "Я.Маркет";
  if (provider === "ozon") return "OZON";
  return provider;
}

function blockerFixHref(blocker: ExportBlocker, reason: string): string {
  const category = blocker.category_id || "";
  const product = blocker.product_id || "";
  const lower = reason.toLowerCase();
  if (category && (lower.includes("категор") || lower.includes("marketcategoryid"))) {
    return `/sources?tab=sources&category=${encodeURIComponent(category)}`;
  }
  if (category && (lower.includes("маппинг") || lower.includes("сопоставлен") || lower.includes("параметр"))) {
    return `/sources?tab=params&category=${encodeURIComponent(category)}`;
  }
  if (category && (lower.includes("значен") || lower.includes("dictionary"))) {
    return `/sources?tab=values&category=${encodeURIComponent(category)}`;
  }
  if (product && (lower.includes("изображ") || lower.includes("pictures") || lower.includes("медиа"))) {
    return `/products/${encodeURIComponent(product)}?tab=media`;
  }
  if (product && lower.includes("описание")) {
    return `/products/${encodeURIComponent(product)}?tab=description`;
  }
  if (product) return `/products/${encodeURIComponent(product)}`;
  return category ? `/sources?tab=params&category=${encodeURIComponent(category)}` : "/catalog/exchange?tab=export";
}

function blockerFixLabel(reason: string): string {
  const lower = reason.toLowerCase();
  if (lower.includes("категор")) return "Открыть категории";
  if (lower.includes("маппинг") || lower.includes("сопоставлен") || lower.includes("параметр")) return "Открыть параметры";
  if (lower.includes("значен")) return "Открыть значения";
  if (lower.includes("изображ") || lower.includes("pictures") || lower.includes("медиа")) return "Открыть медиа";
  if (lower.includes("описание")) return "Открыть описание";
  return "Открыть место исправления";
}

export default function CatalogExportFeature({ embedded = false }: { embedded?: boolean } = {}) {
  const [searchParams] = useSearchParams();
  const [nodes, setNodes] = useState<ExchangeNode[]>([]);
  const [productCountsByCategory, setProductCountsByCategory] = useState<Record<string, number>>({});
  const [providers, setProviders] = useState<ProviderRow[]>([]);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);
  const [includeDescendants, setIncludeDescendants] = useState(true);
  const [selectedProviders, setSelectedProviders] = useState<Record<string, boolean>>({ yandex_market: true, ozon: false });
  const [selectedStores, setSelectedStores] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(false);
  const [run, setRun] = useState<ExportRunResp | null>(null);
  const [err, setErr] = useState("");
  const initialCategoryId = String(searchParams.get("category") || "").trim();
  const initialProductIds = [
    ...String(searchParams.get("product") || "").split(","),
    ...String(searchParams.get("products") || "").split(","),
  ].map((item) => item.trim()).filter(Boolean);

  useEffect(() => {
    const load = async () => {
      const [n, counts, c] = await Promise.all([
        api<{ nodes: ExchangeNode[] }>("/catalog/nodes"),
        api<{ counts: Record<string, number> }>("/catalog/products/counts"),
        api<ConnectorsResp>("/connectors/status"),
      ]);
      setNodes(n.nodes || []);
      setProductCountsByCategory(counts.counts || {});
      const exportProviders = (c.providers || [])
        .filter((x) => ["yandex_market", "ozon"].includes(x.code))
        .map((provider) => ({
          ...provider,
          import_stores: provider.import_stores || [],
        }))
        .filter((provider) => provider.code !== EXPORT_PROVIDER_CODE || (provider.import_stores || []).some(isAllowedExportStore));
      setProviders(exportProviders);
      const gtUsd = exportProviders
        .find((provider) => provider.code === EXPORT_PROVIDER_CODE)
        ?.import_stores?.find(isAllowedExportStore)?.id;
      const ozonStores = exportProviders.find((provider) => provider.code === "ozon")?.import_stores || [];
      const defaultOzonStoreIds = ozonStores.filter((store) => store.enabled !== false).map((store) => store.id).filter(Boolean);
      setSelectedProviders({
        [EXPORT_PROVIDER_CODE]: Boolean(gtUsd),
        ozon: defaultOzonStoreIds.length > 0,
      });
      setSelectedStores({
        ...(gtUsd ? { [EXPORT_PROVIDER_CODE]: [gtUsd] } : {}),
        ...(defaultOzonStoreIds.length ? { ozon: defaultOzonStoreIds } : {}),
      });
    };
    void load();
  }, []);

  useEffect(() => {
    if (initialProductIds.length) return;
    if (!initialCategoryId || !nodes.some((node) => node.id === initialCategoryId)) return;
    setSelectedNodeIds((prev) => (prev.length === 1 && prev[0] === initialCategoryId ? prev : [initialCategoryId]));
  }, [initialCategoryId, initialProductIds.length, nodes]);

  useEffect(() => {
    if (!initialProductIds.length) return;
    setSelectedNodeIds([]);
    setIncludeDescendants(false);
    setSelectedProductIds((prev) => {
      const next = Array.from(new Set(initialProductIds));
      return prev.length === next.length && prev.every((id, index) => id === next[index]) ? prev : next;
    });
  }, [initialProductIds.join(",")]);

  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);

  const activeTargets = useMemo(() => {
    return Object.entries(selectedProviders)
      .filter(([, on]) => !!on)
      .map(([provider]) => ({ provider, store_ids: selectedStores[provider] || [] }))
      .filter((target) => target.store_ids.length > 0);
  }, [selectedProviders, selectedStores]);

  const selectedScope = useMemo(() => {
    if (!selectedNodeIds.length && !selectedProductIds.length) return "Весь каталог";
    if (selectedProductIds.length && !selectedNodeIds.length) return `Товары: ${selectedProductIds.length}`;
    if (selectedNodeIds.length === 1 && !selectedProductIds.length) return nodeById.get(selectedNodeIds[0])?.name || "Выбранная категория";
    if (selectedNodeIds.length && !selectedProductIds.length) return `Разделы: ${selectedNodeIds.length}`;
    return `Разделы: ${selectedNodeIds.length} · Товары: ${selectedProductIds.length}`;
  }, [nodeById, selectedNodeIds, selectedProductIds]);

  const selectedTargetsCount = useMemo(
    () => activeTargets.reduce((sum, item) => sum + item.store_ids.length, 0),
    [activeTargets],
  );
  const totalBlocked = useMemo(
    () => (run?.batches || []).reduce((sum, item) => sum + (item.not_ready_count ?? Math.max(0, item.count - item.ready_count)), 0),
    [run],
  );
  const exportBlockers = useMemo<ExportBlocker[]>(() => {
    const byKey = new Map<string, ExportBlocker>();
    for (const batch of run?.batches || []) {
      for (const blocker of batch.blockers || []) {
        const missing = (blocker.missing || []).filter(Boolean);
        if (!missing.length) continue;
        const key = [
          batch.provider,
          blocker.product_id,
          blocker.offer_id || "",
          missing.join("|"),
        ].join("::");
        if (!byKey.has(key)) {
          byKey.set(key, {
            provider: batch.provider,
            providerTitle: providerTitle(batch.provider),
            product_id: blocker.product_id,
            offer_id: blocker.offer_id,
            product_title: blocker.product_title,
            category_id: blocker.category_id,
            missing,
          });
        }
      }
    }
    return Array.from(byKey.values()).slice(0, 12);
  }, [run]);

  async function startExport() {
    setLoading(true);
    setErr("");
    const runLimit = selectedProductIds.length ? Math.max(1, selectedProductIds.length) : 50;
    try {
      const res = await api<ExportRunResp>("/catalog/exchange/export/run", {
        method: "POST",
        body: JSON.stringify({
          selection: {
            mode: selectedNodeIds.length || selectedProductIds.length ? "mixed" : "all",
            node_ids: selectedNodeIds,
            product_ids: selectedProductIds,
            include_descendants: includeDescendants,
          },
          targets: activeTargets,
          limit: runLimit,
        }),
      });
      setRun(res);
    } catch (e) {
      setErr((e as Error).message || "Ошибка подготовки экспорта");
    } finally {
      setLoading(false);
    }
  }

  const inspector = (
    <div className="cx-workspaceInspector">
      <InspectorPanel title="Область" subtitle="Что уходит в выгрузку">
        <div className="cx-inspectorList">
          <div className="cx-inspectorRow"><span>Выбрано</span><strong>{selectedScope}</strong></div>
          {selectedNodeIds.length ? (
            <div className="cx-inspectorRow"><span>Глубина</span><strong>{includeDescendants ? "Вся ветка" : "Только категория"}</strong></div>
          ) : null}
          <div className="cx-inspectorRow"><span>Целей</span><strong>{selectedTargetsCount}</strong></div>
        </div>
      </InspectorPanel>

      <InspectorPanel title="Каналы" subtitle="Что сейчас выбрано для batch run">
        <div className="cx-inspectorStack">
          {providers.map((provider) => {
            const stores = provider.import_stores || [];
            const current = selectedStores[provider.code] || [];
            return (
              <div key={provider.code} className="cx-sourceInspectorCard">
                <div>
                  <strong>{provider.title}</strong>
                  <p>{current.length ? `${current.length} магазинов выбрано` : `${stores.length} магазинов доступно`}</p>
                </div>
                <Badge tone={selectedProviders[provider.code] ? "active" : "neutral"}>
                  {selectedProviders[provider.code] ? "Включен" : "Выключен"}
                </Badge>
              </div>
            );
          })}
        </div>
      </InspectorPanel>

      {run ? (
        <InspectorPanel title="Последний batch" subtitle="Итог текущей подготовки">
          <div className="cx-inspectorList">
            <div className="cx-inspectorRow"><span>Run ID</span><strong>{run.run_id}</strong></div>
            <div className="cx-inspectorRow"><span>Товаров</span><strong>{run.count}</strong></div>
            <div className="cx-inspectorRow"><span>Batch rows</span><strong>{run.batches.length}</strong></div>
          </div>
        </InspectorPanel>
      ) : null}
    </div>
  );

  return (
    <div className="cx-page cx-pageModern">
      {!embedded ? (
        <PageHeader
          title="Экспорт"
          subtitle="Собирай batch-выгрузку по выбранным каналам и магазинам из той же рабочей области, где отбирается каталог."
          actions={(
            <>
              <Link className="btn" to="/products">К товарам</Link>
              <Button variant="primary" onClick={() => void startExport()} disabled={loading || activeTargets.length === 0}>
                {loading ? "Готовлю…" : "Подготовить экспорт"}
              </Button>
            </>
          )}
        />
      ) : null}

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
              title="Цели экспорта"
              subtitle="Выбирай площадки и конкретные магазины. Экспорт запускается как batch-подготовка по текущей области."
              className="cx-workspaceToolbar"
              actions={(
                <div className="cx-toolbarActions">
                  <Badge tone={activeTargets.length ? "active" : "neutral"}>
                    {activeTargets.length ? `${activeTargets.length} канала` : "Нет каналов"}
                  </Badge>
                  <Button variant="primary" onClick={() => void startExport()} disabled={loading || activeTargets.length === 0}>
                    {loading ? "Готовлю…" : "Подготовить"}
                  </Button>
                </div>
              )}
            >
              <div className="cx-targetsBoard">
                {providers.map((provider) => {
                  const checked = !!selectedProviders[provider.code];
                  const stores = provider.import_stores || [];
                  const current = new Set(selectedStores[provider.code] || []);
                  return (
                    <div key={provider.code} className="cx-targetCard">
                      <label className="cx-inlineCheck">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => setSelectedProviders((prev) => ({ ...prev, [provider.code]: e.target.checked }))}
                        />
                        <span>{provider.title}</span>
                      </label>
                      <div className="cx-storeChips">
                        {stores.map((store) => (
                          <label key={store.id} className={`cx-storeChip ${current.has(store.id) ? "isActive" : ""}`}>
                            <input
                              type="checkbox"
                              checked={current.has(store.id)}
                              onChange={(e) => {
                                const next = new Set(selectedStores[provider.code] || []);
                                if (e.target.checked) next.add(store.id);
                                else next.delete(store.id);
                                setSelectedStores((prev) => ({ ...prev, [provider.code]: Array.from(next) }));
                              }}
                            />
                            <span>{store.title}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </DataToolbar>

            <SummaryMetricRow
              items={[
                { label: "Выбранная область", value: selectedScope },
                { label: "Каналов", value: activeTargets.length },
                { label: "Целей", value: selectedTargetsCount },
              ]}
            />

            {loading && !run ? (
              <section className="card cx-exportPreparing">
                <div className="cx-exportPreparingPulse" aria-hidden="true" />
                <div>
                  <div className="cx-paneTitle">Готовлю выгрузку</div>
                  <div className="cx-paneSub">
                    {selectedProductIds.length
                      ? "Проверяю только выбранные SKU: медиа, описание, категории, параметры и значения для выбранных площадок."
                      : "Проверяю первые 50 SKU в выбранной области: медиа, описание, категории, параметры и значения для выбранных площадок."}
                  </div>
                </div>
                <div className="cx-exportPreparingMeta">
                  <span>Область: <b>{selectedScope}</b></span>
                  <span>Каналов: <b>{activeTargets.length}</b></span>
                  <span>Целей: <b>{selectedTargetsCount}</b></span>
                </div>
              </section>
            ) : run ? (
              <>
                <SummaryMetricRow
                  items={[
                    { label: "SKU", value: run.summary?.product_count ?? run.count },
                    { label: "Целей выгрузки", value: run.summary?.target_count ?? run.batches.length },
                    { label: "Готовых строк", value: run.summary?.ready_target_items ?? 0 },
                    { label: "Блокеров", value: run.summary?.blocked_target_items ?? totalBlocked, accent: (run.summary?.blocked_target_items ?? totalBlocked) > 0 },
                  ]}
                />

                <section className="card cx-pane">
                  <div className="cx-paneHead">
                    <div>
                      <div className="cx-paneTitle">Очередь экспорта</div>
                      <div className="cx-paneSub">Видно, по каким каналам и магазинам собран batch и сколько SKU готовы к выгрузке.</div>
                    </div>
                  </div>
                  <div className="cx-resultsTableWrap">
                    <table className="cx-resultsTable">
                      <thead>
                        <tr>
                          <th>Площадка</th>
                          <th>Магазин</th>
                          <th>Статус</th>
                          <th>Готово</th>
                          <th>Блокеры</th>
                          <th>Всего</th>
                        </tr>
                      </thead>
                      <tbody>
                        {run.batches.map((row, idx) => (
                          <tr key={`${row.provider}:${row.store_id}:${idx}`}>
                            <td>{row.provider === "yandex_market" ? "Я.Маркет" : row.provider === "ozon" ? "OZON" : row.provider}</td>
                            <td>{row.store_title}</td>
                            <td>
                              <Badge tone={row.status === "ready" ? "active" : "pending"}>
                                {row.status === "ready" ? "Готово" : "Есть блокеры"}
                              </Badge>
                            </td>
                            <td>{row.ready_count}</td>
                            <td>{row.not_ready_count ?? Math.max(0, row.count - row.ready_count)}</td>
                            <td>{row.count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                {exportBlockers.length > 0 ? (
                  <section className="card cx-pane">
                    <div className="cx-paneHead">
                      <div>
                        <div className="cx-paneTitle">Что мешает выгрузке</div>
                        <div className="cx-paneSub">Уникальные SKU с причинами и прямыми переходами к месту исправления.</div>
                      </div>
                    </div>
                    <div className="cx-exportBlockers">
                      {exportBlockers.map((blocker) => (
                          <div key={`${blocker.provider}:${blocker.product_id}:${blocker.offer_id || ""}:${blocker.missing.join("|")}`} className="cx-exportBlocker">
                            <div className="cx-exportBlockerHead">
                              <strong>{blocker.providerTitle}</strong>
                              <span>{blocker.offer_id ? `SKU GT ${blocker.offer_id}` : blocker.product_id}</span>
                            </div>
                            <div className="cx-exportBlockerProduct">
                              <Link to={`/products/${encodeURIComponent(blocker.product_id)}`}>{blocker.product_title || blocker.product_id}</Link>
                            </div>
                            <ul>
                              {blocker.missing.slice(0, 4).map((reason) => <li key={reason}>{reason}</li>)}
                            </ul>
                            <div className="cx-exportBlockerActions">
                              <Link className="btn" to={`/products/${encodeURIComponent(blocker.product_id)}`}>Открыть SKU</Link>
                              <Link className="btn btn-primary" to={blockerFixHref(blocker, blocker.missing[0] || "")}>{blockerFixLabel(blocker.missing[0] || "")}</Link>
                            </div>
                          </div>
                      ))}
                    </div>
                  </section>
                ) : null}
              </>
            ) : (
              <EmptyState
                title="Выбери каналы и магазины"
                description="Сначала задай цели экспорта, затем запусти batch-подготовку по текущей области каталога."
                action={<Button variant="primary" onClick={() => void startExport()} disabled={loading || activeTargets.length === 0}>{loading ? "Готовлю…" : "Подготовить экспорт"}</Button>}
              />
            )}
          </div>
        )}
        inspector={inspector}
      />
    </div>
  );
}
