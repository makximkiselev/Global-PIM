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
    title: "Сводка",
    icon: "workspace",
    summary: "Что требует внимания и где продолжить работу.",
    flow: ["очереди", "ошибки", "следующий шаг"],
    sections: [
      {
        title: "Контроль",
        items: [{ href: "/", label: "Рабочая сводка", page: "dashboard" }],
      },
    ],
  },
  {
    title: "Каталог",
    icon: "catalog",
    summary: "Категории, SKU, группы вариантов, медиа и готовность контента.",
    flow: ["категории", "SKU", "группы", "медиа"],
    sections: [
      {
        title: "Работа с товарами",
        items: [
          { href: "/catalog", label: "Каталог и перемещение", page: "catalog" },
          { href: "/products", label: "Список SKU", page: "products" },
          { href: "/products/new", label: "Создать SKU", page: "products" },
          { href: "/catalog/groups", label: "Группы вариантов", page: "product_groups" },
          { href: "/images/infographics", label: "Медиа", page: "infographics" },
        ],
      },
      {
        title: "Готовность",
        items: [{ href: "/catalog/content-index", label: "Индекс контента", page: "stats_card_quality" }],
      },
    ],
  },
  {
    title: "Импорт и модель",
    icon: "models",
    summary: "Загрузка товаров, сопоставление параметров, конкуренты, инфо-модель и словари.",
    flow: ["импорт", "параметры", "конкуренты", "модель"],
    sections: [
      {
        title: "Загрузка и сопоставление",
        items: [
          { href: "/catalog/import", label: "Импортировать товары", page: "catalog_import" },
          { href: "/sources?tab=params", label: "Сопоставить параметры", page: "sources_mapping" },
          { href: "/data-prep/competitors", label: "Сопоставить конкурентов", page: "sources_mapping" },
        ],
      },
      {
        title: "Модель данных",
        items: [
          { href: "/templates", label: "Собрать модель", page: "templates" },
          { href: "/dictionaries", label: "Словари", page: "dictionaries" },
        ],
      },
    ],
  },
  {
    title: "Каналы",
    icon: "sources",
    summary: "Подключения, категории площадок, значения, проверка и выгрузка.",
    flow: ["подключить", "сопоставить", "проверить", "выгрузить"],
    sections: [
      {
        title: "Подготовка выгрузки",
        items: [
          { href: "/connectors/status", label: "Подключения", page: "connectors_status" },
          { href: "/sources?tab=sources", label: "Сопоставить категории", page: "sources_mapping" },
          { href: "/sources?tab=values", label: "Настроить значения", page: "sources_mapping" },
          { href: "/catalog/export", label: "Выгрузить товары", page: "catalog_export" },
        ],
      },
    ],
  },
  {
    title: "Администрирование",
    icon: "admin",
    summary: "Организация, команда, права, приглашения и системные настройки.",
    flow: ["организация", "команда", "доступ"],
    sections: [
      {
        title: "Организация",
        items: [
          { href: "/admin/organizations", label: "Организация", page: "admin_access" },
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

function isActive(currentLocation: string, href: string): boolean {
  const [currentPath, currentSearch = ""] = currentLocation.split("?");
  const [hrefPath, hrefSearch = ""] = href.split("?");
  if (hrefSearch) {
    const currentParams = new URLSearchParams(currentSearch);
    const hrefParams = new URLSearchParams(hrefSearch);
    for (const [key, value] of hrefParams.entries()) {
      if (currentParams.get(key) !== value) return false;
    }
    return currentPath === hrefPath || (hrefPath === "/sources-mapping" && currentPath === "/sources");
  }
  if (hrefPath === "/") return currentPath === "/";
  if (hrefPath === "/catalog") return currentPath === "/catalog";
  return currentPath === hrefPath || currentPath.startsWith(`${hrefPath}/`);
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
  const { pathname, search } = useLocation();
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
  const currentLocation = `${pathname}${search}`;
  const currentLabel = useMemo(() => findCurrentLabel(currentLocation, visibleGroups), [currentLocation, visibleGroups]);
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
        group.sections.some((section) => section.items.some((item) => isActive(currentLocation, item.href))),
      ) || visibleGroups[0];
    setActiveGroupTitle((current) => {
      if (!activeGroup?.title) return current;
      if (!current) return activeGroup.title;
      const currentVisible = visibleGroups.some((group) => group.title === current);
      if (!currentVisible) return activeGroup.title;
      const routeInsideCurrent = visibleGroups
        .find((group) => group.title === current)
        ?.sections.some((section) => section.items.some((item) => isActive(currentLocation, item.href)));
      return routeInsideCurrent ? current : activeGroup.title;
    });
  }, [currentLocation, visibleGroups]);

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
                  currentLocation={currentLocation}
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
