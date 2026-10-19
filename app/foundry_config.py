"""Configuración compartida de Azure AI Foundry (Azure OpenAI) para el LLM y los embeddings."""
from __future__ import annotations

from urllib.parse import urlparse

from app.config import settings


def missing(embeddings: bool = False) -> list[str]:
    """Variables sin definir (o aún con el marcador REEMPLAZAR-…) para usar Foundry."""
    deployment = settings.foundry_ai_embed_deployment if embeddings else settings.foundry_ai_deployment
    name = "FOUNDRY_AI_EMBED_DEPLOYMENT" if embeddings else "FOUNDRY_AI_DEPLOYMENT"
    values = (
        ("FOUNDRY_AI_ENDPOINT", settings.foundry_ai_endpoint),
        ("FOUNDRY_AI_TOKEN", settings.foundry_ai_token),
        ("FOUNDRY_AI_API_VERSION", settings.foundry_ai_api_version),
        (name, deployment),
    )
    return [n for n, v in values if not v or v.startswith("REEMPLAZAR")]


def deployment_base_url(deployment: str) -> str:
    """`https://<host>/openai/deployments/<deployment>`; solo el host: si se pega una URL con ruta no se duplica."""
    parts = urlparse(settings.foundry_ai_endpoint)
    if parts.scheme != "https":  # el token no puede viajar en claro
        raise RuntimeError("FOUNDRY_AI_ENDPOINT debe empezar por https://")
    return f"https://{parts.netloc}/openai/deployments/{deployment}"
