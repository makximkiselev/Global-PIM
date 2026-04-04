import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../app/auth/AuthContext";

type CatalogRow = { code: string; title: string };
type RoleRow = {
  id: string;
  code: string;
  name: string;
  description?: string;
  pages: string[];
  actions: string[];
  is_system?: boolean;
};
type UserRow = {
  id: string;
  login: string;
  email: string;
  name: string;
  role_ids: string[];
  roles?: RoleRow[];
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  last_login_at?: string | null;
  last_login_ip?: string | null;
};
type LoginEventRow = {
  id: string;
  at?: string | null;
  login?: string | null;
  user_id?: string | null;
  user_name?: string | null;
  status?: string | null;
  ip?: string | null;
  user_agent?: string | null;
};

type AdminBootstrapResp = {
  ok: boolean;
  roles: RoleRow[];
  users: UserRow[];
  events: LoginEventRow[];
  catalog: { pages: CatalogRow[]; actions: CatalogRow[] };
};

const EMPTY_ROLE: RoleRow = { id: "", code: "", name: "", description: "", pages: [], actions: [], is_system: false };
const EMPTY_USER: UserRow = { id: "", login: "", email: "", name: "", role_ids: [], is_active: true };
const EMPTY_CREATE_USER = { login: "", email: "", name: "", role_ids: [] as string[], is_active: true };
type AdminTab = "users" | "roles";

function normalizeAdminTab(value: string | null): AdminTab {
  return value === "roles" ? "roles" : "users";
}

function fmt(s?: string | null) {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("ru-RU");
}

