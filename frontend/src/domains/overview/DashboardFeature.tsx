import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import MetricGrid from "../../components/data/MetricGrid";
import Card from "../../components/ui/Card";
import PageHeader from "../../components/ui/PageHeader";
import Alert from "../../components/ui/Alert";
import Badge from "../../components/ui/Badge";
import { api } from "../../lib/api";
import { useAuth } from "../../app/auth/AuthContext";

type StatsSummary = {
  categories: number;
  products: number;
  templates: number;
  connectors_configured: number;
  connectors_total: number;
};

type QueueItem = {
  title: string;
  text: string;
  to: string;
  value: string;
};

type QuickAction = {
  title: string;
  text: string;
  to: string;
  label: string;
};

function QueueCard({ item }: { item: QueueItem }) {
  return (
    <Link className="controlCenterQueueCard" to={item.to}>
      <div className="controlCenterQueueValue">{item.value}</div>
      <div className="controlCenterQueueTitle">{item.title}</div>
      <div className="controlCenterQueueText">{item.text}</div>
    </Link>
  );
}

function QuickActionCard({ action }: { action: QuickAction }) {
  return (
    <Link className="controlCenterQuickAction" to={action.to}>
      <div className="controlCenterQuickActionTitle">{action.title}</div>
      <div className="controlCenterQuickActionText">{action.text}</div>
      <span className="controlCenterQuickActionLabel">{action.label}</span>
    </Link>
  );
}

