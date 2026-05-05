import { useEffect, useMemo, useState } from "react";
import DataTable from "../../components/data/DataTable";
import InspectorPanel from "../../components/data/InspectorPanel";
import MetricGrid from "../../components/data/MetricGrid";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import EmptyState from "../../components/ui/EmptyState";
import { api } from "../../lib/api";

type Source = {
  id: "restore" | "store77";
  name: string;
  domain: string;
  status: string;
  parser_strategy?: string;
};

type Candidate = {
  id: string;
  product_id: string;
  product_title?: string;
  product_sku?: string;
  source_id: "restore" | "store77";
  source_name?: string;
  url: string;
  title?: string;
  confidence_score?: number;
  confidence_reasons?: string[];
  status: "needs_review" | "approved" | "rejected" | "stale" | string;
  last_seen_at?: string;
  reviewed_at?: string;
  rejection_reason?: string;
};

type SourcesResp = { ok: boolean; sources: Source[] };
type CandidatesResp = { ok: boolean; items: Candidate[]; count: number; sources: Source[] };
type DiscoveryRun = {
  id: string;
  scanned_products_count?: number;
  status: string;
  created_count?: number;
  updated_count?: number;
  errors_count?: number;
};
type RunResp = { ok: boolean; created_count: number; updated_count: number; errors_count: number; run: DiscoveryRun };
type RunStatusResp = { ok: boolean; run: DiscoveryRun };

function score(candidate: Candidate): string {
  const raw = Number(candidate.confidence_score || 0);
  if (!Number.isFinite(raw)) return "0%";
  return `${Math.round(raw * 100)}%`;
}

function statusTone(status: Candidate["status"]): "active" | "pending" | "danger" | "neutral" {
  if (status === "approved") return "active";
  if (status === "rejected") return "danger";
  if (status === "needs_review") return "pending";
  return "neutral";
}

function statusLabel(status: Candidate["status"]): string {
  if (status === "approved") return "Подтверждено";
  if (status === "rejected") return "Отклонено";
  if (status === "needs_review") return "На модерации";
  if (status === "stale") return "Устарело";
  return status || "—";
}

