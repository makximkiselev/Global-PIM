import { useEffect, useMemo, useState } from "react";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import EmptyState from "../../components/ui/EmptyState";
import { api } from "../../lib/api";

type CompetitorSource = {
  id: "restore" | "store77";
  name: string;
  domain: string;
  status: string;
};

type CompetitorCandidate = {
  id: string;
  product_id: string;
  source_id: "restore" | "store77";
  source_name?: string;
  url: string;
  title?: string;
  match_group_key?: string;
  product_sim_profile?: string;
  candidate_sim_profile?: string;
  confidence_score?: number;
  confidence_reasons?: string[];
  status: "needs_review" | "approved" | "rejected" | "stale" | string;
  last_seen_at?: string;
  reviewed_at?: string;
  rejection_reason?: string;
};

type CompetitorLink = {
  id?: string;
  candidate_id?: string;
  product_id?: string;
  source_id?: string;
  url?: string;
  status?: string;
  source?: string;
  confirmed_at?: string;
  last_checked_at?: string;
  last_enriched_at?: string;
};

type CompetitorSourceSummary = {
  source_id: "restore" | "store77";
  source_name: string;
  domain: string;
  status: "confirmed" | "review" | "no_exact_match" | "scan_error" | "empty" | string;
  label: string;
  message: string;
  confirmed_count: number;
  actionable_count: number;
  hidden_count: number;
  best_score?: number | null;
  best_title?: string;
  best_url?: string;
  best_reasons?: string[];
  last_scanned_at?: string;
  retry_after_seconds?: number;
  scan_error?: string;
  scan_evidence?: {
    direct_url?: string;
    query_terms?: string[];
    category_urls?: string[];
  };
};

const FALLBACK_COMPETITOR_SOURCES: CompetitorSource[] = [
  { id: "restore", name: "re-store", domain: "re-store.ru", status: "active" },
  { id: "store77", name: "store77", domain: "store77.net", status: "active" },
];

type ProductCompetitorResp = {
  ok: boolean;
  product_id: string;
  items: CompetitorCandidate[];
  confirmed_links: CompetitorLink[];
  counts: {
    total: number;
    needs_review: number;
    approved: number;
    rejected: number;
    stale: number;
    confirmed_links: number;
  };
  sources: CompetitorSource[];
  source_summaries?: CompetitorSourceSummary[];
};

type ProductFeatureValue = {
  code?: string;
  name?: string;
  value?: string;
  values?: string[];
  source_values?: Record<string, unknown>;
};

type ProductSnapshot = {
  id: string;
  content?: {
    media_images?: Array<Record<string, unknown>>;
    media?: Array<Record<string, unknown>>;
    features?: ProductFeatureValue[];
    source_values?: Record<string, unknown>;
    source_evidence?: Record<string, unknown>;
  };
};

type ProductResp = { product: ProductSnapshot };

type DiscoveryRun = {
  id: string;
  status: string;
  scanned_products_count?: number;
  created_count?: number;
  updated_count?: number;
};

type RunResp = { ok: boolean; run: DiscoveryRun };
type RunStatusResp = { ok: boolean; run: DiscoveryRun };
type ManualLinkResp = { ok: boolean; link?: CompetitorLink };
type EnrichResp = {
  ok: boolean;
  enriched_sources?: string[];
  matched_count?: number;
  unmatched_count?: number;
  errors?: Array<{ source_id?: string; error?: string; retryable?: boolean }>;
};
type EnrichJobResp = EnrichResp & {
  job_id: string;
  product_id: string;
  status: "queued" | "running" | "completed" | "failed" | string;
  message?: string;
  media_images_count?: number;
  error?: string;
};

const MIN_REVIEW_COMPETITOR_SCORE = 0.45;

function scoreLabel(candidate: CompetitorCandidate): string {
  const raw = Number(candidate.confidence_score || 0);
  return Number.isFinite(raw) ? `${Math.round(raw * 100)}%` : "0%";
}

