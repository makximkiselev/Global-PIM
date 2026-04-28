import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../app/auth/AuthContext";
import DataList from "../../components/data/DataList";
import DataTable from "../../components/data/DataTable";
import InspectorPanel from "../../components/data/InspectorPanel";
import MetricGrid from "../../components/data/MetricGrid";
import WorkspaceFrame from "../../components/layout/WorkspaceFrame";
import Alert from "../../components/ui/Alert";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import EmptyState from "../../components/ui/EmptyState";
import Field from "../../components/ui/Field";
import PageHeader from "../../components/ui/PageHeader";
import PageTabs from "../../components/ui/PageTabs";
import Select from "../../components/ui/Select";
import TextInput from "../../components/ui/TextInput";
import { api } from "../../lib/api";

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
  platform_user_id: string;
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
  platform_roles: Array<{ code: string; name: string }>;
  flags?: { is_developer?: boolean };
};

type AdminMode = "organizations" | "members" | "invites" | "platform";

type Props = {
  initialTab: AdminMode;
};

const TAB_TO_PATH: Record<AdminMode, string> = {
  organizations: "/admin/organizations",
  members: "/admin/members",
  invites: "/admin/invites",
  platform: "/admin/platform",
};

const ROLE_LABELS: Record<string, string> = {
  org_owner: "Владелец",
  org_admin: "Администратор",
  org_editor: "Редактор",
  org_viewer: "Наблюдатель",
};

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

