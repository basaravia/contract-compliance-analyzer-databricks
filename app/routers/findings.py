"""Endpoints de edición manual de hallazgos: corrección de bbox/estado,
creación de anotaciones nuevas y recálculo de evidencia tras editar el bbox."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.analysis_engine import recalculate_finding
from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Analysis, Document, Finding, Rule
from app.schemas import FindingCreate, FindingOut, FindingUpdate

router = APIRouter(prefix="/api/findings", tags=["findings"])


def _get_finding_or_404(db: Session, finding_id: str) -> Finding:
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Hallazgo no encontrado")
    return finding


def _get_analysis_and_rule(db: Session, finding: Finding) -> tuple[Analysis, Document, Rule]:
    analysis = db.get(Analysis, finding.analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="El análisis asociado ya no existe")
    document = db.get(Document, analysis.contract_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="El documento del contrato ya no existe")
    rule = db.get(Rule, finding.rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="La regla asociada ya no existe")
    return analysis, document, rule


@router.post("", response_model=FindingOut, status_code=201)
def create_finding(
    payload: FindingCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> Finding:
    analysis = db.get(Analysis, payload.analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")
    rule = db.get(Rule, payload.rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Regla no encontrada")

    document = db.get(Document, analysis.contract_document_id)
    if document is not None and payload.page > document.page_count:
        raise HTTPException(status_code=400, detail="La página indicada excede el número de páginas del documento")

    finding = Finding(
        analysis_id=payload.analysis_id,
        rule_id=payload.rule_id,
        status=payload.status,
        justification=payload.justification,
        page=payload.page,
        bbox_x0=payload.bbox.x0,
        bbox_y0=payload.bbox.y0,
        bbox_x1=payload.bbox.x1,
        bbox_y1=payload.bbox.y1,
        severity=payload.severity,
        is_manual=True,
        normative_refs=[{"citation": r.citation, "page": r.page} for r in rule.references],
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


@router.patch("/{finding_id}", response_model=FindingOut)
def update_finding(
    finding_id: str,
    payload: FindingUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Finding:
    finding = _get_finding_or_404(db, finding_id)

    data = payload.model_dump(exclude_unset=True, exclude={"bbox", "recalculate"})
    for key, value in data.items():
        setattr(finding, key, value)
    if payload.bbox is not None:
        finding.bbox_x0 = payload.bbox.x0
        finding.bbox_y0 = payload.bbox.y0
        finding.bbox_x1 = payload.bbox.x1
        finding.bbox_y1 = payload.bbox.y1

    finding.edited = True

    if payload.recalculate:
        _, document, rule = _get_analysis_and_rule(db, finding)
        recalculate_finding(db, finding, document, rule)
        # Los campos explícitos que envió el usuario prevalecen sobre el recálculo automático.
        if payload.status is not None:
            finding.status = payload.status
        if payload.justification is not None:
            finding.justification = payload.justification

    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


@router.delete("/{finding_id}", status_code=204)
def delete_finding(
    finding_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> None:
    finding = _get_finding_or_404(db, finding_id)
    db.delete(finding)
    db.commit()
