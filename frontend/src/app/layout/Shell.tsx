import { ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../../lib/api";
import { useAuth } from "../auth/AuthContext";
import AppShell from "../../components/layout/AppShell";
import ShellSidebarNav, { type ShellNavGroup } from "../../components/layout/ShellSidebarNav";
import ShellThemeToggle from "../../components/layout/ShellThemeToggle";
import ShellWorkspaceBar from "../../components/layout/ShellWorkspaceBar";
import Alert from "../../components/ui/Alert";
import Button from "../../components/ui/Button";
import Field from "../../components/ui/Field";
import Modal from "../../components/ui/Modal";
import TextInput from "../../components/ui/TextInput";

const groups: ShellNavGroup[] = [
  {
    title: "Рабочее пространство",
    icon: "workspace",
    summary: "Главная точка входа: обзор, качество и быстрые действия.",
    sections: [
      {
        title: "Обзор",
        items: [{ href: "/", label: "Дашборд", page: "dashboard" }],
      },
    ],
  },
  {
    title: "Каталог",
    icon: "catalog",
    summary: "Категории, товары, группы и обмен данными по каталогу.",
    sections: [
      {
        title: "Товары",
        items: [
          { href: "/catalog", label: "Каталог", page: "catalog" },
          { href: "/catalog/groups", label: "Группы", page: "product_groups" },
          { href: "/catalog/content-index", label: "Контент-индекс", page: "stats_card_quality" },
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
    title: "Модели",
    icon: "models",
    summary: "Шаблоны, параметры и структура товарных моделей.",
    sections: [
      {
        title: "Структура",
        items: [
          { href: "/templates", label: "Мастер-шаблоны", page: "templates" },
          { href: "/dictionaries", label: "Параметры", page: "dictionaries" },
        ],
      },
    ],
  },
  {
    title: "Источники",
    icon: "sources",
    summary: "Маппинг источников, маркетплейсов и коннекторный контур.",
    sections: [
      {
        title: "Контур",
        items: [
          { href: "/sources", label: "Маппинг", page: "sources_mapping" },
          { href: "/connectors/status", label: "Коннекторы", page: "connectors_status" },
        ],
      },
    ],
  },
  {
    title: "Медиа",
    icon: "media",
    summary: "Контентные материалы и генерация визуальных артефактов.",
    sections: [
      {
        title: "Контент",
        items: [{ href: "/images/infographics", label: "Инфографика", page: "infographics" }],
      },
    ],
  },
  {
    title: "Администрирование",
    icon: "admin",
    summary: "Организации, команда, роли и права доступа.",
    sections: [
      {
        title: "Организация",
        items: [
          { href: "/admin/organizations", label: "Организации", page: "admin_access" },
          { href: "/admin/members", label: "Команда", page: "admin_access" },
          { href: "/admin/invites", label: "Инвайты", page: "admin_access" },
        ],
      },
      {
        title: "Права",
        items: [
          { href: "/admin/access", label: "Роли и права", page: "admin_access" },
          { href: "/admin/platform", label: "Платформа", page: "admin_access", developerOnly: true },
        ],
      },
    ],
  },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  if (href === "/catalog") return pathname === "/catalog";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function filterGroups(canPage: (code: string) => boolean, isDeveloper: boolean): ShellNavGroup[] {
  return groups
    .map((group) => ({
      ...group,
      sections: group.sections
        .map((section) => ({
          ...section,
          items: section.items.filter((item) => {
            if (item.developerOnly && !isDeveloper) return false;
            return !item.page || canPage(item.page);
          }),
        }))
        .filter((section) => section.items.length > 0),
    }))
    .filter((group) => group.sections.length > 0);
}

function findCurrentLabel(pathname: string, groupsList: ShellNavGroup[]) {
  for (const group of groupsList) {
    for (const section of group.sections) {
      for (const item of section.items) {
        if (isActive(pathname, item.href)) return item.label;
      }
    }
  }
  return "";
}

function shellRoleLabel(code?: string | null, isDeveloper = false) {
  if (isDeveloper) return "Разработчик";
  const normalized = String(code || "").toLowerCase();
  if (normalized === "org_owner") return "Владелец";
  if (normalized === "org_admin") return "Администратор";
  if (normalized === "org_editor") return "Редактор";
  if (normalized === "org_viewer") return "Наблюдатель";
  return "Участник";
}

function shellStatusLabel(status?: string | null) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "active" || normalized === "ready") return "Активна";
  if (normalized === "provisioning") return "Настраивается";
  if (normalized === "pending") return "Ожидает";
  if (["failed", "error", "suspended", "revoked"].includes(normalized)) return "Проблема";
  return "Неизвестно";
}

export default function Shell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const {
    canPage,
    user,
    logout,
    organizations,
    currentOrganization,
    switchOrganization,
    isDeveloper,
    provisioningStatus,
  } = useAuth();
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordOk, setPasswordOk] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);
  const [switchingOrganization, setSwitchingOrganization] = useState(false);

  const visibleGroups = useMemo(() => filterGroups(canPage, isDeveloper), [canPage, isDeveloper]);
  const currentLabel = useMemo(() => findCurrentLabel(pathname, visibleGroups), [pathname, visibleGroups]);
  const [activeGroupTitle, setActiveGroupTitle] = useState("");
  const showWorkspaceBar = false;
  const showShellHeading = false;
  const organizationStatus = String(provisioningStatus?.organization?.status || currentOrganization?.status || "unknown");
  const userLabel = user?.name || user?.login || user?.email || "Пользователь";
  const userMeta = user?.login || user?.email || "";
  const roleLabel = shellRoleLabel(currentOrganization?.membership_role, isDeveloper);
  const userInitials = userLabel
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase() || "SP";

  useEffect(() => {
    const activeGroup =
      visibleGroups.find((group) =>
        group.sections.some((section) => section.items.some((item) => isActive(pathname, item.href))),
      ) || visibleGroups[0];
    setActiveGroupTitle((current) => {
      if (!activeGroup?.title) return current;
      if (!current) return activeGroup.title;
      const currentVisible = visibleGroups.some((group) => group.title === current);
      if (!currentVisible) return activeGroup.title;
      const routeInsideCurrent = visibleGroups
        .find((group) => group.title === current)
        ?.sections.some((section) => section.items.some((item) => isActive(pathname, item.href)));
      return routeInsideCurrent ? current : activeGroup.title;
    });
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

  async function handleOrganizationChange(nextOrganizationId: string) {
    if (!nextOrganizationId || nextOrganizationId === currentOrganization?.id) return;
    setSwitchingOrganization(true);
    try {
      await switchOrganization(nextOrganizationId);
    } finally {
      setSwitchingOrganization(false);
    }
  }

  return (
    <>
      <AppShell
        eyebrow="Рабочий контур"
        title={currentLabel || "SmartPim"}
        showHeading={showShellHeading}
        topbar={showWorkspaceBar ? (
          <ShellWorkspaceBar
            organizations={organizations}
            currentOrganization={currentOrganization}
            switching={switchingOrganization}
            onChange={(organizationId) => void handleOrganizationChange(organizationId)}
            organizationStatus={String(provisioningStatus?.organization?.status || currentOrganization?.status || "unknown")}
            isDeveloper={isDeveloper}
            userName={user?.name || "Пользователь"}
            userMeta={user?.login || user?.email || ""}
            onChangePassword={() => setShowPasswordModal(true)}
            onLogout={() => {
              void logout();
            }}
          />
        ) : undefined}
        sidebar={
          <aside className="shellSidebar">
            <div className="shellSidebarInner">
              <div className="shellSidebarBrand">
                <Link to="/" className="shellSidebarBrandLink">
                  <div className="logo" />
                  <div className="shellSidebarBrandText">
                    <div className="shellSidebarBrandTitle">SmartPim</div>
                    <div className="shellSidebarBrandSub">Control surface</div>
                  </div>
                </Link>
              </div>

              <div className="shellSidebarWorkspace">
                <ShellSidebarNav
                  pathname={pathname}
                  groups={visibleGroups}
                  activeGroupTitle={activeGroupTitle}
                  onSelectGroup={setActiveGroupTitle}
                  isActive={isActive}
                  railFooter={
                    <>
                      <ShellThemeToggle />
                      <button
                        type="button"
                        className="shellRailUser"
                        aria-label={`Пользователь: ${userLabel}`}
                        title={`${userLabel}${userMeta ? ` · ${userMeta}` : ""}`}
                        onClick={() => setShowPasswordModal(true)}
                      >
                        {userInitials}
                      </button>
                    </>
                  }
                  panelFooter={
                    <div className="shellNavAccount">
                      <div className="shellNavAccountOrg">
                        <div className="shellNavAccountLabel">Организация</div>
                        {organizations.length > 1 ? (
                          <select
                            className="shellNavAccountSelect"
                            value={currentOrganization?.id || ""}
                            disabled={switchingOrganization}
                            onChange={(event) => void handleOrganizationChange(event.target.value)}
                          >
                            {organizations.map((organization) => (
                              <option key={organization.id} value={organization.id}>
                                {organization.name}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <div className="shellNavAccountName">{currentOrganization?.name || "Организация"}</div>
                        )}
                        <div className={`shellStatusBadge is-${organizationStatus.toLowerCase()}`}>{shellStatusLabel(organizationStatus)}</div>
                      </div>
                      <div className="shellNavAccountUser">
                        <div className="shellNavAvatar">{userInitials}</div>
                        <div className="shellNavUserCopy">
                          <div className="shellNavUserName">{userLabel}</div>
                          <div className="shellNavUserMeta">{userMeta || roleLabel}</div>
                        </div>
                        <div className="shellRoleBadge">{roleLabel}</div>
                      </div>
                      <div className="shellNavAccountActions">
                        <button type="button" className="shellNavAccountButton" onClick={() => setShowPasswordModal(true)}>
                          Сменить пароль
                        </button>
                        <button
                          type="button"
                          className="shellNavAccountButton"
                          onClick={() => {
                            void logout();
                          }}
                        >
                          Выйти
                        </button>
                      </div>
                    </div>
                  }
                />
              </div>
            </div>
          </aside>
        }
      >
        {children}
      </AppShell>

      <Modal open={showPasswordModal} onClose={() => setShowPasswordModal(false)} title="Смена пароля" subtitle="Обнови пароль текущего аккаунта." width="compact">
        <div className="authForm">
          <Field label="Текущий пароль">
            <TextInput type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
          </Field>
          <Field label="Новый пароль">
            <TextInput type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
          </Field>
          {passwordError ? <Alert tone="error">{passwordError}</Alert> : null}
          {passwordOk ? <Alert tone="success">{passwordOk}</Alert> : null}
          <div className="accessActions">
            <Button variant="primary" onClick={submitPasswordChange} disabled={savingPassword}>
              Сменить пароль
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