function confirmedLinkTime(link: CompetitorLink): string {
  const value = link.last_enriched_at || link.last_checked_at || link.confirmed_at;
  return value ? new Date(value).toLocaleString("ru-RU") : "пока не загружали";
}

function isReviewCandidate(candidate: CompetitorCandidate): boolean {
  if (candidate.status !== "needs_review") return false;
  const score = Number(candidate.confidence_score || 0);
  return Number.isFinite(score) && score >= MIN_REVIEW_COMPETITOR_SCORE;
}

function statusTone(status: string): "active" | "pending" | "danger" | "neutral" {
  if (status === "approved") return "active";
  if (status === "rejected") return "danger";
  if (status === "needs_review") return "pending";
  return "neutral";
}

function statusLabel(status: string): string {
  if (status === "approved") return "Подтверждено";
  if (status === "rejected") return "Отклонено";
  if (status === "needs_review") return "На модерации";
  if (status === "stale") return "Устарело";
  return status || "—";
}

function simProfileLabel(value?: string): string {
  if (value === "nano_sim_esim") return "nano SIM + eSIM";
  if (value === "esim_only") return "eSIM only";
  if (value === "dual_sim") return "Dual SIM";
  if (value === "physical_sim") return "SIM";
  return "SIM не распознан";
}

function hasBlockingSimConflict(candidate: CompetitorCandidate): boolean {
  const productSim = String(candidate.product_sim_profile || "").trim();
  const candidateSim = String(candidate.candidate_sim_profile || "").trim();
  const knownProfiles = new Set(["nano_sim_esim", "esim_only", "dual_sim", "physical_sim"]);
  return knownProfiles.has(productSim) && knownProfiles.has(candidateSim) && productSim !== candidateSim;
}

function reasonCaption(candidate: CompetitorCandidate): string {
  const reasons = (candidate.confidence_reasons || []).join(" ").toLowerCase();
  if (reasons.includes("конфликт") || reasons.includes("проверь")) return "Что проверить";
  return "Почему подходит";
}

function sourceLabel(value?: string): string {
  if (value === "restore") return "re-store";
  if (value === "store77") return "store77";
  return value || "источник";
}

function sourceSummaryTone(status: string): "active" | "pending" | "danger" | "neutral" {
  if (status === "confirmed") return "active";
  if (status === "review") return "pending";
  if (status === "no_exact_match" || status === "scan_error") return "danger";
  return "neutral";
}

function sourceBestScoreLabel(summary: CompetitorSourceSummary): string {
  const raw = Number(summary.best_score || 0);
  if (!Number.isFinite(raw) || raw <= 0) return "—";
  return `${Math.round(raw * 100)}%`;
}

function enrichErrorLabel(error?: string): string {
  const value = String(error || "").toUpperCase();
  if (value.includes("TIMEOUT")) return "источник долго отвечает";
  if (value.includes("FETCH")) return "не удалось открыть карточку";
  if (value.includes("NO_FIELDS")) return "в карточке не найдены параметры";
  if (value.includes("UNSUPPORTED")) return "сайт не поддерживается";
  return "не удалось загрузить данные";
}

function sourceScanTime(summary: CompetitorSourceSummary): string {
  const value = summary.last_scanned_at;
  return value ? new Date(value).toLocaleString("ru-RU") : "";
}

function emptySourceSummary(source: CompetitorSource): CompetitorSourceSummary {
  return {
    source_id: source.id,
    source_name: source.name,
    domain: source.domain,
    status: "empty",
    label: "Не сканировали",
    message: "По этому источнику пока нет кандидатов для SKU.",
    confirmed_count: 0,
    actionable_count: 0,
    hidden_count: 0,
  };
}

function safeRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function safeList<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : [];
}

