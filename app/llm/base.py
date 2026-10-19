"""Interfaz del adaptador de evaluación de reglas (LLM)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.pdf.coords import BBoxPoints
from app.schemas import RuleEvaluationResult


@dataclass
class RetrievedChunk:
    chunk_id: str
    page: int
    text: str
    bbox: BBoxPoints
    score: float


@dataclass
class RuleContext:
    rule_name: str
    rule_description: str
    jurisdiction: str
    normative_citations: list[str]


class RuleEvaluator(ABC):
    @abstractmethod
    def evaluate(self, rule: RuleContext, chunks: list[RetrievedChunk]) -> RuleEvaluationResult:
        """Evalúa una regla contra los fragmentos recuperados del contrato.

        Debe devolver siempre un `RuleEvaluationResult` válido. Si no hay
        evidencia suficiente, el resultado debe tener status
        'no_determinable' o 'requiere_revision' y bbox=None; nunca debe
        inventar coordenadas o citar texto que no exista en los chunks.
        """
        raise NotImplementedError
