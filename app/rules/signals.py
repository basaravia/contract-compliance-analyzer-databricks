"""Señales deterministas (léxicas) compartidas entre el evaluador mock y el
contexto que se ofrece al LLM real.

Se calculan una sola vez con una función pura para que:
- El evaluador mock las use directamente (en vez de reinventar la lógica).
- El adaptador Vertex/Gemini las incluya como contexto auditable en el
  prompt ("señales deterministas/semánticas" exigidas junto a la evidencia).
- El motor de análisis (`app.analysis_engine`) las persista en la traza de
  explicabilidad (`FindingTrace`) sin tener que duplicar el cálculo.

Es una heurística de coincidencia de palabras clave (bag-of-words), no
comprensión semántica real: se documenta así explícitamente en toda salida
que la use.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.llm.base import RetrievedChunk, RuleContext

STOPWORDS = {
    "de", "la", "el", "en", "y", "a", "los", "las", "un", "una", "para", "con",
    "que", "se", "por", "del", "al", "su", "sus", "o", "e", "no", "si", "es",
    "debe", "deberá", "podrá", "como", "las", "los",
}

NEGATION_MARKERS = ("no se", "no podrá", "no deberá", "sin ", "prohibido", "queda excluido", "no cuenta con", "carece de")
AFFIRMATION_MARKERS = ("se compromete", "garantiza", "cumple con", "de acuerdo con", "conforme a", "se obliga a")

MIN_OVERLAP_RATIO = 0.15


def _keywords(text: str) -> set[str]:
    tokens = "".join(c.lower() if c.isalnum() else " " for c in text).split()
    return {t for t in tokens if len(t) > 3 and t not in STOPWORDS}


@dataclass
class LexicalSignals:
    """Resultado del cálculo determinista sobre un conjunto de fragmentos
    recuperados para una regla dada."""

    keyword_overlap_ratio: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)
    negation_markers_found: list[str] = field(default_factory=list)
    affirmation_markers_found: list[str] = field(default_factory=list)
    best_chunk_id: str | None = None
    best_combined_score: float = 0.0


def compute_lexical_signals(rule: RuleContext, chunks: list[RetrievedChunk]) -> LexicalSignals:
    """Calcula solapamiento léxico y marcadores de negación/afirmación sobre
    el fragmento con mejor combinación de solapamiento léxico + similitud de
    recuperación. No inventa señales: si no hay fragmentos o no hay
    vocabulario analizable, devuelve una señal vacía (todo en cero/listas
    vacías), nunca valores fabricados."""
    if not chunks:
        return LexicalSignals()

    rule_kw = _keywords(rule.rule_description) | _keywords(rule.rule_name)
    if not rule_kw:
        return LexicalSignals()

    best_chunk: RetrievedChunk | None = None
    best_overlap = 0.0
    best_combined = 0.0
    best_matched: set[str] = set()

    for chunk in chunks:
        chunk_kw = _keywords(chunk.text)
        if not chunk_kw:
            continue
        matched = rule_kw & chunk_kw
        overlap = len(matched) / max(1, len(rule_kw))
        combined = 0.6 * overlap + 0.4 * max(0.0, chunk.score)
        if combined > best_combined:
            best_combined = combined
            best_overlap = overlap
            best_chunk = chunk
            best_matched = matched

    if best_chunk is None:
        return LexicalSignals()

    text_lower = best_chunk.text.lower()
    negation_found = [m.strip() for m in NEGATION_MARKERS if m in text_lower]
    affirmation_found = [m.strip() for m in AFFIRMATION_MARKERS if m in text_lower]

    return LexicalSignals(
        keyword_overlap_ratio=round(best_overlap, 4),
        matched_keywords=sorted(best_matched),
        negation_markers_found=negation_found,
        affirmation_markers_found=affirmation_found,
        best_chunk_id=best_chunk.chunk_id,
        best_combined_score=round(best_combined, 4),
    )
