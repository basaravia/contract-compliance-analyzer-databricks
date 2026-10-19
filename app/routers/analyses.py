"""Endpoints de análisis: ejecución (síncrona, adecuada al tamaño del MVP),
consulta y exportación del PDF anotado."""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.analysis_engine import run_analysis
from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Analysis, AnalysisStatus, Document, DocumentType, Finding, Rule
from app.output.assemble import build_input
from app.output.workpaper import build_workpaper
from app.pdf.annotate import AnnotationSpec, build_annotated_pdf
from app.schemas import AnalysisCreate, AnalysisDetailOut, AnalysisOut, FindingOut
from app.security import resolve_upload_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analyses", tags=["analyses"])

# Un análisis a la vez: protege la cuota de Groq, la memoria del servidor y evita duplicados por reintentos
# (p. ej. tras un timeout del proxy, el servidor sigue trabajando aunque el navegador ya no espere).
_analysis_slot = threading.Lock()


def _get_analysis_or_404(db: Session, analysis_id: str) -> Analysis:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")
    return analysis


@router.post("", response_model=AnalysisDetailOut, status_code=201)
def create_analysis(
    payload: AnalysisCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> Analysis:
    if not _analysis_slot.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Ya hay un análisis en curso. Espera a que termine e inténtalo de nuevo.")
    try:
        return _create_analysis(payload, db, user)
    finally:
        _analysis_slot.release()


def _create_analysis(payload: AnalysisCreate, db: Session, user: CurrentUser) -> AnalysisDetailOut:
    document = db.get(Document, payload.contract_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento de contrato no encontrado")
    if document.doc_type != DocumentType.contrato:
        raise HTTPException(status_code=400, detail="El documento indicado no es un contrato")

    if payload.rule_ids:
        rules = db.query(Rule).filter(Rule.id.in_(payload.rule_ids), Rule.active.is_(True)).all()
        missing = set(payload.rule_ids) - {r.id for r in rules}
        if missing:
            raise HTTPException(status_code=404, detail=f"Reglas no encontradas o inactivas: {sorted(missing)}")
    else:
        rules = db.query(Rule).filter(Rule.active.is_(True)).all()

    if not rules:
        raise HTTPException(status_code=400, detail="No hay reglas activas para evaluar")

    analysis = Analysis(
        contract_document_id=document.id,
        status=AnalysisStatus.running.value,
        created_by=user.email,
        rule_ids=[r.id for r in rules],
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    try:
        run_analysis(db, analysis, document, rules)
        analysis.status = AnalysisStatus.done.value
        analysis.finished_at = datetime.utcnow()
    except Exception:  # noqa: BLE001
        # El detalle (rutas, trazas) va al log del servidor, no al cliente.
        logger.exception("Falló el análisis %s", analysis.id)
        analysis.status = AnalysisStatus.failed.value
        analysis.error_message = "El análisis falló por un error interno. Revisa el registro del servidor."
        analysis.finished_at = datetime.utcnow()
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    findings = db.query(Finding).filter(Finding.analysis_id == analysis.id).all()
    return _to_detail(analysis, findings)


def _to_detail(analysis: Analysis, findings: list[Finding]) -> AnalysisDetailOut:
    data = AnalysisOut.model_validate(analysis, from_attributes=True).model_dump()
    data["findings"] = [FindingOut.model_validate(f, from_attributes=True) for f in findings]
    return AnalysisDetailOut.model_validate(data)


@router.get("", response_model=list[AnalysisOut])
def list_analyses(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> list[Analysis]:
    return db.query(Analysis).order_by(Analysis.created_at.desc()).all()


@router.get("/{analysis_id}", response_model=AnalysisDetailOut)
def get_analysis(
    analysis_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> AnalysisDetailOut:
    analysis = _get_analysis_or_404(db, analysis_id)
    findings = db.query(Finding).filter(Finding.analysis_id == analysis_id).all()
    return _to_detail(analysis, findings)


@router.get("/{analysis_id}/export.pdf")
def export_analysis_pdf(
    analysis_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> Response:
    analysis = _get_analysis_or_404(db, analysis_id)
    document = db.get(Document, analysis.contract_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="El documento del contrato ya no existe")

    findings = db.query(Finding).filter(Finding.analysis_id == analysis_id).all()
    rules_by_id = {r.id: r for r in db.query(Rule).filter(Rule.id.in_({f.rule_id for f in findings})).all()}

    specs = []
    for f in findings:
        if f.page is None or None in (f.bbox_x0, f.bbox_y0, f.bbox_x1, f.bbox_y1):
            continue
        rule = rules_by_id.get(f.rule_id)
        label = rule.name if rule else f.rule_id
        specs.append(
            AnnotationSpec(
                page=f.page,
                x0=f.bbox_x0,
                y0=f.bbox_y0,
                x1=f.bbox_x1,
                y1=f.bbox_y1,
                status=f.status,
                label=label,
                note=f.justification,
            )
        )

    path = resolve_upload_path(document.stored_filename)
    pdf_bytes = build_annotated_pdf(str(path), specs)
    filename = f"analisis-{analysis_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{analysis_id}/export.json")
def export_analysis_json(
    analysis_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> Response:
    analysis = _get_analysis_or_404(db, analysis_id)
    findings = db.query(Finding).filter(Finding.analysis_id == analysis_id).all()
    detail = _to_detail(analysis, findings)
    filename = f"analisis-{analysis_id}.json"
    return Response(
        content=detail.model_dump_json(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{analysis_id}/papel-trabajo.xlsx")
def export_workpaper(
    analysis_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> Response:
    """Papel de trabajo de auditoría (Excel, 2 hojas). Se genera sin llamar a ningún modelo."""
    analysis = _get_analysis_or_404(db, analysis_id)
    document = db.get(Document, analysis.contract_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="El documento del contrato ya no existe")
    content = build_workpaper(build_input(db, analysis, document))
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="papel-trabajo-{analysis_id}.xlsx"'},
    )
