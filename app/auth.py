"""Autenticación.

Modos, seleccionados por `AUTH_MODE`:

- ``local`` (por defecto): sin credenciales, útil para desarrollo/demo.
  Toda petición se atribuye a un usuario de desarrollo fijo
  (`LOCAL_DEV_USER_EMAIL`). Nunca debe usarse en producción.
- ``oidc``: Authorization Code Flow contra Microsoft Entra ID (Azure AD).
  El backend valida la firma del `id_token` contra las claves públicas
  (JWKS) publicadas por Entra, verifica `iss`, `aud`, `exp` y `nonce`, y
  jamás confía en el `id_token` sin verificar su firma.

- ``databricks``: la app corre en Databricks Apps. La plataforma autentica al usuario (SSO del workspace)
  ANTES de que la petición llegue a la app y añade las cabeceras ``X-Forwarded-Email`` /
  ``X-Forwarded-Preferred-Username``. La app no tiene login propio ni cookie de sesión; solo lee esas
  cabeceras. Es seguro únicamente porque el contenedor no es alcanzable sin pasar por el proxy.

La sesión se guarda en una cookie firmada con `itsdangerous`
(HMAC, no cifrado: no debe contener datos sensibles, solo email/nombre),
`httponly=True` (no accesible desde JS, mitiga robo vía XSS) y
`samesite=lax`. La verificación de expiración (`max_age`) hace que una
cookie robada deje de ser válida pasado `SESSION_MAX_AGE`.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings
from app.schemas import UserOut

SESSION_COOKIE = "ccap_session"
OAUTH_STATE_COOKIE = "ccap_oauth_state"
SESSION_MAX_AGE = 8 * 3600
OAUTH_STATE_MAX_AGE = 600

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="ccap-session-v1")
_oauth_state_serializer = URLSafeTimedSerializer(settings.secret_key, salt="ccap-oauth-state-v1")


def secure_cookies() -> bool:
    """En 'development' se permite http://localhost (secure=False);
    en cualquier otro entorno las cookies exigen HTTPS."""
    return settings.app_env != "development"


@dataclass
class CurrentUser:
    email: str
    name: str
    auth_mode: str


# ---------------------------------------------------------------------------
# Descubrimiento OIDC + JWKS (con caché en memoria de proceso)
# ---------------------------------------------------------------------------
class _OIDCCache:
    def __init__(self) -> None:
        self.config: dict | None = None
        self.jwks: dict | None = None
        self.fetched_at: float = 0.0

    def is_stale(self) -> bool:
        return self.config is None or (time.time() - self.fetched_at) > 3600


_cache = _OIDCCache()


def _discovery_url() -> str:
    return f"https://login.microsoftonline.com/{settings.oidc_tenant_id}/v2.0/.well-known/openid-configuration"


async def _load_oidc_config(client: httpx.AsyncClient) -> dict:
    if _cache.is_stale():
        resp = await client.get(_discovery_url(), timeout=10.0)
        resp.raise_for_status()
        _cache.config = resp.json()
        jwks_resp = await client.get(_cache.config["jwks_uri"], timeout=10.0)
        jwks_resp.raise_for_status()
        _cache.jwks = jwks_resp.json()
        _cache.fetched_at = time.time()
    return _cache.config  # type: ignore[return-value]


def _get_signing_key(kid: str):
    for key in (_cache.jwks or {}).get("keys", []):
        if key.get("kid") == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(key)
    raise HTTPException(status_code=401, detail="No se encontró la clave de firma del proveedor de identidad")


def _verify_id_token(id_token: str, nonce: str) -> dict:
    if not _cache.jwks:
        raise HTTPException(status_code=500, detail="Configuración OIDC no inicializada")
    try:
        header = jwt.get_unverified_header(id_token)
        key = _get_signing_key(header["kid"])
        claims = jwt.decode(
            id_token,
            key=key,
            algorithms=["RS256"],
            audience=settings.oidc_client_id,
            issuer=_cache.config["issuer"],
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Token de identidad inválido: {e}") from e

    if claims.get("nonce") != nonce:
        raise HTTPException(status_code=401, detail="El nonce del token no coincide (posible ataque de repetición)")
    return claims


# ---------------------------------------------------------------------------
# Dependencias FastAPI
# ---------------------------------------------------------------------------
def _databricks_user(request: Request) -> CurrentUser:
    """Identidad que el proxy de Databricks Apps adjunta tras autenticar con SSO."""
    email = (request.headers.get("x-forwarded-email") or request.headers.get("x-forwarded-preferred-username") or "").strip()
    if not email:
        raise HTTPException(status_code=401, detail="No autenticado")
    name = (request.headers.get("x-forwarded-preferred-username") or email).strip()
    return CurrentUser(email=email[:254], name=name[:200], auth_mode="databricks")


def get_current_user(request: Request, ccap_session: str | None = Cookie(default=None)) -> CurrentUser:
    if settings.auth_mode == "databricks":
        return _databricks_user(request)

    if settings.auth_mode == "local":
        return CurrentUser(
            email=settings.local_dev_user_email,
            name=settings.local_dev_user_name,
            auth_mode="local",
        )

    if not ccap_session:
        raise HTTPException(status_code=401, detail="No autenticado")
    try:
        data = _serializer.loads(ccap_session, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada") from None

    return CurrentUser(email=data["email"], name=data.get("name") or data["email"], auth_mode="oidc")


def session_is_valid(request: Request, ccap_session: str | None) -> bool:
    """Para páginas HTML (que redirigen a /auth/login en vez de devolver 401)."""
    try:
        get_current_user(request, ccap_session)
        return True
    except HTTPException:
        return False


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
router = APIRouter(tags=["auth"])


@router.get("/auth/me", response_model=UserOut)
def me(user: CurrentUser = Depends(get_current_user)) -> UserOut:
    return UserOut(email=user.email, name=user.name, auth_mode=user.auth_mode)


@router.get("/auth/login")
async def login() -> RedirectResponse:
    if settings.auth_mode != "oidc":
        raise HTTPException(status_code=400, detail="AUTH_MODE no está configurado como 'oidc'")
    if not (settings.oidc_tenant_id and settings.oidc_client_id):
        raise HTTPException(status_code=500, detail="OIDC no está configurado (falta tenant/client id)")

    async with httpx.AsyncClient() as client:
        config = await _load_oidc_config(client)

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "redirect_uri": settings.oidc_redirect_uri,
        "response_mode": "query",
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
    }
    authorize_url = f"{config['authorization_endpoint']}?{urlencode(params)}"

    resp = RedirectResponse(authorize_url, status_code=302)
    resp.set_cookie(
        OAUTH_STATE_COOKIE,
        _oauth_state_serializer.dumps({"state": state, "nonce": nonce}),
        max_age=OAUTH_STATE_MAX_AGE,
        httponly=True,
        secure=secure_cookies(),
        samesite="lax",
    )
    return resp


@router.get("/auth/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    ccap_oauth_state: str | None = Cookie(default=None),
) -> RedirectResponse:
    if settings.auth_mode != "oidc":
        raise HTTPException(status_code=400, detail="AUTH_MODE no está configurado como 'oidc'")
    if error:
        raise HTTPException(status_code=401, detail=f"El proveedor de identidad devolvió un error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Falta 'code' o 'state' en la respuesta del proveedor")
    if not ccap_oauth_state:
        raise HTTPException(status_code=400, detail="Falta la cookie de estado OAuth (expirada o bloqueada)")

    try:
        saved = _oauth_state_serializer.loads(ccap_oauth_state, max_age=OAUTH_STATE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=400, detail="Estado OAuth inválido o expirado") from None

    if not secrets.compare_digest(saved["state"], state):
        raise HTTPException(status_code=400, detail="El parámetro 'state' no coincide (posible CSRF de login)")

    async with httpx.AsyncClient() as client:
        config = await _load_oidc_config(client)
        token_resp = await client.post(
            config["token_endpoint"],
            data={
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.oidc_redirect_uri,
            },
            timeout=10.0,
        )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=401, detail="No se pudo intercambiar el código de autorización")

    token_data = token_resp.json()
    id_token = token_data.get("id_token")
    if not id_token:
        raise HTTPException(status_code=401, detail="El proveedor no devolvió un id_token")

    claims = _verify_id_token(id_token, nonce=saved["nonce"])
    email = claims.get("preferred_username") or claims.get("email") or claims.get("upn")
    name = claims.get("name") or email
    if not email:
        raise HTTPException(status_code=401, detail="El token no contiene un email/identificador de usuario")

    session_token = _serializer.dumps({"email": email, "name": name})
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=secure_cookies(),
        samesite="lax",
    )
    resp.delete_cookie(OAUTH_STATE_COOKIE)
    return resp


@router.post("/auth/logout")
def logout() -> RedirectResponse:
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(SESSION_COOKIE, path="/", secure=secure_cookies(), httponly=True, samesite="lax")
    return resp
