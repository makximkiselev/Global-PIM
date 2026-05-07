import { Navigate, Routes, Route, useParams, useSearchParams } from "react-router-dom";
import { useEffect } from "react";
import Shell from "./layout/Shell";
import { useAuth } from "./auth/AuthContext";
import { firstAllowedPath } from "./auth/permissions";

import DashboardRoute from "../routes/DashboardRoute";
import CatalogRoute from "../routes/CatalogRoute";
import ProductListRoute from "../routes/ProductListRoute";
import ProductNewRoute from "../routes/ProductNewRoute";
import ProductRoute from "../routes/ProductRoute";
import ProductGroupsRoute from "../routes/ProductGroupsRoute";
import Infographics from "../domains/data-prep/InfographicsFeature";
import CatalogExchangeFeature from "../domains/products/CatalogExchangeFeature";
import DataSourcesFeature from "../domains/data-prep/DataSourcesFeature";
import ProfileFeature from "../domains/admin/ProfileFeature";
import CompetitorMappingFeature from "../domains/data-prep/CompetitorMappingFeature";

// ✅ mapping
import Placeholder from "../shared/placeholders/Placeholder";

// ✅ dictionaries
import Login from "../pages/Login";
import Register from "../pages/Register";
import InviteAccept from "../pages/InviteAccept";
import AdminAccessRoute from "../routes/AdminAccessRoute";
import OrganizationsRoute from "../routes/OrganizationsRoute";
import DictionariesRoute from "../routes/DictionariesRoute";
import DictionaryEditorRoute from "../routes/DictionaryEditorRoute";
import SourcesMappingRoute from "../routes/SourcesMappingRoute";
import TemplateEditorRoute from "../routes/TemplateEditorRoute";
import TemplatesRoute from "../routes/TemplatesRoute";

function SessionKickToLogin({ reason }: { reason: "denied" | "expired" }) {
  useEffect(() => {
    void fetch("/api/auth/logout", { method: "POST", credentials: "include", keepalive: true }).finally(() => {
      window.location.replace(`/login?${reason}=1`);
    });
  }, [reason]);

  return <div className="pageLoading">Перенаправление...</div>;
}

function RequirePage({ page, children }: { page: string; children: JSX.Element }) {
  const { loading, authenticated, canPage, user } = useAuth();
  if (loading) return <div className="pageLoading">Загрузка...</div>;
  if (!authenticated || !user) return <Navigate to="/login" replace />;
  if (!canPage(page)) return <SessionKickToLogin reason="denied" />;
  return children;
}

function RequireAnyPage({ pages, children }: { pages: string[]; children: JSX.Element }) {
  const { loading, authenticated, canPage, user } = useAuth();
  if (loading) return <div className="pageLoading">Загрузка...</div>;
  if (!authenticated || !user) return <Navigate to="/login" replace />;
  if (!pages.some((page) => canPage(page))) return <SessionKickToLogin reason="denied" />;
  return children;
}

function CompetitorCategoryRoute() {
  const params = useParams();
  const [searchParams] = useSearchParams();
  const rawView = searchParams.get("view");
  const view = rawView === "links" || rawView === "mapping" || rawView === "pool" ? rawView : "all";
  return <CompetitorMappingFeature categoryId={params.categoryId || ""} view={view} />;
}

function ProtectedApp() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<RequirePage page="dashboard"><DashboardRoute /></RequirePage>} />
        <Route path="/catalog" element={<RequirePage page="catalog"><CatalogRoute /></RequirePage>} />
        <Route path="/catalog/groups" element={<RequirePage page="product_groups"><ProductGroupsRoute /></RequirePage>} />
        <Route path="/products/media" element={<RequirePage page="infographics"><Placeholder title="Медиа товаров" /></RequirePage>} />
        <Route path="/media" element={<Navigate to="/products/media" replace />} />
        <Route path="/catalog/content-index" element={<RequirePage page="stats_card_quality"><Placeholder title="Контент-индекс" /></RequirePage>} />
        <Route path="/products" element={<RequirePage page="products"><ProductListRoute /></RequirePage>} />
        <Route path="/catalog/exchange" element={<RequireAnyPage pages={["catalog_import", "catalog_export"]}><CatalogExchangeFeature /></RequireAnyPage>} />
        <Route path="/catalog/import" element={<Navigate to="/catalog/exchange?tab=import" replace />} />
        <Route path="/catalog/export" element={<Navigate to="/catalog/exchange?tab=export" replace />} />
        <Route path="/profile" element={<ProfileFeature />} />

        <Route path="/templates" element={<RequirePage page="templates"><TemplatesRoute /></RequirePage>} />
        <Route path="/templates/:categoryId" element={<RequirePage page="templates"><TemplateEditorRoute /></RequirePage>} />

        <Route path="/products/new" element={<RequirePage page="products"><ProductNewRoute /></RequirePage>} />
        <Route path="/products/:productId" element={<RequirePage page="products"><ProductRoute /></RequirePage>} />

        <Route path="/dictionaries" element={<RequirePage page="dictionaries"><DictionariesRoute /></RequirePage>} />
        <Route path="/dictionaries/:dictId" element={<RequirePage page="dictionaries"><DictionaryEditorRoute /></RequirePage>} />
        <Route path="/data-prep/competitors" element={<Navigate to="/connectors/status?tab=competitors" replace />} />
        <Route path="/competitor-mapping/category/:categoryId" element={<RequirePage page="sources_mapping"><CompetitorCategoryRoute /></RequirePage>} />

        <Route path="/sources" element={<RequirePage page="sources_mapping"><SourcesMappingRoute /></RequirePage>} />
        <Route path="/sources-mapping" element={<RequirePage page="sources_mapping"><SourcesMappingRoute /></RequirePage>} />
        <Route path="/competitor-mapping" element={<Navigate to="/data-prep/competitors" replace />} />
        <Route path="/marketplace-mapping" element={<Navigate to="/sources?tab=sources" replace />} />
        <Route path="/connectors/status" element={<RequireAnyPage pages={["connectors_status", "sources_mapping"]}><DataSourcesFeature /></RequireAnyPage>} />
        <Route path="/images/infographics" element={<RequirePage page="infographics"><Infographics /></RequirePage>} />
        <Route path="/data-prep/infographics" element={<Navigate to="/images/infographics" replace />} />

        <Route path="/admin/access" element={<RequirePage page="admin_access"><AdminAccessRoute /></RequirePage>} />
        <Route path="/admin/organizations" element={<RequirePage page="admin_access"><OrganizationsRoute initialTab="organizations" /></RequirePage>} />
        <Route path="/admin/members" element={<RequirePage page="admin_access"><OrganizationsRoute initialTab="members" /></RequirePage>} />
        <Route path="/admin/invites" element={<RequirePage page="admin_access"><OrganizationsRoute initialTab="invites" /></RequirePage>} />
        <Route path="/admin/platform" element={<RequirePage page="admin_access"><OrganizationsRoute initialTab="platform" /></RequirePage>} />
      </Routes>
    </Shell>
  );
}

export default function App() {
  const { authenticated, loading, user } = useAuth();
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
      <Route path="/login" element={<Navigate to={firstAllowedPath(user?.pages || [])} replace />} />
      <Route path="/register" element={<Navigate to={firstAllowedPath(user?.pages || [])} replace />} />
      <Route path="/invite/accept" element={<InviteAccept />} />
      <Route path="/auth" element={<Navigate to="/login" replace />} />
      <Route path="/*" element={<ProtectedApp />} />
    </Routes>
  );
}
