import { useQueryClient } from "@tanstack/react-query";
import { FileText, ListChecks, LogOut, ShieldCheck } from "lucide-react";
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
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>
      <header className="topbar">
        <div className="topbar-title">
          <h1>
            <ShieldCheck size={22} className="brand-icon" /> Analizador de Cumplimiento Contractual
          </h1>
          <p className="subtitle">Comprueba un contrato contra tus criterios, con la evidencia marcada en el PDF. No es asesoría legal.</p>
        </div>
        <div className="topbar-meta">
          {user?.auth_mode === "local" && <span className="badge">modo de desarrollo</span>}
          <span className="user-email">{user?.email}</span>
          {canLogout && (
            <button type="button" className="btn btn-secondary" onClick={logout}>
              <LogOut size={16} /> Cerrar sesión
            </button>
          )}
        </div>
      </header>
      <nav className="tabs" aria-label="Secciones">
        {([
          ["/documentos", "1. Documentos", FileText],
          ["/reglas", "2. Criterios", ListChecks],
          ["/analisis", "3. Análisis", ShieldCheck],
        ] as const).map(([to, label, Icon]) => (
          <NavLink key={to} to={to} className={({ isActive }) => "tab-btn" + (isActive ? " active" : "")}>
            <Icon size={16} /> {label}
          </NavLink>
        ))}
      </nav>
      <main id="contenido" tabIndex={-1}>
        <Outlet />
      </main>
    </>
  );
}

export function App() {
  const { isPending, error } = useMe();
  if (isPending) return <p className="loading" role="status">Cargando…</p>;
  if (error instanceof ApiError && error.status === 401) return <LoginPage />;
  if (error) return <p className="form-msg error" role="alert">No se pudo contactar con el servidor.</p>;

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
