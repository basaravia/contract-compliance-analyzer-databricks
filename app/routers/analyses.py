"""Endpoints de análisis: ejecución en segundo plano con progreso consultable,
consulta y exportación del PDF anotado."""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session, sessionmaker

from app import progress
from app.analysis_engine import run_analysis
from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Analysis, AnalysisStatus, Document, DocumentType, Finding, Rule
from app.output.assemble import build_input
from app.output.workpaper import build_workpaper
from app.pdf.annotate import AnnotationSpec, build_annotated_pdf
from app.schemas import AnalysisCreate, AnalysisDetailOut, AnalysisOut, AnalysisProgressOut, FindingOut
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


def _spawn(target) -> None:
    """Lanza el análisis en un hilo propio: la petición responde al instante y el navegador sigue el progreso.
    Las pruebas lo sustituyen por una llamada directa."""
    threading.Thread(target=target, name="analisis", daemon=True).start()


@router.post("", response_model=AnalysisOut, status_code=202)
def create_analysis(
    payload: AnalysisCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> Analysis:
    if not _analysis_slot.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Ya hay un análisis en curso. Espera a que termine e inténtalo de nuevo.")
    try:
        analysis = _create_analysis(payload, db, user)
    except BaseException:
        _analysis_slot.release()
        raise
    # El hilo abre su propia sesión sobre el mismo motor que la petición (en pruebas, la BD temporal).
    session_factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)
    progress.start(analysis.id, total=len(analysis.rule_ids))
    _spawn(lambda: _run_in_background(analysis.id, session_factory))
    db.refresh(analysis)
    return analysis


def _create_analysis(payload: AnalysisCreate, db: Session, user: CurrentUser) -> Analysis:
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
    return analysis


def _run_in_background(analysis_id: str, session_factory: sessionmaker) -> None:
    db = session_factory()
    try:
        analysis = db.get(Analysis, analysis_id)
        document = db.get(Document, analysis.contract_document_id)
        by_id = {r.id: r for r in db.query(Rule).filter(Rule.id.in_(analysis.rule_ids)).all()}
        rules = [by_id[rid] for rid in analysis.rule_ids if rid in by_id]
        try:
            run_analysis(db, analysis, document, rules, report=lambda **kw: progress.report(analysis_id, **kw))
            analysis.status = AnalysisStatus.done.value
        except Exception:  # noqa: BLE001
            # El detalle (rutas, trazas) va al log del servidor, no al cliente.
            logger.exception("Falló el análisis %s", analysis_id)
            db.rollback()
            analysis = db.get(Analysis, analysis_id)
            analysis.status = AnalysisStatus.failed.value
            analysis.error_message = "El análisis falló por un error interno. Revisa el registro del servidor."
        analysis.finished_at = datetime.utcnow()
        db.commit()
    except Exception:  # noqa: BLE001 - ni siquiera se pudo marcar el fallo: queda en el log
        logger.exception("No se pudo cerrar el análisis %s", analysis_id)
    finally:
        db.close()
        progress.finish(analysis_id)
        _analysis_slot.release()


@router.get("/{analysis_id}/progress", response_model=AnalysisProgressOut)
def get_analysis_progress(
    analysis_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> AnalysisProgressOut:
    analysis = _get_analysis_or_404(db, analysis_id)
    live = progress.snapshot(analysis_id) if analysis.status == AnalysisStatus.running.value else None
    status = analysis.status
    if status == AnalysisStatus.running.value and live is None:
        # La app se reinició a mitad de análisis: el hilo ya no existe y no va a terminar.
        status = "interrupted"
    return AnalysisProgressOut(status=status, error_message=analysis.error_message, live=live)


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
        for extra in f.extra_regions or []:  # la cláusula sigue en otra página: se marca también ahí
            specs.append(
                AnnotationSpec(
                    page=extra["page"], x0=extra["x0"], y0=extra["y0"], x1=extra["x1"], y1=extra["y1"],
                    status=f.status, label=f"{label} (continuación)", note=f.justification,
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
