"""Protección CSRF (patrón doble-cookie / double-submit).

Toda petición de escritura (POST/PUT/PATCH/DELETE) bajo /api o /auth debe
incluir el header `X-CSRF-Token` con el mismo valor que la cookie
`ccap_csrf`. Un sitio de terceros puede provocar que el navegador envíe la
cookie de sesión automáticamente, pero no puede leer el valor de la cookie
CSRF (protegido por same-origin policy) para reproducirlo en el header, así
que no puede forjar la petición. Esta protección se aplica en todos los
modos de autenticación (local y oidc): en modo local no hay cookie de
sesión, pero igualmente evita que una página externa dispare acciones de
escritura contra la API vía el navegador del usuario.
"""
from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CSRF_COOKIE = "ccap_csrf"
CSRF_HEADER = "x-csrf-token"
PROTECTED_PREFIXES = ("/api", "/auth")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secure_cookies: bool = True):
        super().__init__(app)
        self.secure_cookies = secure_cookies

    async def dispatch(self, request: Request, call_next):
        cookie_token = request.cookies.get(CSRF_COOKIE)

        needs_check = (
            request.method not in SAFE_METHODS
            and any(request.url.path.startswith(p) for p in PROTECTED_PREFIXES)
            # El login OIDC y el callback son navegaciones GET normales; el resto
            # de rutas de auth (logout) y toda /api sí requieren el token.
        )
        if needs_check:
            header_token = request.headers.get(CSRF_HEADER)
            if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
                return Response(
                    content='{"detail":"Token CSRF ausente o inválido"}',
                    status_code=403,
                    media_type="application/json",
                )

        response = await call_next(request)

        if not cookie_token:
            new_token = secrets.token_urlsafe(32)
            response.set_cookie(
                CSRF_COOKIE,
                new_token,
                httponly=False,  # debe ser legible por JS para ecoarlo en el header
                secure=self.secure_cookies,
                samesite="lax",
                path="/",
                max_age=8 * 3600,
            )
        return response
