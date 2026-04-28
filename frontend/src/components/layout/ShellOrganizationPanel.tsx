export type ShellOrganizationOption = {
  id: string;
  name: string;
  status?: string;
};

export default function ShellOrganizationPanel({
  organizations,
  currentOrganization,
  switching,
  onChange,
  organizationStatus,
  isDeveloper,
}: {
  organizations: ShellOrganizationOption[];
  currentOrganization: ShellOrganizationOption | null;
  switching: boolean;
  onChange: (organizationId: string) => void;
  organizationStatus: string;
  isDeveloper: boolean;
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
    <div className="shellSidebarOrg">
      <div className="shellSidebarOrgEyebrow">Организация</div>
      {organizations.length > 1 ? (
        <select
          className="shellSidebarSelect"
          value={currentOrganization.id}
          onChange={(e) => onChange(e.target.value)}
          disabled={switching}
        >
          {organizations.map((organization) => (
            <option key={organization.id} value={organization.id}>
              {organization.name}
            </option>
          ))}
        </select>
      ) : (
        <div className="shellSidebarOrgName">{currentOrganization.name}</div>
      )}
      <div className="shellSidebarStatusRow">
        <span className={`shellStatusBadge is-${normalizedStatus}`}>{statusLabel}</span>
        {isDeveloper ? <span className="shellRoleBadge">Разработчик</span> : null}
      </div>
    </div>
  );
}
