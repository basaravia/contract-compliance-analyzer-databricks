"""Orquestador del pipeline de análisis de cumplimiento contractual.

Flujo por análisis:
1. Extraer el texto del contrato (`app.pdf.extract`), nativo o con OCR
   opcional si está disponible.
2. Fragmentar el texto en chunks con su bbox (`app.chunking`).
3. Calcular embeddings de los chunks y construir un índice FAISS en memoria
   (uno por análisis; el contrato puede tener cientos de fragmentos, no
   millones, por lo que reconstruirlo por análisis es adecuado para el MVP).
4. Por cada regla activa, recuperar los `top_k` chunks más similares y pedir
   al evaluador (`app.llm`) un veredicto grounded en ese texto.
5. Persistir un `Finding` por regla, siempre validado contra
   `RuleEvaluationResult` antes de guardarse.

Ninguna etapa inventa evidencia: si no hay texto extraíble (documento
escaneado sin OCR) o no hay chunks relevantes, el resultado se degrada a
`no_determinable` / `requiere_revision` en vez de fabricar una cita.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.chunking import Chunk, chunk_document
from app.llm import get_rule_evaluator
from app.llm.base import RetrievedChunk, RuleContext
from app.models import Analysis, Document, ExtractionStatus, Finding, Rule
from app.pdf.coords import BBoxPoints
from app.config import settings
from app.pdf.extract import DocumentExtraction, extract_document, extract_text_in_bbox
from app.retrieval.embeddings import get_embedding_provider
from app.retrieval.faiss_index import FaissVectorIndex
from app.rules.signals import compute_lexical_signals
from app.schemas import AnalysisTrace, DeterministicSignals, ExtractionSignal, FindingTrace, RetrievalSignal
from app.security import resolve_upload_path

logger = logging.getLogger(__name__)

TOP_K = 5


def extract_and_update_document(db: Session, document: Document) -> DocumentExtraction:
    """Extrae el texto del PDF y actualiza el estado de extracción del documento."""
    path = resolve_upload_path(document.stored_filename)
    extraction = extract_document(str(path))

    has_any_text = any(page.full_text.strip() for page in extraction.pages)
    document.is_scanned = any(page.is_scanned for page in extraction.pages)

    if extraction.any_scanned_without_ocr and not has_any_text:
        document.extraction_status = ExtractionStatus.scanned_no_ocr
    elif has_any_text:
        document.extraction_status = ExtractionStatus.done
    else:
        document.extraction_status = ExtractionStatus.failed

    db.add(document)
    db.commit()
    db.refresh(document)
    return extraction


def _llm_model_name() -> str | None:
    return {
        "vertex": settings.vertex_llm_model,
        "groq": settings.groq_llm_model or None,
        "foundry": settings.foundry_ai_deployment or None,
    }.get(settings.llm_provider)


def _build_finding_trace(
    rule_ctx: RuleContext,
    retrieved: list[RetrievedChunk],
    extraction: DocumentExtraction,
    justification: str,
    confidence: float,
    requires_review: bool,
    limitations: list[str],
    result=None,
    second_pass: str | None = None,
    chunks_scanned: int | None = None,
    chunks_total: int | None = None,
) -> dict:
    """Traza de la búsqueda de una regla: qué se recuperó, con qué score y qué
    señales léxicas había. Solo registra lo que realmente ocurrió."""
    ocr_used = any(p.ocr_used for p in extraction.pages)
    scanned = any(p.is_scanned for p in extraction.pages)
    method = "none" if not any(p.blocks for p in extraction.pages) else ("ocr" if ocr_used else "native")
    lex = compute_lexical_signals(rule_ctx, retrieved)
    trace = FindingTrace(
        method_summary=(
            f"Búsqueda semántica de {len(retrieved)} fragmento(s) del contrato "
            f"(top_k={TOP_K}{'; ampliada a todo el contrato' if second_pass else ''}) "
            f"y evaluación con proveedor '{settings.llm_provider}'."
        ),
        extraction=ExtractionSignal(method=method, is_scanned=scanned, ocr_used=ocr_used),
        lexical_signals=DeterministicSignals(
            keyword_overlap_ratio=lex.keyword_overlap_ratio,
            matched_keywords=lex.matched_keywords,
            negation_markers_found=lex.negation_markers_found,
            affirmation_markers_found=lex.affirmation_markers_found,
            best_chunk_id=lex.best_chunk_id,
        ),
        retrieval_signals=[
            RetrievalSignal(chunk_id=c.chunk_id, page=c.page, score=float(c.score), text_excerpt=c.text[:400 if len(retrieved) <= 10 else 120])
            for c in retrieved
        ],
        normative_sections_compared=list(rule_ctx.normative_citations),
        grader_provider=settings.llm_provider,
        grader_model=_llm_model_name(),
        grader_rubric=list(result.grader_rubric) if result is not None else [],
        grader_criteria_results=list(result.grader_criteria_results) if result is not None else [],
        justification=justification[:4000],
        limitations=limitations + (list(result.limitations) if result is not None else []),
        requires_human_review=requires_review or (result.requires_human_review if result is not None else False),
        confidence=confidence,
        second_pass=second_pass,
        chunks_scanned=chunks_scanned,
        chunks_total=chunks_total,
    )
    return trace.model_dump(mode="json")


def _looks_absent(result) -> bool:
    """Misma noción de «no hay cláusula» que usa el papel (classify_search → N): sin evidencia y
    el evaluador dice no_cumple/no_determinable. `requiere_revision` NO es ausencia (es duda)."""
    return not (result.evidence_text or "").strip() and result.status in ("no_cumple", "no_determinable")


def _retrieve(rule: Rule, embedder, index: FaissVectorIndex, chunks_by_id: dict[str, Chunk], top_k: int) -> list[RetrievedChunk]:
    query_vec = embedder.embed([f"{rule.name}. {rule.description}"])[0]
    out: list[RetrievedChunk] = []
    for hit in index.search(query_vec, top_k=top_k):
        chunk = chunks_by_id.get(hit.chunk_id)
        if chunk is not None:
            out.append(RetrievedChunk(chunk_id=chunk.chunk_id, page=chunk.page, text=chunk.text, bbox=chunk.bbox, score=hit.score))
    return out


def _build_index(chunks: list[Chunk]) -> tuple[FaissVectorIndex, dict[str, Chunk]]:
    embedder = get_embedding_provider()
    by_id = {c.chunk_id: c for c in chunks}
    index = FaissVectorIndex(dim=embedder.dim)
    if chunks:
        vectors = embedder.embed([c.text for c in chunks])
        index.build([c.chunk_id for c in chunks], vectors)
    return index, by_id


def run_analysis(db: Session, analysis: Analysis, document: Document, rules: list[Rule]) -> None:
    """Ejecuta el análisis de forma síncrona (adecuado para el tamaño de
    contrato/reglas del MVP) y persiste un Finding por regla."""
    extraction = extract_and_update_document(db, document)
    chunks = chunk_document(extraction)

    embedder = get_embedding_provider()
    index, chunks_by_id = _build_index(chunks)
    evaluator = get_rule_evaluator()

    page_sizes = {p.page: (p.width, p.height) for p in extraction.pages}

    for rule in rules:
        retrieved: list[RetrievedChunk] = _retrieve(rule, embedder, index, chunks_by_id, TOP_K) if chunks else []

        rule_ctx = RuleContext(
            rule_name=rule.name,
            rule_description=rule.description,
            jurisdiction=rule.jurisdiction,
            normative_citations=[r.citation for r in rule.references],
        )

        if not chunks and document.extraction_status == ExtractionStatus.scanned_no_ocr:
            result_status = "no_determinable"
            result_justification = (
                "El documento parece ser un PDF escaneado y no hay OCR disponible en este "
                "despliegue. No es posible determinar el cumplimiento de esta regla de forma "
                "automática; requiere revisión manual del documento original."
            )
            finding = Finding(
                analysis_id=analysis.id,
                rule_id=rule.id,
                status=result_status,
                justification=result_justification,
                evidence_text=None,
                normative_refs=[{"citation": r.citation, "page": r.page} for r in rule.references],
                page=None,
                confidence=0.0,
                severity=rule.severity,
            )
            finding.trace = _build_finding_trace(
                rule_ctx, retrieved, extraction, result_justification, 0.0, True,
                ["Documento escaneado sin OCR: no se pudo buscar texto en el contrato."],
            )
        else:
            result = evaluator.evaluate(rule_ctx, retrieved)
            second_pass = scanned = None
            total = len(chunks)
            if chunks and settings.second_pass_enabled and _looks_absent(result):
                if len(retrieved) >= total:
                    # La primera pasada ya vio todo el contrato: no hay nada más que buscar.
                    second_pass, scanned = "confirmed_absent", total
                else:
                    cap = min(total, max(1, settings.full_scan_max_chunks))
                    retrieved = _retrieve(rule, embedder, index, chunks_by_id, cap)
                    wide = evaluator.evaluate(rule_ctx, retrieved)
                    scanned = len(retrieved)
                    if wide.status == "requiere_revision":
                        second_pass = "failed"
                    elif not _looks_absent(wide):
                        second_pass = "found"
                    else:
                        second_pass = "confirmed_absent" if scanned >= total else "partial_scan"
                    result = wide
            bbox_x0 = bbox_y0 = bbox_x1 = bbox_y1 = None
            page = result.page
            if result.bbox is not None and page is not None:
                width, height = page_sizes.get(page, (result.bbox.x1, result.bbox.y1))
                clamped = BBoxPoints(result.bbox.x0, result.bbox.y0, result.bbox.x1, result.bbox.y1).clamp(width, height)
                bbox_x0, bbox_y0, bbox_x1, bbox_y1 = clamped.x0, clamped.y0, clamped.x1, clamped.y1

            finding = Finding(
                analysis_id=analysis.id,
                rule_id=rule.id,
                status=result.status,
                justification=result.justification,
                evidence_text=result.evidence_text,
                normative_refs=[{"citation": r.citation, "page": r.page} for r in rule.references],
                page=page,
                bbox_x0=bbox_x0,
                bbox_y0=bbox_y0,
                bbox_x1=bbox_x1,
                bbox_y1=bbox_y1,
                confidence=result.confidence,
                severity=rule.severity,
            )
            finding.trace = _build_finding_trace(
                rule_ctx, retrieved, extraction, result.justification, result.confidence,
                result.status == "requiere_revision",
                ([] if retrieved else ["No se recuperó ningún fragmento del contrato para esta regla."])
                + (["Búsqueda no exhaustiva: el contrato tiene más fragmentos que el tope de la segunda pasada."]
                   if second_pass == "partial_scan" else []),
                result,
                second_pass=second_pass,
                chunks_scanned=scanned,
                chunks_total=total if second_pass else None,
            )
        db.add(finding)

    analysis.analysis_trace = AnalysisTrace(
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.vertex_embedding_model if settings.embedding_provider == "vertex" else None,
        llm_provider=settings.llm_provider,
        llm_model=_llm_model_name(),
        retrieval_top_k=TOP_K,
        rules_evaluated=len(rules),
        limitations=(
            ["Embeddings mock: la recuperación es léxica, no semántica."]
            if settings.embedding_provider == "mock"
            else []
        ),
    ).model_dump(mode="json")
    db.commit()


def recalculate_finding(db: Session, finding: Finding, document: Document, rule: Rule) -> None:
    """Recalcula justification/evidence_text/status a partir del bbox actual
    del finding (tras una edición manual). Usa exclusivamente el texto nativo
    contenido en ese bbox: nunca inventa evidencia."""
    if finding.page is None or None in (finding.bbox_x0, finding.bbox_y0, finding.bbox_x1, finding.bbox_y1):
        finding.status = "requiere_revision"
        finding.justification = "No hay página/bbox definidos para recalcular la evidencia."
        finding.evidence_text = None
        finding.confidence = 0.0
        return

    path = resolve_upload_path(document.stored_filename)
    bbox = BBoxPoints(finding.bbox_x0, finding.bbox_y0, finding.bbox_x1, finding.bbox_y1)
    text = extract_text_in_bbox(str(path), finding.page, bbox)

    if not text:
        finding.evidence_text = None
        finding.justification = (
            "El área seleccionada no contiene texto extraíble (posible zona escaneada, "
            "imagen o selección vacía). Requiere revisión manual."
        )
        finding.status = "requiere_revision"
        finding.confidence = 0.0
        return

    evaluator = get_rule_evaluator()
    chunk = RetrievedChunk(chunk_id=f"manual-edit-{finding.id}", page=finding.page, text=text, bbox=bbox, score=1.0)
    rule_ctx = RuleContext(
        rule_name=rule.name,
        rule_description=rule.description,
        jurisdiction=rule.jurisdiction,
        normative_citations=[r.citation for r in rule.references],
    )
    result = evaluator.evaluate(rule_ctx, [chunk])
    finding.status = result.status
    finding.justification = result.justification
    finding.evidence_text = result.evidence_text or text[:2000]
    finding.confidence = result.confidence
