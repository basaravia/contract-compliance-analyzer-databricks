"""Endpoints de gestión de documentos (normativas y contratos)."""
from __future__ import annotations

from typing import Literal

from fastapi.concurrency import run_in_threadpool
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.analysis_engine import extract_and_update_document
from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.db import get_db
from app.models import Analysis, Document
from app.pdf.extract import get_page_count
from app.pdf.render import render_page_png
from app.schemas import DocumentOut
from app import storage
from app.security import resolve_upload_path, upload_target_path, validate_and_store_pdf

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get_document_or_404(db: Session, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return doc


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    doc_type: Literal["normativa", "contrato"] = Form(...),
    title: str | None = Form(default=None),
    jurisdiction: str = Form(default=settings.default_jurisdiction),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Document:
    stored_name, original_name, size = await validate_and_store_pdf(file)
    path = upload_target_path(stored_name)

    try:
        page_count = await run_in_threadpool(get_page_count, str(path))
    except Exception as e:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="El PDF está corrupto o no se pudo leer") from e

    try:
        await run_in_threadpool(storage.push, stored_name, path)
    except Exception as e:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail="No se pudo guardar el documento en el almacenamiento") from e

    document = Document(
        doc_type=doc_type,
        original_filename=original_name,
        stored_filename=stored_name,
        title=(title or original_name).strip()[:200] or original_name,
        jurisdiction=(jurisdiction or settings.default_jurisdiction)[:10],
        page_count=page_count,
        uploaded_by=user.email,
        file_size_bytes=size,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        # En un hilo: PyMuPDF sobre un PDF grande no debe congelar el login ni /healthz (1 solo worker).
        await run_in_threadpool(extract_and_update_document, db, document)
    except Exception:
        # La subida es válida aunque la extracción falle; el estado queda
        # reflejado en `extraction_status` para que el usuario lo vea.
        document.extraction_status = "failed"
        db.add(document)
        db.commit()
        db.refresh(document)

    return document


@router.get("", response_model=list[DocumentOut])
def list_documents(
    doc_type: Literal["normativa", "contrato"] | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[Document]:
    query = db.query(Document)
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    return query.order_by(Document.uploaded_at.desc()).all()


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> Document:
    return _get_document_or_404(db, document_id)


@router.get("/{document_id}/pages/{page_number}.png")
def get_page_png(
    document_id: str,
    page_number: int,
    dpi: int = Query(default=150, ge=50, le=400),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    document = _get_document_or_404(db, document_id)
    path = resolve_upload_path(document.stored_filename)
    try:
        png_bytes = render_page_png(str(path), page_number, dpi=dpi)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Número de página fuera de rango") from e
    return Response(content=png_bytes, media_type="image/png")


@router.delete("/{document_id}", status_code=204, response_model=None)
def delete_document(
    document_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> Response:
    document = _get_document_or_404(db, document_id)
    in_use = db.query(Analysis).filter(Analysis.contract_document_id == document_id).first()
    if in_use is not None:
        raise HTTPException(status_code=409, detail="No se puede eliminar: el documento tiene análisis asociados")

    path = upload_target_path(document.stored_filename)
    db.delete(document)
    db.commit()
    path.unlink(missing_ok=True)
    storage.remove(document.stored_filename)
    return Response(status_code=204, response_model=None)
