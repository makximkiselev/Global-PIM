import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import CatalogExchangePicker, { type ExchangeNode, type ExchangeProduct } from "../components/CatalogExchangePicker";
import { api } from "../lib/api";
import "../styles/catalog-exchange.css";

type Store = { id: string; title: string; enabled?: boolean };
type ProviderRow = { code: string; title: string; import_stores?: Store[] };
type ConnectorsResp = { providers?: ProviderRow[] };
type ExportRunResp = {
  ok: boolean;
  run_id: string;
  count: number;
  batches: Array<{ provider: string; store_id: string; store_title: string; status: string; ready_count: number; count: number }>;
};

export default function CatalogExportPage() {
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

  return (
    <div className="cx-page">
      <div className="cx-head">
        <div>
          <h1>Экспорт</h1>
          <p>Выбор каталога, площадок и магазинов. Экспорт подготавливается последовательно по каждому каналу.</p>
        </div>
        <div className="cx-headActions">
          <Link className="btn" to="/products">К товарам</Link>
          <button className="btn primary" onClick={() => void startExport()} disabled={loading || activeTargets.length === 0}>
            {loading ? "Готовлю…" : "Подготовить экспорт"}
          </button>
        </div>
      </div>

      <section className="card cx-controls cx-targets">
        {providers.map((provider) => {
          const checked = !!selectedProviders[provider.code];
          const stores = provider.import_stores || [];
          const current = new Set(selectedStores[provider.code] || []);
          return (
            <div key={provider.code} className="cx-targetCard">
              <label className="cx-inlineCheck"><input type="checkbox" checked={checked} onChange={(e) => setSelectedProviders((prev) => ({ ...prev, [provider.code]: e.target.checked }))} /><span>{provider.title}</span></label>
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

      {run ? (
        <section className="card cx-pane">
          <div className="cx-paneHead">
            <div>
              <div className="cx-paneTitle">Очередь экспорта</div>
              <div className="cx-paneSub">Сейчас подготовка работает полноценно для Яндекс.Маркета. OZON в очереди уже заведён, но отправка еще не подключена.</div>
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
      ) : null}
    </div>
  );
}
