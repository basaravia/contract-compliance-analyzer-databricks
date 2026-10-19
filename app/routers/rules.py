"""Endpoints CRUD de reglas de cumplimiento, con importación masiva en
formato JSON o texto en lenguaje natural."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Rule, RuleReference
from app.rules.parser import parse_natural_language_rules
from app.schemas import RuleCreate, RuleImportPayload, RuleOut, RuleUpdate

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _get_rule_or_404(db: Session, rule_id: str) -> Rule:
    rule = (
        db.query(Rule)
        .options(selectinload(Rule.references))
        .filter(Rule.id == rule_id)
        .first()
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Regla no encontrada")
    return rule


def _create_rule(db: Session, payload: RuleCreate, created_by: str) -> Rule:
    rule = Rule(
        name=payload.name,
        description=payload.description,
        jurisdiction=payload.jurisdiction,
        category=payload.category,
        severity=payload.severity,
        active=payload.active,
        created_by=created_by,
    )
    for ref in payload.references:
        rule.references.append(
            RuleReference(
                normative_document_id=ref.normative_document_id,
                citation=ref.citation,
                page=ref.page,
            )
        )
    db.add(rule)
    return rule


@router.post("", response_model=RuleOut, status_code=201)
def create_rule(
    payload: RuleCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> Rule:
    rule = _create_rule(db, payload, user.email)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("", response_model=list[RuleOut])
def list_rules(
    active_only: bool = False, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> list[Rule]:
    query = db.query(Rule).options(selectinload(Rule.references))
    if active_only:
        query = query.filter(Rule.active.is_(True))
    return query.order_by(Rule.created_at.desc()).all()


@router.get("/{rule_id}", response_model=RuleOut)
def get_rule(rule_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> Rule:
    return _get_rule_or_404(db, rule_id)


@router.put("/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: str, payload: RuleUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> Rule:
    rule = _get_rule_or_404(db, rule_id)
    data = payload.model_dump(exclude_unset=True, exclude={"references"})
    for key, value in data.items():
        setattr(rule, key, value)
    if payload.references is not None:
        rule.references.clear()
        for ref in payload.references:
            rule.references.append(
                RuleReference(
                    normative_document_id=ref.normative_document_id,
                    citation=ref.citation,
                    page=ref.page,
                )
            )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> None:
    rule = _get_rule_or_404(db, rule_id)
    db.delete(rule)
    db.commit()


@router.post("/import", response_model=list[RuleOut], status_code=201)
def import_rules_json(
    payload: RuleImportPayload, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> list[Rule]:
    created = [_create_rule(db, r, user.email) for r in payload.rules]
    db.commit()
    for rule in created:
        db.refresh(rule)
    return created


@router.post("/import-text", response_model=list[RuleOut], status_code=201)
def import_rules_text(
    text: str = Body(..., embed=True, max_length=200_000),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[Rule]:
    parsed = parse_natural_language_rules(text)
    if parsed.errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "El texto contiene bloques de regla con errores de formato",
                "errors": [{"bloque": e.block_index, "error": e.message} for e in parsed.errors],
            },
        )
    if not parsed.rules:
        raise HTTPException(status_code=422, detail="No se encontró ninguna regla válida en el texto")

    created = [_create_rule(db, r, user.email) for r in parsed.rules]
    db.commit()
    for rule in created:
        db.refresh(rule)
    return created
