import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useSearchParams } from "react-router-dom";
import { useOrgPath } from "../../app/orgRoutes";
import CatalogExchangePicker, { type ExchangeNode } from "../../components/CatalogExchangePicker";
import DataToolbar from "../../components/data/DataToolbar";
import InspectorPanel from "../../components/data/InspectorPanel";
import WorkspaceFrame from "../../components/layout/WorkspaceFrame";
import { api } from "../../lib/api";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import "../../styles/catalog-exchange.css";

type Store = { id: string; title: string; enabled?: boolean; export_enabled?: boolean };
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
type ExportPackageResp = {
  ok: boolean;
  package: {
    version: number;
    run_id: string;
    created_at?: string;
    status: "ready" | "partial" | string;
    summary?: {
      batch_count?: number;
      ready_items?: number;
      blocked_items?: number;
      warnings_count?: number;
    };
    warnings?: Array<{
      provider?: string;
      store_id?: string;
      store_title?: string;
      blocked_items?: number;
    }>;
    batches?: Array<{
      provider: string;
      store_id: string;
      store_title: string;
      status: string;
      ready_count: number;
      blocked_count: number;
      items: Array<{ product_id: string; offer_id?: string; payload: Record<string, unknown> }>;
    }>;
  };
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
  target?: "competitors" | "media" | "description" | "sources" | "params" | "values" | "product" | "import" | string;
  parameter?: string;
  count?: number;
};

type MetricItem = {
  label: string;
  value: number | string;
  hint?: string;
  accent?: boolean;
};

