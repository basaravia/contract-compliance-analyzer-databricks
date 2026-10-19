"""Tests de `MockRuleEvaluator`: el punto clave es demostrar que la
evaluación heurística NUNCA inventa evidencia ni coordenadas: cuando hay
evidencia, `evidence_text`/`page`/`bbox` provienen literalmente del chunk
recuperado; cuando no hay solapamiento léxico suficiente o no hay chunks,
degrada a `no_determinable` sin bbox.

Nota sobre los textos de ejemplo: `AFFIRMATION_MARKERS` incluye
substrings como "garantiza" y "se compromete", que también pueden aparecer
dentro de una frase negada (p. ej. "no garantiza"). Para que los casos de
"solo negación" y "solo afirmación" sean inequívocos bajo la heurística
léxica actual (basada en presencia de substrings, documentada como una
heurística simple y no NLU real), los textos de este archivo evitan que
un marcador de un tipo aparezca "escondido" dentro de una frase del otro
tipo, salvo en el caso explícitamente diseñado para `parcial`.
"""
from __future__ import annotations

from app.llm.base import RetrievedChunk, RuleContext
from app.llm.mock import MockRuleEvaluator
from app.pdf.coords import BBoxPoints

RULE = RuleContext(
    rule_name="Proteccion de datos personales",
    rule_description=(
        "El contrato debe incluir una clausula donde el proveedor se compromete a "
        "proteger los datos personales de los usuarios conforme a la normativa de "
        "proteccion de datos (LOPDP)."
    ),
    jurisdiction="EC",
    normative_citations=["LOPDP Art. 5"],
)


def _evaluator() -> MockRuleEvaluator:
    return MockRuleEvaluator()


def test_no_chunks_returns_no_determinable_without_bbox():
    result = _evaluator().evaluate(RULE, [])

    assert result.status == "no_determinable"
    assert result.bbox is None
    assert result.evidence_text is None
    assert result.page is None


def test_chunk_without_lexical_overlap_returns_no_determinable_without_bbox():
    unrelated_chunk = RetrievedChunk(
        chunk_id="c1",
        page=3,
        text=(
            "El presente contrato de arrendamiento de vehiculos establece el "
            "kilometraje maximo permitido y las tarifas de combustible aplicables "
            "durante el periodo de alquiler."
        ),
        bbox=BBoxPoints(10, 10, 100, 50),
        score=0.1,
    )

    result = _evaluator().evaluate(RULE, [unrelated_chunk])

    assert result.status == "no_determinable"
    assert result.bbox is None
    assert result.evidence_text is None
    assert result.confidence < 0.5


def test_affirmation_only_chunk_returns_cumple_with_literal_evidence():
    text = (
        "Clausula de Proteccion de Datos Personales. El proveedor se compromete a "
        "proteger los datos personales de los usuarios y garantiza el cumplimiento "
        "de la normativa de proteccion de datos conforme a la LOPDP en todo momento."
    )
    chunk = RetrievedChunk(
        chunk_id="p1-c0",
        page=1,
        text=text,
        bbox=BBoxPoints(50, 50, 515, 97),
        score=0.9,
    )

    result = _evaluator().evaluate(RULE, [chunk])

    assert result.status == "cumple"
    assert result.evidence_text is not None
    # Nunca debe inventar texto: la evidencia es literalmente un substring
    # (tras strip) del texto del chunk recuperado.
    assert result.evidence_text in chunk.text
    assert result.page == chunk.page
    assert result.bbox is not None
    assert result.bbox.x0 == chunk.bbox.x0
    assert result.bbox.y0 == chunk.bbox.y0
    assert result.bbox.x1 == chunk.bbox.x1
    assert result.bbox.y1 == chunk.bbox.y1
    assert result.confidence > 0.0


def test_negation_only_chunk_returns_no_cumple():
    text = (
        "El proveedor no cuenta con ningun mecanismo de proteccion de datos "
        "personales y carece de politica de tratamiento de dichos datos; esta "
        "obligacion queda excluido explicitamente del contrato firmado por ambas "
        "partes segun la normativa vigente sobre datos personales."
    )
    chunk = RetrievedChunk(
        chunk_id="p1-c1",
        page=2,
        text=text,
        bbox=BBoxPoints(50, 100, 500, 160),
        score=0.8,
    )

    result = _evaluator().evaluate(RULE, [chunk])

    assert result.status == "no_cumple"
    assert result.evidence_text is not None
    assert result.evidence_text in chunk.text
    assert result.page == chunk.page
    assert result.bbox is not None
    assert result.bbox.x0 == chunk.bbox.x0
    assert result.bbox.y1 == chunk.bbox.y1


def test_chunk_with_both_markers_returns_parcial():
    text = (
        "El proveedor se compromete a proteger los datos personales conforme a la "
        "LOPDP, sin embargo carece de un procedimiento claro de notificacion y "
        "dicha obligacion queda excluido en casos de fuerza mayor."
    )
    chunk = RetrievedChunk(
        chunk_id="p1-c2",
        page=1,
        text=text,
        bbox=BBoxPoints(50, 200, 500, 260),
        score=0.85,
    )

    result = _evaluator().evaluate(RULE, [chunk])

    assert result.status == "parcial"
    assert result.evidence_text is not None
    assert result.evidence_text in chunk.text


def test_multiple_chunks_picks_best_overlap_and_evidence_still_literal():
    good_text = (
        "Clausula de Proteccion de Datos Personales. El proveedor se compromete a "
        "proteger los datos personales de los usuarios conforme a la LOPDP."
    )
    unrelated_text = (
        "Condiciones de pago y facturacion mensual del contrato de suministro."
    )
    good_chunk = RetrievedChunk(
        chunk_id="good", page=1, text=good_text, bbox=BBoxPoints(0, 0, 200, 40), score=0.9
    )
    unrelated_chunk = RetrievedChunk(
        chunk_id="bad", page=1, text=unrelated_text, bbox=BBoxPoints(0, 100, 200, 140), score=0.2
    )

    result = _evaluator().evaluate(RULE, [unrelated_chunk, good_chunk])

    assert result.status == "cumple"
    assert result.evidence_text in good_chunk.text
    assert result.bbox is not None
    assert result.bbox.x0 == good_chunk.bbox.x0
    assert result.bbox.y1 == good_chunk.bbox.y1