function competitorImportStats(product: ProductSnapshot | null, links: CompetitorLink[]) {
  if (!links.length) {
    return {
      mediaCount: 0,
      matchedCount: 0,
      extractedCount: 0,
      unmatchedCount: 0,
      mediaBySource: [] as Array<{ sourceId: string; mediaCount: number; updatedAt: string }>,
      hasEvidence: false,
    };
  }

  const content = safeRecord(product?.content);
  const sourceValues = safeRecord(content.source_values);
  const sourceEvidence = safeRecord(content.source_evidence);
  const competitorsEvidence = safeRecord(sourceEvidence.competitors);
  const features = safeList<ProductFeatureValue>(content.features);
  const mediaImages = safeList<Record<string, unknown>>(content.media_images).length
    ? safeList<Record<string, unknown>>(content.media_images)
    : safeList<Record<string, unknown>>(content.media);

  const sourceIds = new Set(links.map((link) => String(link.source_id || "").trim()).filter(Boolean));
  const sourceMedia = safeRecord(sourceValues.media_images);
  let mediaFromConfirmedSources = 0;
  for (const item of mediaImages) {
    const source = String(item.source || "").trim();
    if (sourceIds.has(source)) mediaFromConfirmedSources += 1;
  }

  let matchedFromFeatures = 0;
  for (const feature of features) {
    const competitorValues = safeRecord(safeRecord(feature.source_values).competitor);
    if (Object.keys(competitorValues).some((sourceId) => sourceIds.has(sourceId))) {
      matchedFromFeatures += 1;
    }
  }

  let matchedFromEvidence = 0;
  let unmatchedFromEvidence = 0;
  for (const sourceId of sourceIds) {
    const evidence = safeRecord(competitorsEvidence[sourceId]);
    matchedFromEvidence += Object.keys(safeRecord(evidence.matched_specs)).length;
    unmatchedFromEvidence += Object.keys(safeRecord(evidence.unmatched_specs)).length;
  }

  const mediaBySource = Array.from(sourceIds).map((sourceId) => {
    const meta = safeRecord(sourceMedia[sourceId]);
    const countFromMeta = Number(meta.count || 0);
    const countFromItems = mediaImages.filter((item) => String(item.source || "").trim() === sourceId).length;
    return {
      sourceId,
      mediaCount: Math.max(countFromMeta, countFromItems),
      updatedAt: String(meta.updated_at || ""),
    };
  });

  return {
    mediaCount: mediaFromConfirmedSources,
    matchedCount: Math.max(matchedFromFeatures, matchedFromEvidence),
    extractedCount: matchedFromEvidence + unmatchedFromEvidence,
    unmatchedCount: unmatchedFromEvidence,
    mediaBySource,
    hasEvidence: Boolean(matchedFromFeatures || matchedFromEvidence || unmatchedFromEvidence || mediaFromConfirmedSources),
  };
}

