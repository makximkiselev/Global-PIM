import { ReactNode, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { api } from "../../lib/api";

type NavItem = { href: string; label: string; page?: string };
type NavSection = { title: string; items: NavItem[] };
type NavGroup = { title: string; items?: NavItem[]; sections?: NavSection[] };

const groups: NavGroup[] = [
  {
    title: "Главная",
    items: [{ href: "/", label: "Дашборд", page: "dashboard" }],
  },
  {
    title: "Каталог",
    sections: [
      {
        title: "Товары",
        items: [
          { href: "/catalog", label: "Каталог", page: "catalog" },
          { href: "/products", label: "Товары", page: "products" },
          { href: "/catalog/groups", label: "Группы товаров", page: "product_groups" },
        ],
      },
      {
        title: "Обмен",
        items: [
          { href: "/catalog/import", label: "Импорт", page: "catalog_import" },
          { href: "/catalog/export", label: "Экспорт", page: "catalog_export" },
        ],
      },
    ],
  },
  {
    title: "Шаблоны",
    items: [
      { href: "/templates", label: "Мастер-шаблоны", page: "templates" },
      { href: "/dictionaries", label: "Параметры", page: "dictionaries" },
    ],
  },
  {
    title: "Источники",
    sections: [
      {
        title: "Маппинг",
        items: [
          { href: "/sources-mapping", label: "Маппинг источников", page: "sources_mapping" },
        ],
      },
      {
        title: "Коннекторы",
        items: [{ href: "/connectors/status", label: "Статус коннекторов", page: "connectors_status" }],
      },
    ],
  },
  {
    title: "Медиа",
    items: [{ href: "/images/infographics", label: "Генерация инфографики", page: "infographics" }],
  },
  {
    title: "Статистика",
    items: [
      { href: "/stats/card-quality", label: "Качество карточек", page: "stats_card_quality" },
      { href: "/stats/marketplace-quality", label: "Качество на маркетплейсах", page: "stats_marketplace_quality" },
    ],
  },
  {
    title: "Администрирование",
    items: [{ href: "/admin/access", label: "Доступ и роли", page: "admin_access" }],
  },
];

function groupItems(group: NavGroup): NavItem[] {
  return group.items ?? group.sections?.flatMap((section) => section.items) ?? [];
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  if (href === "/catalog") return pathname === "/catalog";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function groupActive(pathname: string, group: NavGroup): boolean {
  return groupItems(group).some((item) => isActive(pathname, item.href));
}

export default function Shell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const { canPage, user, logout } = useAuth();
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordOk, setPasswordOk] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);

  const visibleGroups = useMemo(() => {
    return groups
      .map((group) => {
        const items = (group.items || []).filter((item) => !item.page || canPage(item.page));
        const sections = (group.sections || [])
          .map((section) => ({ ...section, items: section.items.filter((item) => !item.page || canPage(item.page)) }))
          .filter((section) => section.items.length > 0);
        if (!items.length && !sections.length) return null;
        return { ...group, items: items.length ? items : undefined, sections: sections.length ? sections : undefined };
      })
      .filter(Boolean) as NavGroup[];
  }, [canPage]);

  const currentGroupTitle = useMemo(() => {
    return visibleGroups.find((g) => groupActive(pathname, g))?.title || visibleGroups[0]?.title || "";
  }, [pathname, visibleGroups]);

  async function submitPasswordChange() {
    setSavingPassword(true);
    setPasswordError("");
    setPasswordOk("");
    try {
      await api("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setCurrentPassword("");
      setNewPassword("");
      setPasswordOk("Пароль обновлен");
    } catch (e) {
      setPasswordError((e as Error).message || "Ошибка смены пароля");
    } finally {
      setSavingPassword(false);
    }
  }

  return (
    <div className="shell shellTopLayout">
      <header className="shellTopNav">
        <div className="shellTopNavInner">
          <Link to="/" className="shellBrand">
            <div className="logo" />
            <div className="shellBrandText">
              <div className="shellBrandTitle">GT PIM</div>
              <div className="shellBrandSub">Global PIM</div>
            </div>
          </Link>

          <nav className="shellPrimaryNav" aria-label="Основная навигация">
            {visibleGroups.map((group) => {
              const selected = currentGroupTitle === group.title;
              const items = groupItems(group);
              const isDirect = !group.sections && items.length === 1;

              if (isDirect) {
                return (
                  <Link
                    key={group.title}
                    to={items[0].href}
                    className={`shellPrimaryLink shellPrimaryLinkDirect${selected ? " active" : ""}`}
                  >
                    {group.title}
                  </Link>
                );
              }

              return (
                <div key={group.title} className="shellPrimaryItem">
                  <button type="button" className={`shellPrimaryLink${selected ? " active" : ""}`}>
                    {group.title}
                    <span className="shellPrimaryCaret">▾</span>
                  </button>

                  <div className={`shellMegaPanel ${group.sections ? "isSections" : "isList"}`}>
                    {group.sections ? (
                      group.sections.map((section) => (
                        <div key={section.title} className="shellMegaSection">
                          <div className="shellMegaSectionTitle">{section.title}</div>
                          <div className="shellMegaLinks">
                            {section.items.map((item) => (
                              <Link
                                key={item.href}
                                to={item.href}
                                className={`shellMegaLink${isActive(pathname, item.href) ? " active" : ""}`}
                              >
                                {item.label}
                              </Link>
                            ))}
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="shellMegaLinks">
                        {items.map((item) => (
                          <Link
                            key={item.href}
                            to={item.href}
                            className={`shellMegaLink${isActive(pathname, item.href) ? " active" : ""}`}
                          >
                            {item.label}
                          </Link>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </nav>

          <div className="shellUser">
            <div className="shellUserMeta">
              <div className="shellUserName">{user?.name || "Пользователь"}</div>
              <div className="shellUserEmail">{user?.login || user?.email || ""}</div>
            </div>
            <button type="button" className="btn" onClick={() => setShowPasswordModal(true)}>
              Сменить пароль
            </button>
            <button type="button" className="btn" onClick={() => logout()}>
              Выйти
            </button>
          </div>
        </div>
      </header>

      <main className="main shellMain">{children}</main>
      {showPasswordModal ? (
        <div className="modalBackdrop" onClick={() => setShowPasswordModal(false)}>
          <div className="modalCard modalCardCompact" onClick={(e) => e.stopPropagation()}>
            <div className="modalHeader">
              <div>
                <div className="modalTitle">Смена пароля</div>
                <div className="modalSubtitle">Обнови пароль текущего аккаунта.</div>
              </div>
              <button type="button" className="btn" onClick={() => setShowPasswordModal(false)}>Закрыть</button>
            </div>
            <div className="authForm">
              <label className="authField"><span>Текущий пароль</span><input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} /></label>
              <label className="authField"><span>Новый пароль</span><input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} /></label>
              {passwordError ? <div className="authError">{passwordError}</div> : null}
              {passwordOk ? <div className="page-inlineSuccess">{passwordOk}</div> : null}
              <div className="accessActions">
                <button type="button" className="btn primary" onClick={submitPasswordChange} disabled={savingPassword}>
                  Сменить пароль
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
