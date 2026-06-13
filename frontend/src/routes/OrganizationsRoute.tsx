import OrganizationsAdminFeature from "../domains/admin/OrganizationsAdminFeature";

type Props = {
  initialTab: "organizations" | "members" | "invites" | "roles" | "platform";
};

export default function OrganizationsRoute({ initialTab }: Props) {
  return <OrganizationsAdminFeature initialTab={initialTab} />;
}
