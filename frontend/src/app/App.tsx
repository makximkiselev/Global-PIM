import { Navigate, Routes, Route, useLocation, useParams } from "react-router-dom";
import { lazy, Suspense, useEffect } from "react";
import Shell from "./layout/Shell";
import { useAuth } from "./auth/AuthContext";
import { firstAllowedPath } from "./auth/permissions";

import Placeholder from "../shared/placeholders/Placeholder";

import Login from "../pages/Login";
import Register from "../pages/Register";
import InviteAccept from "../pages/InviteAccept";
import { orgRouteKey, stripOrgPrefix, useOrgPath, withOrgPath } from "./orgRoutes";

const DashboardRoute = lazy(() => import("../routes/DashboardRoute"));
const CatalogRoute = lazy(() => import("../routes/CatalogRoute"));
const ProductListRoute = lazy(() => import("../routes/ProductListRoute"));
const ProductNewRoute = lazy(() => import("../routes/ProductNewRoute"));
const ProductRoute = lazy(() => import("../routes/ProductRoute"));
const ProductGroupsRoute = lazy(() => import("../routes/ProductGroupsRoute"));
const Infographics = lazy(() => import("../domains/data-prep/InfographicsFeature"));
const CatalogExchangeFeature = lazy(() => import("../domains/products/CatalogExchangeFeature"));
const DataSourcesFeature = lazy(() => import("../domains/data-prep/DataSourcesFeature"));
const ProfileFeature = lazy(() => import("../domains/admin/ProfileFeature"));
const OrganizationsRoute = lazy(() => import("../routes/OrganizationsRoute"));
const DictionariesRoute = lazy(() => import("../routes/DictionariesRoute"));
const DictionaryEditorRoute = lazy(() => import("../routes/DictionaryEditorRoute"));
const SourcesMappingRoute = lazy(() => import("../routes/SourcesMappingRoute"));
const CompetitorCatalogImportRoute = lazy(() => import("../routes/CompetitorCatalogImportRoute"));
const TemplateEditorRoute = lazy(() => import("../routes/TemplateEditorRoute"));
const TemplatesRoute = lazy(() => import("../routes/TemplatesRoute"));

function RouteLoader() {
  return (
    <section className="routeLoadingShell" role="status" aria-live="polite" aria-label="Загрузка рабочей области">
      <div className="routeLoadingHeader">
        <div>
          <span className="routeLoadingEyebrow">Рабочая область</span>
          <strong>Загружаем данные</strong>
          <p>Подготавливаем каталог, фильтры и таблицы.</p>
        </div>
        <span className="routeLoadingPulse" />
      </div>
      <div className="routeLoadingGrid">
        <aside className="routeLoadingPanel routeLoadingSidebar">
          <span className="routeLoadingLine isTitle" />
          <span className="routeLoadingLine" />
          <span className="routeLoadingLine" />
          <span className="routeLoadingLine isShort" />
          <span className="routeLoadingLine" />
        </aside>
        <main className="routeLoadingPanel routeLoadingMain">
          <div className="routeLoadingMetrics">
            <span />
            <span />
            <span />
          </div>
          <div className="routeLoadingToolbar">
            <span className="routeLoadingLine isWide" />
            <span className="routeLoadingButton" />
            <span className="routeLoadingButton" />
          </div>
          <div className="routeLoadingRows">
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
        </main>
      </div>
    </section>
  );
}

function SessionKickToLogin({ reason }: { reason: "denied" | "expired" }) {
  useEffect(() => {
    void fetch("/api/auth/logout", { method: "POST", credentials: "include", keepalive: true }).finally(() => {
      window.location.replace(`/login?${reason}=1`);
    });
  }, [reason]);

  return <div className="pageLoading">Перенаправление...</div>;
}

function RequirePage({ page, children }: { page: string; children: JSX.Element }) {
  const { loading, authenticated, canPage, user, currentOrganization } = useAuth();
  if (loading) return <div className="pageLoading">Загрузка...</div>;
  if (!authenticated || !user) return <Navigate to="/login" replace />;
  if (!currentOrganization) return <div className="pageLoading">Организация не выбрана</div>;
  if (!canPage(page)) return <SessionKickToLogin reason="denied" />;
  return children;
}

