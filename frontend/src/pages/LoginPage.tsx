/** 401 en la SPA: en Databricks Apps el SSO lo resuelve la plataforma antes de llegar aquí, así que solo aparece
 *  si se abre la app sin pasar por el proxy. No hay formulario de contraseña. */
export function LoginPage() {
  return (
    <div className="login-body">
      <main className="login-card">
        <h1>Analizador de Cumplimiento Contractual</h1>
        <p className="subtitle">No se pudo identificar tu sesión.</p>
        <p>Abre la aplicación desde tu workspace de Databricks (Compute → Apps) para entrar con tu usuario.</p>
        <p className="login-note">Herramienta de apoyo; no constituye asesoría legal.</p>
      </main>
    </div>
  );
}
