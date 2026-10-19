"""Esquemas Pydantic para la API y para validar salidas del modelo (LLM).

Toda salida del LLM se valida contra `RuleEvaluationResult` antes de persistirse.
Si la validación falla o no hay evidencia, el llamador debe degradar el resultado
a `requiere_revision` / `no_determinable` en vez de inventar datos.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FindingStatusLiteral = Literal[
    "cumple", "no_cumple", "parcial", "no_determinable", "requiere_revision"
]
SeverityLiteral = Literal["alta", "media", "baja"]


# ---------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    doc_type: str
    original_filename: str
    title: str | None
    jurisdiction: str
    language: str
    page_count: int
    is_scanned: bool
    extraction_status: str
    uploaded_at: datetime
    file_size_bytes: int


# ---------------------------------------------------------------------------
# Reglas
# ---------------------------------------------------------------------------
class RuleReferenceIn(BaseModel):
    normative_document_id: str | None = None
    citation: str = Field(..., min_length=1, max_length=300)
    page: int | None = Field(default=None, ge=1)


class RuleReferenceOut(RuleReferenceIn):
    model_config = ConfigDict(from_attributes=True)
    id: str


class RuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    jurisdiction: str = Field(default="EC", max_length=10)
    category: str | None = Field(default=None, max_length=100)
    severity: SeverityLiteral = "media"
    active: bool = True
    references: list[RuleReferenceIn] = Field(default_factory=list)


class RuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    category: str | None = None
    severity: SeverityLiteral | None = None
    active: bool | None = None
    references: list[RuleReferenceIn] | None = None


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    jurisdiction: str
    category: str | None
    severity: str
    active: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    references: list[RuleReferenceOut]


class RuleImportPayload(BaseModel):
    """Formato aceptado para importación masiva de reglas vía JSON."""

    rules: list[RuleCreate]

    @field_validator("rules")
    @classmethod
    def not_empty(cls, v: list[RuleCreate]) -> list[RuleCreate]:
        if not v:
            raise ValueError("La lista de reglas no puede estar vacía")
        return v


# ---------------------------------------------------------------------------
# Análisis / Hallazgos (findings)
# ---------------------------------------------------------------------------
class AnalysisCreate(BaseModel):
    contract_document_id: str
    rule_ids: list[str] = Field(default_factory=list, description="Vacío = todas las reglas activas")


class NormativeRefOut(BaseModel):
    document_id: str | None = None
    title: str | None = None
    citation: str
    page: int | None = None


class BBox(BaseModel):
    """Coordenadas en puntos PDF (origen esquina superior izquierda, y crece hacia abajo)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @field_validator("x1")
    @classmethod
    def x1_after_x0(cls, v: float, info) -> float:
        x0 = info.data.get("x0")
        if x0 is not None and v < x0:
            raise ValueError("x1 debe ser >= x0")
        return v

    @field_validator("y1")
    @classmethod
    def y1_after_y0(cls, v: float, info) -> float:
        y0 = info.data.get("y0")
        if y0 is not None and v < y0:
            raise ValueError("y1 debe ser >= y0")
        return v


class GraderCriterionResult(BaseModel):
    """Veredicto del grader (LLM o heurística) sobre un criterio individual
    de la rúbrica de evaluación. `met=None` significa que el criterio no pudo
    determinarse con la evidencia disponible (nunca se fuerza a True/False)."""

    criterion: str = Field(..., min_length=1, max_length=500)
    met: bool | None = None


class RuleEvaluationResult(BaseModel):
    """Esquema estricto de salida esperado del LLM (o del proveedor mock).

    Cualquier campo faltante o inconsistente debe forzar `requiere_revision`
    en la capa que invoca al proveedor, nunca debe inventarse evidencia.
    Los campos de rúbrica/limitaciones/revisión humana hacen explícito el
    razonamiento del grader para la traza de explicabilidad
    (`FindingTrace`); si el proveedor no los completa, quedan vacíos en vez
    de inventarse.
    """

    status: FindingStatusLiteral
    justification: str = Field(..., min_length=1, max_length=4000)
    evidence_text: str | None = Field(default=None, max_length=4000)
    page: int | None = Field(default=None, ge=1)
    bbox: BBox | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    grader_rubric: list[str] = Field(default_factory=list, max_length=20)
    grader_criteria_results: list[GraderCriterionResult] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    requires_human_review: bool = False


# ---------------------------------------------------------------------------
# Traza de explicabilidad (analysis_trace / finding trace)
# ---------------------------------------------------------------------------
class ExtractionSignal(BaseModel):
    """Método de extracción de texto del documento que produjo la evidencia
    disponible para este hallazgo."""

    method: Literal["native", "ocr", "none"]
    is_scanned: bool
    ocr_used: bool