function RequireAnyPage({ pages, children }: { pages: string[]; children: JSX.Element }) {
  const { loading, authenticated, canPage, user, currentOrganization } = useAuth();
  if (loading) return <div className="pageLoading">Загрузка...</div>;
  if (!authenticated || !user) return <Navigate to="/login" replace />;
  if (!currentOrganization) return <div className="pageLoading">Организация не выбрана</div>;
  if (!pages.some((page) => canPage(page))) return <SessionKickToLogin reason="denied" />;
  return children;
}

function CompetitorCategoryRoute() {
  const params = useParams();
  const orgPath = useOrgPath();
  const category = encodeURIComponent(params.categoryId || "");
  return <Navigate to={orgPath(`/sources?tab=sources&category=${category}`)} replace />;
}

function CatalogExchangeRedirect({ tab }: { tab: "import" | "export" }) {
  const location = useLocation();
  const orgPath = useOrgPath();
  const searchParams = new URLSearchParams(location.search);
  searchParams.set("tab", tab);
  return <Navigate to={orgPath(`/catalog/exchange?${searchParams.toString()}`)} replace />;
}

function WorkspaceRedirect({ to }: { to: string }) {
  const orgPath = useOrgPath();
  return <Navigate to={orgPath(to)} replace />;
}

function WorkspaceRoutes() {
  return (
    <Shell>
      <Suspense fallback={<RouteLoader />}>
        <Routes>
          <Route index element={<RequirePage page="dashboard"><DashboardRoute /></RequirePage>} />
          <Route path="catalog" element={<RequirePage page="catalog"><CatalogRoute /></RequirePage>} />
          <Route path="catalog/groups" element={<RequirePage page="product_groups"><ProductGroupsRoute /></RequirePage>} />
          <Route path="groups" element={<WorkspaceRedirect to="/catalog/groups" />} />
          <Route path="product-groups" element={<WorkspaceRedirect to="/catalog/groups" />} />
          <Route path="products/groups" element={<WorkspaceRedirect to="/catalog/groups" />} />
          <Route path="products/media" element={<WorkspaceRedirect to="/images/infographics" />} />
          <Route path="media" element={<WorkspaceRedirect to="/images/infographics" />} />
          <Route path="infographics" element={<WorkspaceRedirect to="/images/infographics" />} />
          <Route path="catalog/content-index" element={<RequirePage page="stats_card_quality"><Placeholder title="Контент-индекс" /></RequirePage>} />
          <Route path="products" element={<RequirePage page="products"><ProductListRoute /></RequirePage>} />
          <Route path="catalog/exchange" element={<RequireAnyPage pages={["catalog_import", "catalog_export"]}><CatalogExchangeFeature /></RequireAnyPage>} />
          <Route path="catalog/import" element={<CatalogExchangeRedirect tab="import" />} />
          <Route path="catalog/export" element={<CatalogExchangeRedirect tab="export" />} />
          <Route path="profile" element={<ProfileFeature />} />

          <Route path="templates" element={<RequirePage page="templates"><TemplatesRoute /></RequirePage>} />
          <Route path="templates/:categoryId" element={<RequirePage page="templates"><TemplateEditorRoute /></RequirePage>} />

          <Route path="products/new" element={<RequirePage page="products"><ProductNewRoute /></RequirePage>} />
          <Route path="products/:productId" element={<RequirePage page="products"><ProductRoute /></RequirePage>} />

          <Route path="dictionaries" element={<RequirePage page="dictionaries"><DictionariesRoute /></RequirePage>} />
          <Route path="dictionaries/:dictId" element={<RequirePage page="dictionaries"><DictionaryEditorRoute /></RequirePage>} />
          <Route path="data-prep/competitors" element={<WorkspaceRedirect to="/connectors/status?tab=competitors" />} />
          <Route path="competitor-mapping/category/:categoryId" element={<RequirePage page="sources_mapping"><CompetitorCategoryRoute /></RequirePage>} />

          <Route path="sources" element={<RequirePage page="sources_mapping"><SourcesMappingRoute /></RequirePage>} />
          <Route path="sources-mapping" element={<RequirePage page="sources_mapping"><SourcesMappingRoute /></RequirePage>} />
          <Route path="data-prep/competitor-import" element={<RequirePage page="sources_mapping"><CompetitorCatalogImportRoute /></RequirePage>} />
          <Route path="competitor-catalog" element={<WorkspaceRedirect to="/data-prep/competitor-import" />} />
          <Route path="competitor-import" element={<WorkspaceRedirect to="/data-prep/competitor-import" />} />
          <Route path="competitor-mapping" element={<WorkspaceRedirect to="/sources?tab=competitors" />} />
          <Route path="marketplace-mapping" element={<WorkspaceRedirect to="/sources?tab=sources" />} />
          <Route path="connectors/status" element={<RequireAnyPage pages={["connectors_status", "sources_mapping"]}><DataSourcesFeature /></RequireAnyPage>} />
          <Route path="connectors" element={<WorkspaceRedirect to="/connectors/status" />} />
          <Route path="data-sources" element={<WorkspaceRedirect to="/connectors/status" />} />
          <Route path="data-prep/sources" element={<WorkspaceRedirect to="/connectors/status" />} />
          <Route path="images/infographics" element={<RequirePage page="infographics"><Infographics /></RequirePage>} />
          <Route path="data-prep/infographics" element={<WorkspaceRedirect to="/images/infographics" />} />

          <Route path="admin/access" element={<RequirePage page="admin_access"><OrganizationsRoute initialTab="roles" /></RequirePage>} />
          <Route path="admin/organizations" element={<RequirePage page="admin_access"><OrganizationsRoute initialTab="organizations" /></RequirePage>} />
          <Route path="admin/members" element={<RequirePage page="admin_access"><OrganizationsRoute initialTab="members" /></RequirePage>} />
          <Route path="admin/invites" element={<RequirePage page="admin_access"><OrganizationsRoute initialTab="invites" /></RequirePage>} />
          <Route path="admin/roles" element={<RequirePage page="admin_access"><OrganizationsRoute initialTab="roles" /></RequirePage>} />
          <Route path="admin/platform" element={<RequirePage page="admin_access"><OrganizationsRoute initialTab="platform" /></RequirePage>} />
          <Route path="*" element={<WorkspaceRedirect to="/" />} />
        </Routes>
      </Suspense>
    </Shell>
  );
}

