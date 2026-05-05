import OrganizationsAdminFeature from "../domains/admin/OrganizationsAdminFeature";

type Props = {
  initialTab: "organizations" | "members" | "invites" | "platform";
};

export default function OrganizationsRoute({ initialTab }: Props) {
  return <OrganizationsAdminFeature initialTab={initialTab} />;
}
