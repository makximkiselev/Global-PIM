import { ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../../lib/api";
import { useAuth } from "../auth/AuthContext";
import AppShell from "../../components/layout/AppShell";
import ShellSidebarNav, { type ShellNavGroup } from "../../components/layout/ShellSidebarNav";
import ShellThemeToggle from "../../components/layout/ShellThemeToggle";
import Alert from "../../components/ui/Alert";
import Button from "../../components/ui/Button";
import Field from "../../components/ui/Field";
import Modal from "../../components/ui/Modal";
import TextInput from "../../components/ui/TextInput";
import { orgAwarePath, stripOrgPrefix, withOrgPath } from "../orgRoutes";

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
    summary: "Категории, товары, группы, медиа, инфографика, импорт и экспорт.",
    flow: ["каталог", "товары", "медиа", "обмен"],
    sections: [
      {
        title: "Работа с товарами",
        items: [
          { href: "/catalog", label: "Каталог", page: "catalog" },
          { href: "/products", label: "Товары", page: "products" },
          { href: "/catalog/groups", label: "Группы", page: "product_groups" },
        ],
      },
      {
        title: "Медиа",
        items: [
          { href: "/products/media", label: "Медиа по товарам", page: "infographics" },
          { href: "/images/infographics", label: "Создание инфографики", page: "infographics" },
        ],
      },
      {
        title: "Обмен",
        items: [
          { href: "/catalog/exchange", label: "Импорт / Экспорт", pages: ["catalog_import", "catalog_export"] },
        ],
      },
    ],
  },
  {
    title: "Инфо-модели",
    icon: "models",
    summary: "Инфо-модели, сопоставления и источники данных.",
    flow: ["категории", "параметры", "модель", "источники"],
    sections: [
      {
        title: "Рабочие области",
        items: [
          { href: "/templates", label: "Инфо-модели", page: "templates" },
          { href: "/sources?tab=sources", label: "Сопоставления", page: "sources_mapping" },
          { href: "/connectors/status", label: "Источники данных", pages: ["connectors_status", "sources_mapping"] },
        ],
      },
    ],
  },
  {
    title: "Администрирование",
    icon: "admin",
    summary: "Организация, команда, права, роли и приглашения.",
    flow: ["организация", "команда", "доступ"],
    sections: [
      {
        title: "Организация",
        items: [
          { href: "/admin/organizations", label: "Организация", page: "admin_access" },
        ],
      },
      {
        title: "Права",
        items: [
          { href: "/admin/access", label: "Права и роли", page: "admin_access" },
        ],
      },
    ],
  },
];