function OrgWorkspaceGuard() {
  const { orgKey = "" } = useParams();
  const location = useLocation();
  const { loading, authenticated, currentOrganization, organizations, switchOrganization } = useAuth();
  const currentKey = orgRouteKey(currentOrganization);
  const targetOrganization = organizations.find((organization) => orgRouteKey(organization) === orgKey);

  useEffect(() => {
    if (loading || !authenticated || !targetOrganization || targetOrganization.id === currentOrganization?.id) return;
    void switchOrganization(targetOrganization.id);
  }, [authenticated, currentOrganization?.id, loading, switchOrganization, targetOrganization]);

  if (loading) return <div className="pageLoading">Загрузка...</div>;
  if (!authenticated) return <Navigate to="/login" replace />;
  if (!currentOrganization) return <div className="pageLoading">Организация не выбрана</div>;
  if (!targetOrganization) return <Navigate to={withOrgPath(currentOrganization, "/")} replace />;
  if (currentKey !== orgKey) return <div className="pageLoading">Переключение организации...</div>;

  return <WorkspaceRoutes key={orgKey} />;
}

function LegacyWorkspaceRedirect() {
  const location = useLocation();
  const { currentOrganization } = useAuth();
  const { appPath } = stripOrgPrefix(location.pathname);
  return <Navigate to={`${withOrgPath(currentOrganization, appPath)}${location.search}${location.hash}`} replace />;
}

export default function App() {
  const { authenticated, loading, user, currentOrganization } = useAuth();
  if (loading) return <div className="pageLoading">Загрузка...</div>;
  if (!authenticated) {
    return (
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/invite/accept" element={<InviteAccept />} />
        <Route path="/auth" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route path="/login" element={<Navigate to={withOrgPath(currentOrganization, firstAllowedPath(user?.pages || []))} replace />} />
      <Route path="/register" element={<Navigate to={withOrgPath(currentOrganization, firstAllowedPath(user?.pages || []))} replace />} />
      <Route path="/invite/accept" element={<InviteAccept />} />
      <Route path="/auth" element={<Navigate to="/login" replace />} />
      <Route path="/org/:orgKey/*" element={<OrgWorkspaceGuard />} />
      <Route path="/*" element={<LegacyWorkspaceRedirect />} />
    </Routes>
  );
}