export default function ProductCompetitorPanel({
  productId,
  onEnriched,
  variant = "default",
}: {
  productId: string;
  onEnriched?: () => void | Promise<void>;
  variant?: "default" | "compact";
}) {
  const [context, setContext] = useState<ProductCompetitorResp | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [error, setError] = useState("");
  const [enrichNotice, setEnrichNotice] = useState("");
  const [manualSource, setManualSource] = useState<"restore" | "store77">("store77");
  const [manualUrl, setManualUrl] = useState("");
  const [manualSubmitting, setManualSubmitting] = useState(false);
  const [lastRun, setLastRun] = useState<DiscoveryRun | null>(null);
  const [productSnapshot, setProductSnapshot] = useState<ProductSnapshot | null>(null);

  const candidates = useMemo(() => (context?.items || []).filter(isReviewCandidate), [context?.items]);
  const candidateGroups = useMemo(() => {
    const groups = new Map<string, CompetitorCandidate[]>();
    candidates.forEach((candidate) => {
      const key = candidate.match_group_key || candidate.id;
      groups.set(key, [...(groups.get(key) || []), candidate]);
    });
    return Array.from(groups.entries()).map(([key, items]) => ({
      key,
      items,
      title: key.includes("|") ? key.split("|").filter(Boolean).join(" / ") : "Варианты match",
    }));
  }, [candidates]);
  const selected = useMemo(
    () => candidates.find((item) => item.id === selectedId) || candidates[0] || null,
    [candidates, selectedId],
  );
  const confirmedLinks = context?.confirmed_links || [];
  const importStats = useMemo(() => competitorImportStats(productSnapshot, confirmedLinks), [productSnapshot, confirmedLinks]);
  const hasConfirmedLinks = confirmedLinks.length > 0;
  const sourceSummaries = useMemo(() => {
    const byId = new Map<string, CompetitorSourceSummary>();
    for (const summary of context?.source_summaries || []) {
      const sourceId = String(summary.source_id || "").trim();
      if (sourceId) byId.set(sourceId, summary);
    }
    const sources = (context?.sources?.length ? context.sources : FALLBACK_COMPETITOR_SOURCES);
    for (const source of sources) {
      if (!byId.has(source.id)) byId.set(source.id, emptySourceSummary(source));
    }
    return Array.from(byId.values()).sort((a, b) => sourceLabel(a.source_id).localeCompare(sourceLabel(b.source_id), "ru"));
  }, [context?.source_summaries, context?.sources]);

  async function loadProductSnapshot() {
    if (!productId) return;
    try {
      const response = await api<ProductResp>(`/products/${encodeURIComponent(productId)}?include_variants=false`);
      setProductSnapshot(response.product || null);
    } catch {
      setProductSnapshot(null);
    }
  }

  async function load() {
    if (!productId) return;
    setError("");
    setLoading(true);
    try {
      const [response] = await Promise.all([
        api<ProductCompetitorResp>(`/competitor-mapping/discovery/products/${encodeURIComponent(productId)}`),
        loadProductSnapshot(),
      ]);
      setContext(response);
      setSelectedId((prev) => {
        if (prev && response.items.some((item) => item.id === prev)) return prev;
        return response.items[0]?.id || "";
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить найденные карточки конкурентов");
    } finally {
      setLoading(false);
    }
  }

  async function pollRun(runId: string) {
    for (let attempt = 0; attempt < 24; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 2500));
      try {
        const status = await api<RunStatusResp>(`/competitor-mapping/discovery/runs/${encodeURIComponent(runId)}`);
        setLastRun(status.run);
        if (!["queued", "running"].includes(status.run.status)) {
          await load();
          return;
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : "Не удалось получить статус поиска";
        if (message.includes("Run not found") || message.includes("404")) {
          setLastRun((prev) => prev ? { ...prev, status: "running" } : { id: runId, status: "running" });
          continue;
        }
        setError(message);
        return;
      }
    }
    await load();
  }

  async function runDiscovery() {
    setError("");
    setEnrichNotice("");
    setRunning(true);
    try {
      const sources = (context?.sources?.length ? context.sources : FALLBACK_COMPETITOR_SOURCES).map((source) => source.id);
      const response = await api<RunResp>("/competitor-mapping/discovery/run", {
        method: "POST",
        body: JSON.stringify({ background: true, product_ids: [productId], sources, limit: 1 }),
      });
      setLastRun(response.run);
      void pollRun(response.run.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось запустить поиск");
    } finally {
      setRunning(false);
    }
  }

  async function moderate(candidate: CompetitorCandidate, action: "approve" | "reject") {
    setError("");
    setEnrichNotice("");
    try {
      await api(`/competitor-mapping/discovery/candidates/${encodeURIComponent(candidate.id)}/moderate`, {
        method: "POST",
        body: JSON.stringify(action === "approve" ? { action } : { action, reason: "Отклонено из карточки товара" }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось обновить candidate");
    }
  }

  async function enrichConfirmedLinks() {
    setError("");
    setEnrichNotice("");
    setEnriching(true);
    try {
      const started = await api<EnrichJobResp>(`/competitor-mapping/discovery/products/${encodeURIComponent(productId)}/enrich/jobs`, {
        method: "POST",
      });
      setEnrichNotice(started.message || "Насыщение товара поставлено в очередь.");
      let response: EnrichJobResp = started;
      const deadline = Date.now() + 140_000;
      while (["queued", "running"].includes(response.status) && Date.now() < deadline) {
        await new Promise((resolve) => window.setTimeout(resolve, 4_000));
        response = await api<EnrichJobResp>(`/competitor-mapping/discovery/products/enrich/jobs/${encodeURIComponent(started.job_id)}`);
        if (response.message) setEnrichNotice(response.message);
      }
      if (["queued", "running"].includes(response.status)) {
        throw new Error("Насыщение еще выполняется. Обновите карточку через несколько секунд.");
      }
      if (response.status === "failed") {
        throw new Error(response.error || response.message || "Насыщение не завершилось");
      }
      const sources = response.enriched_sources?.length ? response.enriched_sources.join(", ") : "нет";
      const errors = response.errors || [];
      const errorsText = errors.length
        ? ` Не загрузились: ${errors.map((item) => `${sourceLabel(item.source_id)} — ${enrichErrorLabel(item.error)}${item.retryable ? ", можно повторить" : ""}`).join("; ")}.`
        : "";
      setEnrichNotice(
        `Источники: ${sources}. Медиа: ${response.media_images_count || 0}. Совпало параметров: ${response.matched_count || 0}. Без пары: ${response.unmatched_count || 0}.${errorsText}`,
      );
      await loadProductSnapshot();
      await load();
      await onEnriched?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить данные из подтвержденных ссылок");
    } finally {
      setEnriching(false);
    }
  }

  async function addManualLink() {
    const url = manualUrl.trim();
    if (!url) return;
    setError("");
    setEnrichNotice("");
    setManualSubmitting(true);
    try {
      await api<ManualLinkResp>(`/competitor-mapping/discovery/products/${encodeURIComponent(productId)}/links`, {
        method: "POST",
        body: JSON.stringify({ source_id: manualSource, url }),
      });
      setManualUrl("");
      setEnrichNotice("Ссылка добавлена вручную и стала подтвержденной. Неподтвержденные варианты этого источника отклонены.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось добавить ссылку вручную");
    } finally {
      setManualSubmitting(false);
    }
  }

  useEffect(() => {
    void load();
  }, [productId]);

  const content = (
      <div className={`productCompetitorPanel${variant === "compact" ? " isCompact" : ""}`}>
        <div className="productCompetitorToolbar">
          <div>
            <div className="productWorkspaceMiniTitle">Сопоставление конкурентов</div>
            <p>
              {hasConfirmedLinks
                ? "К товару уже привязаны карточки конкурентов. Ниже видно, что импортировано в карточку SKU."
                : "Сначала найдите и подтвердите точную карточку конкурента. После подтверждения система загрузит медиа, описание и характеристики."}
            </p>
          </div>
          <div className="productCompetitorActions">
            <Button onClick={() => void load()} disabled={loading || running}>
              Обновить
            </Button>
            {hasConfirmedLinks ? (
              <Button onClick={() => void enrichConfirmedLinks()} disabled={loading || running || enriching || !productId}>
                {enriching ? "Загружаю…" : importStats.hasEvidence ? "Обновить импорт" : "Загрузить данные"}
              </Button>
            ) : null}
            <Button variant="primary" onClick={() => void runDiscovery()} disabled={loading || running || !productId}>
              {running ? "Ищу…" : hasConfirmedLinks ? "Найти еще" : "Найти карточки"}
            </Button>
          </div>
        </div>

        <div className="productCompetitorMetrics">
          <div><span>Ссылки</span><strong>{confirmedLinks.length}</strong></div>
          <div><span>Медиа</span><strong>{importStats.mediaCount}</strong></div>
          <div><span>Выгружено хар-к</span><strong>{importStats.extractedCount}</strong></div>
          <div><span>Сопоставлено</span><strong>{importStats.matchedCount}</strong></div>
        </div>

        {hasConfirmedLinks ? (
          <section className="productCompetitorImportSummary" aria-label="Статус импорта конкурентов">
            <div className="productCompetitorImportHead">
              <div>
                <span>Статус товара</span>
                <strong>{importStats.hasEvidence ? "Данные конкурентов загружены" : "Ссылки есть, импорт еще не запускали"}</strong>
              </div>
              <Badge tone={importStats.hasEvidence ? "active" : "pending"}>
                {importStats.hasEvidence ? "ок" : "нужно загрузить"}
              </Badge>
            </div>
            <div className="productCompetitorImportRows">
              {confirmedLinks.map((link) => {
                const sourceId = String(link.source_id || "").trim();
                const mediaMeta = importStats.mediaBySource.find((item) => item.sourceId === sourceId);
                return (
                  <a key={`${sourceId}-${link.url}`} href={link.url} target="_blank" rel="noreferrer" className="productCompetitorImportRow">
                    <span>{sourceLabel(sourceId)}</span>
                    <strong>{link.url}</strong>
                    <em>{mediaMeta?.mediaCount || 0} медиа · {confirmedLinkTime(link)}</em>
                  </a>
                );
              })}
            </div>
            <div className="productCompetitorImportFoot">
              <span>Без сопоставления: <strong>{importStats.unmatchedCount}</strong></span>
              <span>Повторный импорт обновит медиа и источники характеристик.</span>
            </div>
          </section>
        ) : (
          <section className="productCompetitorMatchPrompt" aria-label="Нужно сопоставить товар с конкурентом">
            <div>
              <span>Следующий шаг</span>
              <strong>Подобрать карточку конкурента</strong>
              <p>Запустите поиск здесь, в сопоставлении. Источники данных должны только хранить список сайтов, откуда можно вытягивать данные.</p>
            </div>
            <Button variant="primary" onClick={() => void runDiscovery()} disabled={loading || running || !productId}>
              {running ? "Ищу…" : "Подобрать карточки"}
            </Button>
          </section>
        )}

        {sourceSummaries.length ? (
          <div className="productCompetitorSourceGrid" aria-label="Статус конкурентных источников">
            {sourceSummaries.map((summary) => (
              <div key={summary.source_id} className={`productCompetitorSourceCard is-${summary.status}`}>
                <div className="productCompetitorSourceHead">
                  <div>
                    <span>{summary.source_name}</span>
                    <strong>{summary.domain}</strong>
                  </div>
                  <Badge tone={sourceSummaryTone(summary.status)}>{summary.label}</Badge>
                </div>
                <p>{summary.message}</p>
                {summary.last_scanned_at ? (
                  <div className="productCompetitorSourceBest">
                    <span>Последняя проверка</span>
                    <strong>{sourceScanTime(summary)}</strong>
                    {summary.scan_error ? <em>{enrichErrorLabel(summary.scan_error)}</em> : null}
                  </div>
                ) : null}
                {summary.status === "no_exact_match" && summary.best_title ? (
                  <div className="productCompetitorSourceBest">
                    <span>Лучший скрытый вариант</span>
                    <strong>{summary.best_title}</strong>
                    <em>
                      {[
                        `Точность ${sourceBestScoreLabel(summary)}`,
                        summary.hidden_count ? `скрыто ${summary.hidden_count}` : "",
                        summary.best_reasons?.[0] || "",
                      ].filter(Boolean).join(" · ")}
                    </em>
                  </div>
                ) : null}
                {summary.retry_after_seconds ? (
                  <div className="productCompetitorSourceBest">
                    <span>Повторный поиск</span>
                    <strong>{summary.retry_after_seconds <= 300 ? "можно повторить через 5 минут" : "лучше повторить позже"}</strong>
                    <em>Сначала проверьте, что модель, память, цвет и SIM указаны в SKU без ошибок.</em>
                  </div>
                ) : null}
                {summary.scan_evidence?.direct_url || summary.scan_evidence?.query_terms?.length || summary.scan_evidence?.category_urls?.length ? (
                  <div className="productCompetitorSourceBest">
                    <span>Что проверяли</span>
                    <strong>{summary.scan_evidence.direct_url || summary.scan_evidence.category_urls?.[0] || summary.scan_evidence.query_terms?.[0]}</strong>
                    <em>{summary.scan_evidence.query_terms?.slice(0, 2).join(" · ")}</em>
                  </div>
                ) : null}
                {summary.status === "confirmed" ? (
                  <div className="productCompetitorSourceBest">
                    <span>Что будет загружаться</span>
                    <strong>Параметры, описание и медиа</strong>
                    <em>{summary.confirmed_count} подтвержденная ссылка</em>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}

        {lastRun ? (
          <div className="productCompetitorNotice">
            Последний запуск: {lastRun.status}, найдено/обновлено: {(lastRun.created_count || 0) + (lastRun.updated_count || 0)}
          </div>
        ) : null}
        {enrichNotice ? <div className="productCompetitorNotice">{enrichNotice}</div> : null}
        {error ? <div className="productCompetitorError">{error}</div> : null}

        {loading ? (
          <EmptyState title="Загружаем конкурентов" description="Получаем найденные карточки и подтвержденные ссылки для SKU." />
        ) : candidates.length || context?.confirmed_links.length ? (
          <div className="productCompetitorWorkspace">
            {candidates.length ? (
              <div className="productCompetitorList" aria-label="Competitor candidates">
                {candidateGroups.map((group) => (
                  <section key={group.key} className="productCompetitorGroup">
                    <div className="productCompetitorGroupTitle">
                      <span>Варианты для выбора</span>
                      <strong>{group.title}</strong>
                    </div>
                    <div className="productCompetitorCarousel">
                      {group.items.map((candidate) => (
                        <article
                          key={candidate.id}
                          role="button"
                          tabIndex={0}
                          className={`productCompetitorCandidate${selected?.id === candidate.id ? " isActive" : ""}`}
                          onClick={() => setSelectedId(candidate.id)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              setSelectedId(candidate.id);
                            }
                          }}
                        >
                          <span>
                            <strong>{candidate.title || candidate.url}</strong>
                            <a
                              className="productCompetitorCandidateUrl"
                              href={candidate.url}
                              target="_blank"
                              rel="noreferrer"
                              onClick={(event) => event.stopPropagation()}
                            >
                              {candidate.url}
                            </a>
                          </span>
                          <span className="productCompetitorCandidateMeta">
                            <b>{scoreLabel(candidate)}</b>
                            <small>{simProfileLabel(candidate.candidate_sim_profile)}</small>
                            <Badge tone={statusTone(candidate.status)}>{statusLabel(candidate.status)}</Badge>
                          </span>
                        </article>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            ) : (
              <EmptyState
                className="productCompetitorReadyState"
                title="Кандидатов на выбор нет"
                description="Для SKU уже есть подтвержденная ссылка. Можно сразу загрузить параметры, описание и медиа из нее."
                action={
                  <Button onClick={() => void enrichConfirmedLinks()} disabled={loading || running || enriching || !productId}>
                    {enriching ? "Загружаю…" : "Загрузить параметры и медиа"}
                  </Button>
                }
              />
            )}

            {selected ? (
              <div className="productCompetitorInspector">
                <div className="productCompetitorInspectorHead">
                  <div>
                    <span>{selected.source_name || selected.source_id}</span>
                    <strong>{selected.title || "Карточка конкурента"}</strong>
                  </div>
                  <Badge tone={statusTone(selected.status)}>{statusLabel(selected.status)}</Badge>
                </div>
                <a className="productCompetitorUrl" href={selected.url} target="_blank" rel="noreferrer">
                  {selected.url}
                </a>
                <div className="productCompetitorFacts">
                  <div><span>Точность</span><strong>{scoreLabel(selected)}</strong></div>
                  <div><span>SIM в товаре</span><strong>{simProfileLabel(selected.product_sim_profile)}</strong></div>
                  <div><span>SIM у конкурента</span><strong>{simProfileLabel(selected.candidate_sim_profile)}</strong></div>
                  <div><span>Последняя проверка</span><strong>{selected.last_seen_at ? new Date(selected.last_seen_at).toLocaleString("ru-RU") : "—"}</strong></div>
                  <div><span>{reasonCaption(selected)}</span><strong>{(selected.confidence_reasons || []).join(", ") || "—"}</strong></div>
                </div>
                {hasBlockingSimConflict(selected) ? (
                  <p className="productCompetitorInspectorText">
                    Подтверждение заблокировано: SIM-профиль товара и карточки конкурента распознаны и отличаются. Выберите другую карточку или отклоните этот вариант.
                  </p>
                ) : !String(selected.candidate_sim_profile || "").trim() ? (
                  <p className="productCompetitorInspectorText">
                    SIM у конкурента не распознан автоматически. Можно подтвердить вручную, если модель, память и цвет совпадают.
                  </p>
                ) : null}
                {selected.status === "needs_review" ? (
                  <div className="productCompetitorModeration">
                    <Button
                      variant="primary"
                      onClick={() => void moderate(selected, "approve")}
                      disabled={hasBlockingSimConflict(selected)}
                    >
                      {hasBlockingSimConflict(selected) ? "SIM не совпадает" : `Подтвердить ${sourceLabel(selected.source_id)}`}
                    </Button>
                    <Button variant="danger" onClick={() => void moderate(selected, "reject")}>
                      Отклонить {sourceLabel(selected.source_id)}
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : context?.confirmed_links.length ? (
              <div className="productCompetitorInspector">
                <div className="productCompetitorInspectorHead">
                  <div>
                    <span>Готово к насыщению</span>
                    <strong>Есть подтвержденные ссылки</strong>
                  </div>
                  <Badge tone="active">{context.confirmed_links.length}</Badge>
                </div>
                <p className="productCompetitorInspectorText">
                  Этот SKU не требует выбора кандидата. Следующий шаг — загрузить данные из подтвержденных карточек.
                </p>
              </div>
            ) : null}
          </div>
        ) : null}

        <details className="productCompetitorManual">
          <summary>
            <span>Ручная ссылка</span>
            <em>только если подбор ничего не нашел</em>
          </summary>
          <div>
            <div className="productWorkspaceMiniTitle">Fallback для контент-менеджера</div>
            <p>Основной сценарий — нажать «Найти карточки» и выбрать кандидата. Ссылку вручную добавляем только когда все варианты отклонены.</p>
          </div>
          <div className="productCompetitorManualForm">
            <select value={manualSource} onChange={(event) => setManualSource(event.target.value as "restore" | "store77")}>
              <option value="store77">store77</option>
              <option value="restore">re-store</option>
            </select>
            <input
              value={manualUrl}
              onChange={(event) => setManualUrl(event.target.value)}
              placeholder={manualSource === "store77" ? "https://store77.net/..." : "https://re-store.ru/..."}
            />
            <Button onClick={() => void addManualLink()} disabled={manualSubmitting || !manualUrl.trim()}>
              {manualSubmitting ? "Сохраняю…" : "Добавить"}
            </Button>
          </div>
        </details>

        {variant !== "compact" && context?.confirmed_links.length ? (
          <div className="productCompetitorConfirmed">
            <div className="productWorkspaceMiniTitle">Подтвержденные ссылки</div>
            {context.confirmed_links.map((link) => (
              <a key={`${link.source_id}-${link.url}`} href={link.url} target="_blank" rel="noreferrer">
                <span>{sourceLabel(link.source_id)}</span>
                <strong>{link.url}</strong>
                <em>{confirmedLinkTime(link)}</em>
              </a>
            ))}
          </div>
        ) : null}
      </div>
  );

  if (variant === "compact") return content;

  return (
    <Card title="Конкурентные карточки">
      {content}
    </Card>
  );
}
