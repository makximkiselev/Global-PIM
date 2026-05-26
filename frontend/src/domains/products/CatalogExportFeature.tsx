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
  id?: string;
  created_at?: string;
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
    blockers?: Array<{
      product_id: string;
      offer_id?: string;
      product_title?: string;
      category_id?: string;
      missing: string[];
      missing_details?: ExportMissingDetail[];
    }>;
  }>;
};
type LatestExportRunResp = { ok: boolean; run: ExportRunResp };
type ExportJobResp = {
  ok: boolean;
  job_id: string;
  run_id?: string;
  status: "queued" | "running" | "completed" | "failed" | string;
  phase?: string;
  message?: string;
  summary?: ExportRunResp["summary"];
  error?: string;
  run?: ExportRunResp | null;
};

type ExportBlocker = {
  provider: string;
  providerTitle: string;
  product_id: string;
  offer_id?: string;
  product_title?: string;
  category_id?: string;
  missing: string[];
  missing_details: ExportMissingDetail[];
};

type ExportMissingDetail = {
  code?: string;
  message?: string;
  target?: "competitors" | "media" | "description" | "sources" | "params" | "values" | "product" | string;
  parameter?: string;
  count?: number;
};

type MetricItem = {
  label: string;
  value: number | string;
  accent?: boolean;
};

