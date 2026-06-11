export type OrganizationRouteRef = {
  id: string;
  org_key?: string | null;
  slug?: string | null;
};

export function orgRouteKey(organization: OrganizationRouteRef | null | undefined): string {
  return String(organization?.org_key || organization?.slug || organization?.id || "").trim();
}

export function stripOrgPrefix(pathname: string): { orgKey: string; appPath: string } {
  const normalized = pathname.startsWith("/") ? pathname : `/${pathname}`;
  const match = normalized.match(/^\/org\/([^/]+)(\/.*)?$/);
  if (!match) return { orgKey: "", appPath: normalized || "/" };
  return {
    orgKey: decodeURIComponent(match[1] || ""),
    appPath: match[2] || "/",
  };
}

export function withOrgPath(organization: OrganizationRouteRef | null | undefined, appPath: string): string {
  const key = orgRouteKey(organization);
  const path = appPath.startsWith("/") ? appPath : `/${appPath}`;
  if (!key) return path;
  return `/org/${encodeURIComponent(key)}${path === "/" ? "" : path}`;
}

export function orgAwarePath(currentPathname: string, target: string, organization: OrganizationRouteRef | null | undefined): string {
  if (!target || target.startsWith("http://") || target.startsWith("https://") || target.startsWith("mailto:") || target.startsWith("#")) {
    return target;
  }
  if (target.startsWith("/api/") || target.startsWith("/login") || target.startsWith("/register") || target.startsWith("/invite/accept")) {
    return target;
  }
  if (target.startsWith("/org/")) return target;
  if (!target.startsWith("/")) return target;
  const current = stripOrgPrefix(currentPathname);
  const appPath = target;
  const orgKey = orgRouteKey(organization) || current.orgKey;
  if (!orgKey) return appPath;
  return `/org/${encodeURIComponent(orgKey)}${appPath === "/" ? "" : appPath}`;
}