export default function AdminAccess() {
  const { canAction } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTabState] = useState<AdminTab>(normalizeAdminTab(searchParams.get("tab")));
  const [catalog, setCatalog] = useState<{ pages: CatalogRow[]; actions: CatalogRow[] }>({ pages: [], actions: [] });
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [loginEvents, setLoginEvents] = useState<LoginEventRow[]>([]);
  const [editingRole, setEditingRole] = useState<RoleRow>(EMPTY_ROLE);
  const [editingUser, setEditingUser] = useState<UserRow>(EMPTY_USER);
  const [userPassword, setUserPassword] = useState("");
  const [showCreateUserModal, setShowCreateUserModal] = useState(false);
  const [createUserDraft, setCreateUserDraft] = useState(EMPTY_CREATE_USER);
  const [createUserPassword, setCreateUserPassword] = useState("");
  const [expandedRoleGroups, setExpandedRoleGroups] = useState<string[]>([]);
  const [expandedRolePanels, setExpandedRolePanels] = useState<{ profile: boolean; pages: boolean; actions: boolean }>({
    profile: false,
    pages: true,
    actions: true,
  });
  const [resetPassword, setResetPassword] = useState("");
  const [resetPasswordResult, setResetPasswordResult] = useState("");
  const [showRoleModal, setShowRoleModal] = useState(false);
  const [showDeleteRoleModal, setShowDeleteRoleModal] = useState(false);
  const [saving, setSaving] = useState(false);

  function updateSelectionParams(patch: Partial<{ tab: AdminTab; user: string; role: string }>) {
    const next = new URLSearchParams(searchParams);
    if (patch.tab !== undefined) next.set("tab", patch.tab);
    if (patch.user !== undefined) {
      if (patch.user) next.set("user", patch.user);
      else next.delete("user");
    }
    if (patch.role !== undefined) {
      if (patch.role) next.set("role", patch.role);
      else next.delete("role");
    }
    setSearchParams(next, { replace: true });
  }

  useEffect(() => {
    const nextTab = normalizeAdminTab(searchParams.get("tab"));
    setTabState(nextTab);
  }, [searchParams]);

  function setTab(nextTab: AdminTab) {
    setTabState(nextTab);
    updateSelectionParams({ tab: nextTab });
  }

  function selectUser(nextUser: UserRow, roleGroupName?: string) {
    setEditingUser(nextUser);
    setUserPassword("");
    setResetPassword("");
    setResetPasswordResult("");
    if (roleGroupName) {
      setExpandedRoleGroups((cur) => cur.includes(roleGroupName) ? cur : [...cur, roleGroupName]);
    }
    updateSelectionParams({ tab: "users", user: nextUser.id, role: "" });
  }

  function selectRole(nextRole: RoleRow) {
    setEditingRole(nextRole);
    updateSelectionParams({ tab: "roles", role: nextRole.id, user: "" });
  }

  async function load() {
    setLoading(true);
    setError("");
    try {
      const bootstrap = await api<AdminBootstrapResp>("/auth/admin/bootstrap");
      setCatalog(bootstrap.catalog || { pages: [], actions: [] });
      setRoles(bootstrap.roles || []);
      setUsers(bootstrap.users || []);
      setLoginEvents(bootstrap.events || []);
      const requestedRoleId = searchParams.get("role") || "";
      const requestedUserId = searchParams.get("user") || "";

      const nextRole =
        (requestedRoleId && bootstrap.roles?.find((item) => item.id === requestedRoleId)) ||
        (editingRole.id && bootstrap.roles?.find((item) => item.id === editingRole.id)) ||
        bootstrap.roles?.[0] ||
        EMPTY_ROLE;
      const nextUser =
        (requestedUserId && bootstrap.users?.find((item) => item.id === requestedUserId)) ||
        (editingUser.id && bootstrap.users?.find((item) => item.id === editingUser.id)) ||
        bootstrap.users?.[0] ||
        EMPTY_USER;

      setEditingRole(nextRole);
      setEditingUser(nextUser);
    } catch (e) {
      setError((e as Error).message || "Ошибка загрузки доступа");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const roleOptions = useMemo(() => roles.map((role) => ({ id: role.id, name: role.name })), [roles]);
  const usersByRole = useMemo(() => {
    const order = roleOptions.map((role) => role.name);
    const buckets = new Map<string, UserRow[]>();
    const resolveRoleName = (user: UserRow) => {
      if (!user.role_ids.length) return "Без роли";
      const first = roleOptions.find((role) => user.role_ids.includes(role.id));
      return first?.name || "Без роли";
    };
    for (const user of users) {
      const group = resolveRoleName(user);
      const list = buckets.get(group) || [];
      list.push(user);
      buckets.set(group, list);
    }
    return [...buckets.entries()]
      .sort((a, b) => {
        const ai = order.indexOf(a[0]);
        const bi = order.indexOf(b[0]);
        const av = ai === -1 ? Number.MAX_SAFE_INTEGER : ai;
        const bv = bi === -1 ? Number.MAX_SAFE_INTEGER : bi;
        if (av !== bv) return av - bv;
        return a[0].localeCompare(b[0], "ru");
      })
      .map(([name, items]) => ({
        name,
        items: [...items].sort((a, b) => (a.name || a.login).localeCompare(b.name || b.login, "ru")),
      }));
  }, [users, roleOptions]);
  const selectedUserRoleNames = useMemo(
    () => roleOptions.filter((role) => editingUser.role_ids.includes(role.id)).map((role) => role.name),
    [roleOptions, editingUser.role_ids],
  );
  const selectedUserEvents = useMemo(
    () => loginEvents.filter((event) => !editingUser.id || event.user_id === editingUser.id || event.login === editingUser.login).slice(0, 12),
    [loginEvents, editingUser.id, editingUser.login],
  );

  useEffect(() => {
    if (tab !== "users" || !usersByRole.length) return;
    const requestedUserId = searchParams.get("user") || "";
    if (requestedUserId) {
      const nextUser = users.find((user) => user.id === requestedUserId);
      if (nextUser && nextUser.id !== editingUser.id) {
        setEditingUser(nextUser);
      }
    }
    const activeGroup = usersByRole.find((group) => group.items.some((user) => user.id === editingUser.id))?.name;
    const fallbackGroup = usersByRole[0]?.name;
    const next = activeGroup || fallbackGroup;
    if (!next) return;
    setExpandedRoleGroups((cur) => (cur.includes(next) ? cur : [...cur, next]));
  }, [tab, usersByRole, editingUser.id, users, searchParams]);

  useEffect(() => {
    if (tab !== "roles" || !roles.length) return;
    const requestedRoleId = searchParams.get("role") || "";
    if (!requestedRoleId) return;
    const nextRole = roles.find((role) => role.id === requestedRoleId);
    if (nextRole && nextRole.id !== editingRole.id) {
      setEditingRole(nextRole);
    }
  }, [tab, roles, editingRole.id, searchParams]);

  useEffect(() => {
    if (tab === "users" && users.length) {
      const requestedUserId = searchParams.get("user") || "";
      if (requestedUserId && !users.some((user) => user.id === requestedUserId)) {
        updateSelectionParams({ user: editingUser.id || users[0]?.id || "" });
      }
    }
    if (tab === "roles" && roles.length) {
      const requestedRoleId = searchParams.get("role") || "";
      if (requestedRoleId && !roles.some((role) => role.id === requestedRoleId)) {
        updateSelectionParams({ role: editingRole.id || roles[0]?.id || "" });
      }
    }
  }, [tab, users, roles, editingUser.id, editingRole.id]);

  function toggleCode(list: string[], code: string) {
    return list.includes(code) ? list.filter((item) => item !== code) : [...list, code];
  }

  async function saveRole() {
    setSaving(true);
    setError("");
    try {
      const payload = {
        code: editingRole.code,
        name: editingRole.name,
        description: editingRole.description || "",
        pages: editingRole.pages,
        actions: editingRole.actions,
      };
      if (editingRole.id) {
        await api(`/auth/admin/roles/${encodeURIComponent(editingRole.id)}`, { method: "PUT", body: JSON.stringify(payload) });
      } else {
        await api("/auth/admin/roles", { method: "POST", body: JSON.stringify(payload) });
      }
      await load();
    } catch (e) {
      setError((e as Error).message || "Ошибка сохранения роли");
    } finally {
      setSaving(false);
    }
  }

  async function deleteRole() {
    if (!editingRole.id) return;
    setSaving(true);
    setError("");
    try {
      await api(`/auth/admin/roles/${encodeURIComponent(editingRole.id)}`, { method: "DELETE" });
      setShowDeleteRoleModal(false);
      await load();
    } catch (e) {
      setError((e as Error).message || "Ошибка удаления роли");
    } finally {
      setSaving(false);
    }
  }

  async function saveUser() {
    setSaving(true);
    setError("");
    try {
      const payload = {
        login: editingUser.login,
        email: editingUser.email,
        name: editingUser.name,
        role_ids: editingUser.role_ids,
        is_active: editingUser.is_active,
        password: userPassword || undefined,
      };
      if (editingUser.id) {
        await api(`/auth/admin/users/${encodeURIComponent(editingUser.id)}`, { method: "PUT", body: JSON.stringify(payload) });
      } else {
        await api("/auth/admin/users", { method: "POST", body: JSON.stringify(payload) });
      }
      setUserPassword("");
      await load();
    } catch (e) {
      setError((e as Error).message || "Ошибка сохранения пользователя");
    } finally {
      setSaving(false);
    }
  }

  async function createUser() {
    setSaving(true);
    setError("");
    try {
      await api("/auth/admin/users", {
        method: "POST",
        body: JSON.stringify({
          login: createUserDraft.login,
          email: createUserDraft.email,
          name: createUserDraft.name,
          role_ids: createUserDraft.role_ids,
          is_active: createUserDraft.is_active,
          password: createUserPassword || undefined,
        }),
      });
      setShowCreateUserModal(false);
      setCreateUserDraft(EMPTY_CREATE_USER);
      setCreateUserPassword("");
      await load();
    } catch (e) {
      setError((e as Error).message || "Ошибка создания пользователя");
    } finally {
      setSaving(false);
    }
  }

  async function doResetPassword() {
    if (!editingUser.id) return;
    setSaving(true);
    setError("");
    setResetPasswordResult("");
    try {
      const data = await api<{ ok: boolean; password: string }>(`/auth/admin/users/${encodeURIComponent(editingUser.id)}/reset-password`, {
        method: "POST",
        body: JSON.stringify({ password: resetPassword || undefined }),
      });
      setResetPassword("");
      setResetPasswordResult(data.password || "");
      await load();
    } catch (e) {
      setError((e as Error).message || "Ошибка сброса пароля");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-shell accessPage">
      <div className="page-header">
        <div className="page-header-main">
          <div className="page-title">Доступ и роли</div>
          <div className="page-subtitle">Пользователи, роли, права страниц и действий.</div>
        </div>
      </div>
      <div className="page-tabs">
        <button className={`page-tab${tab === "users" ? " active" : ""}`} onClick={() => setTab("users")}>Пользователи</button>
        <button className={`page-tab${tab === "roles" ? " active" : ""}`} onClick={() => setTab("roles")}>Роли</button>
      </div>
      {error ? <div className="authError page-inlineError">{error}</div> : null}
      <div className="accessWorkspace">
        <aside className="card accessSidebar">
          <div className="accessListHeader">
            <div className="accessListTitle">{tab === "users" ? "Пользователи" : "Роли"}</div>
            <button
              className="btn"
              onClick={() => {
                if (tab === "users") {
                  setCreateUserDraft(EMPTY_CREATE_USER);
                  setCreateUserPassword("");
                  setShowCreateUserModal(true);
                } else {
                  setEditingRole(EMPTY_ROLE);
                  setShowRoleModal(true);
                }
              }}
              disabled={tab === "users" ? !canAction("users.manage") : !canAction("roles.manage")}
            >
              Создать
            </button>
          </div>
          {tab === "users" ? <div className="accessListHint">Показываются пользователи модуля авторизации.</div> : null}
          <div className="accessList">
            {tab === "users"
              ? usersByRole.map((group) => (
                  <div key={group.name} className="accessListGroup">
                    <button
                      className={`accessListGroupToggle${expandedRoleGroups.includes(group.name) ? " isOpen" : ""}`}
                      onClick={() => setExpandedRoleGroups((cur) => cur.includes(group.name) ? cur.filter((name) => name !== group.name) : [...cur, group.name])}
                    >
                      <span className="accessListGroupCaret">{expandedRoleGroups.includes(group.name) ? "▾" : "▸"}</span>
                      <span className="accessListGroupTitle">{group.name}</span>
                      <span className="accessListGroupCount">{group.items.length}</span>
                    </button>
                    {expandedRoleGroups.includes(group.name) ? (
                      <div className="accessListGroupRows">
                        {group.items.map((item) => (
                          <button
                            key={item.id}
                            className={`accessRow${editingUser.id === item.id ? " active" : ""}`}
                            onClick={() => selectUser(item, group.name)}
                          >
                            <div className="accessRowTitle">{item.name}</div>
                            <div className="accessRowSub">{item.login}</div>
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))
              : roles.map((item) => (
                  <button
                    key={item.id}
                    className={`accessRow${editingRole.id === item.id ? " active" : ""}`}
                    onClick={() => selectRole(item as RoleRow)}
                  >
                    <div className="accessRowTitle">{item.name}</div>
                    <div className="accessRowSub">{(item as RoleRow).code}</div>
                  </button>
                ))}
          </div>
        </aside>

        {tab === "users" ? (
          <section className="accessContent">
            <div className="card accessHero">
              <div className="accessHeroMain">
                <div className="accessEditorHeader">Пользователь</div>
                <div className="accessHeroName">{editingUser.name || "Новый пользователь"}</div>
                <div className="accessHeroSub">{editingUser.login || "Логин не задан"}</div>
              </div>
              <div className="accessHeroMeta">
                <button className="btn primary accessHeroSaveBtn" onClick={saveUser} disabled={!canAction("users.manage") || saving || loading}>Сохранить</button>
                <div className={`accessStatusChip${editingUser.is_active ? " isActive" : ""}`}>{editingUser.is_active ? "Активен" : "Отключен"}</div>
                {selectedUserRoleNames.length ? (
                  <div className="accessRolePills">
                    {selectedUserRoleNames.map((name) => (
                      <span key={name} className="accessRolePill">{name}</span>
                    ))}
                  </div>
                ) : <div className="accessHeroHint">Роли не назначены</div>}
              </div>
            </div>

            <div className="accessPanels accessPanelsUsers">
              <div className="card accessPanel">
                <div className="accessPermissionTitle">Основное</div>
                <label className="accessField"><span>Имя</span><input value={editingUser.name} onChange={(e) => setEditingUser((cur) => ({ ...cur, name: e.target.value }))} /></label>
                <label className="accessField"><span>Логин</span><input value={editingUser.login} onChange={(e) => setEditingUser((cur) => ({ ...cur, login: e.target.value }))} autoComplete="username" /></label>
                <label className="accessField"><span>Email</span><input value={editingUser.email || ""} onChange={(e) => setEditingUser((cur) => ({ ...cur, email: e.target.value }))} autoComplete="email" /></label>
                <label className="accessField"><span>Пароль {editingUser.id ? "(оставь пустым, чтобы не менять)" : ""}</span><input type="password" value={userPassword} onChange={(e) => setUserPassword(e.target.value)} /></label>
                <label className="accessCheck"><input type="checkbox" checked={editingUser.is_active} onChange={(e) => setEditingUser((cur) => ({ ...cur, is_active: e.target.checked }))} /> Активен</label>
              </div>

              <div className="card accessPanel">
                <div className="accessPermissionTitle">Безопасность</div>
                <div className="accessMeta accessMetaStack">
                  <div>Создан: {fmt(editingUser.created_at)}</div>
                  <div>Последний вход: {fmt(editingUser.last_login_at)}</div>
                  <div>IP последнего входа: {editingUser.last_login_ip || "—"}</div>
                </div>
                {editingUser.id ? (
                  <div className="accessResetBox">
                    <div className="accessResetLabel">Сброс пароля</div>
                    <div className="accessResetRow">
                      <input
                        className="accessResetInput"
                        type="text"
                        placeholder="Новый пароль или оставить пустым для генерации"
                        value={resetPassword}
                        onChange={(e) => setResetPassword(e.target.value)}
                      />
                      <button className="btn" onClick={doResetPassword} disabled={!canAction("users.manage") || saving}>
                        Сбросить
                      </button>
                    </div>
                    {resetPasswordResult ? <div className="accessResetResult">Новый пароль: <code>{resetPasswordResult}</code></div> : null}
                  </div>
                ) : null}
              </div>

              <div className="card accessPanel accessPanelWide">
                <div className="accessPermissionTitle">Роли</div>
                <div className="accessRoleGrid">
                  {roleOptions.map((role) => (
                    <label key={role.id} className="accessRoleCard">
                      <input
                        type="checkbox"
                        checked={editingUser.role_ids.includes(role.id)}
                        onChange={() => setEditingUser((cur) => ({ ...cur, role_ids: toggleCode(cur.role_ids, role.id) }))}
                      />
                      <span>{role.name}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="card accessPanel accessPanelWide">
                <div className="accessPermissionTitle">Последние входы</div>
                <div className="accessEvents">
                  {selectedUserEvents.length ? selectedUserEvents.map((event) => (
                    <div key={event.id} className={`accessEvent accessEvent-${event.status || "unknown"}`}>
                      <div className="accessEventMain">
                        <strong>{event.user_name || event.login || "—"}</strong>
                        <span>{fmt(event.at)}</span>
                      </div>
                      <div className="accessEventMeta">
                        <span>{event.status === "success" ? "Успешно" : "Ошибка"}</span>
                        <span>{event.ip || "—"}</span>
                      </div>
                    </div>
                  )) : <div className="accessEmpty">Для этого пользователя входов пока нет.</div>}
                </div>
              </div>
            </div>
          </section>
        ) : (
          <section className="accessContent">
            <div className="card accessRoleHero">
              <div className="accessRoleHeroTop">
                <div className="accessHeroMain">
                  <div className="accessHeroName">{editingRole.name || "Новая роль"}</div>
                  <div className="accessHeroSub">@{editingRole.code || "role_code"}</div>
                </div>
                <div className="accessRoleHeroAside">
                  <div className="accessRoleHeroActions">
                    <button
                      className="accessIconBtn"
                      type="button"
                      aria-label="Редактировать роль"
                      title="Редактировать роль"
                      onClick={() => setShowRoleModal(true)}
                      disabled={!canAction("roles.manage")}
                    >
                      ✎
                    </button>
                    <button
                      className="accessIconBtn accessIconBtnDanger"
                      type="button"
                      aria-label="Удалить роль"
                      title="Удалить роль"
                      onClick={() => setShowDeleteRoleModal(true)}
                      disabled={!canAction("roles.manage") || !editingRole.id || !!editingRole.is_system}
                    >
                      🗑
                    </button>
                  </div>
                  <div className="accessRoleMetaInline">
                    <div className={`accessStatusChip${editingRole.is_system ? " isNeutral" : ""}`}>{editingRole.is_system ? "Системная" : "Пользовательская"}</div>
                    <div className="accessRoleMetricPill">
                      <span>Страницы</span>
                      <strong>{editingRole.pages.includes("*") ? "Все" : editingRole.pages.length}</strong>
                    </div>
                    <div className="accessRoleMetricPill">
                      <span>Действия</span>
                      <strong>{editingRole.actions.includes("*") ? "Все" : editingRole.actions.length}</strong>
                    </div>
                  </div>
                </div>
              </div>
              {editingRole.description ? <div className="accessRoleHeroText">{editingRole.description}</div> : null}
            </div>

            <div className="accessPanels accessPanelsRolesModern">
              <div className="accessRoleAccordionStack">
                <section className={`card accessPanel accessAccordionCard${expandedRolePanels.pages ? " isOpen" : ""}`}>
                  <button
                    type="button"
                    className="accessAccordionHeader"
                    onClick={() => setExpandedRolePanels((cur) => ({ ...cur, pages: !cur.pages }))}
                  >
                    <div>
                      <div className="accessPermissionTitle">Страницы</div>
                      <div className="accessPanelSubtle">Разделы, которые может открывать роль.</div>
                    </div>
                    <div className="accessAccordionHeaderMeta">
                      <div className="accessMatrixCount">{editingRole.pages.includes("*") ? "Все страницы" : `${editingRole.pages.length} выбрано`}</div>
                      <span className="accessAccordionCaret">{expandedRolePanels.pages ? "▾" : "▸"}</span>
                    </div>
                  </button>
                  {expandedRolePanels.pages ? (
                    <div className="accessAccordionBody">
                      <div className="accessRoleGrid accessCapabilityGrid accessCapabilityGridPages">
                        {catalog.pages.map((page) => (
                          <label key={page.code} className={`accessRoleCard accessCapabilityCard${editingRole.pages.includes(page.code) || editingRole.pages.includes("*") ? " isChecked" : ""}`}>
                            <input
                              type="checkbox"
                              checked={editingRole.pages.includes(page.code) || editingRole.pages.includes("*")}
                              onChange={() => setEditingRole((cur) => ({ ...cur, pages: toggleCode(cur.pages, page.code) }))}
                              disabled={!!editingRole.is_system && editingRole.code === "owner"}
                            />
                            <span>{page.title}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </section>

                <section className={`card accessPanel accessAccordionCard${expandedRolePanels.actions ? " isOpen" : ""}`}>
                  <button
                    type="button"
                    className="accessAccordionHeader"
                    onClick={() => setExpandedRolePanels((cur) => ({ ...cur, actions: !cur.actions }))}
                  >
                    <div>
                      <div className="accessPermissionTitle">Действия</div>
                      <div className="accessPanelSubtle">Операции, которые роль может выполнять в системе.</div>
                    </div>
                    <div className="accessAccordionHeaderMeta">
                      <div className="accessMatrixCount">{editingRole.actions.includes("*") ? "Все действия" : `${editingRole.actions.length} выбрано`}</div>
                      <span className="accessAccordionCaret">{expandedRolePanels.actions ? "▾" : "▸"}</span>
                    </div>
                  </button>
                  {expandedRolePanels.actions ? (
                    <div className="accessAccordionBody">
                      <div className="accessRoleGrid accessCapabilityGrid accessCapabilityGridActions">
                        {catalog.actions.map((action) => (
                          <label key={action.code} className={`accessRoleCard accessCapabilityCard${editingRole.actions.includes(action.code) || editingRole.actions.includes("*") ? " isChecked" : ""}`}>
                            <input
                              type="checkbox"
                              checked={editingRole.actions.includes(action.code) || editingRole.actions.includes("*")}
                              onChange={() => setEditingRole((cur) => ({ ...cur, actions: toggleCode(cur.actions, action.code) }))}
                              disabled={!!editingRole.is_system && editingRole.code === "owner"}
                            />
                            <span>{action.title}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </section>
              </div>
            </div>
          </section>
        )}
      </div>

      {showCreateUserModal ? (
        <div className="modalBackdrop" onClick={() => !saving && setShowCreateUserModal(false)}>
          <div className="modalCard modalCardCompact" onClick={(e) => e.stopPropagation()}>
            <div className="modalHeader">
              <div>
                <div className="modalTitle">Новый пользователь</div>
                <div className="modalSubtitle">Создание пользователя модуля авторизации.</div>
              </div>
              <button className="btn" onClick={() => setShowCreateUserModal(false)} disabled={saving}>Закрыть</button>
            </div>

            <div className="accessCreateUserGrid">
              <label className="accessField">
                <span>Имя</span>
                <input value={createUserDraft.name} onChange={(e) => setCreateUserDraft((cur) => ({ ...cur, name: e.target.value }))} />
              </label>
              <label className="accessField">
                <span>Логин</span>
                <input value={createUserDraft.login} onChange={(e) => setCreateUserDraft((cur) => ({ ...cur, login: e.target.value }))} autoComplete="username" />
              </label>
              <label className="accessField">
                <span>Email</span>
                <input value={createUserDraft.email} onChange={(e) => setCreateUserDraft((cur) => ({ ...cur, email: e.target.value }))} autoComplete="email" />
              </label>
              <label className="accessField">
                <span>Пароль</span>
                <input type="password" value={createUserPassword} onChange={(e) => setCreateUserPassword(e.target.value)} autoComplete="new-password" />
              </label>
              <label className="accessCheck">
                <input
                  type="checkbox"
                  checked={createUserDraft.is_active}
                  onChange={(e) => setCreateUserDraft((cur) => ({ ...cur, is_active: e.target.checked }))}
                />
                Активен
              </label>
            </div>

            <div className="card accessPanel accessPanelWide" style={{ marginTop: 16 }}>
              <div className="accessPermissionTitle">Роли</div>
              <div className="accessRoleGrid">
                {roleOptions.map((role) => (
                  <label key={role.id} className="accessRoleCard">
                    <input
                      type="checkbox"
                      checked={createUserDraft.role_ids.includes(role.id)}
                      onChange={() => setCreateUserDraft((cur) => ({ ...cur, role_ids: toggleCode(cur.role_ids, role.id) }))}
                    />
                    <span>{role.name}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="accessActions" style={{ marginTop: 16 }}>
              <button className="btn" onClick={() => setShowCreateUserModal(false)} disabled={saving}>Отмена</button>
              <button
                className="btn primary"
                onClick={createUser}
                disabled={!canAction("users.manage") || saving || !createUserDraft.login.trim() || !createUserPassword.trim()}
              >
                Создать
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {showRoleModal ? (
        <div className="modalBackdrop" onClick={() => !saving && setShowRoleModal(false)}>
          <div className="modalCard modalCardCompact" onClick={(e) => e.stopPropagation()}>
            <div className="modalHeader">
              <div>
                <div className="modalTitle">{editingRole.id ? "Редактирование роли" : "Новая роль"}</div>
                <div className="modalSubtitle">Измени базовые поля роли в отдельном компактном окне.</div>
              </div>
              <button className="btn" onClick={() => setShowRoleModal(false)} disabled={saving}>Закрыть</button>
            </div>

            <div className="accessPanel">
              <label className="accessField"><span>Код</span><input value={editingRole.code} onChange={(e) => setEditingRole((cur) => ({ ...cur, code: e.target.value }))} disabled={!!editingRole.is_system} /></label>
              <label className="accessField"><span>Название</span><input value={editingRole.name} onChange={(e) => setEditingRole((cur) => ({ ...cur, name: e.target.value }))} /></label>
              <label className="accessField"><span>Описание</span><textarea rows={6} value={editingRole.description || ""} onChange={(e) => setEditingRole((cur) => ({ ...cur, description: e.target.value }))} /></label>
            </div>

            <div className="accessActions" style={{ marginTop: 16 }}>
              <button className="btn" onClick={() => setShowRoleModal(false)} disabled={saving}>Отмена</button>
              <button className="btn primary" onClick={async () => { await saveRole(); setShowRoleModal(false); }} disabled={!canAction("roles.manage") || saving || loading}>
                Сохранить
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {showDeleteRoleModal ? (
        <div className="modalBackdrop" onClick={() => !saving && setShowDeleteRoleModal(false)}>
          <div className="modalCard modalCardCompact" onClick={(e) => e.stopPropagation()}>
            <div className="modalHeader">
              <div>
                <div className="modalTitle">Удалить роль</div>
                <div className="modalSubtitle">Роль будет удалена только если она не системная и не назначена пользователям.</div>
              </div>
              <button className="btn" onClick={() => setShowDeleteRoleModal(false)} disabled={saving}>Закрыть</button>
            </div>

            <div className="accessEmpty">
              Будет удалена роль <strong>{editingRole.name || editingRole.code}</strong>.
            </div>

            <div className="accessActions" style={{ marginTop: 16 }}>
              <button className="btn" onClick={() => setShowDeleteRoleModal(false)} disabled={saving}>Отмена</button>
              <button className="btn danger" onClick={deleteRole} disabled={!canAction("roles.manage") || saving || !editingRole.id || !!editingRole.is_system}>
                Удалить
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
