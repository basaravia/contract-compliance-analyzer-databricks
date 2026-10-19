"""Adaptador a Groq (API compatible con OpenAI) para evaluar reglas.

Usa `httpx` (ya es dependencia del proyecto), sin SDKs extra. Reutiliza el
prompt y la validación de anclaje (grounding) del adaptador de Vertex: si la
llamada falla o la salida no valida contra `RuleEvaluationResult`, se degrada a
`requiere_revision`; nunca se inventan coordenadas ni evidencia.
"""
from __future__ import annotations

import json
import logging

import httpx
from pydantic import ValidationError

from app.config import settings
from app.llm.base import RetrievedChunk, RuleContext
from app.llm.vertex_gemini import VertexGeminiRuleEvaluator
from app.schemas import RuleEvaluationResult

logger = logging.getLogger(__name__)


class GroqRuleEvaluator(VertexGeminiRuleEvaluator):
    def __init__(self):  # noqa: D107 - no hereda el __init__ de Vertex (sin LangChain)
        missing = [
            name
            for name, value in (("GROQ_API_KEY", settings.groq_api_key), ("GROQ_LLM_MODEL", settings.groq_llm_model))
            if not value
        ]
        if missing:
            raise RuntimeError(f"Faltan variables de configuración para Groq: {', '.join(missing)}")
        self._model = settings.groq_llm_model
        self._provider_label = "Groq"
        self._client = httpx.Client(
            base_url=settings.groq_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            timeout=settings.groq_timeout_s,
        )

    def evaluate(self, rule: RuleContext, chunks: list[RetrievedChunk]) -> RuleEvaluationResult:
        if not chunks:
            return RuleEvaluationResult(
                status="no_determinable",
                justification="Sin fragmentos recuperados del contrato para esta regla.",
                confidence=0.0,
            )
        try:
            body = {
                "model": self._model,
                "messages": [{"role": "user", "content": self._build_prompt(rule, chunks)}],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
            if getattr(self, "_omit_temperature", False):  # modelos de razonamiento: solo la temperatura de fábrica
                body.pop("temperature")
            resp = self._client.post("/chat/completions", json=body)
            resp.raise_for_status()
            data = json.loads(resp.json()["choices"][0]["message"]["content"])
            result = RuleEvaluationResult.model_validate(data)
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError, IndexError, TypeError) as e:
            # Solo el tipo de error: el mensaje de httpx puede incluir cabeceras/URL.
            logger.warning("Fallo evaluando regla '%s' con %s: %s", rule.rule_name, self._provider_label, type(e).__name__)
            return RuleEvaluationResult(
                status="requiere_revision",
                justification=(
                    "El modelo no devolvió una respuesta válida o analizable. "
                    "Se requiere revisión manual de esta regla."
                ),
                confidence=0.0,
            )
        return self._validate_grounding(result, chunks)
