import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Card from "../../components/ui/Card";
import Alert from "../../components/ui/Alert";
import Badge from "../../components/ui/Badge";
import { api } from "../../lib/api";
import { useAuth } from "../../app/auth/AuthContext";
import { useOrgPath } from "../../app/orgRoutes";

type StatsSummary = {
  categories: number;
  products: number;
  templates: number;
  connectors_configured: number;
  connectors_total: number;
  mapping_issues?: {
    count: number;
    items: MappingIssue[];
  };
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

type MappingIssue = {
  id: string;
  type: string;
  title: string;
  text: string;
  to: string;
  provider_title?: string;
  category_name?: string;
  category_path?: string;
  changed_count?: number;
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

function platformWord(count: number) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return "площадка";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "площадки";
  return "площадок";
}

export default function DashboardFeature() {
  const { loading: authLoading, authenticated } = useAuth();
  const orgPath = useOrgPath();
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
          setLoadError("Сводка не ответила вовремя. Экран открыт с базовыми данными.");
        } else if (error instanceof Error && error.message === "AUTH_REQUIRED") {
          setLoadError("Сессия истекла. Нужно войти заново.");
        } else {
          setLoadError("Сводка временно недоступна. Экран открыт с базовыми данными.");
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
      title: "Сопоставления",
      text: "Категории площадок, конкуренты, параметры и значения.",
      to: "/sources?tab=sources",
      value: stats ? `${Number(stats.mapping_issues?.count || 0)}` : "—",
    },
  ];

  const missingConnectors = stats ? Math.max(0, stats.connectors_total - stats.connectors_configured) : 0;
  const connectorIssue =
    stats && stats.connectors_total > 0 && missingConnectors > 0
      ? `${missingConnectors} ${platformWord(missingConnectors)} ${missingConnectors === 1 ? "требует" : "требуют"} настройки`
      : stats && stats.connectors_total === 0
        ? "Площадки еще не подключены"
        : "Площадки готовы к обмену";
  const mappingIssues = stats?.mapping_issues?.items || [];
  const mappingIssuesCount = Number(stats?.mapping_issues?.count || 0);

  const quickActions: QuickAction[] = [
    {
      title: "Создать товар",
      text: "Завести новый SKU и сразу перейти к наполнению карточки.",
      to: "/products/new",
      label: "Новый SKU",
    },
    {
      title: "Открыть импорт",
      text: "Загрузить Excel и создать или обновить товары в каталоге.",
      to: "/catalog/exchange?tab=import",
      label: "Импорт",
    },
    {
      title: "Сопоставить параметры",
      text: "Проверить связи категорий, полей и значений для площадок.",
      to: "/sources?tab=sources",
      label: "Сопоставления",
    },
    {
      title: "Проверить площадки",
      text: "Посмотреть подключение источников и ошибки перед выгрузкой.",
      to: "/connectors/status?tab=marketplaces",
      label: "Источники",
    },
  ];

  return (
    <div className="dashboard-page page-shell controlCenterPage">
      <header className="controlCenterCommandHeader">
        <div className="controlCenterCommandContext">
          <span>Рабочая панель</span>
          <h1>Операционная сводка</h1>
          <p>Быстрый вход в товары, каталог, источники, сопоставления и подготовку к выгрузке.</p>
        </div>
        <div className="controlCenterCommandControls">
          <Link className="btn" to={orgPath("/products")}>
            Открыть товары
          </Link>
          <Link className="btn primary" to={orgPath("/products/new")}>
            Создать товар
          </Link>
        </div>
      </header>

      {loadError ? <Alert tone="error">Не удалось загрузить сводку: {loadError}</Alert> : null}

      <section className="controlCenterStatusStrip" aria-label="Состояние рабочего контура">
        <div>
          <span>Категории</span>
          <strong>{stats ? stats.categories : "—"}</strong>
          <em>структура каталога</em>
        </div>
        <div>
          <span>Товары</span>
          <strong>{stats ? stats.products : "—"}</strong>
          <em>рабочие SKU</em>
        </div>
        <div>
          <span>Параметры</span>
          <strong>{stats ? stats.templates : "—"}</strong>
          <em>категорий с моделью</em>
        </div>
        <div>
          <span>Площадки</span>
          <strong>{connectorsLabel}</strong>
          <em>готовы к обмену</em>
        </div>
      </section>

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
              <QueueCard key={item.title} item={{ ...item, to: orgPath(item.to) }} />
            ))}
          </div>
        </Card>

        <Card className="controlCenterPanel">
          <div className="controlCenterPanelHead">
            <div>
              <div className="controlCenterEyebrow">Площадки</div>
              <div className="controlCenterPanelTitle">Что требует внимания сейчас</div>
            </div>
            <Badge tone={stats && stats.connectors_total > stats.connectors_configured ? "danger" : "active"}>
              {stats && stats.connectors_total > stats.connectors_configured ? "Требует проверки" : "Стабильно"}
            </Badge>
          </div>
          <div className="controlCenterIssueStack">
            {mappingIssues.length ? (
              <div className="controlCenterIssueCard controlCenterIssueCardAccent">
                <div className="controlCenterIssueTitle">Сопоставления требуют действия</div>
                <div className="controlCenterIssueText">
                  {mappingIssuesCount} {mappingIssuesCount === 1 ? "задача" : "задач"} по категориям и параметрам перед выгрузкой.
                </div>
                <div className="controlCenterIssueLinks">
                  {mappingIssues.slice(0, 3).map((issue) => (
                    <Link key={issue.id} className="controlCenterIssueLink" to={orgPath(issue.to)}>
                      <span>{issue.title}</span>
                      <small>{issue.category_name || issue.category_path || "Открыть категорию"}</small>
                    </Link>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="controlCenterIssueCard">
              <div className="controlCenterIssueTitle">Состояние площадок</div>
              <div className="controlCenterIssueText">{connectorIssue}</div>
            </div>
            <div className="controlCenterIssueCard">
              <div className="controlCenterIssueTitle">Следующий шаг</div>
              <div className="controlCenterIssueText">
                Проверь подключение площадок и сопоставление параметров до следующей выгрузки.
              </div>
            </div>
            <Link className="btn" to={orgPath("/connectors/status?tab=marketplaces")}>
              Открыть источники
            </Link>
          </div>
        </Card>
      </section>

      <section className="controlCenterSecondaryGrid">
        <Card className="controlCenterPanel">
          <div className="controlCenterPanelHead">
            <div>
              <div className="controlCenterEyebrow">Готовность</div>
              <div className="controlCenterPanelTitle">Готовность рабочего контура</div>
            </div>
          </div>
          <div className="controlCenterReadinessList">
            <div><span>Каталог</span><strong>{stats ? `${stats.categories}` : "—"}</strong><em>категорий готовы к рабочему контексту</em></div>
            <div><span>Параметры</span><strong>{stats ? `${stats.templates}` : "—"}</strong><em>категорий с утвержденными полями</em></div>
            <div><span>Площадки</span><strong>{connectorsLabel}</strong><em>площадок в рабочем контуре</em></div>
          </div>
        </Card>

        <Card className="controlCenterPanel">
          <div className="controlCenterPanelHead">
            <div>
              <div className="controlCenterEyebrow">Операции</div>
              <div className="controlCenterPanelTitle">Импорт, экспорт и сопоставления</div>
            </div>
          </div>
          <div className="controlCenterOperations">
            <Link className="controlCenterOperationRow" to={orgPath("/catalog/exchange?tab=import")}>
              <div>
                <strong>Импорт каталога</strong>
                <small>Загрузка Excel и импорт в товары.</small>
              </div>
              <span>Импорт</span>
            </Link>
            <Link className="controlCenterOperationRow" to={orgPath("/catalog/exchange?tab=export")}>
              <div>
                <strong>Экспорт данных</strong>
                <small>Выгрузка подготовленных данных и контроль ошибок.</small>
              </div>
              <span>Экспорт</span>
            </Link>
            <Link className="controlCenterOperationRow" to={orgPath("/sources?tab=sources")}>
              <div>
                <strong>Сопоставления</strong>
                <small>Связка категорий, параметров, значений и источников.</small>
              </div>
              <span>Открыть</span>
            </Link>
          </div>
        </Card>
      </section>

      <section className="controlCenterQuickActionsGrid">
        {quickActions.map((action) => (
          <QuickActionCard key={action.title} action={{ ...action, to: orgPath(action.to) }} />
        ))}
      </section>
    </div>
  );
}