export default function CompetitorDiscoveryPanel() {
  const [sources, setSources] = useState<Source[]>([]);
  const [items, setItems] = useState<Candidate[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [lastRun, setLastRun] = useState<DiscoveryRun | null>(null);

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) || items[0] || null,
    [items, selectedId],
  );

  const counts = useMemo(() => {
    return {
      total: items.length,
      review: items.filter((item) => item.status === "needs_review").length,
      approved: items.filter((item) => item.status === "approved").length,
      rejected: items.filter((item) => item.status === "rejected").length,
    };
  }, [items]);

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [sourceResp, candidateResp] = await Promise.all([
        api<SourcesResp>("/competitor-mapping/discovery/sources"),
        api<CandidatesResp>("/competitor-mapping/discovery/candidates"),
      ]);
      setSources(sourceResp.sources || candidateResp.sources || []);
      setItems(candidateResp.items || []);
      setSelectedId((prev) => {
        if (prev && (candidateResp.items || []).some((item) => item.id === prev)) return prev;
        return (candidateResp.items || [])[0]?.id || "";
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить competitor discovery");
    } finally {
      setLoading(false);
    }
  }

  async function runDiscovery() {
    setError("");
    setRunning(true);
    try {
      const response = await api<RunResp>("/competitor-mapping/discovery/run", {
        method: "POST",
        body: JSON.stringify({ background: true, sources: sources.map((sourceItem) => sourceItem.id), limit: 50 }),
      });
      setLastRun(response.run);
      void pollRun(response.run.id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Не удалось запустить поиск";
      setError(message.includes("504") || message.includes("Gateway") ? "Поиск занял слишком много времени. Запусти меньший batch или переведи crawl в фоновые задачи." : message);
    } finally {
      setRunning(false);
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

  async function moderate(candidate: Candidate, action: "approve" | "reject") {
    setError("");
    try {
      await api(`/competitor-mapping/discovery/candidates/${encodeURIComponent(candidate.id)}/moderate`, {
        method: "POST",
        body: JSON.stringify(action === "approve" ? { action } : { action, reason: "Отклонено контент-менеджером" }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось обновить candidate");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="competitorDiscovery">
      <div className="competitorDiscoveryHeader">
        <div>
          <div className="sourcesMappingCanvasTitle">Очередь конкурентных ссылок</div>
          <div className="sourcesMappingCanvasSub">
            Система ищет карточки на re-store и store77, сопоставляет их с нашими SKU и отправляет candidates на модерацию.
          </div>
        </div>
        <div className="competitorDiscoveryActions">
          <Button onClick={() => void load()} disabled={loading || running}>
            Обновить
          </Button>
          <Button variant="primary" onClick={() => void runDiscovery()} disabled={running || loading || !sources.length}>
            {running ? "Ищу…" : "Запустить поиск"}
          </Button>
        </div>
      </div>

      <MetricGrid
        className="competitorDiscoveryMetrics"
        items={[
          { label: "Candidates", value: counts.total, meta: "все найденные ссылки" },
          { label: "На модерации", value: counts.review, meta: "нужно решение" },
          { label: "Approved", value: counts.approved, meta: "связано с товаром" },
          { label: "Rejected", value: counts.rejected, meta: "negative signal" },
        ]}
      />

      <div className="competitorDiscoverySources">
        {sources.map((source) => (
          <div key={source.id} className="competitorDiscoverySource">
            <div>
              <strong>{source.name}</strong>
              <span>{source.domain}</span>
            </div>
            <Badge tone={source.status === "active" ? "active" : "neutral"}>{source.parser_strategy || source.status}</Badge>
          </div>
        ))}
      </div>

      {lastRun ? (
        <div className="competitorDiscoveryNotice">
          Последний запуск: {lastRun.status}, товаров просканировано: {lastRun.scanned_products_count || 0}, candidates: {(lastRun.created_count || 0) + (lastRun.updated_count || 0)}
        </div>
      ) : null}
      {error ? <div className="competitorDiscoveryError">{error}</div> : null}

      <div className="competitorDiscoveryWorkspace">
        <div className="competitorDiscoveryTablePanel">
          {loading ? (
            <EmptyState title="Загружаем competitor queue" description="Подтягиваем sources и candidates." />
          ) : (
            <DataTable
              rows={items}
              rowKey={(row) => row.id}
              empty="Пока нет candidates. Запусти поиск по re-store и store77."
              gridTemplate="minmax(260px, 1.2fr) minmax(120px, .5fr) minmax(130px, .45fr) minmax(130px, .45fr)"
              columns={[
                {
                  key: "product",
                  label: "Товар / ссылка",
                  render: (row) => (
                    <button className="competitorDiscoveryRowButton" type="button" onClick={() => setSelectedId(row.id)}>
                      <strong>{row.product_title || row.title || row.product_id}</strong>
                      <span>{row.url}</span>
                    </button>
                  ),
                },
                {
                  key: "source",
                  label: "Источник",
                  render: (row) => <span>{row.source_name || row.source_id}</span>,
                },
                {
                  key: "score",
                  label: "Score",
                  render: (row) => <strong>{score(row)}</strong>,
                },
                {
                  key: "status",
                  label: "Статус",
                  render: (row) => <Badge tone={statusTone(row.status)}>{statusLabel(row.status)}</Badge>,
                },
              ]}
            />
          )}
        </div>

        <InspectorPanel
          title={selected ? "Candidate" : "Нет candidate"}
          subtitle={selected ? selected.url : "Запусти поиск или выбери строку в очереди."}
          className="competitorDiscoveryInspector"
          actions={
            selected?.status === "needs_review" ? (
              <div className="competitorDiscoveryInspectorActions">
                <Button variant="primary" onClick={() => void moderate(selected, "approve")}>
                  Подтвердить
                </Button>
                <Button variant="danger" onClick={() => void moderate(selected, "reject")}>
                  Отклонить
                </Button>
              </div>
            ) : null
          }
        >
          {selected ? (
            <div className="competitorDiscoveryFacts">
              <div><span>Товар</span><strong>{selected.product_title || selected.product_id}</strong></div>
              <div><span>SKU</span><strong>{selected.product_sku || "—"}</strong></div>
              <div><span>Источник</span><strong>{selected.source_name || selected.source_id}</strong></div>
              <div><span>Score</span><strong>{score(selected)}</strong></div>
              <div><span>Статус</span><Badge tone={statusTone(selected.status)}>{statusLabel(selected.status)}</Badge></div>
              <div><span>Последняя проверка</span><strong>{selected.last_seen_at ? new Date(selected.last_seen_at).toLocaleString("ru-RU") : "—"}</strong></div>
              {selected.rejection_reason ? <div><span>Причина</span><strong>{selected.rejection_reason}</strong></div> : null}
              <div className="competitorDiscoveryReasons">
                <span>Evidence</span>
                {(selected.confidence_reasons || []).length ? (
                  selected.confidence_reasons?.map((reason) => <em key={reason}>{reason}</em>)
                ) : (
                  <em>Evidence появится после discovery run.</em>
                )}
              </div>
            </div>
          ) : (
            <EmptyState title="Очередь пуста" description="Candidates появятся после discovery run." />
          )}
        </InspectorPanel>
      </div>
    </div>
  );
}
