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
from collections.abc import Callable
from dataclasses import dataclass

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
    notes: list[str] | None = None,
    reference_summary: list[str] | None = None,
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
            + ("".join(" " + r for r in (reference_summary or [])))
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
        limitations=limitations + list(notes or []) + (list(result.limitations) if result is not None else []),
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
            out.append(_to_retrieved(chunk, hit.score))
    return out


def _to_retrieved(chunk: Chunk, score: float, cited_from: str | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        page=chunk.page,
        text=chunk.text,
        bbox=chunk.bbox,
        score=score,
        label=chunk.label,
        continues_on=[r.page for r in chunk.extra_regions] or None,
        cited_from=cited_from,
    )


MAX_CITED_EXTRA = 3  # tope de cláusulas citadas que se añaden al contexto de una regla


def _with_cited_clauses(retrieved: list[RetrievedChunk], chunks_by_id: dict[str, Chunk]) -> list[RetrievedChunk]:
    """Una cláusula que dice «conforme a la cláusula quinta» pierde su sentido sin ella: se añade al contexto el
    texto de las cláusulas citadas por los fragmentos recuperados (un nivel, con tope)."""
    present = {c.chunk_id for c in retrieved}
    extra: list[RetrievedChunk] = []
    for source in list(retrieved):
        src = chunks_by_id.get(source.chunk_id)
        if src is None:
            continue
        for ref_id in src.refs:
            if ref_id in present or len(extra) >= MAX_CITED_EXTRA:
                continue
            cited = chunks_by_id.get(ref_id)
            if cited is not None:
                present.add(ref_id)
                extra.append(_to_retrieved(cited, 0.0, cited_from=src.label or src.chunk_id))
    return retrieved + extra


def _source_chunk(page: int | None, bbox: BBoxPoints | None, retrieved: list[RetrievedChunk], chunks_by_id: dict[str, Chunk]) -> Chunk | None:
    """Fragmento del que salió la evidencia que el evaluador citó (por página y recuadro)."""
    if page is None or bbox is None:
        return None
    best: tuple[float, Chunk] | None = None
    for r in retrieved:
        chunk = chunks_by_id.get(r.chunk_id)
        if chunk is None or r.cited_from or chunk.page != page:
            continue
        w = min(chunk.bbox.x1, bbox.x1) - max(chunk.bbox.x0, bbox.x0)
        h = min(chunk.bbox.y1, bbox.y1) - max(chunk.bbox.y0, bbox.y0)
        overlap = w * h if w > 0 and h > 0 else 0.0
        if best is None or overlap > best[0]:
            best = (overlap, chunk)
    return best[1] if best else None


def _reference_notes(source: Chunk | None, chunks_by_id: dict[str, Chunk]) -> tuple[list[str], list[str]]:
    """(avisos, resumen): citas internas sin destino y cláusulas citadas cuyo texto se incluyó."""
    if source is None:
        return [], []
    label = source.label or source.chunk_id
    warnings = [
        f"La cláusula «{label}» cita «{ref}», que no se encontró en el documento: revisa ese enlace."
        for ref in source.unresolved_refs
    ]
    included = [chunks_by_id[r].label or r for r in source.refs[:MAX_CITED_EXTRA] if r in chunks_by_id]
    return warnings, ([f"Se incluyó el texto de {', '.join('«' + i + '»' for i in included)} porque la cláusula lo cita."] if included else [])


def _build_index(chunks: list[Chunk]) -> tuple[FaissVectorIndex, dict[str, Chunk]]:
    embedder = get_embedding_provider()
    by_id = {c.chunk_id: c for c in chunks}
    index = FaissVectorIndex(dim=embedder.dim)
    if chunks:
        vectors = embedder.embed([c.text for c in chunks])
        index.build([c.chunk_id for c in chunks], vectors)
    return index, by_id


def _no_report(**_: object) -> None:
    pass


