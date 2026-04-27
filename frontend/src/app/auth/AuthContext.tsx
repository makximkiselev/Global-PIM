import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import { firstAllowedPath } from "./permissions";

type CatalogRow = { code: string; title: string };
type PlatformRoleRow = {
  id: string;
  code: string;
  name: string;
  description?: string;
};
type OrganizationRow = {
  id: string;
  slug: string;
  name: string;
  status: string;
  membership_role?: string | null;
};
type ProvisioningJobRow = {
  id: string;
  organization_id: string;
  status: string;
  attempt: number;
  error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};
type TenantRegistryRow = {
  organization_id: string;
  db_host: string;
  db_port: number;
  db_name: string;
  db_user: string;
  db_secret_ref: string;
  status: string;
  schema_version?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};
type ProvisioningStatusResp = {
  ok: boolean;
  organization: OrganizationRow;
  tenant_registry?: TenantRegistryRow | null;
  latest_job?: ProvisioningJobRow | null;
};
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
  is_active: boolean;
  role_ids: string[];
  pages: string[];
  actions: string[];
};
type SessionResp = {
  authenticated: boolean;
  user?: UserRow | null;
  roles?: RoleRow[];
  platform_roles?: PlatformRoleRow[];
  organizations?: OrganizationRow[];
  current_organization?: OrganizationRow | null;
  effective_access?: { pages: string[]; actions: string[] };
  flags?: { is_developer?: boolean };
  catalog?: { pages: CatalogRow[]; actions: CatalogRow[] };
};

type AuthCtx = {
  loading: boolean;
  authenticated: boolean;
  user: UserRow | null;
  roles: RoleRow[];
  platformRoles: PlatformRoleRow[];
  organizations: OrganizationRow[];
  currentOrganization: OrganizationRow | null;
  isDeveloper: boolean;
  provisioningStatus: ProvisioningStatusResp | null;
  provisioningStatusLoading: boolean;
  catalog: { pages: CatalogRow[]; actions: CatalogRow[] };
  login: (login: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  switchOrganization: (organizationId: string) => Promise<void>;
  canPage: (code: string) => boolean;
  canAction: (code: string) => boolean;
  firstPath: string;
};

const AuthContext = createContext<AuthCtx | null>(null);

const EMPTY_CATALOG = { pages: [], actions: [] };
const SESSION_CACHE_KEY = "smartpim.auth.session";

function readCachedSession(): SessionResp | null {
  try {
    const raw = window.sessionStorage.getItem(SESSION_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as SessionResp) : null;
  } catch {
    return null;
  }
}

function writeCachedSession(session: SessionResp) {
  try {
    if (!session.authenticated || !session.user) {
      window.sessionStorage.removeItem(SESSION_CACHE_KEY);
      return;
    }
    window.sessionStorage.setItem(SESSION_CACHE_KEY, JSON.stringify(session));
  } catch {
    // ignore storage errors
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const cachedSession = readCachedSession();
  const [loading, setLoading] = useState(!cachedSession);
  const [session, setSession] = useState<SessionResp>(cachedSession || { authenticated: false, catalog: EMPTY_CATALOG });
  const [provisioningStatus, setProvisioningStatus] = useState<ProvisioningStatusResp | null>(null);
  const [provisioningStatusLoading, setProvisioningStatusLoading] = useState(false);

  function applySession(data: SessionResp) {
    const nextSession = {
      authenticated: !!data.authenticated,
      user: data.user || null,
      roles: data.roles || [],
      platform_roles: data.platform_roles || [],
      organizations: data.organizations || [],
      current_organization: data.current_organization || null,
      effective_access: data.effective_access || { pages: data.user?.pages || [], actions: data.user?.actions || [] },
      flags: data.flags || { is_developer: false },
      catalog: data.catalog || EMPTY_CATALOG,
    };
    writeCachedSession(nextSession);
    setSession(nextSession);
  }

  async function refresh() {
    const data = await api<SessionResp>("/auth/session");
    applySession(data);
  }

  async function login(login: string, password: string) {
    const data = await api<SessionResp>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ login, password }),
    });
    applySession(data);
  }

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    writeCachedSession({ authenticated: false, catalog: EMPTY_CATALOG });
    setSession({ authenticated: false, catalog: EMPTY_CATALOG });
    setProvisioningStatus(null);
  }

  async function switchOrganization(organizationId: string) {
    const data = await api<SessionResp>("/platform/organizations/switch", {
      method: "POST",
      body: JSON.stringify({ organization_id: organizationId }),
    });
    applySession(data);
  }

  useEffect(() => {
    let alive = true;
    refresh()
      .catch(() => {
        if (alive && !cachedSession) {
          writeCachedSession({ authenticated: false, catalog: EMPTY_CATALOG });
          setSession({ authenticated: false, catalog: EMPTY_CATALOG });
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const currentOrganizationId = session.current_organization?.id;
    if (!session.authenticated || !currentOrganizationId) {
      setProvisioningStatus(null);
      setProvisioningStatusLoading(false);
      return;
    }
    let alive = true;
    setProvisioningStatusLoading(true);
    api<ProvisioningStatusResp>("/platform/organizations/current/status")
      .then((data) => {
        if (alive) setProvisioningStatus(data);
      })
      .catch(() => {
        if (alive) setProvisioningStatus(null);
      })
      .finally(() => {
        if (alive) setProvisioningStatusLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [session.authenticated, session.current_organization?.id]);

  const value = useMemo<AuthCtx>(() => {
    const pages = session.effective_access?.pages || session.user?.pages || [];
    const actions = session.effective_access?.actions || session.user?.actions || [];
    const canPage = (code: string) => pages.includes("*") || pages.includes(code);
    const canAction = (code: string) => actions.includes("*") || actions.includes(code);
    return {
      loading,
      authenticated: !!session.authenticated,
      user: session.user || null,
      roles: session.roles || [],
      platformRoles: session.platform_roles || [],
      organizations: session.organizations || [],
      currentOrganization: session.current_organization || null,
      isDeveloper: !!session.flags?.is_developer,
      provisioningStatus,
      provisioningStatusLoading,
      catalog: session.catalog || EMPTY_CATALOG,
      login,
      logout,
      refresh,
      switchOrganization,
      canPage,
      canAction,
      firstPath: firstAllowedPath(pages),
    };
  }, [loading, provisioningStatus, provisioningStatusLoading, session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("AuthContext missing");
  return ctx;
}
