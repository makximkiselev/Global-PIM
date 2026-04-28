import Button from "../ui/Button";
import ShellThemeToggle from "./ShellThemeToggle";

type OrganizationOption = {
  id: string;
  name: string;
  status?: string;
};

export default function ShellWorkspaceBar({
  organizations,
  currentOrganization,
  switching,
  onChange,
  organizationStatus,
  isDeveloper,
  userName,
  userMeta,
  onChangePassword,
  onLogout,
}: {
  organizations: OrganizationOption[];
  currentOrganization: OrganizationOption | null;
  switching: boolean;
  onChange: (organizationId: string) => void;
  organizationStatus: string;
  isDeveloper: boolean;
  userName: string;
  userMeta: string;
  onChangePassword: () => void;
  onLogout: () => void;
}) {
  if (!currentOrganization) return null;
  const normalizedStatus = organizationStatus.toLowerCase();
  const statusLabel =
    normalizedStatus === "active" || normalizedStatus === "ready" ? "Активна" :
    normalizedStatus === "provisioning" ? "Настраивается" :
    normalizedStatus === "pending" ? "Ожидает" :
    ["failed", "error", "suspended", "revoked"].includes(normalizedStatus) ? "Проблема" :
    "Неизвестно";

  return (
    <div className="shellWorkspaceBar">
      <div className="shellWorkspaceCluster">
        <div className="shellWorkspaceBlock">
          <div className="shellWorkspaceLabel">Организация</div>
          {organizations.length > 1 ? (
            <select
              className="shellWorkspaceSelect"
              value={currentOrganization.id}
              onChange={(event) => onChange(event.target.value)}
              disabled={switching}
            >
              {organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.name}
                </option>
              ))}
            </select>
          ) : (
            <div className="shellWorkspaceValue">{currentOrganization.name}</div>
          )}
        </div>
        <div className="shellWorkspaceBadges">
          <span className={`shellStatusBadge is-${normalizedStatus}`}>{statusLabel}</span>
          {isDeveloper ? <span className="shellRoleBadge">Разработчик</span> : null}
        </div>
      </div>

      <div className="shellWorkspaceCluster isActions">
        <div className="shellWorkspaceUser">
          <div className="shellWorkspaceUserName">{userName}</div>
          <div className="shellWorkspaceUserMeta">{userMeta}</div>
        </div>
        <div className="shellWorkspaceButtons">
          <ShellThemeToggle />
          <Button className="shellWorkspaceButton" onClick={onChangePassword}>
            Сменить пароль
          </Button>
          <Button className="shellWorkspaceButton" onClick={onLogout}>
            Выйти
          </Button>
        </div>
      </div>
    </div>
  );
}