def run_analysis(
    db: Session, analysis: Analysis, document: Document, rules: list[Rule], report: Callable[..., None] = _no_report
) -> None:
    """Ejecuta el análisis y persiste un Finding por regla. `report(phase=, done=, detail=)` avisa del avance
    (fases de `app.progress.PHASES`); por defecto no hace nada."""
    report(phase=0, detail=f"{document.page_count} página(s)")
    extraction = extract_and_update_document(db, document)
    chunks = chunk_document(extraction)

    report(phase=1, detail=f"{len(chunks)} fragmento(s) de texto")
    embedder = get_embedding_provider()
    index, chunks_by_id = _build_index(chunks)
    evaluator = get_rule_evaluator()

    page_sizes = {p.page: (p.width, p.height) for p in extraction.pages}

    report(phase=2, done=0)
    for done, rule in enumerate(rules):
        report(done=done, detail=rule.name)
        retrieved: list[RetrievedChunk] = _retrieve(rule, embedder, index, chunks_by_id, TOP_K) if chunks else []
        retrieved = _with_cited_clauses(retrieved, chunks_by_id)

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
                    report(detail=f"{rule.name} (segunda búsqueda en todo el contrato)")
                    retrieved = _retrieve(rule, embedder, index, chunks_by_id, cap)  # ya incluye todo: no hay citas que añadir
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

            source = _source_chunk(page, result.bbox, retrieved, chunks_by_id)
            ref_warnings, ref_summary = _reference_notes(source, chunks_by_id)
            extra_regions = [
                {"page": r.page, "x0": r.bbox.x0, "y0": r.bbox.y0, "x1": r.bbox.x1, "y1": r.bbox.y1}
                for r in (source.extra_regions if source is not None else [])
            ]
            finding = Finding(
                analysis_id=analysis.id,
                rule_id=rule.id,
                status=result.status,
                justification=result.justification,
                evidence_text=result.evidence_text,
                extra_regions=extra_regions,
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
                notes=ref_warnings,
                reference_summary=ref_summary,
            )
        db.add(finding)

    report(phase=3, done=len(rules), detail="")
    analysis.analysis_trace = AnalysisTrace(
        embedding_provider=settings.embedding_provider,
        embedding_model={
            "vertex": settings.vertex_embedding_model,
            "foundry": settings.foundry_ai_embed_deployment or None,
        }.get(settings.embedding_provider),
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


@dataclass
class RegionEvaluation:
    status: str
    justification: str
    evidence_text: str | None
    confidence: float
    has_text: bool


def _context_chunks(path: str, page: int, bbox: BBoxPoints) -> list[RetrievedChunk]:
    """Cláusula(s) completa(s) que contienen el recuadro y las que estas citan, como contexto del análisis."""
    chunks = chunk_document(extract_document(path))
    by_id = {c.chunk_id: c for c in chunks}
    hits: list[Chunk] = []
    for c in chunks:
        if c.kind in ("header", "footer", "side", "stamp"):
            continue
        for r in c.regions:
            w = min(r.bbox.x1, bbox.x1) - max(r.bbox.x0, bbox.x0)
            h = min(r.bbox.y1, bbox.y1) - max(r.bbox.y0, bbox.y0)
            if r.page == page and w > 0 and h > 0:
                hits.append(c)
                break
    out: list[RetrievedChunk] = []
    seen: set[str] = set()
    for c in hits[:2]:
        if c.chunk_id not in seen:
            seen.add(c.chunk_id)
            out.append(_to_retrieved(c, 0.0, cited_from=f"contexto del recuadro: {c.label or c.chunk_id}"))
        for ref in c.refs:
            if ref not in seen and ref in by_id and len(out) < 2 + MAX_CITED_EXTRA:
                seen.add(ref)
                out.append(_to_retrieved(by_id[ref], 0.0, cited_from=f"citada desde {c.label or c.chunk_id}"))
    return out


def evaluate_region(
    document: Document, rule: Rule, page: int, bbox: BBoxPoints, instructions: str = "", deep: bool = False
) -> RegionEvaluation:
    """Evalúa con el modelo SOLO el texto nativo contenido en el recuadro: nunca inventa evidencia.
    No toca la base de datos; quien llama decide si guarda el resultado."""
    path = resolve_upload_path(document.stored_filename)
    text = extract_text_in_bbox(str(path), page, bbox)
    if not text:
        return RegionEvaluation(
            status="requiere_revision",
            justification=(
                "El área seleccionada no contiene texto extraíble (posible zona escaneada, "
                "imagen o selección vacía). Requiere revisión manual."
            ),
            evidence_text=None,
            confidence=0.0,
            has_text=False,
        )
    chunk = RetrievedChunk(chunk_id=f"manual-{page}", page=page, text=text, bbox=bbox, score=1.0)
    rule_ctx = RuleContext(
        rule_name=rule.name,
        rule_description=rule.description,
        jurisdiction=rule.jurisdiction,
        normative_citations=[r.citation for r in rule.references],
        extra_instructions=instructions,
    )
    chunks = [chunk]
    if deep:
        try:
            chunks += _context_chunks(str(path), page, bbox)
        except Exception:  # noqa: BLE001 - sin contexto extra el análisis del recuadro sigue siendo válido
            logger.warning("No se pudo reunir el contexto ampliado del recuadro", exc_info=True)
    result = get_rule_evaluator().evaluate(rule_ctx, chunks)
    return RegionEvaluation(
        status=result.status,
        justification=result.justification,
        evidence_text=result.evidence_text or text[:2000],
        confidence=result.confidence,
        has_text=True,
    )


def recalculate_finding(db: Session, finding: Finding, document: Document, rule: Rule) -> None:
    """Recalcula justification/evidence_text/status a partir del bbox actual del finding (tras una edición
    manual), con las indicaciones del auditor si las hubo. Usa exclusivamente el texto nativo de ese bbox."""
    if finding.page is None or None in (finding.bbox_x0, finding.bbox_y0, finding.bbox_x1, finding.bbox_y1):
        finding.status = "requiere_revision"
        finding.justification = "No hay página/bbox definidos para recalcular la evidencia."
        finding.evidence_text = None
        finding.confidence = 0.0
        return

    bbox = BBoxPoints(finding.bbox_x0, finding.bbox_y0, finding.bbox_x1, finding.bbox_y1)
    ev = evaluate_region(document, rule, finding.page, bbox, finding.ai_instructions or "")
    finding.status = ev.status
    finding.justification = ev.justification
    finding.evidence_text = ev.evidence_text
    finding.confidence = ev.confidence


def refresh_evidence_from_regions(finding: Finding, document: Document) -> bool:
    """Tras mover o redimensionar un recuadro SIN pedir IA: actualiza solo el texto de evidencia (lo que hay
    realmente dentro del recuadro y de los tramos de continuación). No toca el estado ni la justificación:
    quedan como estaban hasta que el auditor decida reprocesar con IA. Devuelve True si había texto."""
    if finding.page is None or None in (finding.bbox_x0, finding.bbox_y0, finding.bbox_x1, finding.bbox_y1):
        return False
    path = str(resolve_upload_path(document.stored_filename))
    parts = [extract_text_in_bbox(path, finding.page, BBoxPoints(finding.bbox_x0, finding.bbox_y0, finding.bbox_x1, finding.bbox_y1))]
    for extra in finding.extra_regions or []:
        parts.append(extract_text_in_bbox(path, extra["page"], BBoxPoints(extra["x0"], extra["y0"], extra["x1"], extra["y1"])))
    text = "\n".join(p for p in parts if p).strip()
    if not text:
        return False
    finding.evidence_text = text[:8000]
    return True