function isActive(currentLocation: string, href: string): boolean {
  const [currentPath, currentSearch = ""] = currentLocation.split("?");
  const [hrefPath, hrefSearch = ""] = href.split("?");
  if ((hrefPath === "/sources" || hrefPath === "/sources-mapping") && (currentPath === "/sources" || currentPath === "/sources-mapping")) {
    return true;
  }
  if (hrefPath === "/admin/organizations" && ["/admin/organizations", "/admin/members", "/admin/invites"].includes(currentPath)) {
    return true;
  }
  if (hrefPath === "/admin/access" && currentPath === "/admin/access") {
    return true;
  }
  if (hrefSearch) {
    const currentParams = new URLSearchParams(currentSearch);
    const hrefParams = new URLSearchParams(hrefSearch);
    for (const [key, value] of hrefParams.entries()) {
      if (currentParams.get(key) !== value) return false;
    }
    return currentPath === hrefPath;
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
            if (item.pages?.length) return item.pages.some((page) => canPage(page));
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

function organizationStatusLabel(status: string) {
  const normalized = status.toLowerCase();
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
  const appPathname = stripOrgPrefix(pathname).appPath;
  const appLocation = `${appPathname}${search}`;
  const currentLabel = useMemo(() => findCurrentLabel(appLocation, visibleGroups), [appLocation, visibleGroups]);
  const [activeGroupTitle, setActiveGroupTitle] = useState("");
  const showShellHeading = false;
  const userLabel = user?.name || user?.login || user?.email || "Пользователь";
  const userMeta = user?.login || user?.email || "";
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
        group.sections.some((section) => section.items.some((item) => isActive(appLocation, item.href))),
      ) || visibleGroups[0];
    setActiveGroupTitle((current) => {
      if (!activeGroup?.title) return current;
      if (!current) return activeGroup.title;
      const currentVisible = visibleGroups.some((group) => group.title === current);
      if (!currentVisible) return activeGroup.title;
      const routeInsideCurrent = visibleGroups
        .find((group) => group.title === current)
        ?.sections.some((section) => section.items.some((item) => isActive(appLocation, item.href)));
      return routeInsideCurrent ? current : activeGroup.title;
    });
  }, [appLocation, visibleGroups]);

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
      const nextOrganization = organizations.find((organization) => organization.id === nextOrganizationId) || null;
      window.location.assign(withOrgPath(nextOrganization, "/"));
    } finally {
      setSwitchingOrganization(false);
    }
  }

  const currentOrganizationStatus = String(provisioningStatus?.organization?.status || currentOrganization?.status || "unknown");
  const normalizedOrganizationStatus = currentOrganizationStatus.toLowerCase();
  const currentOrganizationLabel = organizationStatusLabel(currentOrganizationStatus);

  return (
    <>
      <AppShell
        eyebrow="Рабочий контур"
        title={currentLabel || "SmartPim"}
        showHeading={showShellHeading}
        sidebar={
          <aside className="shellSidebar">
            <div className="shellSidebarInner">
              <div className="shellSidebarBrand">
                <Link to={withOrgPath(currentOrganization, "/")} className="shellSidebarBrandLink">
                  <div className="logo" />
                  <div className="shellSidebarBrandText">
                    <div className="shellSidebarBrandTitle">SmartPim</div>
                    <div className="shellSidebarBrandSub">Рабочая панель</div>
                  </div>
                </Link>
              </div>

              <div className="shellSidebarWorkspace">
                <ShellSidebarNav
                  pathname={pathname}
                  currentLocation={appLocation}
                  groups={visibleGroups}
                  activeGroupTitle={activeGroupTitle}
                  onSelectGroup={setActiveGroupTitle}
                  isActive={isActive}
                  resolveHref={(href) => orgAwarePath(pathname, href, currentOrganization)}
                  railFooter={
                    <>
                      <ShellThemeToggle />
                      <Link
                        to={withOrgPath(currentOrganization, "/profile")}
                        className="shellRailUser"
                        aria-label={`Пользователь: ${userLabel}`}
                        title={`${userLabel}${userMeta ? ` · ${userMeta}` : ""}`}
                      >
                        {userInitials}
                      </Link>
                    </>
                  }
                  panelFooter={
                    currentOrganization ? (
                      <div className="shellNavAccount">
                        <div className="shellNavAccountOrg">
                          <div className="shellNavAccountLabel">Организация</div>
                          {organizations.length > 1 ? (
                            <select
                              className="shellNavAccountSelect"
                              value={currentOrganization.id}
                              onChange={(event) => void handleOrganizationChange(event.target.value)}
                              disabled={switchingOrganization}
                              aria-label="Переключить организацию"
                            >
                              {organizations.map((organization) => (
                                <option key={organization.id} value={organization.id}>
                                  {organization.name}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <div className="shellNavAccountName">{currentOrganization.name}</div>
                          )}
                          <div className="shellSidebarStatusRow">
                            <span className={`shellStatusBadge is-${normalizedOrganizationStatus}`}>{currentOrganizationLabel}</span>
                            {isDeveloper ? <span className="shellRoleBadge">Разработчик</span> : null}
                          </div>
                        </div>

                        <div className="shellNavAccountUser">
                          <div className="shellNavAvatar">{userInitials}</div>
                          <div className="shellNavUserCopy">
                            <div className="shellNavUserName">{userLabel}</div>
                            {userMeta ? <div className="shellNavUserMeta">{userMeta}</div> : null}
                          </div>
                        </div>

                        <div className="shellNavAccountActions">
                          <button type="button" className="shellNavAccountButton" onClick={() => setShowPasswordModal(true)}>
                            Пароль
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
                    ) : null
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
