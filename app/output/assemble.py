"""Arma la entrada del papel de trabajo desde la base de datos y el PDF del contrato.

Separado de `workpaper.py` para que el generador del Excel no dependa de SQLAlchemy."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Analysis, Document, Finding, Rule
from app.output.workpaper import WorkpaperInput, WorkpaperRow, enrich
from app.pdf.extract import extract_document
from app.security import resolve_upload_path


def _page_texts(document: Document) -> dict[int, str]:
    extraction = extract_document(str(resolve_upload_path(document.stored_filename)))
    return {p.page: p.full_text for p in extraction.pages}


def build_input(db: Session, analysis: Analysis, document: Document) -> WorkpaperInput:
    findings = db.query(Finding).filter(Finding.analysis_id == analysis.id).all()
    rules = {r.id: r for r in db.query(Rule).filter(Rule.id.in_({f.rule_id for f in findings})).all()}
    order = {rid: i for i, rid in enumerate(analysis.rule_ids or [])}
    rows: list[WorkpaperRow] = []
    for f in sorted(findings, key=lambda f: order.get(f.rule_id, 10_000)):
        rule = rules.get(f.rule_id)
        trace = f.trace or {}
        signals = trace.get("retrieval_signals") or []
        has_bbox = None not in (f.bbox_x0, f.bbox_y0, f.bbox_x1, f.bbox_y1)
        rows.append(WorkpaperRow(
            rule_id=f.rule_id,
            rule_name=rule.name if rule else f.rule_id,
            rule_description=rule.description if rule else "",
            category=rule.category if rule else None,
            severity=f.severity,
            citations=[r["citation"] for r in (f.normative_refs or []) if r.get("citation")],
            status=f.status,
            justification=f.justification,
            evidence_text=f.evidence_text,
            page=f.page,
            bbox=(f.bbox_x0, f.bbox_y0, f.bbox_x1, f.bbox_y1) if has_bbox else None,
            confidence=f.confidence,
            edited=f.edited,
            is_manual=f.is_manual,
            retrieved=(trace.get("chunks_scanned") or len(signals)) if trace else None,
            best_score=max((s["score"] for s in signals), default=None) if trace else None,
            retrieved_pages=sorted({s["page"] for s in signals}),
            second_pass=trace.get("second_pass"),
            chunks_scanned=trace.get("chunks_scanned"),
            chunks_total=trace.get("chunks_total"),
        ))
    status = getattr(document.extraction_status, "value", document.extraction_status)
    inp = WorkpaperInput(
        contract_name=document.title or document.original_filename,
        contract_pages=document.page_count,
        extraction_status=str(status),
        rows=rows,
        analysis_id=analysis.id,
        analysis_trace=analysis.analysis_trace or None,
    )
    return enrich(inp, _page_texts(document))
