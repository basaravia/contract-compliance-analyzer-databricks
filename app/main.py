"""Punto de entrada de la aplicación FastAPI.

Ensambla routers, aplica cabeceras de seguridad y CSRF, sirve el frontend
estático y expone un healthcheck. `AUTH_MODE=local` (por defecto) permite
arrancar el MVP sin ninguna credencial externa; `AUTH_MODE=oidc` activa el
flujo real contra Microsoft Entra ID.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Cookie, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.auth import router as auth_router
from app.auth import session_is_valid
from app.config import settings
from app.csrf import CSRFMiddleware
from app.db import init_db
from app.routers.analyses import router as analyses_router
from app.routers.documents import router as documents_router
from app.routers.findings import router as findings_router
from app.routers.rules import router as rules_router

BASE_DIR = Path(__file__).resolve().parent
# Build de producción del frontend React (`npm run build` en frontend/). Si no existe, se sirve la UI clásica.
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Cabeceras de defensa en profundidad contra XSS/clickjacking/sniffing.

    La CSP es estricta (sin 'unsafe-inline') porque todo el JS/CSS del
    frontend vive en archivos estáticos propios, nunca inline ni de un CDN
    externo: así un XSS reflejado/almacenado no puede ejecutar script.
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
        if settings.app_env != "development":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


DEFAULT_SECRET = "change-me-dev-only-not-a-real-secret"


def validate_runtime_config() -> None:
    """Se niega a arrancar con una configuración insegura fuera de desarrollo.

    Pensado para cuando la app queda expuesta a internet (proxy público): un fallo de configuración debe
    impedir el arranque, no degradarse en silencio."""
    if settings.app_env == "development":
        return
    problems = []
    if settings.auth_mode == "local":
        problems.append("AUTH_MODE=local no exige login; usa AUTH_MODE=databricks u oidc fuera de desarrollo")
    # Con AUTH_MODE=databricks no se firma ninguna cookie de sesión: SECRET_KEY no protege nada.
    if settings.auth_mode != "databricks" and (settings.secret_key == DEFAULT_SECRET or len(settings.secret_key) < 32):
        problems.append("SECRET_KEY es la de ejemplo o tiene menos de 32 caracteres")
    if problems:
        raise RuntimeError("Configuración insegura para APP_ENV=" + settings.app_env + ": " + "; ".join(problems))


@asynccontextmanager
async def _lifespan(app: FastAPI):
    validate_runtime_config()
    init_db()
    yield


def create_app() -> FastAPI:
    production = settings.app_env != "development"
    app = FastAPI(
        title="Analizador de Cumplimiento Contractual",
        description=(
            "MVP para evaluar el cumplimiento de contratos frente a un conjunto de reglas "
            "normativas (ej. LOPDP Ecuador), con evidencia trazable (página + bbox) y edición manual."
        ),
        version="0.1.0",
        lifespan=_lifespan,
        # La documentación interactiva describe toda la API: no se publica fuera de desarrollo.
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CSRFMiddleware, secure_cookies=settings.app_env != "development")

    app.include_router(auth_router)
    app.include_router(documents_router)
    app.include_router(rules_router)
    app.include_router(analyses_router)
    app.include_router(findings_router)

    static_dir = BASE_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    spa_index = FRONTEND_DIST / "index.html"
    spa_enabled = spa_index.is_file()

    if spa_enabled:
        # Vite emite los bundles con hash en dist/assets: se pueden cachear sin riesgo.
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="spa-assets")

        def _spa() -> Response:
            # Solo HTML estático: los datos y la autenticación los resuelve cada /api/*; si la sesión no
            # vale, la SPA recibe 401 y muestra un aviso de acceso (SSO del workspace u OIDC).
            return FileResponse(spa_index, headers={"Cache-Control": "no-store"})

        @app.get("/", include_in_schema=False)
        def index_spa() -> Response:
            return _spa()

        @app.get("/login", include_in_schema=False)
        def login_spa() -> Response:
            if settings.auth_mode == "oidc":
                return RedirectResponse("/auth/login", status_code=302)
            return RedirectResponse("/", status_code=302)

        # Rutas del cliente (react-router): cualquier GET que no sea API/auth/healthz devuelve el index.
        @app.get("/{path:path}", include_in_schema=False)
        def spa_fallback(path: str) -> Response:
            if path.split("/", 1)[0] in {"api", "auth", "static", "assets", "healthz"}:
                return Response(status_code=404)
            candidate = (FRONTEND_DIST / path).resolve()
            if FRONTEND_DIST.resolve() in candidate.parents and candidate.is_file():
                return FileResponse(candidate)  # favicon, robots, etc.
            return _spa()

        return app

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, ccap_session: str | None = Cookie(default=None)) -> Response:
        if settings.auth_mode not in {"local", "databricks"} and not session_is_valid(request, ccap_session):
            return RedirectResponse("/auth/login", status_code=302)
        return templates.TemplateResponse(
            request, "index.html", {"auth_mode": settings.auth_mode, "default_jurisdiction": settings.default_jurisdiction}
        )

    @app.get("/login", include_in_schema=False)
    def login_page() -> Response:
        return RedirectResponse("/auth/login" if settings.auth_mode == "oidc" else "/", status_code=302)

    return app


app = create_app()
