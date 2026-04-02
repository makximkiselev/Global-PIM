import { Navigate, Routes, Route } from "react-router-dom";
import { useEffect } from "react";
import Shell from "./layout/Shell";
import { useAuth } from "./auth/AuthContext";
import { firstAllowedPath } from "./auth/permissions";

import Dashboard from "../pages/Dashboard";
import Catalog from "../pages/Catalog";
import Templates from "../pages/Templates";
import TemplateEditor from "../pages/TemplateEditor";
import ProductNew from "../pages/ProductNew";
import Product from "../pages/Product";
import ProductGroups from "../pages/ProductGroups";
import Infographics from "../pages/Infographics";
import ProductsPage from "../pages/Products";
import CatalogImportPage from "../pages/CatalogImport";
import CatalogExportPage from "../pages/CatalogExport";

// ✅ mapping
import SourcesMapping from "../pages/SourcesMapping";
import ConnectorsStatus from "../pages/ConnectorsStatus";
import Placeholder from "../pages/Placeholder";

// ✅ dictionaries
import Dictionaries from "../pages/Dictionary";
import DictionaryEditor from "../pages/DictionaryEditor";
import Login from "../pages/Login";
import AdminAccess from "../pages/AdminAccess";

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
        <Route path="/" element={<RequirePage page="dashboard"><Dashboard /></RequirePage>} />
        <Route path="/catalog" element={<RequirePage page="catalog"><Catalog /></RequirePage>} />
        <Route path="/catalog/groups" element={<RequirePage page="product_groups"><ProductGroups /></RequirePage>} />
        <Route path="/products" element={<RequirePage page="products"><ProductsPage /></RequirePage>} />
        <Route path="/catalog/import" element={<RequirePage page="catalog_import"><CatalogImportPage /></RequirePage>} />
        <Route path="/catalog/export" element={<RequirePage page="catalog_export"><CatalogExportPage /></RequirePage>} />

        <Route path="/templates" element={<RequirePage page="templates"><Templates /></RequirePage>} />
        <Route path="/templates/:categoryId" element={<RequirePage page="templates"><TemplateEditor /></RequirePage>} />

        <Route path="/products/new" element={<RequirePage page="products"><ProductNew /></RequirePage>} />
        <Route path="/products/:productId" element={<RequirePage page="products"><Product /></RequirePage>} />

        <Route path="/dictionaries" element={<RequirePage page="dictionaries"><Dictionaries /></RequirePage>} />
        <Route path="/dictionaries/:dictId" element={<RequirePage page="dictionaries"><DictionaryEditor /></RequirePage>} />

        <Route path="/sources-mapping" element={<RequirePage page="sources_mapping"><SourcesMapping /></RequirePage>} />
        <Route path="/competitor-mapping" element={<Navigate to="/sources-mapping?tab=competitor_links" replace />} />
        <Route path="/marketplace-mapping" element={<Navigate to="/sources-mapping?tab=mp_categories" replace />} />
        <Route path="/connectors/status" element={<RequirePage page="connectors_status"><ConnectorsStatus /></RequirePage>} />
        <Route path="/images/infographics" element={<RequirePage page="infographics"><Infographics /></RequirePage>} />

        <Route path="/stats/card-quality" element={<RequirePage page="stats_card_quality"><Placeholder title="Качество карточек" /></RequirePage>} />
        <Route path="/stats/marketplace-quality" element={<RequirePage page="stats_marketplace_quality"><Placeholder title="Качество на маркетплейсах" /></RequirePage>} />
        <Route path="/admin/access" element={<RequirePage page="admin_access"><AdminAccess /></RequirePage>} />
      </Routes>
    </Shell>
  );
}

export default function App() {
  const { authenticated, loading, user } = useAuth();
  if (loading) return <div className="pageLoading">Загрузка...</div>;
  return (
    <Routes>
      <Route path="/login" element={authenticated ? <Navigate to={firstAllowedPath(user?.pages || [])} replace /> : <Login />} />
      <Route path="/auth" element={<Navigate to="/login" replace />} />
      <Route path="/*" element={authenticated ? <ProtectedApp /> : <Navigate to="/login" replace />} />
    </Routes>
  );
}
