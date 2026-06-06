import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import PageHeader from "../../components/ui/PageHeader";
import "../../styles/ops-status.css";

type StatusTone = "ok" | "warn" | "critical" | string;
type OpsSection = {
  status: StatusTone;
  title: string;
  detail?: string;
  current_user?: string;
  drift?: Array<Record<string, unknown>>;
  function_drift?: Array<Record<string, unknown>>;
  s3_enabled?: boolean;
  organization_id?: string;
  labels?: Record<string, string>;
  summary?: Array<Record<string, unknown>>;
  recent?: Array<Record<string, unknown>>;
  rows?: Array<Record<string, unknown>>;
  totals?: Record<string, unknown>;
  items?: Array<Record<string, unknown>>;
  providers?: Array<Record<string, unknown>>;
  errors?: Array<Record<string, unknown>>;
};
type OpsStatusResp = {
  ok: boolean;
  status: StatusTone;
  sections: Record<string, OpsSection>;
};

const STATUS_LABELS: Record<string, string> = {
  ok: "Готово",
  warn: "Проверить",
  critical: "Критично",
};

function statusTone(status?: StatusTone): "active" | "pending" | "danger" | "neutral" {
  if (status === "ok") return "active";
  if (status === "warn") return "pending";
  if (status === "critical") return "danger";
  return "neutral";
}

function statusLabel(status?: StatusTone) {
  return STATUS_LABELS[String(status || "")] || "Неизвестно";
}

