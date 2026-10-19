"""Configuración centralizada de la aplicación (vía variables de entorno / .env)."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    secret_key: str = "change-me-dev-only-not-a-real-secret"

    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"
    upload_dir: str = str(BASE_DIR / "data" / "uploads")
    max_upload_mb: int = 25

    # Auth
    auth_mode: str = "local"  # local | oidc | databricks
    local_dev_user_email: str = "dev@example.com"
    local_dev_user_name: str = "Usuario de Desarrollo"

    oidc_tenant_id: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = "http://localhost:8000/auth/callback"

    # Embeddings / LLM
    embedding_provider: str = "mock"  # mock | vertex
    llm_provider: str = "mock"  # mock | vertex | groq | foundry

    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    vertex_embedding_model: str = "gemini-embedding-001"
    vertex_llm_model: str = "gemini-3.6-flash"
    google_application_credentials: str = ""

    # Groq (API compatible con OpenAI)
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_llm_model: str = ""
    groq_timeout_s: float = 60.0

    # Databricks Apps (AUTH_MODE=databricks / LLM_PROVIDER=databricks). La plataforma inyecta DATABRICKS_HOST,
    # DATABRICKS_CLIENT_ID/SECRET (principal de servicio de la app) y DATABRICKS_APP_PORT.
    databricks_host: str = ""
    # Azure AI Foundry (Azure OpenAI). El token es secreto: en Databricks Apps llega por `valueFrom`.
    foundry_ai_endpoint: str = ""
    foundry_ai_api_version: str = ""
    foundry_ai_token: str = ""
    foundry_ai_deployment: str = ""
    foundry_omit_temperature: bool = False  # GPT-5.x (razonamiento) solo acepta la temperatura de fábrica
    foundry_timeout_s: float = 60.0
    # Ruta de un Volume de Unity Catalog (/Volumes/<catalogo>/<esquema>/<volumen>/...) donde se guarda la copia
    # durable de los PDF. El disco del contenedor es efímero: sin esto los PDF se pierden al reiniciar la app.
    upload_volume_path: str = ""
    # Lakebase (Postgres gestionado). Los inyecta el recurso `database` de la app; la contraseña es un token OAuth.
    pghost: str = ""
    pgport: int = 5432
    pgdatabase: str = "databricks_postgres"
    pguser: str = ""
    pgsslmode: str = "require"

    # Segunda pasada antes de declarar «no encontrado» (ver docs/arquitectura/03)
    second_pass_enabled: bool = True
    full_scan_max_chunks: int = 40  # tope de fragmentos que se envían al evaluador en la pasada ampliada

    # Vector index
    vector_index_provider: str = "faiss"

    default_jurisdiction: str = "EC"

    @property
    def use_lakebase(self) -> bool:
        return bool(self.pghost)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()

Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
if settings.database_url.startswith("sqlite:///"):
    Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
