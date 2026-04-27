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
        <span className={`shellStatusBadge is-${organizationStatus.toLowerCase()}`}>{organizationStatus}</span>
        {isDeveloper ? <span className="shellRoleBadge">Developer</span> : null}
      </div>
    </div>
  );
}