function formatBytes(value: unknown) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n <= 0) return "0 Б";
  const units = ["Б", "КБ", "МБ", "ГБ", "ТБ"];
  let size = n;
  let idx = 0;
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx += 1;
  }
  return `${size.toFixed(size >= 10 || idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function formatDate(value: unknown) {
  if (!value) return "—";
  const d = new Date(String(value));
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("ru-RU");
}

function formatMetric(value: unknown) {
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  if (typeof value === "number") return value.toLocaleString("ru-RU");
  if (typeof value === "string" && value.length) return value;
  return "0";
}

function metricEntries(section?: OpsSection) {
  return Object.entries(section?.totals || {}).filter(([_, value]) => typeof value !== "object").slice(0, 6);
}

function SectionCard({ section }: { section?: OpsSection }) {
  if (!section) return null;
  return (
    <Card className="opsStatusCard">
      <div className="opsStatusCardHead">
        <div>
          <h3>{section.title}</h3>
          <p>{section.detail || "Нет деталей."}</p>
        </div>
        <Badge tone={statusTone(section.status)}>{statusLabel(section.status)}</Badge>
      </div>
    </Card>
  );
}

function MetricStrip({ section }: { section?: OpsSection }) {
  const entries = metricEntries(section);
  if (!entries.length) return null;
  return (
    <div className="opsStatusMetrics">
      {entries.map(([key, value]) => (
        <div className="opsStatusMetric" key={key}>
          <span>{key.replaceAll("_", " ")}</span>
          <strong>{formatMetric(value)}</strong>
        </div>
      ))}
    </div>
  );
}

function IssueList({ items, empty }: { items?: Array<Record<string, unknown>>; empty: string }) {
  const rows = items || [];
  if (!rows.length) return <p className="opsStatusEmpty">{empty}</p>;
  return (
    <div className="opsStatusList">
      {rows.slice(0, 18).map((row, idx) => {
        const href = String(row.href || "");
        const title = String(row.title || row.field || row.command || "Пункт");
        const issue = String(row.issue || row.command || row.error || "");
        const body = (
          <>
            <div>
              <strong>{title}</strong>
              {row.field ? <span>{String(row.field)}</span> : null}
              {issue ? <span>{issue}</span> : null}
            </div>
            <Badge tone={row.type === "workflow" || row.type === "media" ? "pending" : "neutral"}>{String(row.type || row.status || "check")}</Badge>
          </>
        );
        return href ? (
          <Link className="opsStatusListItem opsStatusListLink" to={href} key={`${title}-${idx}`}>
            {body}
          </Link>
        ) : (
          <div className="opsStatusListItem" key={`${title}-${idx}`}>
            {body}
          </div>
        );
      })}
    </div>
  );
}

export default function SystemStatusFeature() {
  const [data, setData] = useState<OpsStatusResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState("");
  const loadStatus = useCallback(async () => {
    setFetching(true);
    setError("");
    try {
      setData(await api<OpsStatusResp>("/ops/status"));
    } catch (e) {
      setError((e as Error).message || "Не удалось загрузить статус.");
    } finally {
      setLoading(false);
      setFetching(false);
    }
  }, []);
  useEffect(() => {
    void loadStatus();
    const timer = window.setInterval(() => void loadStatus(), 30_000);
    return () => window.clearInterval(timer);
  }, [loadStatus]);
  const sections = data?.sections || {};
  const workflowRows = sections.workflows?.summary || [];
  const workflowRecent = sections.workflows?.recent || [];
  const tableRows = sections.table_sizes?.rows || [];
  const driftRows = [...(sections.db_grants?.drift || []), ...(sections.db_grants?.function_drift || [])];
  const marketplaceProviders = sections.marketplaces?.providers || [];
  const marketplaceErrors = sections.marketplaces?.errors || [];
  const exportTargets = sections.export_targets?.rows || [];

  return (
    <div className="opsStatusPage">
      <PageHeader
        title="Состояние системы"
        subtitle="Операционный экран для релиза, прав БД, workflow-задач, медиа и роста данных."
        actions={<Button onClick={() => void loadStatus()} disabled={fetching}>Обновить</Button>}
      />

      {error ? (
        <div className="opsStatusError">{error}</div>
      ) : null}

      <section className="opsStatusHero">
        <div>
          <span>Общий статус</span>
          <h2>{statusLabel(data?.status || (loading ? "warn" : "critical"))}</h2>
          <p>{loading ? "Загружаем диагностику." : "Проверка обновляется автоматически каждые 30 секунд."}</p>
        </div>
        <Badge tone={statusTone(data?.status)}>{data?.ok ? "Можно работать" : "Нужно вмешательство"}</Badge>
      </section>

      <section className="opsStatusGrid">
        <SectionCard section={sections.db_grants} />
        <SectionCard section={sections.storage} />
        <SectionCard section={sections.marketplaces} />
        <SectionCard section={sections.export_targets} />
        <SectionCard section={sections.workflows} />
        <SectionCard section={sections.review_queue} />
        <SectionCard section={sections.lineage} />
        <SectionCard section={sections.ai_governance} />
        <SectionCard section={sections.access} />
        <SectionCard section={sections.info_model_versions} />
        <SectionCard section={sections.growth_controls} />
        <SectionCard section={sections.release_safety} />
        <SectionCard section={sections.auth_smoke} />
        <SectionCard section={sections.table_sizes} />
      </section>

      <section className="opsStatusActions">
        <Link to="/connectors/status?tab=marketplaces">Коннекторы и магазины</Link>
        <Link to="/sources?tab=categories">Сопоставления категорий</Link>
        <Link to="/catalog/exchange?tab=export">Экспорт товаров</Link>
        <Link to="/admin/access">Права и роли</Link>
      </section>

      <section className="opsStatusSplit">
        <Card title="Следующие проверки" className="opsStatusPanel">
          <MetricStrip section={sections.review_queue} />
          <IssueList items={sections.review_queue?.items} empty="Очередь проверки пуста." />
        </Card>

        <Card title="Lineage товаров" className="opsStatusPanel">
          <MetricStrip section={sections.lineage} />
          <IssueList items={sections.lineage?.items} empty="Явных разрывов lineage на выборке не найдено." />
        </Card>
      </section>

      <section className="opsStatusSplit">
        <Card title="Магазины площадок" className="opsStatusPanel">
          {marketplaceProviders.length ? (
            <div className="opsStatusMarketplaceList">
              {marketplaceProviders.map((provider) => {
                const stores = Array.isArray(provider.stores) ? provider.stores : [];
                return (
                  <div className="opsStatusMarketplace" key={String(provider.provider || provider.title)}>
                    <div className="opsStatusMarketplaceHead">
                      <strong>{String(provider.title || provider.provider || "Площадка")}</strong>
                      <span>{stores.length} магазинов</span>
                    </div>
                    {stores.length ? stores.map((store) => (
                      <div className="opsStatusStore" key={String(store.store_id || store.title)}>
                        <div>
                          <strong>{String(store.title || store.store_id || "Магазин")}</strong>
                          <span>{String(store.last_check_status || "idle")} · {formatDate(store.last_check_at)}</span>
                        </div>
                        <div className="opsStatusFlags">
                          <Badge tone={store.enabled ? "active" : "neutral"}>{store.enabled ? "Импорт" : "Без импорта"}</Badge>
                          <Badge tone={store.export_enabled ? "active" : "neutral"}>{store.export_enabled ? "Экспорт" : "Без экспорта"}</Badge>
                          <Badge tone={store.safe_test_enabled ? "pending" : "neutral"}>{store.safe_test_enabled ? "Safe-test" : "Не тестовый"}</Badge>
                        </div>
                      </div>
                    )) : <p className="opsStatusEmpty">Магазины не подключены.</p>}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="opsStatusEmpty">Данных по магазинам пока нет.</p>
          )}
        </Card>

        <Card title="Цели экспорта" className="opsStatusPanel">
          <MetricStrip section={sections.export_targets} />
          {exportTargets.length ? (
            <div className="opsStatusList">
              {exportTargets.map((row, idx) => (
                <Link className="opsStatusListItem opsStatusListLink" to={String(row.href || "/connectors/status?tab=marketplaces")} key={`${row.provider}-${row.store_id}-${idx}`}>
                  <div>
                    <strong>{String(row.provider_title || row.provider || "Площадка")} · {String(row.title || row.store_id || "Магазин")}</strong>
                    <span>{String(row.last_check_status || "idle")}</span>
                  </div>
                  <Badge tone={row.safe_test_enabled ? "pending" : "active"}>{row.safe_test_enabled ? "Safe-test" : "Экспорт"}</Badge>
                </Link>
              ))}
            </div>
          ) : (
            <p className="opsStatusEmpty">Магазины для экспорта не выбраны.</p>
          )}
        </Card>
      </section>

      <section className="opsStatusSplit">
        <Card title="Ошибки marketplace API" className="opsStatusPanel">
          {marketplaceErrors.length ? (
            <div className="opsStatusList">
              {marketplaceErrors.map((row, idx) => (
                <div className="opsStatusListItem" key={`${row.provider}-${row.scope}-${idx}`}>
                  <div>
                    <strong>{String(row.title || row.provider || "Ошибка")}</strong>
                    <span>{String(row.error || "Без текста ошибки")}</span>
                  </div>
                  <Badge tone="danger">{String(row.scope || "api")}</Badge>
                </div>
              ))}
            </div>
          ) : (
            <p className="opsStatusEmpty">Ошибок доступа и методов площадок не найдено.</p>
          )}
        </Card>

        <Card title="AI governance" className="opsStatusPanel">
          <MetricStrip section={sections.ai_governance} />
          {sections.ai_governance?.summary?.length ? (
            <div className="opsStatusTable">
              <div className="opsStatusTableHead">
                <span>Workflow</span>
                <span>Статус</span>
                <span>Кол-во</span>
                <span>Обновлено</span>
              </div>
              {sections.ai_governance.summary.map((row, idx) => (
                <div className="opsStatusTableRow" key={`${row.workflow}-${row.status}-${idx}`}>
                  <strong>{sections.ai_governance?.labels?.[String(row.workflow)] || String(row.workflow || "—")}</strong>
                  <Badge tone={statusTone(row.status === "failed" ? "critical" : row.status === "running" || row.status === "queued" ? "warn" : "ok")}>{String(row.status || "—")}</Badge>
                  <span>{String(row.count || 0)}</span>
                  <span>{formatDate(row.latest_at)}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="opsStatusEmpty">AI workflow пока не запускались.</p>
          )}
        </Card>
      </section>

      <section className="opsStatusSplit">
        <Card title="Workflow runs" className="opsStatusPanel">
          {workflowRows.length ? (
            <div className="opsStatusTable">
              <div className="opsStatusTableHead">
                <span>Workflow</span>
                <span>Статус</span>
                <span>Кол-во</span>
                <span>Обновлено</span>
              </div>
              {workflowRows.map((row, idx) => (
                <div className="opsStatusTableRow" key={`${row.workflow}-${row.status}-${idx}`}>
                  <strong>{sections.workflows?.labels?.[String(row.workflow)] || String(row.workflow || "—")}</strong>
                  <Badge tone={statusTone(row.status === "failed" ? "critical" : row.status === "running" || row.status === "queued" ? "warn" : "ok")}>{String(row.status || "—")}</Badge>
                  <span>{String(row.count || 0)}</span>
                  <span>{formatDate(row.latest_at)}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="opsStatusEmpty">Активных workflow-записей нет.</p>
          )}
        </Card>

        <Card title="Последние проблемные задачи" className="opsStatusPanel">
          {workflowRecent.length ? (
            <div className="opsStatusList">
              {workflowRecent.map((row, idx) => (
                <div className="opsStatusListItem" key={`${row.run_id}-${idx}`}>
                  <div>
                    <strong>{sections.workflows?.labels?.[String(row.workflow)] || String(row.workflow || "—")}</strong>
                    <span>{String(row.message || row.error || "Без сообщения")}</span>
                  </div>
                  <Badge tone={statusTone(row.status === "failed" ? "critical" : "warn")}>{String(row.status || "—")}</Badge>
                </div>
              ))}
            </div>
          ) : (
            <p className="opsStatusEmpty">Нет queued/running/failed задач.</p>
          )}
        </Card>
      </section>

      <section className="opsStatusSplit">
        <Card title="Крупные таблицы" className="opsStatusPanel">
          {tableRows.length ? (
            <div className="opsStatusTable">
              <div className="opsStatusTableHead">
                <span>Таблица</span>
                <span>Размер</span>
                <span>Данные</span>
                <span>Строки</span>
              </div>
              {tableRows.map((row, idx) => (
                <div className="opsStatusTableRow" key={`${row.table_name}-${idx}`}>
                  <strong>{String(row.table_name || "—")}</strong>
                  <span>{formatBytes(row.total_bytes)}</span>
                  <span>{formatBytes(row.table_bytes)}</span>
                  <span>{String(row.estimated_rows || 0)}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="opsStatusEmpty">Размеры таблиц пока не получены.</p>
          )}
        </Card>

        <Card title="Рост данных" className="opsStatusPanel">
          <MetricStrip section={sections.growth_controls} />
          <IssueList
            items={sections.growth_controls?.items?.map((row) => ({
              ...row,
              title: row.path,
              issue: `${formatBytes(row.payload_bytes)} · ${formatDate(row.updated_at)}`,
              type: "json",
            }))}
            empty="Крупных json-документов не найдено."
          />
        </Card>
      </section>

      <section className="opsStatusSplit">
        <Card title="Дрифт прав БД" className="opsStatusPanel">
          {driftRows.length ? (
            <div className="opsStatusList">
              {driftRows.slice(0, 12).map((row, idx) => (
                <div className="opsStatusListItem" key={`${row.relname || row.proname}-${idx}`}>
                  <div>
                    <strong>{String(row.relname || row.proname || "Объект")}</strong>
                    <span>owner: {String(row.owner || "—")}</span>
                  </div>
                  <Badge tone="pending">{String(row.relkind || "fn")}</Badge>
                </div>
              ))}
            </div>
          ) : (
            <p className="opsStatusEmpty">Дрифта владельцев не найдено. Текущий пользователь: {sections.db_grants?.current_user || "—"}.</p>
          )}
        </Card>

        <Card title="Доступ и роли" className="opsStatusPanel">
          <MetricStrip section={sections.access} />
          <IssueList items={sections.access?.items} empty="Пользователей с невалидными ролями не найдено." />
        </Card>
      </section>

      <section className="opsStatusSplit">
        <Card title="Версии инфо-моделей" className="opsStatusPanel">
          <MetricStrip section={sections.info_model_versions} />
          <IssueList items={sections.info_model_versions?.items} empty="Инфо-модели пока не найдены." />
        </Card>

        <Card title="Release safety" className="opsStatusPanel">
          <MetricStrip section={sections.release_safety} />
          <IssueList items={sections.release_safety?.items} empty="Чеклист релиза пуст." />
        </Card>

        <Card title="Authenticated smoke" className="opsStatusPanel">
          <MetricStrip section={sections.auth_smoke} />
          <IssueList items={sections.auth_smoke?.items} empty="Authenticated smoke не настроен." />
        </Card>
      </section>
    </div>
  );
}
