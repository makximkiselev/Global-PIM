import { useQuery } from "@tanstack/react-query";
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

export default function SystemStatusFeature() {
  const statusQuery = useQuery<OpsStatusResp>({
    queryKey: ["ops", "status"],
    queryFn: () => api<OpsStatusResp>("/ops/status"),
    refetchInterval: 30_000,
  });
  const data = statusQuery.data;
  const sections = data?.sections || {};
  const workflowRows = sections.workflows?.summary || [];
  const workflowRecent = sections.workflows?.recent || [];
  const tableRows = sections.table_sizes?.rows || [];
  const driftRows = [...(sections.db_grants?.drift || []), ...(sections.db_grants?.function_drift || [])];

  return (
    <div className="opsStatusPage">
      <PageHeader
        title="Состояние системы"
        subtitle="Операционный экран для релиза, прав БД, workflow-задач, медиа и роста данных."
        actions={<Button onClick={() => void statusQuery.refetch()} disabled={statusQuery.isFetching}>Обновить</Button>}
      />

      {statusQuery.error ? (
        <div className="opsStatusError">{(statusQuery.error as Error).message || "Не удалось загрузить статус."}</div>
      ) : null}

      <section className="opsStatusHero">
        <div>
          <span>Общий статус</span>
          <h2>{statusLabel(data?.status || (statusQuery.isLoading ? "warn" : "critical"))}</h2>
          <p>{statusQuery.isLoading ? "Загружаем диагностику." : "Проверка обновляется автоматически каждые 30 секунд."}</p>
        </div>
        <Badge tone={statusTone(data?.status)}>{data?.ok ? "Можно работать" : "Нужно вмешательство"}</Badge>
      </section>

      <section className="opsStatusGrid">
        <SectionCard section={sections.db_grants} />
        <SectionCard section={sections.storage} />
        <SectionCard section={sections.workflows} />
        <SectionCard section={sections.table_sizes} />
      </section>

      <section className="opsStatusActions">
        <Link to="/connectors/status?tab=marketplaces">Коннекторы и магазины</Link>
        <Link to="/sources?tab=categories">Сопоставления категорий</Link>
        <Link to="/catalog/exchange?tab=export">Экспорт товаров</Link>
        <Link to="/admin/access">Права и роли</Link>
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
      </section>
    </div>
  );
}
