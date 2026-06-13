import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../app/auth/AuthContext";
import { useOrgPath } from "../../app/orgRoutes";
import DataList from "../../components/data/DataList";
import DataTable from "../../components/data/DataTable";
import InspectorPanel from "../../components/data/InspectorPanel";
import Alert from "../../components/ui/Alert";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import EmptyState from "../../components/ui/EmptyState";
import Field from "../../components/ui/Field";
import Select from "../../components/ui/Select";
import TextInput from "../../components/ui/TextInput";
import { api } from "../../lib/api";
import AdminAccessFeature from "./AdminAccessFeature";

type OrganizationRow = {
  id: string;
  slug: string;
  name: string;
  status: string;
  membership_role?: string | null;
  tenant_status?: string | null;
  member_count: number;
  pending_invite_count: number;
};

type MemberRow = {
  id: string;
  organization_id: string;
  user_id: string;
  org_role_code: string;
  status: string;
  email: string;
  name: string;
  user_status: string;
  last_login_at?: string | null;
};

type InviteRow = {
  id: string;
  organization_id: string;
  email: string;
  org_role_code: string;
  status: string;
  expires_at?: string | null;
  accepted_at?: string | null;
  created_at?: string | null;
  created_by_name?: string | null;
  created_by_email?: string | null;
};

type WorkspaceBootstrapResp = {
  ok: boolean;
  organizations: OrganizationRow[];
  selected_organization: OrganizationRow;
  members: MemberRow[];
  invites: InviteRow[];
};

type AdminMode = "organizations" | "members" | "invites" | "roles";

type Props = {
  initialTab: AdminMode | "platform";
};

const TAB_TO_PATH: Record<AdminMode, string> = {
  organizations: "/admin/organizations",
  members: "/admin/members",
  invites: "/admin/invites",
  roles: "/admin/roles?tab=roles",
};

const ROLE_LABELS: Record<string, string> = {
  org_owner: "Владелец",
  org_admin: "Администратор",
  org_editor: "Редактор",
  org_viewer: "Наблюдатель",
};

const ORG_ROLE_OPTIONS = [
  { value: "org_owner", label: "Владелец" },
  { value: "org_admin", label: "Администратор" },
  { value: "org_editor", label: "Редактор" },
  { value: "org_viewer", label: "Наблюдатель" },
];

function badgeToneFromStatus(status?: string | null): "neutral" | "active" | "provisioning" | "pending" | "danger" {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "active" || normalized === "ready" || normalized === "accepted") return "active";
  if (normalized === "provisioning") return "provisioning";
  if (normalized === "pending") return "pending";
  if (["failed", "error", "suspended", "revoked", "expired"].includes(normalized)) return "danger";
  return "neutral";
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString("ru-RU");
}

function roleLabel(code?: string | null) {
  return ROLE_LABELS[String(code || "")] || String(code || "—");
}

function personName(name?: string | null, email?: string | null) {
  const normalized = String(name || "").trim();
  if (normalized.toLowerCase() === "owner") return "Владелец";
  return normalized || String(email || "Сотрудник");
}

function statusLabel(status?: string | null) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "active" || normalized === "ready") return "Активна";
  if (normalized === "provisioning") return "Настраивается";
  if (normalized === "pending") return "Ожидает";
  if (normalized === "accepted") return "Принято";
  if (normalized === "expired") return "Истекло";
  if (["failed", "error", "suspended", "revoked"].includes(normalized)) return "Проблема";
  return "Неизвестно";
}

function organizationCaption(organization?: Pick<OrganizationRow, "id" | "slug"> | null) {
  if (!organization) return "Организация не выбрана";
  if (organization.id === "org_default" || organization.slug === "default") return "Основная организация";
  return "Рабочая организация";
}

function pluralRu(value: number, forms: [string, string, string]) {
  const abs = Math.abs(value) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}

function appendSearch(path: string, params: URLSearchParams) {
  const query = params.toString();
  if (!query) return path;
  return `${path}${path.includes("?") ? "&" : "?"}${query}`;
}

