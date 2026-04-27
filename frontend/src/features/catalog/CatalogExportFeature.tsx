import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
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
  batches: Array<{ provider: string; store_id: string; store_title: string; status: string; ready_count: number; count: number }>;
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

export default function CatalogExportFeature() {
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

  useEffect(() => {
    const load = async () => {
      const [n, counts, c] = await Promise.all([
        api<{ nodes: ExchangeNode[] }>("/catalog/nodes"),
        api<{ counts: Record<string, number> }>("/catalog/products/counts"),
        api<ConnectorsResp>("/connectors/status"),
      ]);
      setNodes(n.nodes || []);
      setProductCountsByCategory(counts.counts || {});
      setProviders((c.providers || []).filter((x) => ["yandex_market", "ozon"].includes(x.code)));
    };
    void load();
  }, []);

  const activeTargets = useMemo(() => {
    return Object.entries(selectedProviders)
      .filter(([, on]) => !!on)
      .map(([provider]) => ({ provider, store_ids: selectedStores[provider] || [] }));
  }, [selectedProviders, selectedStores]);

  const selectedScope = useMemo(() => {
    if (!selectedNodeIds.length && !selectedProductIds.length) return "Весь каталог";
    if (selectedProductIds.length && !selectedNodeIds.length) return `Товары: ${selectedProductIds.length}`;
    if (selectedNodeIds.length && !selectedProductIds.length) return `Разделы: ${selectedNodeIds.length}`;
    return `Разделы: ${selectedNodeIds.length} · Товары: ${selectedProductIds.length}`;
  }, [selectedNodeIds, selectedProductIds]);

  const selectedTargetsCount = useMemo(
    () => activeTargets.reduce((sum, item) => sum + Math.max(item.store_ids.length, 1), 0),
    [activeTargets],
  );

  async function startExport() {
    setLoading(true);
    setErr("");
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
          <div className="cx-inspectorRow"><span>Scope</span><strong>{selectedScope}</strong></div>
          <div className="cx-inspectorRow"><span>С дочерними</span><strong>{includeDescendants ? "Да" : "Нет"}</strong></div>
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

            {run ? (
              <>
                <SummaryMetricRow
                  items={[
                    { label: "Товаров в batch", value: run.count },
                    { label: "Подготовлено batch rows", value: run.batches.length },
                    { label: "Целей", value: selectedTargetsCount },
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
                          <th>Всего</th>
                        </tr>
                      </thead>
                      <tbody>
                        {run.batches.map((row, idx) => (
                          <tr key={`${row.provider}:${row.store_id}:${idx}`}>
                            <td>{row.provider === "yandex_market" ? "Я.Маркет" : row.provider === "ozon" ? "OZON" : row.provider}</td>
                            <td>{row.store_title}</td>
                            <td>{row.status}</td>
                            <td>{row.ready_count}</td>
                            <td>{row.count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
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