function defaultExportStoreIds(stores: Store[]): string[] {
  const enabled = stores.filter((store) => store.enabled !== false).map((store) => store.id).filter(Boolean);
  return enabled.length ? enabled : stores.map((store) => store.id).filter(Boolean);
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

function blockerFixHref(blocker: ExportBlocker, reason: string, detail?: ExportMissingDetail): string {
  const category = blocker.category_id || "";
  const product = blocker.product_id || "";
  const target = String(detail?.target || "").trim();
  if (product && target === "competitors") return `/products/${encodeURIComponent(product)}?tab=competitors`;
  if (product && target === "media") return `/products/${encodeURIComponent(product)}?tab=media`;
  if (product && target === "description") return `/products/${encodeURIComponent(product)}?tab=description`;
  if (category && target === "sources") return `/sources?tab=sources&category=${encodeURIComponent(category)}`;
  if (category && target === "params") return `/sources?tab=params&category=${encodeURIComponent(category)}`;
  if (category && target === "values") return `/sources?tab=values&category=${encodeURIComponent(category)}`;
  if (product && target === "product") return `/products/${encodeURIComponent(product)}`;
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
  if (product && lower.includes("конкурент")) {
    return `/products/${encodeURIComponent(product)}?tab=competitors`;
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

function blockerFixLabel(reason: string, detail?: ExportMissingDetail): string {
  const target = String(detail?.target || "").trim();
  if (target === "competitors") return "Открыть конкурентов";
  if (target === "media") return detail?.code === "media_review_required" ? "Проверить медиа" : "Открыть медиа";
  if (target === "description") return "Открыть описание";
  if (target === "sources") return "Открыть категории";
  if (target === "params") return "Открыть параметры";
  if (target === "values") return "Открыть значения";
  if (target === "product") return "Открыть SKU";
  const lower = reason.toLowerCase();
  if (lower.includes("категор")) return "Открыть категории";
  if (lower.includes("маппинг") || lower.includes("сопоставлен") || lower.includes("параметр")) return "Открыть параметры";
  if (lower.includes("значен")) return "Открыть значения";
  if (lower.includes("конкурент")) return "Открыть конкурентов";
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
  const [initialLoading, setInitialLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [run, setRun] = useState<ExportRunResp | null>(null);
  const [err, setErr] = useState("");
  const [preparingMessage, setPreparingMessage] = useState("");
  const [jobId, setJobId] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const initialCategoryId = String(searchParams.get("category") || "").trim();
  const initialProductIds = [
    ...String(searchParams.get("product") || "").split(","),
    ...String(searchParams.get("products") || "").split(","),
  ].map((item) => item.trim()).filter(Boolean);

  useEffect(() => {
    const load = async () => {
      setInitialLoading(true);
      try {
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
          .filter((provider) => (provider.import_stores || []).length > 0);
        setProviders(exportProviders);
        const nextSelectedProviders: Record<string, boolean> = {};
        const nextSelectedStores: Record<string, string[]> = {};
        for (const provider of exportProviders) {
          const storeIds = defaultExportStoreIds(provider.import_stores || []);
          nextSelectedProviders[provider.code] = storeIds.length > 0;
          if (storeIds.length) nextSelectedStores[provider.code] = storeIds;
        }
        setSelectedProviders({
          yandex_market: false,
          ozon: false,
          ...nextSelectedProviders,
        });
        setSelectedStores(nextSelectedStores);
      } catch (e) {
        setErr((e as Error).message || "Не удалось загрузить данные экспорта");
      } finally {
        setInitialLoading(false);
      }
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
  const selectedTargetLabels = useMemo(() => {
    const out: string[] = [];
    for (const target of activeTargets) {
      const provider = providers.find((item) => item.code === target.provider);
      for (const storeId of target.store_ids || []) {
        const store = (provider?.import_stores || []).find((item) => item.id === storeId);
        out.push(`${provider?.title || providerTitle(target.provider)} / ${store?.title || storeId}`);
      }
    }
    return out;
  }, [activeTargets, providers]);
  const selectedSkuEstimate = useMemo(() => {
    if (selectedProductIds.length) return String(selectedProductIds.length);
    if (selectedNodeIds.length) {
      const directCount = selectedNodeIds.reduce((sum, id) => sum + Number(productCountsByCategory[id] || 0), 0);
      if (directCount > 0) return includeDescendants ? `до ${Math.min(50, directCount)}+` : String(Math.min(50, directCount));
    }
    return "до 50";
  }, [includeDescendants, productCountsByCategory, selectedNodeIds, selectedProductIds.length]);
  const broadExportScope = selectedProductIds.length === 0 && (selectedNodeIds.length !== 1 || includeDescendants);
  const totalBlocked = useMemo(
    () => (run?.batches || []).reduce((sum, item) => sum + (item.not_ready_count ?? Math.max(0, item.count - item.ready_count)), 0),
    [run],
  );
  const runIsReady = Boolean(run) && (run?.summary?.blocked_target_items ?? totalBlocked) === 0;
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
          const missingDetails = (blocker.missing_details || []).filter(Boolean);
          byKey.set(key, {
            provider: batch.provider,
            providerTitle: providerTitle(batch.provider),
            product_id: blocker.product_id,
            offer_id: blocker.offer_id,
            product_title: blocker.product_title,
            category_id: blocker.category_id,
            missing,
            missing_details: missingDetails,
          });
        }
      }
    }
    return Array.from(byKey.values()).slice(0, 12);
  }, [run]);

  function requestExport() {
    if (activeTargets.length === 0 || loading) return;
    setConfirmOpen(true);
  }

  function latestRunPath() {
    const params = new URLSearchParams();
    if (selectedNodeIds.length === 1 && !selectedProductIds.length) params.set("category_id", selectedNodeIds[0]);
    if (selectedProductIds.length === 1 && !selectedNodeIds.length) params.set("product_id", selectedProductIds[0]);
    const query = params.toString();
    return `/catalog/exchange/export/latest-run${query ? `?${query}` : ""}`;
  }

  async function waitForLatestRun(startedAt: number, deadlineMs = 180_000): Promise<ExportRunResp | null> {
    const deadline = Date.now() + deadlineMs;
    while (Date.now() < deadline) {
      try {
        const latest = await api<LatestExportRunResp>(latestRunPath());
        const candidate = latest.run;
        const createdAt = Date.parse(candidate?.created_at || "");
        if (!Number.isFinite(createdAt) || createdAt >= startedAt - 2_000) return candidate;
      } catch {
        // The run may still be building. Keep polling until the bounded deadline.
      }
      await new Promise((resolve) => window.setTimeout(resolve, 4_000));
    }
    return null;
  }

  async function waitForExportJob(nextJobId: string, startedAt: number): Promise<ExportRunResp | null> {
    const deadline = Date.now() + 180_000;
    while (Date.now() < deadline) {
      const job = await api<ExportJobResp>(`/catalog/exchange/export/jobs/${encodeURIComponent(nextJobId)}`);
      setJobId(job.job_id || nextJobId);
      setPreparingMessage(job.message || "Export batch считается в фоне.");
      if (job.status === "completed" && job.run) return job.run;
      if (job.status === "failed") {
        throw new Error(job.error || job.message || "Export batch не завершился.");
      }
      await new Promise((resolve) => window.setTimeout(resolve, 3_000));
    }
    return await waitForLatestRun(startedAt, 20_000);
  }

  async function startExport() {
    setConfirmOpen(false);
    setLoading(true);
    setErr("");
    setRun(null);
    setPreparingMessage("");
    setJobId("");
    const runLimit = selectedProductIds.length ? Math.max(1, selectedProductIds.length) : 50;
    const startedAt = Date.now();
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 28_000);
    const payload = {
      selection: {
        mode: selectedNodeIds.length || selectedProductIds.length ? "mixed" : "all",
        node_ids: selectedNodeIds,
        product_ids: selectedProductIds,
        include_descendants: includeDescendants,
      },
      targets: activeTargets,
      limit: runLimit,
    };
    try {
      const job = await api<ExportJobResp>("/catalog/exchange/export/jobs", {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify(payload),
      });
      window.clearTimeout(timeoutId);
      setJobId(job.job_id || "");
      setPreparingMessage(job.message || "Export batch поставлен в очередь.");
      const res = job.run || await waitForExportJob(job.job_id, startedAt);
      if (!res) throw new Error("Export batch еще не вернул сохраненный результат.");
      setRun(res);
      setPreparingMessage("");
    } catch (e) {
      window.clearTimeout(timeoutId);
      setPreparingMessage(jobId ? "Batch еще считается на сервере. Проверяю статус job и сохраненный результат." : "Batch еще считается на сервере. Подхватываю сохраненный результат без перезапуска.");
      const latest = await waitForLatestRun(startedAt);
      if (latest) {
        setRun(latest);
        setErr("");
      } else {
        setErr((e as Error).message || "Ошибка подготовки экспорта");
      }
    } finally {
      setLoading(false);
      setPreparingMessage("");
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
            <div className="cx-inspectorRow"><span>Run ID</span><strong>{run.run_id || run.id}</strong></div>
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
              <Button variant="primary" onClick={requestExport} disabled={loading || activeTargets.length === 0}>
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
            dataLoading={initialLoading}
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
                  <Badge tone={initialLoading ? "pending" : activeTargets.length ? "active" : "neutral"}>
                    {initialLoading ? "Загружаю каналы" : activeTargets.length ? `${activeTargets.length} канала` : "Нет каналов"}
                  </Badge>
                  <Button variant="primary" onClick={requestExport} disabled={initialLoading || loading || activeTargets.length === 0}>
                    {loading ? "Готовлю…" : "Подготовить"}
                  </Button>
                </div>
              )}
            >
              <div className="cx-targetsBoard">
                {initialLoading ? (
                  <div className="cx-empty">Загружаю магазины и каналы экспорта…</div>
                ) : providers.map((provider) => {
                  const checked = !!selectedProviders[provider.code];
                  const stores = provider.import_stores || [];
                  const current = new Set(selectedStores[provider.code] || []);
                  return (
                    <div key={provider.code} className="cx-targetCard">
                      <label className="cx-inlineCheck">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => {
                            const enabled = e.target.checked;
                            setSelectedProviders((prev) => ({ ...prev, [provider.code]: enabled }));
                            if (enabled && !(selectedStores[provider.code] || []).length) {
                              const storeIds = defaultExportStoreIds(stores);
                              if (storeIds.length) setSelectedStores((prev) => ({ ...prev, [provider.code]: storeIds }));
                            }
                          }}
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

            {broadExportScope ? (
              <section className="card cx-exportScopeGuard">
                <div>
                  <div className="cx-paneTitle">Широкая область проверки</div>
                  <div className="cx-paneSub">
                    Для массовой области SmartPim готовит контрольный batch до 50 SKU. Для финальной отправки выберите конкретные SKU или узкую категорию без дочерних веток.
                  </div>
                </div>
                <Badge tone="pending">guardrail</Badge>
              </section>
            ) : null}

            {loading && !run ? (
              <section className="card cx-exportPreparing">
                <div className="cx-exportPreparingPulse" aria-hidden="true" />
                <div>
                  <div className="cx-paneTitle">Готовлю выгрузку</div>
                  <div className="cx-paneSub">
                    {preparingMessage || (selectedProductIds.length
                      ? "Проверяю только выбранные SKU: медиа, описание, категории, параметры и значения для выбранных площадок."
                      : "Проверяю первые 50 SKU в выбранной области: медиа, описание, категории, параметры и значения для выбранных площадок.")}
                  </div>
                </div>
                <div className="cx-exportPreparingMeta">
                  <span>Область: <b>{selectedScope}</b></span>
                  {jobId ? <span>Job: <b>{jobId}</b></span> : null}
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

                {runIsReady ? (
                  <section className="card cx-exportReady">
                    <div>
                      <div className="cx-paneTitle">Batch готов к выгрузке</div>
                      <div className="cx-paneSub">
                        Проверка прошла по выбранной области и выбранным магазинам. SmartPim подготовил данные карточки для выбранных площадок.
                      </div>
                    </div>
                    <Badge tone="active">Можно переходить к отправке</Badge>
                  </section>
                ) : null}

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
                              {blocker.missing.slice(0, 4).map((reason, index) => {
                                const detail = blocker.missing_details[index];
                                return <li key={reason}>{detail?.message || reason}</li>;
                              })}
                            </ul>
                            <div className="cx-exportBlockerActions">
                              <Link className="btn" to={`/products/${encodeURIComponent(blocker.product_id)}`}>Открыть SKU</Link>
                              {blocker.missing.slice(0, 4).map((reason, index) => {
                                const detail = blocker.missing_details[index];
                                return (
                                <Link
                                  key={`${reason}:${index}`}
                                  className={`btn ${index === 0 ? "btn-primary" : ""}`}
                                  to={blockerFixHref(blocker, reason, detail)}
                                  title={reason}
                                >
                                  {blockerFixLabel(reason, detail)}
                                </Link>
                                );
                              })}
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
                action={<Button variant="primary" onClick={requestExport} disabled={loading || activeTargets.length === 0}>{loading ? "Готовлю…" : "Подготовить экспорт"}</Button>}
              />
            )}
          </div>
        )}
        inspector={inspector}
      />

      {confirmOpen ? (
        <div className="cx-confirmOverlay" role="dialog" aria-modal="true" aria-label="Подтверждение экспорта">
          <div className="cx-confirmCard">
            <div className="cx-confirmHead">
              <div>
                <span>Проверка перед экспортом</span>
                <strong>Подтвердите область и магазины</strong>
              </div>
              <button className="btn" type="button" onClick={() => setConfirmOpen(false)}>Закрыть</button>
            </div>
            <div className="cx-confirmGrid">
              <div>
                <span>Область</span>
                <strong>{selectedScope}</strong>
              </div>
              <div>
                <span>SKU</span>
                <strong>{selectedSkuEstimate}</strong>
              </div>
              <div>
                <span>Целей</span>
                <strong>{selectedTargetsCount}</strong>
              </div>
            </div>
            <div className="cx-confirmTargets">
              {selectedTargetLabels.map((label) => <span key={label}>{label}</span>)}
            </div>
            <div className="cx-confirmWarning">
              {broadExportScope
                ? "Это широкая проверка до 50 SKU. Для финальной отправки лучше выбрать конкретные SKU или узкую категорию."
                : "Сейчас будет только batch-подготовка и проверка данных по выбранным магазинам. Проверь список целей перед запуском."}
            </div>
            <div className="cx-confirmActions">
              <Button onClick={() => setConfirmOpen(false)}>Отмена</Button>
              <Button variant="primary" onClick={() => void startExport()} disabled={loading || activeTargets.length === 0}>
                {loading ? "Готовлю…" : "Подтвердить и подготовить"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
