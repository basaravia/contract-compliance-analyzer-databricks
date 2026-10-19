"""Evaluador mock/local: heurística determinista de coincidencia léxica.

No es un modelo de lenguaje real ni constituye asesoría legal. Sirve para
que el MVP funcione end-to-end sin credenciales de Vertex AI. Se activa con
LLM_PROVIDER=mock (valor por defecto).

Heurística:
1. Se toma el fragmento del contrato mejor recuperado (por similitud de
   embeddings) que además comparta palabras clave con la descripción de la regla.
2. Se buscan señales de negación ("no ", "sin ", "prohibido", "queda excluido")
   cerca de las palabras clave para inclinar el resultado hacia `no_cumple`.
3. Si no hay solapamiento léxico suficiente, se devuelve `no_determinable`
   sin bbox ni evidencia inventada.
"""
from __future__ import annotations

from app.llm.base import RetrievedChunk, RuleContext, RuleEvaluator
from app.schemas import BBox, RuleEvaluationResult

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


class MockRuleEvaluator(RuleEvaluator):
    def evaluate(self, rule: RuleContext, chunks: list[RetrievedChunk]) -> RuleEvaluationResult:
        if not chunks:
            return RuleEvaluationResult(
                status="no_determinable",
                justification=(
                    "No se encontró contenido en el contrato relacionado con esta regla "
                    "(sin fragmentos recuperados). Requiere revisión manual."
                ),
                evidence_text=None,
                page=None,
                bbox=None,
                confidence=0.0,
            )

        rule_kw = _keywords(rule.rule_description) | _keywords(rule.rule_name)
        if not rule_kw:
            return RuleEvaluationResult(
                status="requiere_revision",
                justification="La descripción de la regla no contiene palabras clave analizables.",
                evidence_text=None,
                page=None,
                bbox=None,
                confidence=0.0,
            )

        best_chunk = None
        best_overlap = 0.0
        for chunk in chunks:
            chunk_kw = _keywords(chunk.text)
            if not chunk_kw:
                continue
            overlap = len(rule_kw & chunk_kw) / max(1, len(rule_kw))
            combined = 0.6 * overlap + 0.4 * max(0.0, chunk.score)
            if combined > best_overlap:
                best_overlap = combined
                best_chunk = chunk

        if best_chunk is None or best_overlap < MIN_OVERLAP_RATIO:
            return RuleEvaluationResult(
                status="no_determinable",
                justification=(
                    "No se halló evidencia textual suficientemente relacionada con la regla "
                    f"'{rule.rule_name}' en el contrato. Requiere revisión manual."
                ),
                evidence_text=None,
                page=None,
                bbox=None,
                confidence=round(min(best_overlap, 0.4), 3),
            )

        text_lower = best_chunk.text.lower()
        has_negation = any(m in text_lower for m in NEGATION_MARKERS)
        has_affirmation = any(m in text_lower for m in AFFIRMATION_MARKERS)

        if has_negation and not has_affirmation:
            status = "no_cumple"
            verdict = "el fragmento localizado sugiere una negación o exclusión respecto de lo exigido por la regla"
        elif has_affirmation and not has_negation:
            status = "cumple"
            verdict = "el fragmento localizado contiene lenguaje afirmativo alineado con lo exigido por la regla"
        elif has_negation and has_affirmation:
            status = "parcial"
            verdict = "el fragmento localizado contiene señales mixtas (afirmación y negación); requiere validación"
        else:
            status = "requiere_revision"
            verdict = "se halló contenido relacionado pero sin señales léxicas claras de cumplimiento o incumplimiento"

        refs = "; ".join(rule.normative_citations) if rule.normative_citations else "sin referencia normativa asociada"
        justification = (
            f"Regla '{rule.rule_name}' (jurisdicción {rule.jurisdiction}): {verdict}. "
            f"Referencias normativas: {refs}. Evaluación generada por heurística local (mock), "
            "no constituye asesoría legal."
        )

        return RuleEvaluationResult(
            status=status,
            justification=justification,
            evidence_text=best_chunk.text.strip()[:2000],
            page=best_chunk.page,
            bbox=BBox(
                x0=best_chunk.bbox.x0,
                y0=best_chunk.bbox.y0,
                x1=best_chunk.bbox.x1,
                y1=best_chunk.bbox.y1,
            ),
            confidence=round(min(0.95, best_overlap), 3),
        )
