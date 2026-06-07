import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef, type Table } from "@tanstack/react-table";
import { Link } from "react-router-dom";
import { useSearchParams } from "react-router-dom";
import CatalogExchangePicker, { type ExchangeNode } from "../../components/CatalogExchangePicker";
import DataToolbar from "../../components/data/DataToolbar";
import InspectorPanel from "../../components/data/InspectorPanel";
import WorkspaceFrame from "../../components/layout/WorkspaceFrame";
import { api } from "../../lib/api";
import { exportSelectionSchema } from "../../lib/exportValidation";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import EmptyState from "../../components/ui/EmptyState";
import PageHeader from "../../components/ui/PageHeader";
import "../../styles/catalog-exchange.css";

type Store = { id: string; title: string; enabled?: boolean; export_enabled?: boolean };
type ProviderRow = { code: string; title: string; import_stores?: Store[] };
type ConnectorsResp = { providers?: ProviderRow[] };
type ExportBootstrapResp = {
  nodes: ExchangeNode[];
  counts: Record<string, number>;
  providers: ProviderRow[];
};
type ExportRunResp = {
  ok: boolean;
  run_id: string;
  id?: string;
  created_at?: string;
  last_submission?: ExportSubmission;
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
type ExportJobRequest = {
  startedAt: number;
  payload: {
    selection: {
      mode: "mixed" | "all";
      node_ids: string[];
      product_ids: string[];
      include_descendants: boolean;
    };
    targets: Array<{ provider: string; store_ids: string[] }>;
    limit: number;
  };
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
      items: Array<{
        product_id: string;
        offer_id?: string;
        payload: Record<string, unknown>;
        audit?: {
          price_source?: string;
          media_count?: number;
          attributes_total?: number;
          attributes_with_source?: number;
          attributes_without_source?: number;
          missing_source?: string[];
        };
      }>;
    }>;
  };
};
type ExportSubmission = {
  ok: boolean;
  status: "submitted" | "failed" | string;
  run_id: string;
  submitted_at?: string;
  dry_run?: boolean;
  summary?: {
    batch_count?: number;
    submitted_batches?: number;
    failed_batches?: number;
  };
  batches?: Array<{
    provider: string;
    store_id: string;
    store_title: string;
    status: "submitted" | "failed" | string;
    ready_items?: number;
    result?: {
      ok?: boolean;
      dry_run?: boolean;
      error?: string;
      status_code?: number;
      request?: { items?: number };
      response?: unknown;
    };
  }>;
};
type ExportSubmitResp = {
  ok: boolean;
  submission: ExportSubmission;
  run?: ExportRunResp & { last_submission?: ExportSubmission };
};
type ExportRunBatch = ExportRunResp["batches"][number];
type ExportPackageBatch = NonNullable<ExportPackageResp["package"]["batches"]>[number];
type ExportPackageItemRow = {
  batch: ExportPackageBatch;
  item: ExportPackageBatch["items"][number];
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
  fix_href?: string;
  fix_label?: string;
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

function ResultsTable<TData>({ table }: { table: Table<TData> }) {
  return (
    <div className="cx-resultsTableWrap">
      <table className="cx-resultsTable">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th key={header.id}>
                  {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function providerTitle(provider: string): string {
  if (provider === "yandex_market") return "Я.Маркет";
  if (provider === "ozon") return "OZON";
  return provider;
}

function exportableProviders(providers: ProviderRow[]): ProviderRow[] {
  return providers
    .filter((provider) => ["yandex_market", "ozon"].includes(provider.code))
    .map((provider) => ({
      ...provider,
      import_stores: provider.import_stores || [],
    }))
    .filter((provider) => (provider.import_stores || []).length > 0);
}

function blockerFixHref(blocker: ExportBlocker, reason: string, detail?: ExportMissingDetail): string {
  if (detail?.fix_href) return detail.fix_href;
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
  if (detail?.fix_label) return detail.fix_label;
  const target = String(detail?.target || "").trim();
  if (detail?.code === "parameter_mapping_required") return "Собрать инфо-модель";
  if (target === "competitors") return "Открыть источники";
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
  if (lower.includes("конкурент")) return "Открыть источники";
  if (lower.includes("изображ") || lower.includes("pictures") || lower.includes("медиа")) return "Открыть медиа";
  if (lower.includes("описание")) return "Открыть описание";
  return "Открыть место исправления";
}

export default function CatalogExportFeature({ embedded = false }: { embedded?: boolean } = {}) {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [nodes, setNodes] = useState<ExchangeNode[]>([]);
  const [productCountsByCategory, setProductCountsByCategory] = useState<Record<string, number>>({});
  const [providers, setProviders] = useState<ProviderRow[]>([]);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);
  const [includeDescendants, setIncludeDescendants] = useState(true);
  const [selectedProviders, setSelectedProviders] = useState<Record<string, boolean>>({});
  const [selectedStores, setSelectedStores] = useState<Record<string, string[]>>({});
  const [bootstrapInitialized, setBootstrapInitialized] = useState(false);
  const [run, setRun] = useState<ExportRunResp | null>(null);
  const [err, setErr] = useState("");
  const [preparingMessage, setPreparingMessage] = useState("");
  const [jobId, setJobId] = useState("");
  const [jobStartedAt, setJobStartedAt] = useState(0);
  const [packageLoading, setPackageLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [exportPackage, setExportPackage] = useState<ExportPackageResp["package"] | null>(null);
  const [submission, setSubmission] = useState<ExportSubmission | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [broadScopeConfirmed, setBroadScopeConfirmed] = useState(false);
  const initialCategoryId = String(searchParams.get("category") || "").trim();
  const initialProductIds = [
    ...String(searchParams.get("product") || "").split(","),
    ...String(searchParams.get("products") || "").split(","),
  ].map((item) => item.trim()).filter(Boolean);

  const exportBootstrapQuery = useQuery({
    queryKey: ["catalog-export-bootstrap"],
    queryFn: async (): Promise<ExportBootstrapResp> => {
      const [n, counts, c] = await Promise.all([
        api<{ nodes: ExchangeNode[] }>("/catalog/nodes"),
        api<{ counts: Record<string, number> }>("/catalog/products/counts"),
        api<ConnectorsResp>("/connectors/status"),
      ]);
      return {
        nodes: n.nodes || [],
        counts: counts.counts || {},
        providers: exportableProviders(c.providers || []),
      };
    },
  });
  const initialLoading = exportBootstrapQuery.isLoading && !bootstrapInitialized;

  useEffect(() => {
    const data = exportBootstrapQuery.data;
    if (!data) return;
    setNodes(data.nodes);
    setProductCountsByCategory(data.counts);
    setProviders(data.providers);
    if (!bootstrapInitialized) {
      setSelectedProviders(Object.fromEntries(data.providers.map((provider) => [
        provider.code,
        (provider.import_stores || []).some((store) => store.export_enabled !== false),
      ])));
      setSelectedStores(Object.fromEntries(data.providers.map((provider) => [
        provider.code,
        (provider.import_stores || []).filter((store) => store.export_enabled !== false).map((store) => store.id),
      ])));
      setBootstrapInitialized(true);
    }
  }, [bootstrapInitialized, exportBootstrapQuery.data]);

  useEffect(() => {
    if (!exportBootstrapQuery.error) return;
    setErr((exportBootstrapQuery.error as Error).message || "Не удалось загрузить данные экспорта");
  }, [exportBootstrapQuery.error]);

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
  const selectedTargetWord = selectedTargetsCount === 1 ? "цель" : selectedTargetsCount > 1 && selectedTargetsCount < 5 ? "цели" : "целей";
  const exportBadgeText = initialLoading
    ? "Загружаю каналы"
    : providers.length === 0
      ? "Нет магазинов"
      : activeTargets.length
        ? `${activeTargets.length} канала`
        : "Не выбрано";
  const exportBadgeTone = initialLoading ? "pending" : activeTargets.length ? "active" : "neutral";
  const selectedCategoryForLinks = selectedNodeIds[0] || initialCategoryId;
  const sourcesCategoryHref = selectedCategoryForLinks
    ? `/sources?tab=sources&category=${encodeURIComponent(selectedCategoryForLinks)}`
    : "/sources?tab=sources";
  const exportEmptyTitle = providers.length === 0
    ? "Нет магазинов для экспорта"
    : activeTargets.length > 0
      ? "Готово к подготовке"
      : "Выберите магазины выше";
  const exportEmptyDescription = providers.length === 0
    ? "Сначала добавьте хотя бы один магазин в коннекторах или проверьте привязку категории к площадкам."
    : activeTargets.length > 0
      ? `Выбрано ${selectedTargetsCount} ${selectedTargetWord} для области "${selectedScope}". Запустите подготовку в панели целей экспорта.`
      : "Отметьте Я.Маркет или Ozon и конкретные магазины, затем запустите подготовку по выбранной области каталога.";
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
        const path = latestRunPath();
        const latest = await queryClient.fetchQuery({
          queryKey: ["catalog-export-latest-run", path],
          queryFn: () => api<LatestExportRunResp>(path),
          staleTime: 0,
        });
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

  const exportJobQuery = useQuery({
    queryKey: ["catalog-export-job", jobId],
    queryFn: () => api<ExportJobResp>(`/catalog/exchange/export/jobs/${encodeURIComponent(jobId)}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = (query.state.data as ExportJobResp | undefined)?.status || "queued";
      return status === "queued" || status === "running" ? 3_000 : false;
    },
  });

  const exportMutation = useMutation({
    mutationFn: async ({ payload }: ExportJobRequest) => {
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), 28_000);
      try {
        return await api<ExportJobResp>("/catalog/exchange/export/jobs", {
          method: "POST",
          signal: controller.signal,
          body: JSON.stringify(payload),
        });
      } finally {
        window.clearTimeout(timeoutId);
      }
    },
    onMutate: ({ startedAt }) => {
      setJobStartedAt(startedAt);
      setErr("");
      setRun(null);
      setPreparingMessage("");
      setJobId("");
      setExportPackage(null);
      setSubmission(null);
    },
    onSuccess: (job) => {
      setJobId(job.job_id || "");
      setPreparingMessage(job.message || "Export batch поставлен в очередь.");
      if (job.status === "completed" && job.run) {
        setRun(job.run);
        setPreparingMessage("");
        setJobId("");
      }
    },
    onError: async (error, { startedAt }) => {
      setPreparingMessage("Batch еще считается на сервере. Подхватываю сохраненный результат без перезапуска.");
      const latest = await waitForLatestRun(startedAt);
      if (latest) {
        setRun(latest);
        setErr("");
      } else {
        setErr((error as Error).message || "Ошибка подготовки экспорта");
      }
      setPreparingMessage("");
    },
  });

  const jobRunning = Boolean(jobId) && !["completed", "failed"].includes(exportJobQuery.data?.status || "");
  const loading = exportMutation.isPending || jobRunning;

  useEffect(() => {
    if (!bootstrapInitialized || loading || jobId) return;
    const exactProductScope = selectedProductIds.length === 1 && selectedNodeIds.length === 0;
    const exactCategoryScope = selectedNodeIds.length === 1 && selectedProductIds.length === 0;
    if (!exactProductScope && !exactCategoryScope) return;
    let cancelled = false;
    const path = latestRunPath();
    void (async () => {
      try {
        const latest = await queryClient.fetchQuery({
          queryKey: ["catalog-export-latest-run", path],
          queryFn: () => api<LatestExportRunResp>(path),
          staleTime: 0,
        });
        if (!cancelled && latest.run) {
          setRun(latest.run);
          setSubmission(latest.run.last_submission || null);
        }
      } catch {
        if (!cancelled) {
          setRun(null);
          setSubmission(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    bootstrapInitialized,
    jobId,
    loading,
    queryClient,
    selectedNodeIds.join(","),
    selectedProductIds.join(","),
  ]);

  useEffect(() => {
    const job = exportJobQuery.data;
    if (!job) return;
    setPreparingMessage(job.message || (jobRunning ? "Export batch считается в фоне." : ""));
    if (job.status === "completed") {
      if (job.run) {
        setRun(job.run);
        setErr("");
        setPreparingMessage("");
        setJobId("");
        void queryClient.invalidateQueries({ queryKey: ["catalog-export-latest-run"] });
      } else if (jobStartedAt) {
        void (async () => {
          const latest = await waitForLatestRun(jobStartedAt, 20_000);
          if (latest) {
            setRun(latest);
            setErr("");
          } else {
            setErr("Export batch завершился, но сохраненный результат пока не найден.");
          }
          setPreparingMessage("");
          setJobId("");
        })();
      }
    } else if (job.status === "failed") {
      setErr(job.error || job.message || "Export batch не завершился.");
      setPreparingMessage("");
      setJobId("");
    }
  }, [exportJobQuery.data, jobRunning, jobStartedAt, queryClient]);

  useEffect(() => {
    if (!run?.last_submission) return;
    setSubmission(run.last_submission);
  }, [run?.last_submission]);

  useEffect(() => {
    if (!exportJobQuery.error || !jobId) return;
    setErr((exportJobQuery.error as Error).message || "Не удалось проверить статус export job.");
  }, [exportJobQuery.error, jobId]);

  function requestExport() {
    if (loading) return;
    const validation = exportSelectionSchema.pick({ targets: true }).safeParse({ targets: activeTargets });
    if (!validation.success) {
      setErr(validation.error.issues[0]?.message || "Выберите магазины для экспорта");
      return;
    }
    setBroadScopeConfirmed(false);
    setConfirmOpen(true);
  }

  async function startExport() {
    setConfirmOpen(false);
    const runLimit = selectedProductIds.length ? Math.max(1, selectedProductIds.length) : 50;
    const startedAt = Date.now();
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
    const validation = exportSelectionSchema.safeParse(payload);
    if (!validation.success) {
      setErr(validation.error.issues[0]?.message || "Проверьте область и магазины экспорта");
      return;
    }
    exportMutation.mutate({ startedAt, payload: validation.data });
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
        link.download = `${runId}-payload.json`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
      }
    } catch (e) {
      setErr((e as Error).message || "Не удалось собрать export payload.");
    } finally {
      setPackageLoading(false);
    }
  }

  async function submitExportPackage() {
    const runId = run?.run_id || run?.id || "";
    if (!runId || submitting) return;
    setSubmitting(true);
    setErr("");
    try {
      const response = await api<ExportSubmitResp>(`/catalog/exchange/export/runs/${encodeURIComponent(runId)}/submit`, {
        method: "POST",
        body: JSON.stringify({ dry_run: false }),
      });
      setSubmission(response.submission);
      if (response.run) setRun(response.run);
      if (!response.ok) {
        const failed = response.submission.batches?.find((batch) => batch.status !== "submitted");
        setErr(failed?.result?.error || "Часть batch не отправилась. Проверьте статус отправки ниже.");
      }
    } catch (e) {
      setErr((e as Error).message || "Не удалось отправить export package.");
    } finally {
      setSubmitting(false);
    }
  }

  const exportQueueColumns = useMemo<ColumnDef<ExportRunBatch>[]>(() => [
    {
      id: "provider",
      header: () => "Площадка",
      cell: ({ row }) => providerTitle(row.original.provider),
    },
    {
      id: "store",
      header: () => "Магазин",
      cell: ({ row }) => row.original.store_title || row.original.store_id,
    },
    {
      id: "status",
      header: () => "Статус",
      cell: ({ row }) => (
        <Badge tone={row.original.status === "ready" ? "active" : "pending"}>
          {row.original.status === "ready" ? "Готово" : "Есть блокеры"}
        </Badge>
      ),
    },
    {
      id: "ready",
      header: () => "Готово",
      cell: ({ row }) => row.original.ready_count,
    },
    {
      id: "blocked",
      header: () => "Блокеры",
      cell: ({ row }) => row.original.not_ready_count ?? Math.max(0, row.original.count - row.original.ready_count),
    },
    {
      id: "total",
      header: () => "Всего",
      cell: ({ row }) => row.original.count,
    },
  ], []);
  const exportQueueTable = useReactTable({
    data: run?.batches || [],
    columns: exportQueueColumns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row, index) => `${row.provider}:${row.store_id}:${index}`,
  });

  const packageBatchColumns = useMemo<ColumnDef<ExportPackageBatch>[]>(() => [
    {
      id: "provider",
      header: () => "Площадка",
      cell: ({ row }) => providerTitle(row.original.provider),
    },
    {
      id: "store",
      header: () => "Магазин",
      cell: ({ row }) => row.original.store_title || row.original.store_id,
    },
    {
      id: "ready",
      header: () => "Payload rows",
      cell: ({ row }) => row.original.ready_count,
    },
    {
      id: "status",
      header: () => "Статус",
      cell: ({ row }) => (
        <Badge tone={row.original.status === "ready" ? "active" : "pending"}>
          {row.original.status === "ready" ? "Готов" : `${row.original.blocked_count} блок.`}
        </Badge>
      ),
    },
  ], []);
  const packageBatchTable = useReactTable({
    data: exportPackage?.batches || [],
    columns: packageBatchColumns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => `${row.provider}:${row.store_id}`,
  });

  const packageItemRows = useMemo<ExportPackageItemRow[]>(
    () => (exportPackage?.batches || []).flatMap((batch) =>
      (batch.items || []).slice(0, 6).map((item) => ({ batch, item })),
    ),
    [exportPackage],
  );
  const packageItemColumns = useMemo<ColumnDef<ExportPackageItemRow>[]>(() => [
    {
      id: "row",
      header: () => "Payload row",
      cell: ({ row }) => `${providerTitle(row.original.batch.provider)} · ${row.original.item.product_id}`,
    },
    {
      id: "offer",
      header: () => "Offer ID",
      cell: ({ row }) => row.original.item.offer_id || "—",
    },
    {
      id: "price",
      header: () => "Цена",
      cell: ({ row }) => row.original.item.audit?.price_source || "unknown",
    },
    {
      id: "media",
      header: () => "Медиа",
      cell: ({ row }) => row.original.item.audit?.media_count ?? 0,
    },
    {
      id: "attributes",
      header: () => "Параметры",
      cell: ({ row }) => {
        const audit = row.original.item.audit || {};
        return `${audit.attributes_with_source ?? 0}/${audit.attributes_total ?? 0}`;
      },
    },
    {
      id: "missing",
      header: () => "Без источника",
      cell: ({ row }) => {
        const missing = row.original.item.audit?.missing_source || [];
        return missing.length ? missing.slice(0, 3).join(", ") : "—";
      },
    },
  ], []);
  const packageItemTable = useReactTable({
    data: packageItemRows,
    columns: packageItemColumns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => `${row.batch.provider}:${row.batch.store_id}:${row.item.product_id}:${row.item.offer_id || ""}`,
  });

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
                ) : providers.length === 0 ? (
                  <div className="cx-empty cx-exportEmptyHint">
                    <strong>Нет магазинов для экспорта</strong>
                    <span>Включите магазины для выгрузки в настройках коннекторов или проверьте привязку категории к площадкам.</span>
                    <div className="cx-emptyActions">
                      <Link className="btn btn-primary" to="/connectors/status?tab=marketplaces">Открыть коннекторы</Link>
                      <Link className="btn" to={sourcesCategoryHref}>Проверить привязку</Link>
                    </div>
                  </div>
                ) : providers.map((provider) => {
                  const checked = !!selectedProviders[provider.code];
                  const stores = provider.import_stores || [];
                  const current = new Set(selectedStores[provider.code] || []);
                  return (
                    <div key={provider.code} className="cx-targetCard">
                      <label className={`cx-inlineCheck ${stores.length ? "" : "isDisabled"}`}>
                        <input
                          type="checkbox"
                          checked={stores.length > 0 && checked}
                          disabled={!stores.length}
                          onChange={(e) => {
                            setSelectedProviders((prev) => ({ ...prev, [provider.code]: e.target.checked }));
                            if (!e.target.checked) {
                              setSelectedStores((prev) => ({ ...prev, [provider.code]: [] }));
                            }
                          }}
                        />
                        <span>{provider.title}</span>
                      </label>
                      <div className="cx-storeChips">
                        {stores.map((store) => {
                          const storeDisabled = store.enabled === false;
                          return (
                            <label key={store.id} className={`cx-storeChip ${current.has(store.id) && !storeDisabled ? "isActive" : ""} ${storeDisabled ? "isDisabled" : ""}`}>
                              <input
                                type="checkbox"
                                checked={!storeDisabled && current.has(store.id)}
                                disabled={storeDisabled}
                                onChange={(e) => {
                                  const next = new Set(selectedStores[provider.code] || []);
                                  if (e.target.checked) next.add(store.id);
                                  else next.delete(store.id);
                                  setSelectedStores((prev) => ({ ...prev, [provider.code]: Array.from(next) }));
                                  setSelectedProviders((prev) => ({ ...prev, [provider.code]: next.size > 0 }));
                                }}
                              />
                              <span>{store.title}</span>
                            </label>
                          );
                        })}
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
                    <div className="cx-exportReadyActions">
                      <Badge tone="active">Можно переходить к отправке</Badge>
                      <Button onClick={() => void loadExportPackage(false)} disabled={packageLoading}>
                        {packageLoading ? "Собираю…" : "Показать payload"}
                      </Button>
                      <Button onClick={() => void loadExportPackage(true)} disabled={packageLoading}>
                        Скачать JSON
                      </Button>
                      <Button variant="primary" onClick={() => void submitExportPackage()} disabled={submitting || packageLoading}>
                        {submitting ? "Отправляю…" : "Отправить на площадки"}
                      </Button>
                    </div>
                  </section>
                ) : null}

                {submission ? (
                  <section className="card cx-pane">
                    <div className="cx-paneHead">
                      <div>
                        <div className="cx-paneTitle">Статус отправки</div>
                        <div className="cx-paneSub">
                          Результат последней отправки по этому run. Магазины не выбираются заново: используется готовый batch.
                        </div>
                      </div>
                      <Badge tone={submission.ok ? "active" : "danger"}>
                        {submission.ok ? "Отправлено" : "Есть ошибки"}
                      </Badge>
                    </div>
                    <div className="cx-payloadSummary">
                      <div><span>Run</span><strong>{submission.run_id}</strong></div>
                      <div><span>Batch</span><strong>{submission.summary?.batch_count ?? 0}</strong></div>
                      <div><span>Отправлено</span><strong>{submission.summary?.submitted_batches ?? 0}</strong></div>
                      <div><span>Ошибки</span><strong>{submission.summary?.failed_batches ?? 0}</strong></div>
                    </div>
                    <div className="cx-exportBlockers">
                      {(submission.batches || []).map((batch) => (
                        <div key={`${batch.provider}:${batch.store_id}`} className="cx-exportBlocker">
                          <div className="cx-exportBlockerHead">
                            <strong>{providerTitle(batch.provider)} · {batch.store_title || batch.store_id}</strong>
                            <Badge tone={batch.status === "submitted" ? "active" : "danger"}>
                              {batch.status === "submitted" ? "Принято" : "Ошибка"}
                            </Badge>
                          </div>
                          <div className="cx-exportBlockerProduct">
                            SKU в запросе: <b>{batch.result?.request?.items ?? batch.ready_items ?? 0}</b>
                            {batch.result?.status_code ? <> · HTTP <b>{batch.result.status_code}</b></> : null}
                          </div>
                          {batch.result?.error ? (
                            <div className="cx-exportBlockerReasons">
                              <span>{batch.result.error}</span>
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </section>
                ) : null}

                {exportPackage ? (
                  <section className="card cx-pane">
                    <div className="cx-paneHead">
                      <div>
                        <div className="cx-paneTitle">Payload для отправки</div>
                        <div className="cx-paneSub">Финальный пакет по текущему run: только готовые строки, сгруппированные по площадке и магазину.</div>
                      </div>
                      <Badge tone={exportPackage.status === "ready" ? "active" : "pending"}>
                        {exportPackage.status === "ready" ? "Готов" : "Частичный"}
                      </Badge>
                    </div>
                    <div className="cx-payloadSummary">
                      <div><span>Run</span><strong>{exportPackage.run_id}</strong></div>
                      <div><span>Batch</span><strong>{exportPackage.summary?.batch_count ?? 0}</strong></div>
                      <div><span>Payload rows</span><strong>{exportPackage.summary?.ready_items ?? 0}</strong></div>
                      <div><span>Блокеры</span><strong>{exportPackage.summary?.blocked_items ?? 0}</strong></div>
                    </div>
                    <ResultsTable table={packageBatchTable} />
                    <ResultsTable table={packageItemTable} />
                  </section>
                ) : null}

                <section className="card cx-pane">
                  <div className="cx-paneHead">
                    <div>
                      <div className="cx-paneTitle">Очередь экспорта</div>
                      <div className="cx-paneSub">Видно, по каким каналам и магазинам собран batch и сколько SKU готовы к выгрузке.</div>
                    </div>
                  </div>
                  <ResultsTable table={exportQueueTable} />
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
                title={exportEmptyTitle}
                description={exportEmptyDescription}
                action={providers.length === 0 ? (
                  <div className="cx-emptyActions">
                    <Link className="btn btn-primary" to="/connectors/status?tab=marketplaces">Открыть коннекторы</Link>
                    <Link className="btn" to={sourcesCategoryHref}>Проверить привязку</Link>
                  </div>
                ) : (
                  activeTargets.length > 0 ? null : <Button variant="primary" onClick={requestExport} disabled={loading || activeTargets.length === 0}>
                    {loading ? "Готовлю…" : "Подготовить экспорт"}
                  </Button>
                )}
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
