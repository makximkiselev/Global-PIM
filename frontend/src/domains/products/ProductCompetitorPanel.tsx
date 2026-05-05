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
  candidate_id?: string;
  product_id?: string;
  source_id?: string;
  url?: string;
  status?: string;
  confirmed_at?: string;
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
  errors?: Array<{ source_id?: string; error?: string }>;
};

function scoreLabel(candidate: CompetitorCandidate): string {
  const raw = Number(candidate.confidence_score || 0);
  return Number.isFinite(raw) ? `${Math.round(raw * 100)}%` : "0%";
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

  const candidates = context?.items || [];
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
      setError(err instanceof Error ? err.message : "Не удалось загрузить competitor candidates");
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
      const response = await api<EnrichResp>(`/competitor-mapping/discovery/products/${encodeURIComponent(productId)}/enrich`, {
        method: "POST",
      });
      const sources = response.enriched_sources?.length ? response.enriched_sources.join(", ") : "нет";
      const errorsCount = response.errors?.length || 0;
      setEnrichNotice(
        `Источники: ${sources}. Совпало параметров: ${response.matched_count || 0}. Без пары: ${response.unmatched_count || 0}.${errorsCount ? ` Ошибок: ${errorsCount}.` : ""}`,
      );
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
      setEnrichNotice("Ссылка добавлена вручную и стала confirmed link. Pending candidates этого источника отклонены.");
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
            <div className="productWorkspaceMiniTitle">Product match review</div>
            <p>Найденные re-store/store77 candidates для текущего SKU. Подтверждение сохраняет связь с товаром.</p>
          </div>
          <div className="productCompetitorActions">
            <Button onClick={() => void load()} disabled={loading || running}>
              Обновить
            </Button>
            {context?.counts.confirmed_links ? (
              <Button onClick={() => void enrichConfirmedLinks()} disabled={loading || running || enriching || !productId}>
                {enriching ? "Загружаю…" : "Загрузить данные из ссылок"}
              </Button>
            ) : null}
            <Button variant="primary" onClick={() => void runDiscovery()} disabled={loading || running || !productId}>
              {running ? "Ищу…" : "Найти ссылки"}
            </Button>
          </div>
        </div>

        <div className="productCompetitorMetrics">
          <div><span>Candidates</span><strong>{context?.counts.total || 0}</strong></div>
          <div><span>На модерации</span><strong>{context?.counts.needs_review || 0}</strong></div>
          <div><span>Approved</span><strong>{context?.counts.approved || 0}</strong></div>
          <div><span>Устарело</span><strong>{context?.counts.stale || 0}</strong></div>
          <div><span>Links</span><strong>{context?.counts.confirmed_links || 0}</strong></div>
        </div>

        {lastRun ? (
          <div className="productCompetitorNotice">
            Последний запуск: {lastRun.status}, candidates: {(lastRun.created_count || 0) + (lastRun.updated_count || 0)}
          </div>
        ) : null}
        {enrichNotice ? <div className="productCompetitorNotice">{enrichNotice}</div> : null}
        {error ? <div className="productCompetitorError">{error}</div> : null}

        {loading ? (
          <EmptyState title="Загружаем competitors" description="Получаем candidates и confirmed links для SKU." />
        ) : candidates.length ? (
          <div className="productCompetitorWorkspace">
            <div className="productCompetitorList" aria-label="Competitor candidates">
              {candidateGroups.map((group) => (
                <section key={group.key} className="productCompetitorGroup">
                  <div className="productCompetitorGroupTitle">
                    <span>Группа вариантов</span>
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

            <div className="productCompetitorInspector">
              {selected ? (
                <>
                  <div className="productCompetitorInspectorHead">
                    <div>
                      <span>{selected.source_name || selected.source_id}</span>
                      <strong>{selected.title || "Candidate"}</strong>
                    </div>
                    <Badge tone={statusTone(selected.status)}>{statusLabel(selected.status)}</Badge>
                  </div>
                  <a className="productCompetitorUrl" href={selected.url} target="_blank" rel="noreferrer">
                    {selected.url}
                  </a>
                  <div className="productCompetitorFacts">
                    <div><span>Score</span><strong>{scoreLabel(selected)}</strong></div>
                    <div><span>SIM в PIM</span><strong>{simProfileLabel(selected.product_sim_profile)}</strong></div>
                    <div><span>SIM candidate</span><strong>{simProfileLabel(selected.candidate_sim_profile)}</strong></div>
                    <div><span>Последняя проверка</span><strong>{selected.last_seen_at ? new Date(selected.last_seen_at).toLocaleString("ru-RU") : "—"}</strong></div>
                    <div><span>Evidence</span><strong>{(selected.confidence_reasons || []).join(", ") || "—"}</strong></div>
                  </div>
                  {selected.status === "needs_review" ? (
                    <div className="productCompetitorModeration">
                      <Button variant="primary" onClick={() => void moderate(selected, "approve")}>
                        Подтвердить
                      </Button>
                      <Button variant="danger" onClick={() => void moderate(selected, "reject")}>
                        Отклонить
                      </Button>
                    </div>
                  ) : null}
                </>
              ) : (
                <EmptyState title="Candidate не выбран" description="Выбери строку слева." />
              )}
            </div>
          </div>
        ) : (
          <EmptyState title="Candidates пока нет" description="Запусти поиск по re-store и store77 для этого SKU." />
        )}

        <div className="productCompetitorManual">
          <div>
            <div className="productWorkspaceMiniTitle">Ручная ссылка</div>
            <p>Если все варианты отклонены, content manager вставляет точную карточку. Pending candidates этого источника будут отклонены автоматически.</p>
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
        </div>

        {context?.confirmed_links.length ? (
          <div className="productCompetitorConfirmed">
            <div className="productWorkspaceMiniTitle">Confirmed links</div>
            {context.confirmed_links.map((link) => (
              <a key={`${link.source_id}-${link.url}`} href={link.url} target="_blank" rel="noreferrer">
                <span>{link.source_id}</span>
                <strong>{link.url}</strong>
              </a>
            ))}
          </div>
        ) : null}
      </div>
    </Card>
  );
}