export default function OrganizationsAdminFeature({ initialTab }: Props) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { currentOrganization, switchOrganization, isDeveloper, provisioningStatus } = useAuth();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [bootstrap, setBootstrap] = useState<WorkspaceBootstrapResp | null>(null);
  const [query, setQuery] = useState("");
  const [selectedMemberId, setSelectedMemberId] = useState("");
  const [selectedInviteId, setSelectedInviteId] = useState("");
  const [submittingInvite, setSubmittingInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("org_editor");
  const [inviteResult, setInviteResult] = useState("");

  const activeTab: AdminMode = initialTab === "platform" && !isDeveloper ? "organizations" : initialTab;
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

  const filteredOrganizations = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || activeTab !== "organizations") return organizationRows;
    return organizationRows.filter((row) => `${row.name} ${row.slug} ${row.status}`.toLowerCase().includes(q));
  }, [activeTab, organizationRows, query]);

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
    activeTab === "invites" ? "Поиск инвайта" :
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

  const sidebar = (
    <div className="orgAdminSidebar">
      <div className="orgAdminSidebarHead">
        <div>
          <div className="orgAdminSidebarTitle">Организации</div>
          <div className="orgAdminSidebarMeta">{organizationRows.length} доступно</div>
        </div>
        <Button onClick={() => void load()}>Обновить</Button>
      </div>
      <div className="orgAdminSidebarList">
        {organizationRows.map((organization) => (
          <button
            key={organization.id}
            type="button"
            className={`orgAdminOrgCard${organization.id === selectedOrganizationId ? " active" : ""}`}
            onClick={() => void handleOrganizationSelect(organization.id)}
          >
            <div className="orgAdminOrgTop">
              <div>
                <div className="orgAdminOrgName">{organization.name}</div>
                <div className="orgAdminOrgMeta">{organization.slug}</div>
              </div>
              <Badge tone={badgeToneFromStatus(organization.status)}>{organization.status}</Badge>
            </div>
            <div className="orgAdminOrgStats">
              <span>{organization.member_count} сотрудников</span>
              <span>{organization.pending_invite_count} pending</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );

  const inspector = (
    <div className="orgAdminInspectorStack">
      <InspectorPanel title="Текущая организация" subtitle={selectedOrganization?.slug || "Контекст не выбран"}>
        {selectedOrganization ? (
          <div className="orgAdminInspectorRows">
            <div><span>Статус</span><Badge tone={badgeToneFromStatus(selectedOrganization.status)}>{selectedOrganization.status}</Badge></div>
            <div><span>Роль</span><strong>{roleLabel(selectedOrganization.membership_role)}</strong></div>
            <div><span>Tenant</span><strong>{selectedOrganization.tenant_status || "—"}</strong></div>
            <div><span>Сотрудники</span><strong>{selectedOrganization.member_count}</strong></div>
            <div><span>Pending</span><strong>{selectedOrganization.pending_invite_count}</strong></div>
          </div>
        ) : (
          <div className="dataListEmpty">Организация не выбрана.</div>
        )}
      </InspectorPanel>

      {activeTab === "invites" ? (
        <InspectorPanel title="Инвайт" subtitle={selectedInvite?.email || "Нет активного выбора"}>
          {selectedInvite ? (
            <div className="orgAdminInspectorRows">
              <div><span>Роль</span><strong>{roleLabel(selectedInvite.org_role_code)}</strong></div>
              <div><span>Статус</span><Badge tone={badgeToneFromStatus(selectedInvite.status)}>{selectedInvite.status}</Badge></div>
              <div><span>Создан</span><strong>{formatDate(selectedInvite.created_at)}</strong></div>
              <div><span>Истекает</span><strong>{formatDate(selectedInvite.expires_at)}</strong></div>
              <div><span>Принят</span><strong>{formatDate(selectedInvite.accepted_at)}</strong></div>
            </div>
          ) : (
            <div className="dataListEmpty">Инвайты пока отсутствуют.</div>
          )}
        </InspectorPanel>
      ) : null}

      {activeTab === "platform" && isDeveloper ? (
        <InspectorPanel title="Platform" subtitle="Developer visibility">
          <div className="orgAdminInspectorRows">
            <div><span>Current org</span><strong>{currentOrganization?.name || "—"}</strong></div>
            <div><span>Provisioning</span><strong>{provisioningStatus?.organization?.status || selectedOrganization?.status || "—"}</strong></div>
            <div><span>Latest job</span><strong>{provisioningStatus?.latest_job?.status || "—"}</strong></div>
          </div>
        </InspectorPanel>
      ) : null}
    </div>
  );

  const main = (
    <div className="orgAdminMain">
      <div className="orgAdminCommand">
        <div>
          <div className="orgAdminCommandTitle">
            {activeTab === "organizations" ? "Организации" : activeTab === "members" ? "Команда" : activeTab === "invites" ? "Приглашения" : "Platform"}
          </div>
          <div className="orgAdminCommandMeta">
            {selectedOrganization ? `${selectedOrganization.name} · ${selectedOrganization.slug}` : "Контекст организации не выбран"}
          </div>
        </div>
        <TextInput
          className="orgAdminSearch"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={searchPlaceholder}
        />
      </div>

      {loading ? <div className="pageLoading">Загрузка...</div> : null}
      {!loading && !selectedOrganization ? <EmptyState title="Нет доступной организации" description="Организация нужна для управления сотрудниками и инвайтами." /> : null}

      {!loading && selectedOrganization && activeTab === "organizations" ? (
        <>
          <MetricGrid
            className="orgAdminGrid"
            items={[
              { label: "Сотрудники", value: selectedOrganization.member_count },
              { label: "Pending invite", value: selectedOrganization.pending_invite_count },
              { label: "Tenant status", value: selectedOrganization.tenant_status || "—" },
            ]}
          />
          <DataTable
            className="orgAdminTable"
            gridTemplate="minmax(120px,1fr) 70px 44px 44px"
            rows={filteredOrganizations}
            rowKey={(organization) => organization.id}
            empty="Организации не найдены."
            columns={[
              {
                key: "organization",
                label: "Организация",
                render: (organization) => (
                  <button className="orgAdminEntityButton" type="button" onClick={() => void handleOrganizationSelect(organization.id)}>
                    <span>{organization.name}</span>
                    <small>{organization.slug}</small>
                  </button>
                ),
              },
              { key: "status", label: "Статус", render: (organization) => <Badge tone={badgeToneFromStatus(organization.status)}>{organization.status}</Badge> },
              { key: "members", label: "Сотрудники", render: (organization) => organization.member_count },
              { key: "invites", label: "Pending", render: (organization) => organization.pending_invite_count },
            ]}
          />
        </>
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
                <span className="orgAdminPersonAvatar">{(member.name || member.email || "?").slice(0, 2).toUpperCase()}</span>
                <span>
                  <strong>{member.name || member.email}</strong>
                  <small>{member.email}</small>
                </span>
              </span>
              <span className="orgAdminPersonMeta">
                <span>{roleLabel(member.org_role_code)}</span>
                <Badge tone={badgeToneFromStatus(member.status)}>{member.status}</Badge>
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
              {submittingInvite ? "Создаем..." : "Создать инвайт"}
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
            empty="Инвайты не найдены."
            columns={[
              {
                key: "invite",
                label: "Email",
                render: (invite) => (
                  <button className="orgAdminEntityButton" type="button" onClick={() => setSelectedInviteId(invite.id)}>
                    <span>{invite.email}</span>
                    <small>{invite.created_by_email || invite.created_by_name || "system"}</small>
                  </button>
                ),
              },
              { key: "role", label: "Роль", render: (invite) => roleLabel(invite.org_role_code) },
              { key: "status", label: "Статус", render: (invite) => <Badge tone={badgeToneFromStatus(invite.status)}>{invite.status}</Badge> },
              { key: "expires", label: "Истекает", render: (invite) => formatDate(invite.expires_at) },
            ]}
          />
        </div>
      ) : null}

      {!loading && selectedOrganization && activeTab === "platform" && isDeveloper ? (
        <MetricGrid
          className="orgAdminPlatform"
          items={[
            { label: "Current organization", value: currentOrganization?.name || "—" },
            { label: "Provisioning status", value: provisioningStatus?.organization?.status || selectedOrganization.status },
            { label: "Latest job", value: provisioningStatus?.latest_job?.status || "—" },
          ]}
        />
      ) : null}
    </div>
  );

  const showInlineInspector = activeTab !== "members";

  return (
    <div className="page-shell orgAdminPage">
      <PageHeader
        title="Администрирование"
        subtitle="Организации, команда и права доступа без лишних панелей."
        actions={<Button onClick={() => void load()}>Обновить</Button>}
      />

      <PageTabs
        activeKey={activeTab}
        className="orgAdminTabs"
        items={[
          { key: "organizations", label: "Организации" },
          { key: "members", label: "Команда" },
          { key: "invites", label: "Инвайты" },
          ...(isDeveloper ? [{ key: "platform", label: "Platform" }] : []),
        ]}
        onChange={(key) => {
          const next = key as AdminMode;
          navigate(`${TAB_TO_PATH[next]}?${searchParams.toString()}`);
        }}
      />

      {error ? <Alert tone="error" className="orgAdminNotice">{error}</Alert> : null}

      <WorkspaceFrame
        className="orgAdminWorkspace"
        sidebar={sidebar}
        main={(
          <div className={`orgAdminWorkSurface${showInlineInspector ? "" : " noInspector"}`}>
            <div className="orgAdminWorkMain">{main}</div>
            {showInlineInspector ? <aside className="orgAdminInlineInspector">{inspector}</aside> : null}
          </div>
        )}
      />
    </div>
  );
}