export default function DashboardFeature() {
  const { loading: authLoading, authenticated } = useAuth();
  const [stats, setStats] = useState<StatsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string>("");

  useEffect(() => {
    if (authLoading) return;
    if (!authenticated) {
      setStats(null);
      setLoadError("");
      setLoading(false);
      return;
    }

    let alive = true;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort("SUMMARY_TIMEOUT"), 12000);

    async function loadSummary() {
      try {
        setLoading(true);
        setLoadError("");
        const res = await api<{ ok: boolean } & StatsSummary>("/stats/summary", {
          signal: controller.signal,
        });
        if (!alive) return;
        setStats(res);
        setLoadError("");
      } catch (error) {
        if (!alive) return;
        setStats(null);
        if (error instanceof Error && error.name === "AbortError") {
          setLoadError("Live summary не ответил вовремя. Экран открыт в fallback-режиме.");
        } else if (error instanceof Error && error.message === "AUTH_REQUIRED") {
          setLoadError("Сессия истекла. Нужно войти заново.");
        } else {
          setLoadError("Live summary временно недоступен. Экран открыт в fallback-режиме.");
        }
      } finally {
        window.clearTimeout(timeoutId);
        if (alive) setLoading(false);
      }
    }

    void loadSummary();

    return () => {
      alive = false;
      window.clearTimeout(timeoutId);
      controller.abort("SUMMARY_CLEANUP");
    };
  }, [authLoading, authenticated]);

  const connectorsLabel = stats
    ? stats.connectors_total > 0
      ? `${stats.connectors_configured} / ${stats.connectors_total}`
      : "0"
    : "—";

  const metricItems = [
    { label: "Категории", value: stats ? stats.categories : "—", meta: "структура каталога" },
    { label: "Товары", value: stats ? stats.products : "—", meta: "рабочие SKU" },
    { label: "Инфо-модели", value: stats ? stats.templates : "—", meta: "активные модели" },
    { label: "Каналы", value: connectorsLabel, meta: "подключено к контуру" },
  ];

  const queueItems: QueueItem[] = [
    {
      title: "Товарная очередь",
      text: "Основной вход в SKU, группы и проблемные карточки.",
      to: "/products",
      value: stats ? `${stats.products}` : "—",
    },
    {
      title: "Каталог категорий",
      text: "Структура, привязки и рабочий контекст категорий.",
      to: "/catalog",
      value: stats ? `${stats.categories}` : "—",
    },
    {
      title: "Инфо-модели",
      text: "Структура полей, группы и правила заполнения.",
      to: "/templates",
      value: stats ? `${stats.templates}` : "—",
    },
  ];

  const connectorIssue =
    stats && stats.connectors_total > 0 && stats.connectors_configured < stats.connectors_total
      ? `${stats.connectors_total - stats.connectors_configured} канал(ов) требует настройки`
      : stats && stats.connectors_total === 0
        ? "Каналы еще не подключены"
        : "Канальный контур подключен";

  const readinessItems = [
    {
      label: "Каталог",
      value: stats ? `${stats.categories}` : "—",
      meta: "категорий готовы к рабочему контексту",
    },
    {
      label: "Модели",
      value: stats ? `${stats.templates}` : "—",
      meta: "моделей можно использовать в товарах",
    },
    {
      label: "Коннекторы",
      value: connectorsLabel,
      meta: "каналов в операционном контуре",
    },
  ];

  const quickActions: QuickAction[] = [
    {
      title: "Создать товар",
      text: "Открыть новый SKU и сразу перейти в продуктовый workspace.",
      to: "/products/new",
      label: "Новый SKU",
    },
    {
      title: "Открыть импорт",
      text: "Запустить Excel/import flow и завести данные в товары.",
      to: "/catalog/import",
      label: "Import",
    },
    {
      title: "Проверить маппинг",
      text: "Открыть category и parameter mapping по каналам.",
      to: "/sources-mapping",
      label: "Mapping",
    },
    {
      title: "Проверить каналы",
      text: "Посмотреть состояние коннекторов и ошибки до выгрузки.",
      to: "/connectors/status",
      label: "Channels",
    },
  ];

  return (
    <div className="dashboard-page page-shell controlCenterPage">
      <PageHeader
        title="Control Center"
        subtitle="Рабочий центр каталога, товаров, каналов и операций. Отсюда команда входит в SKU, ошибки и публикацию."
        actions={
          <>
            <Link className="btn" to="/products">
              Открыть товары
            </Link>
            <Link className="btn primary" to="/products/new">
              Создать товар
            </Link>
          </>
        }
      />

      {loadError ? <Alert tone="error">Не удалось загрузить сводку: {loadError}</Alert> : null}

      <MetricGrid items={metricItems} className="controlCenterMetricGrid" />

      <section className="controlCenterPriorityGrid">
        <Card className="controlCenterPanel controlCenterPanelWide">
          <div className="controlCenterPanelHead">
            <div>
              <div className="controlCenterEyebrow">Рабочая очередь</div>
              <div className="controlCenterPanelTitle">Куда команда идет в работу</div>
            </div>
            <Badge tone={loading ? "pending" : "active"}>{loading ? "Загрузка" : "Активно"}</Badge>
          </div>
          <div className="controlCenterQueueGrid">
            {queueItems.map((item) => (
              <QueueCard key={item.title} item={item} />
            ))}
          </div>
        </Card>

        <Card className="controlCenterPanel">
          <div className="controlCenterPanelHead">
            <div>
              <div className="controlCenterEyebrow">Проблемы каналов</div>
              <div className="controlCenterPanelTitle">Что требует внимания сейчас</div>
            </div>
            <Badge tone={stats && stats.connectors_total > stats.connectors_configured ? "danger" : "active"}>
              {stats && stats.connectors_total > stats.connectors_configured ? "Требует проверки" : "Стабильно"}
            </Badge>
          </div>
          <div className="controlCenterIssueStack">
            <div className="controlCenterIssueCard">
              <div className="controlCenterIssueTitle">Состояние коннекторов</div>
              <div className="controlCenterIssueText">{connectorIssue}</div>
            </div>
            <div className="controlCenterIssueCard">
              <div className="controlCenterIssueTitle">Следующий шаг</div>
              <div className="controlCenterIssueText">
                Проверь подключение каналов и перейди в mapping до следующей выгрузки.
              </div>
            </div>
            <Link className="btn" to="/connectors/status">
              Открыть коннекторы
            </Link>
          </div>
        </Card>
      </section>

      <section className="controlCenterSecondaryGrid">
        <Card className="controlCenterPanel">
          <div className="controlCenterPanelHead">
            <div>
              <div className="controlCenterEyebrow">Readiness</div>
              <div className="controlCenterPanelTitle">Готовность рабочего контура</div>
            </div>
          </div>
          <MetricGrid items={readinessItems} className="controlCenterCompactMetrics" />
        </Card>

        <Card className="controlCenterPanel">
          <div className="controlCenterPanelHead">
            <div>
              <div className="controlCenterEyebrow">Операции</div>
              <div className="controlCenterPanelTitle">Импорт, экспорт и каналы</div>
            </div>
          </div>
          <div className="controlCenterOperations">
            <Link className="controlCenterOperationRow" to="/catalog/import">
              <div>
                <strong>Импорт каталога</strong>
                <small>Загрузка Excel и импорт в товары.</small>
              </div>
              <span>Import</span>
            </Link>
            <Link className="controlCenterOperationRow" to="/catalog/export">
              <div>
                <strong>Экспорт данных</strong>
                <small>Выгрузка подготовленных данных и контроль ошибок.</small>
              </div>
              <span>Export</span>
            </Link>
            <Link className="controlCenterOperationRow" to="/sources-mapping">
              <div>
                <strong>Sources / Mapping</strong>
                <small>Связка категорий, параметров и источников.</small>
              </div>
              <span>Open</span>
            </Link>
          </div>
        </Card>
      </section>

      <section className="controlCenterQuickActionsGrid">
        {quickActions.map((action) => (
          <QuickActionCard key={action.title} action={action} />
        ))}
      </section>
    </div>
  );
}