function SummaryMetricRow({ items }: { items: MetricItem[] }) {
  return (
    <section className="cx-summaryStrip card">
      {items.map((item) => (
        <div key={item.label} className={`cx-stripMetric${item.accent ? " isAlert" : ""}`}>
          <span>{item.label}</span>
          <b>{item.value}</b>
          {item.hint ? <em>{item.hint}</em> : null}
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

function storeExportSelected(store: Store): boolean {
  return store.enabled !== false && store.export_enabled === true;
}

function blockerFixHref(blocker: ExportBlocker, reason: string, detail?: ExportMissingDetail): string {
  const category = blocker.category_id || "";
  const product = blocker.product_id || "";
  const target = String(detail?.target || "").trim();
  const sourcesHref = (tab: "sources" | "params" | "values") => {
    const params = new URLSearchParams();
    params.set("tab", tab);
    if (category) params.set("category", category);
    if (product) params.set("product", product);
    return `/sources?${params.toString()}`;
  };
  if (category && detail?.code === "parameter_mapping_required") return `/templates/${encodeURIComponent(category)}`;
  if (product && target === "competitors") return `/products/${encodeURIComponent(product)}?tab=sources`;
  if (product && target === "media") return `/products/${encodeURIComponent(product)}?tab=media`;
  if (product && target === "description") return `/products/${encodeURIComponent(product)}?tab=description`;
  if (target === "import") {
    const params = new URLSearchParams({ tab: "import" });
    if (product) params.set("product", product);
    if (category) params.set("category", category);
    return `/catalog/exchange?${params.toString()}`;
  }
  if (category && target === "sources") return sourcesHref("sources");
  if (category && target === "params") return sourcesHref("params");
  if (category && target === "values") return sourcesHref("values");
  if (product && target === "product") return `/products/${encodeURIComponent(product)}`;
  const lower = reason.toLowerCase();
  if (category && (lower.includes("категор") || lower.includes("marketcategoryid"))) {
    return sourcesHref("sources");
  }
  if (category && (lower.includes("маппинг") || lower.includes("сопоставлен") || lower.includes("параметр"))) {
    return sourcesHref("params");
  }
  if (category && (lower.includes("значен") || lower.includes("dictionary"))) {
    return sourcesHref("values");
  }
  if (product && lower.includes("конкурент")) {
    return `/products/${encodeURIComponent(product)}?tab=sources`;
  }
  if (product && (lower.includes("изображ") || lower.includes("pictures") || lower.includes("медиа"))) {
    return `/products/${encodeURIComponent(product)}?tab=media`;
  }
  if (product && lower.includes("описание")) {
    return `/products/${encodeURIComponent(product)}?tab=description`;
  }
  if (product) return `/products/${encodeURIComponent(product)}`;
  return category ? sourcesHref("params") : "/catalog/exchange?tab=export";
}

function blockerFixLabel(reason: string, detail?: ExportMissingDetail): string {
  const target = String(detail?.target || "").trim();
  if (detail?.code === "parameter_mapping_required") return "Собрать модель категории";
  if (target === "competitors") return "Открыть конкурентов";
  if (target === "media") return detail?.code === "media_review_required" ? "Проверить медиа" : "Открыть медиа";
  if (target === "description") return "Открыть описание";
  if (target === "import") return "Импортировать фото";
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
  const orgPath = useOrgPath();
  const [nodes, setNodes] = useState<ExchangeNode[]>([]);
  const [productCountsByCategory, setProductCountsByCategory] = useState<Record<string, number>>({});
  const [providers, setProviders] = useState<ProviderRow[]>([]);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);
  const [includeDescendants, setIncludeDescendants] = useState(true);
  const [selectedProviders, setSelectedProviders] = useState<Record<string, boolean>>({});
  const [selectedStores, setSelectedStores] = useState<Record<string, string[]>>({});
  const [savingStoreIds, setSavingStoreIds] = useState<Record<string, boolean>>({});
  const [initialLoading, setInitialLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [run, setRun] = useState<ExportRunResp | null>(null);
  const [err, setErr] = useState("");
  const [preparingMessage, setPreparingMessage] = useState("");
  const [jobId, setJobId] = useState("");
  const [packageLoading, setPackageLoading] = useState(false);
  const [exportPackage, setExportPackage] = useState<ExportPackageResp["package"] | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [broadScopeConfirmed, setBroadScopeConfirmed] = useState(false);
  const initialCategoryId = String(searchParams.get("category") || "").trim();
  const initialProductIds = [
    ...String(searchParams.get("product") || "").split(","),
    ...String(searchParams.get("products") || "").split(","),
  ].map((item) => item.trim()).filter(Boolean);

  function applyConnectorsResponse(response: ConnectorsResp) {
    const exportProviders = (response.providers || [])
      .filter((x) => ["yandex_market", "ozon"].includes(x.code))
      .map((provider) => ({
        ...provider,
        import_stores: provider.import_stores || [],
      }));
    setProviders(exportProviders);
    setSelectedProviders(Object.fromEntries(exportProviders.map((provider) => [
      provider.code,
      (provider.import_stores || []).some(storeExportSelected),
    ])));
    setSelectedStores(Object.fromEntries(exportProviders.map((provider) => [
      provider.code,
      (provider.import_stores || [])
        .filter(storeExportSelected)
        .map((store) => store.id),
    ])));
  }

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
        applyConnectorsResponse(c);
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
  const exportBadgeText = initialLoading
    ? "Загружаю каналы"
    : providers.length === 0
      ? "Нет магазинов"
    : activeTargets.length
      ? `${activeTargets.length} канала`
      : "0 магазинов";
  const exportBadgeTone = initialLoading ? "pending" : activeTargets.length ? "active" : "neutral";
  const selectedCategoryForLinks = selectedNodeIds[0] || initialCategoryId;
  const sourcesCategoryHref = selectedCategoryForLinks
    ? `/sources?tab=sources&category=${encodeURIComponent(selectedCategoryForLinks)}`
    : "/sources?tab=sources";
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
  const storesAvailableCount = useMemo(
    () => providers.reduce((sum, provider) => sum + (provider.import_stores || []).filter((store) => store.enabled !== false).length, 0),
    [providers],
  );
  const selectedSkuEstimate = useMemo(() => {
    if (selectedProductIds.length) return String(selectedProductIds.length);
    if (selectedNodeIds.length) {
      const directCount = selectedNodeIds.reduce((sum, id) => sum + Number(productCountsByCategory[id] || 0), 0);
      if (directCount > 0) return includeDescendants ? `до ${Math.min(50, directCount)}+` : String(Math.min(50, directCount));
    }
    return "до 50";
  }, [includeDescendants, productCountsByCategory, selectedNodeIds, selectedProductIds.length]);
  const targetSetupItems = [
    {
      label: "Область",
      value: selectedScope,
      state: selectedProductIds.length || selectedNodeIds.length ? "ready" : "pending",
      hint: selectedProductIds.length ? "точный список SKU" : selectedNodeIds.length ? "категория каталога" : "по умолчанию весь каталог",
    },
    {
      label: "Магазины",
      value: `${selectedTargetsCount}/${storesAvailableCount || 0}`,
      state: selectedTargetsCount ? "ready" : "blocked",
      hint: storesAvailableCount ? "нужно отметить цель" : "нет доступных целей",
    },
    {
      label: "Проверка",
      value: selectedSkuEstimate,
      state: activeTargets.length ? "ready" : "pending",
      hint: activeTargets.length ? "можно собрать пакет" : "ждет магазины",
    },
  ];
  const readyForPrepare = activeTargets.length > 0;
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
    setBroadScopeConfirmed(false);
    setConfirmOpen(true);
  }

  async function updateStoreExport(providerCode: string, storeId: string, exportEnabled: boolean) {
    const savingKey = `${providerCode}:${storeId}`;
    setSavingStoreIds((prev) => ({ ...prev, [savingKey]: true }));
    setErr("");
    setSelectedStores((prev) => {
      const next = new Set(prev[providerCode] || []);
      if (exportEnabled) next.add(storeId);
      else next.delete(storeId);
      const nextStoreIds = Array.from(next);
      setSelectedProviders((current) => ({ ...current, [providerCode]: nextStoreIds.length > 0 }));
      return { ...prev, [providerCode]: nextStoreIds };
    });
    try {
      const response = await api<ConnectorsResp>(`/connectors/status/import-stores/${encodeURIComponent(providerCode)}/${encodeURIComponent(storeId)}/export`, {
        method: "PATCH",
        body: JSON.stringify({ export_enabled: exportEnabled }),
      });
      applyConnectorsResponse(response);
    } catch (e) {
      setErr((e as Error).message || "Не удалось сохранить выбор магазина для экспорта.");
      try {
        const response = await api<ConnectorsResp>("/connectors/status");
        applyConnectorsResponse(response);
      } catch {
        // Keep the visible error from the failed save.
      }
    } finally {
      setSavingStoreIds((prev) => {
        const next = { ...prev };
        delete next[savingKey];
        return next;
      });
    }
  }

  async function updateProviderExport(provider: ProviderRow, exportEnabled: boolean) {
    const stores = (provider.import_stores || []).filter((store) => store.enabled !== false);
    if (!stores.length) return;
    const nextIds = exportEnabled ? stores.map((store) => store.id) : [];
    setSelectedStores((prev) => ({ ...prev, [provider.code]: nextIds }));
    setSelectedProviders((prev) => ({ ...prev, [provider.code]: nextIds.length > 0 }));
    await Promise.all(stores.map((store) => updateStoreExport(provider.code, store.id, exportEnabled)));
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
      setPreparingMessage(job.message || "Проверка выгрузки выполняется в фоне.");
      if (job.status === "completed" && job.run) return job.run;
      if (job.status === "failed") {
        throw new Error(job.error || job.message || "Проверка выгрузки не завершилась.");
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
    setExportPackage(null);
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
      setPreparingMessage(job.message || "Проверка выгрузки поставлена в очередь.");
      const res = job.run || await waitForExportJob(job.job_id, startedAt);
      if (!res) throw new Error("Проверка выгрузки еще не вернула сохраненный результат.");
      setRun(res);
      setPreparingMessage("");
    } catch (e) {
      window.clearTimeout(timeoutId);
      setPreparingMessage(jobId ? "Проверка еще выполняется на сервере. Проверяю статус и сохраненный результат." : "Проверка еще выполняется на сервере. Подхватываю сохраненный результат без перезапуска.");
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

  async function loadExportPackage(download = false) {
    const runId = run?.run_id || run?.id || "";
    if (!runId || packageLoading) return;
    setPackageLoading(true);
    setErr("");
    try {
      const response = await api<ExportPackageResp>(`/catalog/exchange/export/runs/${encodeURIComponent(runId)}/package`);
      setExportPackage(response.package);
      if (download) {
        const json = JSON.stringify(response.package, null, 2);
        const blob = new Blob([json], { type: "application/json;charset=utf-8" });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${runId}-export-package.json`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
      }
    } catch (e) {
      setErr((e as Error).message || "Не удалось собрать пакет выгрузки.");
    } finally {
      setPackageLoading(false);
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

      <InspectorPanel title="Каналы" subtitle="Что сейчас выбрано для выгрузки">
        <div className="cx-inspectorStack">
          {providers.map((provider) => {
            const stores = provider.import_stores || [];
            const current = selectedStores[provider.code] || [];
            const enabledStores = stores.filter((store) => store.enabled !== false);
            return (
              <div key={provider.code} className="cx-sourceInspectorCard">
                <div>
                  <strong>{provider.title}</strong>
                  <p>
                    {current.length
                      ? `${current.length} магазинов выбрано`
                      : stores.length
                        ? `${enabledStores.length} активных из ${stores.length}`
                        : "нет подключенных магазинов"}
                  </p>
                </div>
                <Badge tone={selectedProviders[provider.code] && current.length ? "active" : "neutral"}>
                  {current.length ? "В выгрузке" : "0 выбрано"}
                </Badge>
              </div>
            );
          })}
        </div>
      </InspectorPanel>

      {run ? (
        <InspectorPanel title="Последняя подготовка" subtitle="Итог текущей проверки">
          <div className="cx-inspectorList">
            <div className="cx-inspectorRow"><span>Проверка</span><strong>{run.run_id || run.id}</strong></div>
            <div className="cx-inspectorRow"><span>Товаров</span><strong>{run.count}</strong></div>
            <div className="cx-inspectorRow"><span>Целей</span><strong>{run.batches.length}</strong></div>
          </div>
        </InspectorPanel>
      ) : null}
    </div>
  );

  return (
    <div className="cx-page cx-pageModern">
      {!embedded ? (
        <header className="cxStandaloneCommandHeader">
          <div className="cxStandaloneCommandContext">
            <span>Каталог / экспорт</span>
            <h1>Экспорт</h1>
            <p>Собирайте выгрузку по выбранным площадкам и магазинам из той же рабочей области, где отбирается каталог.</p>
          </div>
          <div className="cxStandaloneCommandControls">
            <Link className="btn" to={orgPath("/products")}>Товары</Link>
            <Button variant="primary" onClick={requestExport} disabled={loading || activeTargets.length === 0}>
              {loading ? "Готовлю…" : "Подготовить экспорт"}
            </Button>
          </div>
        </header>
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
            <SummaryMetricRow
              items={[
                { label: "Область", value: selectedScope, hint: includeDescendants && selectedNodeIds.length ? "с дочерними ветками" : "текущий выбор" },
                { label: "SKU в проверке", value: selectedSkuEstimate, hint: selectedProductIds.length ? "точный выбор" : "контрольная выборка" },
                { label: "Каналы", value: activeTargets.length, hint: "площадки" },
                { label: "Магазины", value: selectedTargetsCount, hint: "цели выгрузки", accent: !readyForPrepare },
              ]}
            />

            <DataToolbar
              title="Магазины для выгрузки"
              subtitle="Выберите площадку и конкретные магазины. SmartPim подготовит выгрузку только по отмеченным строкам."
              className="cx-workspaceToolbar cx-exportCommand"
              compact
              actions={(
                <div className="cx-toolbarActions">
                  <Badge tone={exportBadgeTone}>{exportBadgeText}</Badge>
                  <Button variant="primary" onClick={requestExport} disabled={initialLoading || loading || activeTargets.length === 0}>
                    {loading ? "Готовлю…" : "Подготовить"}
                  </Button>
                </div>
              )}
            >
              <div className="cx-targetsBoard">
                {initialLoading ? (
                  <div className="cx-empty">Загружаю магазины и каналы экспорта…</div>
                ) : providers.length === 0 || storesAvailableCount === 0 ? (
                  <div className="cx-targetSetupEmpty">
                    <div className="cx-targetSetupText">
                      <span>Нет целей экспорта</span>
                      <strong>Подключите магазин перед подготовкой пакета</strong>
                      <p>Выгрузка запускается только по конкретным магазинам. Добавьте Я.Маркет или Ozon в источниках данных, затем вернитесь сюда.</p>
                    </div>
                    <div className="cx-targetSetupSteps">
                      <div><b>1</b><span>Добавить магазин</span></div>
                      <div><b>2</b><span>Проверить категорию</span></div>
                      <div><b>3</b><span>Отметить цель</span></div>
                    </div>
                    <div className="cx-targetSetupActions">
                      <Link className="btn btn-primary" to={orgPath("/connectors/status?tab=stores")}>Открыть магазины</Link>
                      <Link className="btn" to={orgPath(sourcesCategoryHref)}>Привязка категории</Link>
                    </div>
                  </div>
                ) : providers.map((provider) => {
                  const stores = provider.import_stores || [];
                  const current = new Set(selectedStores[provider.code] || []);
                  const enabledStores = stores.filter((store) => store.enabled !== false);
                  const checked = current.size > 0;
                  const providerSaving = stores.some((store) => savingStoreIds[`${provider.code}:${store.id}`]);
                  return (
                    <div key={provider.code} className="cx-targetCard">
                      <div className="cx-targetCardHead">
                        <label className={`cx-inlineCheck ${enabledStores.length ? "" : "isDisabled"}`}>
                          <input
                            type="checkbox"
                            checked={enabledStores.length > 0 && checked}
                            disabled={!enabledStores.length || providerSaving}
                            onChange={(e) => void updateProviderExport(provider, e.target.checked)}
                          />
                          <span>{provider.title}</span>
                        </label>
                        <Badge tone={checked && current.size ? "active" : "neutral"}>
                          {providerSaving ? "сохраняю" : current.size ? `${current.size}/${enabledStores.length || stores.length}` : "0 выбрано"}
                        </Badge>
                      </div>
                      <div className="cx-targetMeta">
                        <span>
                          {stores.length
                            ? `${enabledStores.length} активных из ${stores.length}`
                            : "нет подключенных магазинов"}
                        </span>
                        <strong>{current.size ? `${current.size} выбрано` : stores.length ? "выберите магазин" : "добавьте магазин"}</strong>
                      </div>
                      <div className="cx-storeRows">
                        {stores.map((store) => {
                          const storeDisabled = store.enabled === false;
                          const storeSaving = Boolean(savingStoreIds[`${provider.code}:${store.id}`]);
                          return (
                            <label key={store.id} className={`cx-storeRow ${current.has(store.id) && !storeDisabled ? "isActive" : ""} ${storeDisabled ? "isDisabled" : ""} ${storeSaving ? "isSaving" : ""}`}>
                              <span className="cx-storeRowMain">
                                <input
                                  type="checkbox"
                                  checked={!storeDisabled && current.has(store.id)}
                                  disabled={storeDisabled || storeSaving}
                                  onChange={(e) => void updateStoreExport(provider.code, store.id, e.target.checked)}
                                />
                                <span>
                                  <strong>{store.title}</strong>
                                  <em>{storeSaving ? "сохраняю выбор..." : store.id}</em>
                                </span>
                              </span>
                              <span className="cx-storeRowState" aria-hidden="true" />
                            </label>
                          );
                        })}
                      </div>
                      {!stores.length ? (
                        <div className="cx-targetHelp">
                          <Link to={orgPath(`/connectors/status?tab=stores&provider=${encodeURIComponent(provider.code)}`)}>Добавить магазин</Link>
                        </div>
                      ) : current.size === 0 ? (
                        <div className="cx-targetHelp">Отметьте магазин галочкой. Только выбранные магазины попадут в выгрузку.</div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </DataToolbar>

            <section className="card cx-exportStartPanel">
              <div>
                <div className="cx-paneTitle">Подготовка выгрузки</div>
                <div className="cx-paneSub">
                  Экспорт не отправляет все подряд: сначала собирается проверочный пакет по выбранной области, магазинам, медиа, описанию и параметрам.
                </div>
              </div>
              <div className="cx-exportChecklist">
                {targetSetupItems.map((item) => (
                  <div key={item.label} className={`cx-exportChecklistItem is-${item.state}`}>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                    <em>{item.hint}</em>
                  </div>
                ))}
              </div>
              <div className="cx-exportStartActions">
                {selectedTargetLabels.length ? (
                  <div className="cx-selectedTargets">
                    {selectedTargetLabels.slice(0, 4).map((label) => <span key={label}>{label}</span>)}
                    {selectedTargetLabels.length > 4 ? <span>+{selectedTargetLabels.length - 4}</span> : null}
                  </div>
                ) : (
                  <div className="cx-selectedTargets isEmpty">
                    {storesAvailableCount ? "Сначала отметьте хотя бы один магазин" : "Нет магазинов, доступных для экспорта"}
                  </div>
                )}
                <Button variant="primary" onClick={requestExport} disabled={initialLoading || loading || activeTargets.length === 0}>
                  {loading ? "Готовлю…" : "Подготовить выгрузку"}
                </Button>
              </div>
            </section>

            {broadExportScope ? (
              <section className="card cx-exportScopeGuard">
                <div>
                  <div className="cx-paneTitle">Широкая область проверки</div>
                  <div className="cx-paneSub">
                    Для массовой области SmartPim готовит контрольную выборку до 50 SKU. Для финальной отправки выберите конкретные SKU или узкую категорию без дочерних веток.
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
                      <div className="cx-paneTitle">Пакет готов к выгрузке</div>
                      <div className="cx-paneSub">
                        Проверка прошла по выбранной области и выбранным магазинам. SmartPim подготовил данные карточки для выбранных площадок.
                      </div>
                    </div>
                    <div className="cx-exportReadyActions">
                      <Badge tone="active">Можно переходить к отправке</Badge>
                      <Button onClick={() => void loadExportPackage(false)} disabled={packageLoading}>
                        {packageLoading ? "Собираю…" : "Показать пакет"}
                      </Button>
                      <Button variant="primary" onClick={() => void loadExportPackage(true)} disabled={packageLoading}>
                        Скачать JSON
                      </Button>
                    </div>
                  </section>
                ) : null}

                {exportPackage ? (
                  <section className="card cx-pane">
                    <div className="cx-paneHead">
                      <div>
                        <div className="cx-paneTitle">Пакет для отправки</div>
                        <div className="cx-paneSub">Финальные данные текущей проверки: только готовые строки, сгруппированные по площадке и магазину.</div>
                      </div>
                      <Badge tone={exportPackage.status === "ready" ? "active" : "pending"}>
                        {exportPackage.status === "ready" ? "Готов" : "Частичный"}
                      </Badge>
                    </div>
                    <div className="cx-payloadSummary">
                      <div><span>Проверка</span><strong>{exportPackage.run_id}</strong></div>
                      <div><span>Целей</span><strong>{exportPackage.summary?.batch_count ?? 0}</strong></div>
                      <div><span>Готовых строк</span><strong>{exportPackage.summary?.ready_items ?? 0}</strong></div>
                      <div><span>Блокеры</span><strong>{exportPackage.summary?.blocked_items ?? 0}</strong></div>
                    </div>
                    <div className="cx-resultsTableWrap">
                      <table className="cx-resultsTable">
                        <thead>
                          <tr>
                            <th>Площадка</th>
                            <th>Магазин</th>
                            <th>Готовые строки</th>
                            <th>Статус</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(exportPackage.batches || []).map((batch) => (
                            <tr key={`${batch.provider}:${batch.store_id}`}>
                              <td>{providerTitle(batch.provider)}</td>
                              <td>{batch.store_title || batch.store_id}</td>
                              <td>{batch.ready_count}</td>
                              <td>
                                <Badge tone={batch.status === "ready" ? "active" : "pending"}>
                                  {batch.status === "ready" ? "Готов" : `${batch.blocked_count} блок.`}
                                </Badge>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                ) : null}

                <section className="card cx-pane">
                  <div className="cx-paneHead">
                    <div>
                      <div className="cx-paneTitle">Очередь экспорта</div>
                      <div className="cx-paneSub">Видно, по каким площадкам и магазинам собрана очередь и сколько SKU готовы к выгрузке.</div>
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
                              <Link to={orgPath(`/products/${encodeURIComponent(blocker.product_id)}`)}>{blocker.product_title || blocker.product_id}</Link>
                            </div>
                            <ul>
                              {blocker.missing.slice(0, 4).map((reason, index) => {
                                const detail = blocker.missing_details[index];
                                return <li key={reason}>{detail?.message || reason}</li>;
                              })}
                            </ul>
                            <div className="cx-exportBlockerActions">
                              <Link className="btn" to={orgPath(`/products/${encodeURIComponent(blocker.product_id)}`)}>Открыть SKU</Link>
                              {blocker.missing.slice(0, 4).map((reason, index) => {
                                const detail = blocker.missing_details[index];
                                return (
                                <Link
                                  key={`${reason}:${index}`}
                                  className={`btn ${index === 0 ? "btn-primary" : ""}`}
                                  to={orgPath(blockerFixHref(blocker, reason, detail))}
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
            ) : null}
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
                : "Сейчас будет подготовка и проверка данных по выбранным магазинам. Проверьте список целей перед запуском."}
            </div>
            {broadExportScope ? (
              <div className="cx-confirmGuard">
                <label>
                  <input
                    type="checkbox"
                    checked={broadScopeConfirmed}
                    onChange={(event) => setBroadScopeConfirmed(event.target.checked)}
                  />
                  <span>Понимаю, что запускаю широкую проверку до 50 SKU по ветке или всему каталогу</span>
                </label>
                {selectedNodeIds.length === 1 && includeDescendants ? (
                  <button className="btn sm" type="button" onClick={() => setIncludeDescendants(false)}>
                    Проверить только эту категорию
                  </button>
                ) : null}
              </div>
            ) : null}
            <div className="cx-confirmActions">
              <Button onClick={() => setConfirmOpen(false)}>Отмена</Button>
              <Button variant="primary" onClick={() => void startExport()} disabled={loading || activeTargets.length === 0 || (broadExportScope && !broadScopeConfirmed)}>
                {loading ? "Готовлю…" : "Подтвердить и подготовить"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
