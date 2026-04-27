import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../app/auth/AuthContext";
import DataList from "../components/data/DataList";
import DataTable from "../components/data/DataTable";
import InspectorPanel from "../components/data/InspectorPanel";
import MetricGrid from "../components/data/MetricGrid";
import Alert from "../components/ui/Alert";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Field from "../components/ui/Field";
import PageHeader from "../components/ui/PageHeader";
import PageTabs from "../components/ui/PageTabs";
import Select from "../components/ui/Select";
import TextInput from "../components/ui/TextInput";

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

type Props = {
  initialTab: "organizations" | "members" | "invites" | "platform";
};

const ROLE_LABELS: Record<string, string> = {
  org_owner: "Владелец",
  org_admin: "Администратор",
  org_editor: "Редактор",
  org_viewer: "Наблюдатель",
};

function badgeToneFromStatus(status?: string | null): "neutral" | "active" | "provisioning" | "pending" | "danger" {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "active" || normalized === "ready") return "active";
  if (normalized === "provisioning") return "provisioning";
  if (normalized === "pending") return "pending";
  if (["failed", "error", "suspended"].includes(normalized)) return "danger";
  return "neutral";
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString("ru-RU");
}

export default function OrganizationsAdmin({ initialTab }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    currentOrganization,
    switchOrganization,
    isDeveloper,
    provisioningStatus,
  } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [submittingInvite, setSubmittingInvite] = useState(false);
  const [bootstrap, setBootstrap] = useState<WorkspaceBootstrapResp | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("org_editor");
  const [inviteResult, setInviteResult] = useState("");

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
      const query = new URLSearchParams({ organization_id: organizationId });
      const data = await api<WorkspaceBootstrapResp>(`/platform/workspace/bootstrap?${query.toString()}`);
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
  const activeTab = initialTab === "platform" && !isDeveloper ? "organizations" : initialTab;

  const pendingInvites = useMemo(() => invites.filter((invite) => invite.status === "pending"), [invites]);
  const acceptedInvites = useMemo(() => invites.filter((invite) => invite.status !== "pending"), [invites]);

  async function handleOrganizationSelect(nextOrganizationId: string) {
    if (!nextOrganizationId || nextOrganizationId === currentOrganization?.id) {
      setSearchParams((current) => {
        const next = new URLSearchParams(current);
        next.set("organization", nextOrganizationId);
        return next;
      });
      return;
    }
    setError("");
    try {
      await switchOrganization(nextOrganizationId);
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

  return (
    <div className="page-shell orgAdminPage">
      <PageHeader
        title="Организации и доступ"
        subtitle="Управление организациями, сотрудниками и инвайтами в одном рабочем контуре."
        actions={
          <Button onClick={() => void load()}>
            Обновить
          </Button>
        }
      />

      <PageTabs
        activeKey={activeTab}
        items={[
          { key: "organizations", label: "Организации" },
          { key: "members", label: "Сотрудники" },
          { key: "invites", label: "Приглашения" },
          ...(isDeveloper ? [{ key: "platform", label: "Platform" }] : []),
        ]}
      />

      {error ? <Alert tone="error" className="orgAdminNotice">{error}</Alert> : null}

      <Card className="orgAdminLayout">
        <aside className="orgAdminSidebar">
          <div className="orgAdminSidebarTitle">Доступные организации</div>
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
                  <span>{organization.pending_invite_count} инвайтов</span>
                </div>
              </button>
            ))}
          </div>
        </aside>

        <section className="orgAdminContent">
          {loading ? (
            <div className="pageLoading">Загрузка...</div>
          ) : !selectedOrganization ? (
            <div className="orgAdminEmpty">Нет доступной организации.</div>
          ) : (
            <>
              <div className="orgAdminHero">
                <div>
                  <div className="orgAdminEyebrow">
                    {selectedOrganization.membership_role ? ROLE_LABELS[selectedOrganization.membership_role] || selectedOrganization.membership_role : "Организация"}
                  </div>
                  <h1 className="orgAdminTitle">{selectedOrganization.name}</h1>
                  <div className="orgAdminMeta">
                    <span>{selectedOrganization.slug}</span>
                    <span>{selectedOrganization.member_count} сотрудников</span>
                    <span>{selectedOrganization.pending_invite_count} pending</span>
                  </div>
                </div>
                <div className="orgAdminHeroStatus">
                  <Badge tone={badgeToneFromStatus(selectedOrganization.status)}>{selectedOrganization.status}</Badge>
                  {selectedOrganization.tenant_status ? <span className="shellStatusMeta">tenant: {selectedOrganization.tenant_status}</span> : null}
                </div>
              </div>

              {activeTab === "organizations" ? (
                <MetricGrid
                  className="orgAdminGrid"
                  items={[
                    { label: "Сотрудники", value: selectedOrganization.member_count },
                    { label: "Pending invite", value: selectedOrganization.pending_invite_count },
                    { label: "Tenant status", value: selectedOrganization.tenant_status || "—" },
                  ]}
                />
              ) : null}

              {activeTab === "members" ? (
                <DataTable
                  className="orgAdminTable"
                  gridTemplate="minmax(0,1.4fr) 180px 120px 180px"
                  rows={members}
                  rowKey={(member) => member.id}
                  empty="Сотрудники пока не найдены."
                  columns={[
                    {
                      key: "member",
                      label: "Сотрудник",
                      render: (member) => (
                        <div>
                          <div className="orgAdminCellTitle">{member.name || member.email}</div>
                          <div className="orgAdminCellMeta">{member.email}</div>
                        </div>
                      ),
                    },
                    {
                      key: "role",
                      label: "Роль",
                      render: (member) => ROLE_LABELS[member.org_role_code] || member.org_role_code,
                    },
                    {
                      key: "status",
                      label: "Статус",
                      render: (member) => member.status,
                    },
                    {
                      key: "last_login",
                      label: "Последний вход",
                      render: (member) => formatDate(member.last_login_at),
                    },
                  ]}
                />
              ) : null}

              {activeTab === "invites" ? (
                <div className="orgAdminInvites">
                  <InspectorPanel
                    title="Новое приглашение"
                    subtitle="Создай ссылку доступа для сотрудника внутри текущей организации."
                    className="orgAdminInvitePanel"
                  >
                  <form className="orgAdminInviteForm" onSubmit={(e) => void submitInvite(e)}>
                    <Field label="Email сотрудника">
                      <TextInput
                        value={inviteEmail}
                        onChange={(e) => setInviteEmail(e.target.value)}
                        placeholder="user@company.ru"
                        autoComplete="email"
                      />
                    </Field>
                    <Field label="Роль">
                      <Select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}>
                        <option value="org_admin">Администратор</option>
                        <option value="org_editor">Редактор</option>
                        <option value="org_viewer">Наблюдатель</option>
                      </Select>
                    </Field>
                    <Button type="submit" variant="primary" disabled={submittingInvite}>
                      {submittingInvite ? "Создаем..." : "Создать инвайт"}
                    </Button>
                    {inviteResult ? (
                      <div className="orgAdminInviteResult">
                        <div className="orgAdminSectionTitle">Ссылка приглашения</div>
                        <Alert tone="success" className="orgAdminInviteLink">{inviteResult}</Alert>
                        <Button onClick={() => void copyInviteLink()}>
                          Копировать ссылку
                        </Button>
                      </div>
                    ) : null}
                  </form>
                  </InspectorPanel>

                  <div className="orgAdminInviteLists">
                    <DataList
                      title="Pending"
                      items={pendingInvites}
                      empty="Нет активных приглашений."
                      renderItem={(invite) => (
                        <Card className="orgAdminStackCard" key={invite.id}>
                          <div className="orgAdminCellTitle">{invite.email}</div>
                          <div className="orgAdminCellMeta">
                            {ROLE_LABELS[invite.org_role_code] || invite.org_role_code} · до {formatDate(invite.expires_at)}
                          </div>
                        </Card>
                      )}
                    />

                    <DataList
                      title="История"
                      items={acceptedInvites}
                      empty="История инвайтов пока пустая."
                      renderItem={(invite) => (
                        <Card className="orgAdminStackCard" key={invite.id}>
                          <div className="orgAdminCellTitle">{invite.email}</div>
                          <div className="orgAdminCellMeta">
                            {invite.status} · {formatDate(invite.accepted_at || invite.created_at)}
                          </div>
                        </Card>
                      )}
                    />
                  </div>
                </div>
              ) : null}

              {activeTab === "platform" && isDeveloper ? (
                <MetricGrid
                  className="orgAdminPlatform"
                  items={[
                    { label: "Current organization", value: currentOrganization?.name || "—" },
                    { label: "Provisioning status", value: provisioningStatus?.organization?.status || selectedOrganization.status },
                    { label: "Latest job", value: provisioningStatus?.latest_job?.status || "—" },
                  ]}
                />
              ) : null}
            </>
          )}
        </section>
      </Card>
    </div>
  );
}
