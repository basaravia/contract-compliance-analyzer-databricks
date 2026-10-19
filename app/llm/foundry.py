"""Evaluador sobre Azure AI Foundry (Azure OpenAI), configurado con variables `FOUNDRY_AI_*`.

Reutiliza el evaluador de Groq (mismo prompt, validación de anclaje y degradado a `requiere_revision`); cambia
el destino y la autenticación: `{endpoint}/openai/deployments/{deployment}/chat/completions?api-version=...`
con la cabecera `api-key`. El token llega como recurso secreto de la app (`valueFrom` en app.yaml), nunca en el repo.
"""
from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.config import settings
from app.llm.groq_openai import GroqRuleEvaluator


class FoundryRuleEvaluator(GroqRuleEvaluator):
    def __init__(self):  # noqa: D107 - no hereda el __init__ de Groq (otra autenticación y URL)
        missing = [
            name
            for name, value in (
                ("FOUNDRY_AI_ENDPOINT", settings.foundry_ai_endpoint),
                ("FOUNDRY_AI_TOKEN", settings.foundry_ai_token),
                ("FOUNDRY_AI_API_VERSION", settings.foundry_ai_api_version),
                ("FOUNDRY_AI_DEPLOYMENT", settings.foundry_ai_deployment),
            )
            if not value or value.startswith("REEMPLAZAR")
        ]
        if missing:
            raise RuntimeError(f"Faltan variables de configuración para Foundry: {', '.join(missing)}")
        parts = urlparse(settings.foundry_ai_endpoint)
        if parts.scheme != "https":  # el token no puede viajar en claro
            raise RuntimeError("FOUNDRY_AI_ENDPOINT debe empezar por https://")
        self._model = settings.foundry_ai_deployment
        self._provider_label = "Foundry"
        self._omit_temperature = settings.foundry_omit_temperature
        self._client = httpx.Client(
            # Solo el host: si se pega una URL con ruta no se duplica.
            base_url=f"https://{parts.netloc}/openai/deployments/{settings.foundry_ai_deployment}",
            params={"api-version": settings.foundry_ai_api_version},
            headers={"api-key": settings.foundry_ai_token},
            timeout=settings.foundry_timeout_s,
        )
