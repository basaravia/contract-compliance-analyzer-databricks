import { useQueryClient } from "@tanstack/react-query";
import { NavLink, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { ApiError, apiFetch } from "./api/client";
import { useMe } from "./api/hooks";
import { AnalysisPage } from "./pages/AnalysisPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { LoginPage } from "./pages/LoginPage";
import { ReviewPage } from "./pages/ReviewPage";
import { RulesPage } from "./pages/RulesPage";

function Layout() {
  const { data: user } = useMe();
  const qc = useQueryClient();
  const logout = async () => {
    try {
      await apiFetch("/auth/logout", { method: "POST", redirect: "manual" });
    } finally {
      qc.clear();
      window.location.assign("/login");
    }
  };
  // Con Databricks Apps el SSO lo gestiona la plataforma: no hay sesión propia que cerrar.
  const canLogout = user && user.auth_mode !== "local" && user.auth_mode !== "databricks";

  return (
    <>
      <header className="topbar">
        <div className="topbar-title">
          <h1>Analizador de Cumplimiento Contractual</h1>
          <p className="subtitle">MVP — evidencia trazable (página + coordenadas). No constituye asesoría legal.</p>
        </div>
        <div className="topbar-meta">
          <span className="badge">modo: {user?.auth_mode}</span>
          <span className="badge badge-muted">{user?.email}</span>
          {canLogout && (
            <button type="button" className="btn btn-secondary" onClick={logout}>
              Cerrar sesión
            </button>
          )}
        </div>
      </header>
      <nav className="tabs" aria-label="Secciones">
        {[
          ["/documentos", "Documentos"],
          ["/reglas", "Reglas"],
          ["/analisis", "Análisis"],
        ].map(([to, label]) => (
          <NavLink key={to} to={to} className={({ isActive }) => "tab-btn" + (isActive ? " active" : "")}>
            {label}
          </NavLink>
        ))}
      </nav>
      <main>
        <Outlet />
      </main>
    </>
  );
}

export function App() {
  const { isPending, error } = useMe();
  if (isPending) return <p className="hint">Cargando…</p>;
  if (error instanceof ApiError && error.status === 401) return <LoginPage />;
  if (error) return <p className="form-msg error">No se pudo contactar con el servidor.</p>;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/documentos" replace />} />
        <Route path="documentos" element={<DocumentsPage />} />
        <Route path="reglas" element={<RulesPage />} />
        <Route path="analisis" element={<AnalysisPage />} />
        <Route path="analisis/:id" element={<AnalysisPage />} />
        <Route path="analisis/:id/revision" element={<ReviewPage />} />
        <Route path="login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/documentos" replace />} />
      </Route>
    </Routes>
  );
}
