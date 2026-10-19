"""Evaluador sobre Azure AI Foundry (Azure OpenAI), configurado con variables `FOUNDRY_AI_*`.

Reutiliza el evaluador de Groq (mismo prompt, validación de anclaje y degradado a `requiere_revision`); cambia
el destino y la autenticación: `{endpoint}/openai/deployments/{deployment}/chat/completions?api-version=...`
con la cabecera `api-key`. El token llega como recurso secreto de la app (`valueFrom` en app.yaml), nunca en el repo.
"""
from __future__ import annotations

import httpx

from app import foundry_config
from app.config import settings
from app.llm.groq_openai import GroqRuleEvaluator


class FoundryRuleEvaluator(GroqRuleEvaluator):
    def __init__(self):  # noqa: D107 - no hereda el __init__ de Groq (otra autenticación y URL)
        missing = foundry_config.missing()
        if missing:
            raise RuntimeError(f"Faltan variables de configuración para Foundry: {', '.join(missing)}")
        self._model = settings.foundry_ai_deployment
        self._provider_label = "Foundry"
        self._omit_temperature = settings.foundry_omit_temperature
        self._client = httpx.Client(
            base_url=foundry_config.deployment_base_url(settings.foundry_ai_deployment),
            params={"api-version": settings.foundry_ai_api_version},
            headers={"api-key": settings.foundry_ai_token},
            timeout=settings.foundry_timeout_s,
        )
