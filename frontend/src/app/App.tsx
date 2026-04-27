import { Navigate, Routes, Route } from "react-router-dom";
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
import Infographics from "../pages/Infographics";
import CatalogImportRoute from "../routes/CatalogImportRoute";
import CatalogExportRoute from "../routes/CatalogExportRoute";

// ✅ mapping
import Placeholder from "../pages/Placeholder";

// ✅ dictionaries
import Login from "../pages/Login";
import Register from "../pages/Register";
import InviteAccept from "../pages/InviteAccept";
import AdminAccessRoute from "../routes/AdminAccessRoute";
import OrganizationsRoute from "../routes/OrganizationsRoute";
import ConnectorsStatusRoute from "../routes/ConnectorsStatusRoute";
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

function ProtectedApp() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<RequirePage page="dashboard"><DashboardRoute /></RequirePage>} />
        <Route path="/catalog" element={<RequirePage page="catalog"><CatalogRoute /></RequirePage>} />
        <Route path="/catalog/groups" element={<RequirePage page="product_groups"><ProductGroupsRoute /></RequirePage>} />
        <Route path="/catalog/content-index" element={<RequirePage page="stats_card_quality"><Placeholder title="Контент-индекс" /></RequirePage>} />
        <Route path="/products" element={<RequirePage page="products"><ProductListRoute /></RequirePage>} />
        <Route path="/catalog/import" element={<RequirePage page="catalog_import"><CatalogImportRoute /></RequirePage>} />
        <Route path="/catalog/export" element={<RequirePage page="catalog_export"><CatalogExportRoute /></RequirePage>} />

        <Route path="/templates" element={<RequirePage page="templates"><TemplatesRoute /></RequirePage>} />
        <Route path="/templates/:categoryId" element={<RequirePage page="templates"><TemplateEditorRoute /></RequirePage>} />

        <Route path="/products/new" element={<RequirePage page="products"><ProductNewRoute /></RequirePage>} />
        <Route path="/products/:productId" element={<RequirePage page="products"><ProductRoute /></RequirePage>} />

        <Route path="/dictionaries" element={<RequirePage page="dictionaries"><DictionariesRoute /></RequirePage>} />
        <Route path="/dictionaries/:dictId" element={<RequirePage page="dictionaries"><DictionaryEditorRoute /></RequirePage>} />

        <Route path="/sources-mapping" element={<RequirePage page="sources_mapping"><SourcesMappingRoute /></RequirePage>} />
        <Route path="/competitor-mapping" element={<Navigate to="/sources-mapping?tab=competitor_links" replace />} />
        <Route path="/marketplace-mapping" element={<Navigate to="/sources-mapping?tab=mp_categories" replace />} />
        <Route path="/connectors/status" element={<RequirePage page="connectors_status"><ConnectorsStatusRoute /></RequirePage>} />
        <Route path="/images/infographics" element={<RequirePage page="infographics"><Infographics /></RequirePage>} />

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