class DeterministicSignals(BaseModel):
    """Señales léxicas calculadas de forma determinista (sin LLM), previas a
    la evaluación final. Ver `app.rules.signals.compute_lexical_signals`."""

    keyword_overlap_ratio: float = 0.0
    matched_keywords: list[str] = Field(default_factory=list)
    negation_markers_found: list[str] = Field(default_factory=list)
    affirmation_markers_found: list[str] = Field(default_factory=list)
    best_chunk_id: str | None = None


class RetrievalSignal(BaseModel):
    """Un fragmento recuperado semánticamente (FAISS) y comparado contra la
    regla, con su score de similitud."""

    chunk_id: str
    page: int
    score: float
    text_excerpt: str = Field(..., max_length=400)


class FindingTrace(BaseModel):
    """Resumen verboso y trazable de cómo se produjo un hallazgo: qué se
    extrajo del PDF, qué se recuperó semánticamente, qué señales
    deterministas se calcularon, qué evaluó el grader (LLM o heurística
    mock) y con qué criterio, y si requiere revisión humana.

    Ninguna señal se inventa: cuando una etapa no se ejecutó o no produjo
    resultado, el campo correspondiente queda vacío/None y se documenta en
    `limitations`, nunca se rellena con un valor fabricado.
    """

    method_summary: str = Field(..., min_length=1, max_length=1000)
    extraction: ExtractionSignal
    lexical_signals: DeterministicSignals | None = None
    retrieval_signals: list[RetrievalSignal] = Field(default_factory=list)
    normative_sections_compared: list[str] = Field(default_factory=list)
    grader_provider: str
    grader_model: str | None = None
    grader_rubric: list[str] = Field(default_factory=list)
    grader_criteria_results: list[GraderCriterionResult] = Field(default_factory=list)
    justification: str = Field(..., max_length=4000)
    limitations: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Segunda pasada antes de declarar «no encontrado» (None = no hizo falta):
    #   found            -> la búsqueda ampliada sí halló evidencia
    #   confirmed_absent -> se revisó TODO el contrato y no hay cláusula
    #   partial_scan     -> el contrato supera el tope; la ausencia no es exhaustiva
    #   failed           -> la pasada ampliada falló; no se puede confirmar ni descartar
    second_pass: Literal["found", "confirmed_absent", "partial_scan", "failed"] | None = None
    chunks_scanned: int | None = None
    chunks_total: int | None = None

    @field_validator("normative_sections_compared", "limitations", "grader_rubric", mode="before")
    @classmethod
    def _none_to_empty_list(cls, v):
        return v if v is not None else []


class AnalysisTrace(BaseModel):
    """Metadatos de trazabilidad a nivel de análisis completo (proveedores,
    modelos y configuración usados en toda la corrida)."""

    embedding_provider: str
    embedding_model: str | None = None
    llm_provider: str
    llm_model: str | None = None
    retrieval_top_k: int
    rules_evaluated: int
    limitations: list[str] = Field(default_factory=list)


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    analysis_id: str
    rule_id: str
    status: str
    justification: str
    evidence_text: str | None
    normative_refs: list[dict]
    page: int | None
    bbox_x0: float | None
    bbox_y0: float | None
    bbox_x1: float | None
    bbox_y1: float | None
    confidence: float
    severity: str
    is_manual: bool
    edited: bool
    trace: FindingTrace | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("trace", mode="before")
    @classmethod
    def _empty_trace_to_none(cls, v):
        return v or None


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_document_id: str
    status: str
    error_message: str | None
    created_by: str | None
    created_at: datetime
    finished_at: datetime | None
    rule_ids: list[str]
    analysis_trace: AnalysisTrace | None = None

    @field_validator("analysis_trace", mode="before")
    @classmethod
    def _empty_analysis_trace_to_none(cls, v):
        return v or None


class AnalysisDetailOut(AnalysisOut):
    findings: list[FindingOut]


class FindingUpdate(BaseModel):
    """Corrección manual de un hallazgo: mover/redimensionar bbox, cambiar estado,
    o cualquier combinación. `recalculate=True` dispara una re-evaluación con la
    nueva evidencia extraída del bbox editado."""

    status: FindingStatusLiteral | None = None
    justification: str | None = Field(default=None, max_length=4000)
    page: int | None = Field(default=None, ge=1)
    bbox: BBox | None = None
    severity: SeverityLiteral | None = None
    recalculate: bool = False


class FindingCreate(BaseModel):
    """Creación manual de una anotación/hallazgo nuevo sobre el contrato."""

    analysis_id: str
    rule_id: str
    page: int = Field(..., ge=1)
    bbox: BBox
    status: FindingStatusLiteral = "requiere_revision"
    justification: str = Field(default="Anotación creada manualmente por el usuario.", max_length=4000)
    severity: SeverityLiteral = "media"


class UserOut(BaseModel):
    email: str
    name: str
    auth_mode: str
