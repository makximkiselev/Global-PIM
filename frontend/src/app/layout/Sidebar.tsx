import { NavLink } from "react-router-dom";

function Item({
  to,
  icon,
  label,
  end,
}: {
  to: string;
  icon: string;
  label: string;
  end?: boolean;
}) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => (isActive ? "active" : "")}>
      <span style={{ width: 18, textAlign: "center" }}>{icon}</span>
      {label}
    </NavLink>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="nav-section">
      <div className="nav-title">{title}</div>
      <div className="nav-list">{children}</div>
    </div>
  );
}

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="logo" />
        <div>
          <div className="brand-title">GT PIM</div>
        </div>
      </div>

      <nav className="nav">
        <Section title="Основное">
          <Item to="/" icon="🏠" label="Главная" />
        </Section>

        <Section title="Каталог">
          <Item to="/catalog" icon="🗂️" label="Каталог" end />
          <Item to="/products" icon="📦" label="Товары" end />
          <Item to="/catalog/import" icon="📥" label="Импорт" />
          <Item to="/catalog/export" icon="📤" label="Экспорт" />
          <Item to="/catalog/groups" icon="🧷" label="Группы товаров" />
        </Section>

        <Section title="Мастер-шаблоны">
          <Item to="/templates" icon="🧩" label="Мастер-шаблоны" />
          <Item to="/dictionaries" icon="📚" label="Параметры" />
        </Section>

        <Section title="Коннекторы">
          <Item to="/sources-mapping" icon="🧭" label="Маппинг источников" />
          <Item to="/connectors/status" icon="🟡" label="Статус коннекторов" />
        </Section>

        <Section title="Картинки">
          <Item to="/images/infographics" icon="🖼️" label="Генерация инфографики" />
        </Section>

        <Section title="Статистика">
          <Item to="/stats/card-quality" icon="📈" label="Качество карточек" />
          <Item to="/stats/marketplace-quality" icon="🧪" label="Качество на маркетплейсах" />
        </Section>
      </nav>
    </aside>
  );
}
