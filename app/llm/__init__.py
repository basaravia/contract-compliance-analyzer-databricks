"""Factoría de proveedores LLM (evaluador de reglas)."""
from __future__ import annotations

from app.config import settings
from app.llm.base import RuleEvaluator
from app.llm.mock import MockRuleEvaluator


def get_rule_evaluator() -> RuleEvaluator:
    if settings.llm_provider == "vertex":
        try:
            from app.llm.vertex_gemini import VertexGeminiRuleEvaluator

            return VertexGeminiRuleEvaluator()
        except Exception:
            # Fallback seguro: el MVP debe poder arrancar sin credenciales.
            return MockRuleEvaluator()
    if settings.llm_provider == "groq":
        try:
            from app.llm.groq_openai import GroqRuleEvaluator

            return GroqRuleEvaluator()
        except Exception:
            return MockRuleEvaluator()
    if settings.llm_provider == "foundry":
        try:
            from app.llm.foundry import FoundryRuleEvaluator

            return FoundryRuleEvaluator()
        except Exception:
            return MockRuleEvaluator()
    return MockRuleEvaluator()
