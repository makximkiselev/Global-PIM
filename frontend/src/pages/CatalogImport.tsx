import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
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

export default function CatalogImportPage() {
  const [nodes, setNodes] = useState<ExchangeNode[]>([]);
  const [products, setProducts] = useState<ExchangeProduct[]>([]);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);
  const [includeDescendants, setIncludeDescendants] = useState(true);
  const [useYandex, setUseYandex] = useState(true);
  const [useCompetitors, setUseCompetitors] = useState(true);
  const [loading, setLoading] = useState(false);
  const [run, setRun] = useState<ImportRunResp | null>(null);
  const [err, setErr] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const load = async () => {
      const [n, p] = await Promise.all([
        api<{ nodes: ExchangeNode[] }>("/catalog/nodes"),
        api<{ items: ExchangeProduct[] }>("/catalog/products"),
      ]);
      setNodes(n.nodes || []);
      setProducts(p.items || []);
    };
    void load();
  }, []);

  const unresolved = useMemo(() => (run?.conflicts || []).filter((x) => !x.resolved), [run]);
  const selectedScope = useMemo(() => {
    if (!selectedNodeIds.length && !selectedProductIds.length) return "Весь каталог";
    if (selectedProductIds.length && !selectedNodeIds.length) return `Товары: ${selectedProductIds.length}`;
    if (selectedNodeIds.length && !selectedProductIds.length) return `Разделы: ${selectedNodeIds.length}`;
    return `Разделы: ${selectedNodeIds.length} · Товары: ${selectedProductIds.length}`;
  }, [selectedNodeIds, selectedProductIds]);

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
          <h1>Импорт</h1>
          <p>Насыщение товаров контентом. Сначала тянем Яндекс.Маркет, затем добиваем карточку конкурентами и отдельно разбираем расхождения.</p>
        </div>
        <div className="cx-headActions">
          <Link className="btn" to="/products">К товарам</Link>
          <button className="btn primary" onClick={() => void startImport()} disabled={loading || (!useYandex && !useCompetitors)}>
            {loading ? "Импортирую…" : "Запустить импорт"}
          </button>
        </div>
      </div>

      <section className="cx-importTopGrid">
        <div className="card cx-flowCard">
          <div className="cx-flowCardEyebrow">Сценарий</div>
          <div className="cx-flowSteps">
            <div className="cx-flowStep">
              <span className="cx-flowIndex">1</span>
              <div>
                <div className="cx-flowTitle">Выбор каталога</div>
                <div className="cx-flowText">Весь каталог, ветки дерева или конкретные товары.</div>
              </div>
            </div>
            <div className="cx-flowStep">
              <span className="cx-flowIndex">2</span>
              <div>
                <div className="cx-flowTitle">Яндекс.Маркет</div>
                <div className="cx-flowText">Подтягиваем описание, медиа и значения параметров по мастер-шаблону.</div>
              </div>
            </div>
            <div className="cx-flowStep">
              <span className="cx-flowIndex">3</span>
              <div>
                <div className="cx-flowTitle">Конкуренты</div>
                <div className="cx-flowText">Добиваем пропуски. Конфликтующие значения уходим решать отдельно.</div>
              </div>
            </div>
          </div>
        </div>

        <div className="card cx-sourcesCard">
          <div className="cx-flowCardEyebrow">Источники</div>
          <div className="cx-sourceList">
            <label className={`cx-sourceToggle ${useYandex ? "isActive" : ""}`}>
              <input type="checkbox" checked={useYandex} onChange={(e) => setUseYandex(e.target.checked)} />
              <span className="cx-sourceTitle">Яндекс.Маркет</span>
              <span className="cx-sourceMeta">Приоритетный источник для медиа, описания и характеристик.</span>
            </label>
            <label className={`cx-sourceToggle ${useCompetitors ? "isActive" : ""}`}>
              <input type="checkbox" checked={useCompetitors} onChange={(e) => setUseCompetitors(e.target.checked)} />
              <span className="cx-sourceTitle">Конкуренты</span>
              <span className="cx-sourceMeta">Заполняют пробелы после Маркета и формируют варианты для разрешения конфликтов.</span>
            </label>
          </div>
          <div className="cx-selectionBar">
            <div className="cx-selectionLabel">Выбрано для импорта</div>
            <div className="cx-selectionValue">{selectedScope}</div>
          </div>
        </div>
      </section>

      <CatalogExchangePicker
        nodes={nodes}
        products={products}
        selectedNodeIds={selectedNodeIds}
        selectedProductIds={selectedProductIds}
        onSelectedNodeIdsChange={setSelectedNodeIds}
        onSelectedProductIdsChange={setSelectedProductIds}
        includeDescendants={includeDescendants}
        onIncludeDescendantsChange={setIncludeDescendants}
      />

      {err ? <div className="card cx-error">{err}</div> : null}

      {run ? (
        <>
          <section className="cx-summaryGrid">
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Товаров в прогоне</div><div className="cx-summaryValue">{run.count}</div></div>
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Обновлено</div><div className="cx-summaryValue">{run.updated_products}</div></div>
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Яндекс нашел</div><div className="cx-summaryValue">{run.yandex_result?.matched_products || 0}</div></div>
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Конфликтов</div><div className="cx-summaryValue">{unresolved.length}</div></div>
          </section>

          <section className="cx-summaryGrid">
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Описания готовы</div><div className="cx-summaryValue">{run.import_overview?.description_ready || 0}</div></div>
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Фото готовы</div><div className="cx-summaryValue">{run.import_overview?.images_ready || 0}</div></div>
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">С Маркетом</div><div className="cx-summaryValue">{run.import_overview?.with_yandex_data || 0}</div></div>
            <div className="card cx-summaryCard"><div className="cx-summaryLabel">Ждут добивки</div><div className="cx-summaryValue">{run.import_overview?.still_missing || 0}</div></div>
          </section>

          <section className="card cx-pane">
            <div className="cx-paneHead">
              <div>
                <div className="cx-paneTitle">Результат импорта</div>
                <div className="cx-paneSub">Видно, чем товар насытился после Маркета и конкурентов, и какие блоки еще пустые.</div>
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
                  {(run.products || []).map((row) => (
                    <tr key={row.product_id}>
                      <td><Link to={`/products/${encodeURIComponent(row.product_id)}`}>{row.title}</Link></td>
                      <td>{row.source_summary?.filled_features ?? row.filled_features}</td>
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
                <div className="cx-paneSub">Выбери одно из значений или задай собственное финальное значение.</div>
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
