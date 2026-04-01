import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import { firstAllowedPath } from "./permissions";

type CatalogRow = { code: string; title: string };
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
  catalog?: { pages: CatalogRow[]; actions: CatalogRow[] };
};

type AuthCtx = {
  loading: boolean;
  authenticated: boolean;
  user: UserRow | null;
  roles: RoleRow[];
  catalog: { pages: CatalogRow[]; actions: CatalogRow[] };
  login: (login: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  canPage: (code: string) => boolean;
  canAction: (code: string) => boolean;
  firstPath: string;
};

const AuthContext = createContext<AuthCtx | null>(null);

const EMPTY_CATALOG = { pages: [], actions: [] };

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [session, setSession] = useState<SessionResp>({ authenticated: false, catalog: EMPTY_CATALOG });

  async function refresh() {
    const data = await api<SessionResp>("/auth/session");
    setSession({
      authenticated: !!data.authenticated,
      user: data.user || null,
      roles: data.roles || [],
      catalog: data.catalog || EMPTY_CATALOG,
    });
  }

  async function login(login: string, password: string) {
    const data = await api<SessionResp>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ login, password }),
    });
    setSession({
      authenticated: !!data.authenticated,
      user: data.user || null,
      roles: data.roles || [],
      catalog: data.catalog || EMPTY_CATALOG,
    });
  }

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    setSession({ authenticated: false, catalog: EMPTY_CATALOG });
  }

  useEffect(() => {
    let alive = true;
    setLoading(true);
    refresh()
      .catch(() => {
        if (alive) setSession({ authenticated: false, catalog: EMPTY_CATALOG });
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const value = useMemo<AuthCtx>(() => {
    const pages = session.user?.pages || [];
    const actions = session.user?.actions || [];
    const canPage = (code: string) => pages.includes("*") || pages.includes(code);
    const canAction = (code: string) => actions.includes("*") || actions.includes(code);
    return {
      loading,
      authenticated: !!session.authenticated,
      user: session.user || null,
      roles: session.roles || [],
      catalog: session.catalog || EMPTY_CATALOG,
      login,
      logout,
      refresh,
      canPage,
      canAction,
      firstPath: firstAllowedPath(pages),
    };
  }, [loading, session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("AuthContext missing");
  return ctx;
}