export default function OrganizationsAdminFeature({ initialTab }: Props) {
  const navigate = useNavigate();
  const orgPath = useOrgPath();
  const [searchParams, setSearchParams] = useSearchParams();
  const { currentOrganization, switchOrganization, user } = useAuth();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [bootstrap, setBootstrap] = useState<WorkspaceBootstrapResp | null>(null);
  const [query, setQuery] = useState("");
  const [selectedMemberId, setSelectedMemberId] = useState("");
  const [selectedInviteId, setSelectedInviteId] = useState("");
  const [memberRoleDraft, setMemberRoleDraft] = useState("org_editor");
  const [memberStatusDraft, setMemberStatusDraft] = useState("active");
  const [savingMember, setSavingMember] = useState(false);
  const [deletingMember, setDeletingMember] = useState(false);
  const [submittingInvite, setSubmittingInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("org_editor");
  const [inviteResult, setInviteResult] = useState("");

  const activeTab: AdminMode = initialTab === "platform" ? "organizations" : initialTab;
  const selectedOrganizationId = searchParams.get("organization") || currentOrganization?.id || "";

  async function load(targetOrganizationId?: string) {
    const organizationId = targetOrganizationId || selectedOrganizationId || currentOrganization?.id || "";
    if (!organizationId) {
      setBootstrap(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ organization_id: organizationId });
      const data = await api<WorkspaceBootstrapResp>(`/platform/workspace/bootstrap?${params.toString()}`);
      setBootstrap(data);
    } catch (err) {
      setError((err as Error).message || "Ошибка загрузки организаций");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedOrganizationId]);

  const selectedOrganization = bootstrap?.selected_organization || null;
  const organizationRows = bootstrap?.organizations || [];
  const members = bootstrap?.members || [];
  const invites = bootstrap?.invites || [];
  const pendingInvites = useMemo(() => invites.filter((invite) => invite.status === "pending"), [invites]);

  const selectedMember = useMemo(
    () => members.find((member) => member.id === selectedMemberId) || members[0] || null,
    [members, selectedMemberId],
  );
  const selectedInvite = useMemo(
    () => invites.find((invite) => invite.id === selectedInviteId) || pendingInvites[0] || invites[0] || null,
    [invites, pendingInvites, selectedInviteId],
  );
  const isSelectedMemberSelf = Boolean(selectedMember?.user_id && selectedMember.user_id === user?.id);

  useEffect(() => {
    if (!selectedMember) return;
    setMemberRoleDraft(selectedMember.org_role_code || "org_editor");
    setMemberStatusDraft(selectedMember.status || "active");
  }, [selectedMember?.id, selectedMember?.org_role_code, selectedMember?.status]);

  const filteredMembers = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || activeTab !== "members") return members;
    return members.filter((row) => `${row.name} ${row.email} ${row.org_role_code} ${row.status}`.toLowerCase().includes(q));
  }, [activeTab, members, query]);

  const filteredInvites = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || activeTab !== "invites") return invites;
    return invites.filter((row) => `${row.email} ${row.org_role_code} ${row.status}`.toLowerCase().includes(q));
  }, [activeTab, invites, query]);

  const searchPlaceholder =
    activeTab === "organizations" ? "Поиск организации" :
    activeTab === "members" ? "Поиск сотрудника" :
    activeTab === "invites" ? "Поиск приглашения" :
    "Поиск";

  async function handleOrganizationSelect(nextOrganizationId: string) {
    if (!nextOrganizationId) return;
    setError("");
    try {
      if (nextOrganizationId !== currentOrganization?.id) {
        await switchOrganization(nextOrganizationId);
      }
      setSearchParams((current) => {
        const next = new URLSearchParams(current);
        next.set("organization", nextOrganizationId);
        return next;
      });
    } catch (err) {
      setError((err as Error).message || "Не удалось переключить организацию");
    }
  }

  async function submitInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedOrganization) return;
    setSubmittingInvite(true);
    setError("");
    setInviteResult("");
    try {
      const data = await api<{ ok: boolean; invite: { token: string; email: string } }>(
        `/platform/organizations/${encodeURIComponent(selectedOrganization.id)}/invites`,
        {
          method: "POST",
          body: JSON.stringify({ email: inviteEmail.trim(), org_role_code: inviteRole }),
        },
      );
      const inviteUrl = `${window.location.origin}/invite/accept?token=${encodeURIComponent(data.invite.token)}&email=${encodeURIComponent(data.invite.email)}`;
      setInviteResult(inviteUrl);
      setInviteEmail("");
      await load(selectedOrganization.id);
    } catch (err) {
      setError((err as Error).message || "Не удалось создать приглашение");
    } finally {
      setSubmittingInvite(false);
    }
  }

  async function copyInviteLink() {
    if (!inviteResult) return;
    await navigator.clipboard.writeText(inviteResult);
  }

  async function saveSelectedMember() {
    if (!selectedOrganization || !selectedMember) return;
    setSavingMember(true);
    setError("");
    try {
      await api(`/platform/organizations/${encodeURIComponent(selectedOrganization.id)}/members/${encodeURIComponent(selectedMember.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ org_role_code: memberRoleDraft, status: memberStatusDraft }),
      });
      await load(selectedOrganization.id);
    } catch (err) {
      setError((err as Error).message || "Не удалось обновить участника");
    } finally {
      setSavingMember(false);
    }
  }

  async function deleteSelectedMember() {
    if (!selectedOrganization || !selectedMember) return;
    const confirmed = window.confirm(`Удалить доступ для ${personName(selectedMember.name, selectedMember.email)}?`);
    if (!confirmed) return;
    setDeletingMember(true);
    setError("");
    try {
      await api(`/platform/organizations/${encodeURIComponent(selectedOrganization.id)}/members/${encodeURIComponent(selectedMember.id)}`, {
        method: "DELETE",
      });
      setSelectedMemberId("");
      await load(selectedOrganization.id);
    } catch (err) {
      setError((err as Error).message || "Не удалось удалить участника");
    } finally {
      setDeletingMember(false);
    }
  }

  const organizationSwitcher = organizationRows.length > 1 ? (
    <div className="orgAdminSwitcher" aria-label="Выбор организации">
      {organizationRows.map((organization) => (
        <button
          key={organization.id}
          type="button"
          className={`orgAdminSwitchCard${organization.id === selectedOrganizationId ? " active" : ""}`}
          onClick={() => void handleOrganizationSelect(organization.id)}
        >
          <span>{organization.name}</span>
          <Badge tone={badgeToneFromStatus(organization.status)}>{statusLabel(organization.status)}</Badge>
        </button>
      ))}
    </div>
  ) : null;

  const inspector = (
    <div className="orgAdminInspectorStack">
      <InspectorPanel title="Текущая организация" subtitle={organizationCaption(selectedOrganization)}>
        {selectedOrganization ? (
          <div className="orgAdminInspectorRows">
            <div><span>Статус</span><Badge tone={badgeToneFromStatus(selectedOrganization.status)}>{statusLabel(selectedOrganization.status)}</Badge></div>
            <div><span>Роль</span><strong>{roleLabel(selectedOrganization.membership_role)}</strong></div>
            <div><span>Доступ</span><strong>{selectedOrganization.tenant_status ? statusLabel(selectedOrganization.tenant_status) : "Готов"}</strong></div>
            <div><span>Сотрудники</span><strong>{selectedOrganization.member_count}</strong></div>
            <div><span>Приглашения</span><strong>{selectedOrganization.pending_invite_count}</strong></div>
          </div>
        ) : (
          <div className="dataListEmpty">Организация не выбрана.</div>
        )}
      </InspectorPanel>

      {activeTab === "invites" ? (
        <InspectorPanel title="Приглашение" subtitle={selectedInvite?.email || "Нет активного выбора"}>
          {selectedInvite ? (
            <div className="orgAdminInspectorRows">
              <div><span>Роль</span><strong>{roleLabel(selectedInvite.org_role_code)}</strong></div>
              <div><span>Статус</span><Badge tone={badgeToneFromStatus(selectedInvite.status)}>{statusLabel(selectedInvite.status)}</Badge></div>
              <div><span>Создан</span><strong>{formatDate(selectedInvite.created_at)}</strong></div>
              <div><span>Истекает</span><strong>{formatDate(selectedInvite.expires_at)}</strong></div>
              <div><span>Принят</span><strong>{formatDate(selectedInvite.accepted_at)}</strong></div>
            </div>
          ) : (
            <div className="dataListEmpty">Приглашений пока нет.</div>
          )}
        </InspectorPanel>
      ) : null}

      {activeTab === "members" ? (
        <InspectorPanel title="Участник команды" subtitle={selectedMember?.email || "Выберите сотрудника"}>
          {selectedMember ? (
            <div className="orgAdminMemberEditor">
              <div className="orgAdminInspectorRows">
                <div><span>Имя</span><strong>{personName(selectedMember.name, selectedMember.email)}</strong></div>
                <div><span>Email</span><strong>{selectedMember.email || "—"}</strong></div>
                <div><span>Последний вход</span><strong>{formatDate(selectedMember.last_login_at)}</strong></div>
                <div><span>Статус аккаунта</span><Badge tone={badgeToneFromStatus(selectedMember.user_status)}>{statusLabel(selectedMember.user_status)}</Badge></div>
              </div>
              <Field label="Роль в организации">
                <Select value={memberRoleDraft} onChange={(event) => setMemberRoleDraft(event.target.value)}>
                  {ORG_ROLE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Доступ">
                <Select value={memberStatusDraft} onChange={(event) => setMemberStatusDraft(event.target.value)}>
                  <option value="active">Активен</option>
                  <option value="disabled">Отключен</option>
                </Select>
              </Field>
              <div className="orgAdminInspectorActions">
                <Button variant="primary" onClick={() => void saveSelectedMember()} disabled={savingMember || deletingMember}>
                  {savingMember ? "Сохраняем..." : "Сохранить"}
                </Button>
                <Button variant="danger" onClick={() => void deleteSelectedMember()} disabled={savingMember || deletingMember || isSelectedMemberSelf}>
                  {deletingMember ? "Удаляем..." : "Удалить из организации"}
                </Button>
              </div>
            </div>
          ) : (
            <div className="dataListEmpty">Выберите сотрудника в списке.</div>
          )}
        </InspectorPanel>
      ) : null}

    </div>
  );

  const main = (
    <div className="orgAdminMain">
      <div className="orgAdminCommand">
        <div>
          <div className="orgAdminCommandTitle">
            {activeTab === "organizations" ? "Организация" : activeTab === "members" ? "Команда" : activeTab === "roles" ? "Роли" : "Приглашения"}
          </div>
          <div className="orgAdminCommandMeta">
            {selectedOrganization ? `${selectedOrganization.name} · ${organizationCaption(selectedOrganization)}` : "Организация не выбрана"}
          </div>
        </div>
        {activeTab === "members" || activeTab === "invites" ? (
          <TextInput
            className="orgAdminSearch"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={searchPlaceholder}
          />
        ) : null}
      </div>

      {loading ? <div className="pageLoading">Загрузка...</div> : null}
      {!loading && !selectedOrganization ? <EmptyState title="Нет доступной организации" description="Организация нужна для управления сотрудниками и приглашениями." /> : null}

      {!loading && selectedOrganization && activeTab === "organizations" ? (
        <div className="orgAdminOrgOverview">
          <div className="orgAdminOrgHero">
            <div>
              <div className="orgAdminSectionTitle">Организация</div>
              <h2>{selectedOrganization.name}</h2>
              <p>{organizationCaption(selectedOrganization)} для управления каталогом, товарами, импортом, экспортом и командой.</p>
            </div>
            <Badge tone={badgeToneFromStatus(selectedOrganization.status)}>{statusLabel(selectedOrganization.status)}</Badge>
          </div>
          <section className="orgAdminStatusStrip" aria-label="Состояние организации">
            <div>
              <span>Сотрудники</span>
              <strong>{selectedOrganization.member_count}</strong>
              <em>имеют доступ</em>
            </div>
            <div>
              <span>Приглашения</span>
              <strong>{selectedOrganization.pending_invite_count}</strong>
              <em>ожидают принятия</em>
            </div>
            <div>
              <span>Контур</span>
              <strong>{selectedOrganization.tenant_status ? statusLabel(selectedOrganization.tenant_status) : "Готова"}</strong>
              <em>рабочая организация</em>
            </div>
          </section>
          <div className="orgAdminNextSteps">
            <button type="button" onClick={() => navigate(orgPath(`/admin/members?organization=${encodeURIComponent(selectedOrganization.id)}`))}>
              <span>Команда</span>
              <strong>Проверить сотрудников и роли</strong>
            </button>
            <button type="button" onClick={() => navigate(orgPath(`/admin/invites?organization=${encodeURIComponent(selectedOrganization.id)}`))}>
              <span>Приглашения</span>
              <strong>Добавить нового сотрудника</strong>
            </button>
            <button type="button" onClick={() => navigate(orgPath(`/admin/roles?tab=roles&organization=${encodeURIComponent(selectedOrganization.id)}`))}>
              <span>Роли</span>
              <strong>Настроить права команды</strong>
            </button>
          </div>
        </div>
      ) : null}

      {!loading && selectedOrganization && activeTab === "members" ? (
        <DataList
          className="orgAdminPeopleList"
          items={filteredMembers}
          empty="Сотрудники не найдены."
          renderItem={(member) => (
            <button
              key={member.id}
              type="button"
              className={`orgAdminPersonRow${member.id === selectedMember?.id ? " active" : ""}`}
              onClick={() => setSelectedMemberId(member.id)}
            >
              <span className="orgAdminPersonIdentity">
                <span className="orgAdminPersonAvatar">{personName(member.name, member.email).slice(0, 2).toUpperCase()}</span>
                <span>
                  <strong>{personName(member.name, member.email)}</strong>
                  <small>{member.email}</small>
                </span>
              </span>
              <span className="orgAdminPersonMeta">
                <span>{roleLabel(member.org_role_code)}</span>
                <Badge tone={badgeToneFromStatus(member.status)}>{statusLabel(member.status)}</Badge>
                <small>{formatDate(member.last_login_at)}</small>
              </span>
            </button>
          )}
        />
      ) : null}

      {!loading && selectedOrganization && activeTab === "invites" ? (
        <div className="orgAdminInvites">
          <form className="orgAdminInviteForm" onSubmit={(event) => void submitInvite(event)}>
            <div className="orgAdminSectionTitle">Новое приглашение</div>
            <Field label="Email сотрудника">
              <TextInput value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} placeholder="user@company.ru" autoComplete="email" />
            </Field>
            <Field label="Роль">
              <Select value={inviteRole} onChange={(event) => setInviteRole(event.target.value)}>
                <option value="org_admin">Администратор</option>
                <option value="org_editor">Редактор</option>
                <option value="org_viewer">Наблюдатель</option>
              </Select>
            </Field>
            <Button type="submit" variant="primary" disabled={submittingInvite || !inviteEmail.trim()}>
              {submittingInvite ? "Создаем..." : "Создать приглашение"}
            </Button>
            {inviteResult ? (
              <div className="orgAdminInviteResult">
                <Alert tone="success" className="orgAdminInviteLink">{inviteResult}</Alert>
                <Button onClick={() => void copyInviteLink()}>Копировать ссылку</Button>
              </div>
            ) : null}
          </form>

          <DataTable
            className="orgAdminTable"
            gridTemplate="minmax(150px,1fr) 96px 72px 92px"
            rows={filteredInvites}
            rowKey={(invite) => invite.id}
            empty="Приглашения не найдены."
            columns={[
              {
                key: "invite",
                label: "Email",
                render: (invite) => (
                  <button className="orgAdminEntityButton" type="button" onClick={() => setSelectedInviteId(invite.id)}>
                    <span>{invite.email}</span>
                    <small>{invite.created_by_email || invite.created_by_name || "Создано системой"}</small>
                  </button>
                ),
              },
              { key: "role", label: "Роль", render: (invite) => roleLabel(invite.org_role_code) },
              { key: "status", label: "Статус", render: (invite) => <Badge tone={badgeToneFromStatus(invite.status)}>{statusLabel(invite.status)}</Badge> },
              { key: "expires", label: "Истекает", render: (invite) => formatDate(invite.expires_at) },
            ]}
          />
        </div>
      ) : null}

      {!loading && selectedOrganization && activeTab === "roles" ? (
        <div className="orgAdminAccessEmbed">
          <AdminAccessFeature embedded />
        </div>
      ) : null}

    </div>
  );

  const showInlineInspector = activeTab === "members" || activeTab === "invites";

  return (
    <div className="page-shell orgAdminPage">
      <header className="orgAdminCommandHeader">
        <div className="orgAdminCommandContext">
          <span>Система / доступ</span>
          <h1>Организации и команда</h1>
          <p>Переключайте организацию, проверяйте роли и отправляйте приглашения без отдельной админки.</p>
        </div>
        <div className="orgAdminCommandControls">
          <nav className="orgAdminSegmentedTabs" aria-label="Раздел администрирования">
            {[
              { key: "organizations", label: "Организации" },
              { key: "members", label: "Команда" },
              { key: "invites", label: "Приглашения" },
              { key: "roles", label: "Роли" },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                className={activeTab === item.key ? "active" : ""}
                onClick={() => {
                  const next = item.key as AdminMode;
                  navigate(orgPath(appendSearch(TAB_TO_PATH[next], searchParams)));
                }}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <Button onClick={() => void load()}>Обновить</Button>
        </div>
      </header>

      {error ? <Alert tone="error" className="orgAdminNotice">{error}</Alert> : null}

      <div className={`orgAdminWorkspaceFlat${organizationSwitcher ? "" : " noSwitcher"}`}>
        {organizationSwitcher}
        <div className={`orgAdminWorkSurface${showInlineInspector ? "" : " noInspector"}`}>
          <div className="orgAdminWorkMain">{main}</div>
          {showInlineInspector ? <aside className="orgAdminInlineInspector">{inspector}</aside> : null}
        </div>
      </div>
    </div>
  );
}
