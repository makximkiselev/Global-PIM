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

type AiSuggestionAction = "map_existing" | "create_attribute" | "ignore";

type AiSuggestion = {
  id: string;
  source_id: "restore" | "store77";
  source_name: string;
  raw_value: string;
  action: AiSuggestionAction;
  target_code?: string;
  target_name?: string;
  target_source?: string;
  confidence?: number;
  reason?: string;
  status?: string;
};

type AiSuggestionsResp = {
  ok: boolean;
  mode: "llm" | "rules" | "empty" | string;
  model?: string;
  summary: {
    total: number;
    map_existing: number;
    create_attribute: number;
    ignore: number;
  };
  items: AiSuggestion[];
  warnings?: string[];
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

function aiActionLabel(action: AiSuggestionAction): string {
  if (action === "map_existing") return "Связать";
  if (action === "create_attribute") return "Создать поле";
  return "Игнорировать";
}

function aiActionTone(action: AiSuggestionAction): "active" | "pending" | "neutral" {
  if (action === "map_existing") return "active";
  if (action === "create_attribute") return "pending";
  return "neutral";
}

function aiConfidenceLabel(value?: number): string {
  const raw = Number(value || 0);
  if (!Number.isFinite(raw) || raw <= 0) return "—";
  return `${Math.round(raw * 100)}%`;
}

export default function ProductCompetitorPanel({
  productId,
  onEnriched,
}: {
  productId: string;
  onEnriched?: () => void | Promise<void>;
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
  const [aiLoading, setAiLoading] = useState(false);
  const [aiSuggestions, setAiSuggestions] = useState<AiSuggestionsResp | null>(null);

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

  async function load() {
    if (!productId) return;
    setError("");
    setLoading(true);
    try {
      const response = await api<ProductCompetitorResp>(`/competitor-mapping/discovery/products/${encodeURIComponent(productId)}`);
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
      const sources = (context?.sources || []).map((source) => source.id);
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
      setAiSuggestions(null);
      await load();
      await onEnriched?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить данные из подтвержденных ссылок");
    } finally {
      setEnriching(false);
    }
  }

  async function loadAiSuggestions() {
    setError("");
    setAiLoading(true);
    try {
      const response = await api<AiSuggestionsResp>(`/competitor-mapping/discovery/products/${encodeURIComponent(productId)}/ai-suggestions`, {
        method: "POST",
      });
      setAiSuggestions(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось разобрать незамапленные характеристики");
    } finally {
      setAiLoading(false);
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

  return (
    <Card title="Конкурентные карточки">
      <div className="productCompetitorPanel">
        <div className="productCompetitorToolbar">
          <div>
            <div className="productWorkspaceMiniTitle">Сопоставление с конкурентами</div>
            <p>Найденные карточки re-store/store77 для текущего SKU. Подтверждение сохраняет связь с товаром и открывает загрузку параметров, описания и медиа.</p>
          </div>
          <div className="productCompetitorActions">
            <Button onClick={() => void load()} disabled={loading || running}>
              Обновить
            </Button>
            {context?.counts.confirmed_links ? (
              <Button onClick={() => void enrichConfirmedLinks()} disabled={loading || running || enriching || !productId}>
                {enriching ? "Загружаю…" : "Загрузить параметры и медиа"}
              </Button>
            ) : null}
            {context?.counts.confirmed_links ? (
              <Button onClick={() => void loadAiSuggestions()} disabled={loading || running || enriching || aiLoading || !productId}>
                {aiLoading ? "Разбираю…" : "AI разобрать остатки"}
              </Button>
            ) : null}
            <Button variant="primary" onClick={() => void runDiscovery()} disabled={loading || running || !productId}>
              {running ? "Ищу…" : "Найти карточки"}
            </Button>
          </div>
        </div>

        <div className="productCompetitorMetrics">
          <div><span>Найдено</span><strong>{context?.counts.total || 0}</strong></div>
          <div><span>На модерации</span><strong>{context?.counts.needs_review || 0}</strong></div>
          <div><span>Подтверждено</span><strong>{context?.counts.approved || 0}</strong></div>
          <div><span>Устарело</span><strong>{context?.counts.stale || 0}</strong></div>
          <div><span>Готовых ссылок</span><strong>{context?.counts.confirmed_links || 0}</strong></div>
        </div>

        {context?.source_summaries?.length ? (
          <div className="productCompetitorSourceGrid" aria-label="Статус конкурентных источников">
            {context.source_summaries.map((summary) => (
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

        {aiSuggestions ? (
          <div className="productCompetitorAiQueue">
            <div className="productCompetitorAiHead">
              <div>
                <div className="productWorkspaceMiniTitle">AI-разбор незамапленных характеристик</div>
                <p>Это черновик для контент-менеджера: AI предлагает связать поле, создать глобальный атрибут или игнорировать мусор. Автоматически ничего не применяется.</p>
              </div>
              <div className="productCompetitorAiStats">
                <span><b>{aiSuggestions.summary.map_existing}</b> связать</span>
                <span><b>{aiSuggestions.summary.create_attribute}</b> создать</span>
                <span><b>{aiSuggestions.summary.ignore}</b> игнор</span>
              </div>
            </div>
            {aiSuggestions.warnings?.length ? (
              <div className="productCompetitorAiWarning">
                AI сейчас недоступен. Показаны безопасные предложения по правилам; их можно использовать как черновик для модели.
              </div>
            ) : null}
            {aiSuggestions.items.length ? (
              <div className="productCompetitorAiList">
                {aiSuggestions.items.slice(0, 10).map((item) => (
                  <div key={item.id} className={`productCompetitorAiItem is-${item.action}`}>
                    <div className="productCompetitorAiSource">
                      <Badge tone={aiActionTone(item.action)}>{aiActionLabel(item.action)}</Badge>
                      <span>{sourceLabel(item.source_id)}</span>
                      <strong>{item.source_name}</strong>
                      <em>{item.raw_value}</em>
                    </div>
                    <div className="productCompetitorAiTarget">
                      <span>{item.action === "ignore" ? "Решение" : "Цель"}</span>
                      <strong>{item.action === "ignore" ? "Не переносить в модель" : item.target_name || "Новое поле"}</strong>
                      <em>{item.reason || "—"} · уверенность {aiConfidenceLabel(item.confidence)}</em>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="Незамапленных характеристик нет" description="После загрузки конкурентов все найденные параметры уже связаны или данных нет." />
            )}
          </div>
        ) : null}

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
                        <button
                          key={candidate.id}
                          type="button"
                          className={`productCompetitorCandidate${selected?.id === candidate.id ? " isActive" : ""}`}
                          onClick={() => setSelectedId(candidate.id)}
                        >
                          <span>
                            <strong>{candidate.title || candidate.url}</strong>
                            <em>{candidate.url}</em>
                          </span>
                          <span className="productCompetitorCandidateMeta">
                            <b>{scoreLabel(candidate)}</b>
                            <small>{simProfileLabel(candidate.candidate_sim_profile)}</small>
                            <Badge tone={statusTone(candidate.status)}>{statusLabel(candidate.status)}</Badge>
                          </span>
                        </button>
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
                  <div><span>SIM в PIM</span><strong>{simProfileLabel(selected.product_sim_profile)}</strong></div>
                  <div><span>SIM у конкурента</span><strong>{simProfileLabel(selected.candidate_sim_profile)}</strong></div>
                  <div><span>Последняя проверка</span><strong>{selected.last_seen_at ? new Date(selected.last_seen_at).toLocaleString("ru-RU") : "—"}</strong></div>
                  <div><span>{reasonCaption(selected)}</span><strong>{(selected.confidence_reasons || []).join(", ") || "—"}</strong></div>
                </div>
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
        ) : (
          <EmptyState title="Карточки пока не найдены" description="Запустите поиск по re-store и store77 для этого SKU." />
        )}

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

        {context?.confirmed_links.length ? (
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
    </Card>
  );
}
