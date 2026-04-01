import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import "../styles/app.css"; // ✅ гарантируем базовые стили
import { api } from "../lib/api";

type StatsSummary = {
  categories: number;
  products: number;
  templates: number;
  connectors_configured: number;
  connectors_total: number;
};

export default function Dashboard() {
  const [stats, setStats] = useState<StatsSummary | null>(null);

  useEffect(() => {
    let alive = true;
    api<{ ok: boolean } & StatsSummary>("/stats/summary")
      .then((res) => {
        if (alive) setStats(res);
      })
      .catch(() => {
        if (alive) setStats(null);
      });
    return () => {
      alive = false;
    };
  }, []);

  const connectorsLabel = stats
    ? stats.connectors_total > 0
      ? `${stats.connectors_configured} / ${stats.connectors_total}`
      : `${stats.connectors_configured}`
    : "—";

  return (
    <div className="dashboard-page page">
      <div className="card dashboard-hero">
        <div className="hero-left">
          <div className="h1">Панель управления</div>
          <div className="sub">Каталог, шаблоны, коннекторы и качество</div>
          <div className="hero-actions">
            <div className="search">
              <span style={{ color: "var(--muted)" }}>🔎</span>
              <input placeholder="Поиск: товар, SKU, категория…" />
            </div>
            <Link className="btn primary" to="/products/new">
              ➕ Добавить товар
            </Link>
          </div>
        </div>

        <div className="hero-stats">
          <div className="stat-card">
            <div className="stat-label">Категории</div>
            <div className="stat-value">{stats ? stats.categories : "—"}</div>
            <div className="stat-sub">структура и узлы</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Товары</div>
            <div className="stat-value">{stats ? stats.products : "—"}</div>
            <div className="stat-sub">в работе и готовые</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Коннекторы</div>
            <div className="stat-value">{connectorsLabel}</div>
            <div className="stat-sub">настроено</div>
          </div>
        </div>
      </div>

      <div className="dash-grid">
        <div className="card dash-section">
          <div className="dash-title">Быстрые действия</div>
          <div className="dash-list">
            <Link className="dash-item" to="/products/new">
              <span>➕</span>
              <div>
                <div className="dash-item-title">Создать товар</div>
                <div className="dash-item-sub">карточка + SKU</div>
              </div>
            </Link>
            <div className="dash-item">
              <span>⬆️</span>
              <div>
                <div className="dash-item-title">Импорт товаров</div>
                <div className="dash-item-sub">скоро: XLS/CSV</div>
              </div>
            </div>
            <div className="dash-item">
              <span>✅</span>
              <div>
                <div className="dash-item-title">Проверить качество</div>
                <div className="dash-item-sub">скоро: правила контроля</div>
              </div>
            </div>
          </div>
        </div>

        <div className="card dash-section">
          <div className="dash-title">Качество</div>
          <div className="dash-metric">
            <div>
              <div className="dash-item-title">Качество карточек</div>
              <div className="dash-item-sub">готовность и заполненность</div>
            </div>
            <Link className="btn" to="/stats/card-quality">
              Открыть
            </Link>
          </div>
          <div className="dash-metric">
            <div>
              <div className="dash-item-title">Качество на маркетплейсах</div>
              <div className="dash-item-sub">соответствие требованиям</div>
            </div>
            <Link className="btn" to="/stats/marketplace-quality">
              Открыть
            </Link>
          </div>
        </div>

        <div className="card dash-section">
          <div className="dash-title">Коннекторы</div>
          <div className="dash-metric">
            <div>
              <div className="dash-item-title">Маппинг источников</div>
              <div className="dash-item-sub">маркетплейсы и конкуренты</div>
            </div>
            <Link className="btn" to="/sources-mapping">
              Открыть
            </Link>
          </div>
          <div className="dash-metric">
            <div>
              <div className="dash-item-title">Статус коннекторов</div>
              <div className="dash-item-sub">подключения и ошибки</div>
            </div>
            <Link className="btn" to="/connectors/status">
              Открыть
            </Link>
          </div>
        </div>
      </div>

      <div className="card dash-note">
        <div className="dash-title">Статус разработки</div>
        <div className="dash-note-text">
          Сейчас делаем: главная → каталог → мастер‑шаблоны → товары → импорт →
          парсер → экспорт → генератор картинок.
        </div>
      </div>
    </div>
  );
}
