"""Utilidades de seguridad para carga de archivos: saneado de nombres,
validación de tipo/tamaño y prevención de path traversal.

Ningún archivo subido se ejecuta como código: los PDF solo se leen con
PyMuPDF (parser de datos, no un intérprete) y se almacenan con un nombre
generado por el servidor (uuid), nunca con el nombre original del cliente.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
PDF_MAGIC = b"%PDF-"


def sanitize_filename(filename: str) -> str:
    """Elimina cualquier componente de ruta y caracteres no seguros.

    Nunca se usa el resultado como nombre de almacenamiento (se usa un uuid),
    solo se conserva como metadato legible para el usuario.
    """
    name = Path(filename or "documento.pdf").name  # descarta cualquier ruta
    name = _SAFE_NAME_RE.sub("_", name)
    if not name or name in {".", ".."}:
        name = "documento.pdf"
    return name[:200]


def new_stored_filename(original_filename: str) -> str:
    ext = Path(sanitize_filename(original_filename)).suffix.lower()
    if ext != ".pdf":
        ext = ".pdf"
    return f"{uuid.uuid4().hex}{ext}"


def upload_target_path(stored_filename: str) -> Path:
    """Ruta local de un nombre de archivo almacenado, rechazando cualquier intento de escapar de UPLOAD_DIR
    (path traversal). No toca el disco ni el Volume: sirve para escribir y para borrar."""
    base = Path(settings.upload_dir).resolve()
    candidate = (base / stored_filename).resolve()
    if base not in candidate.parents and candidate != base:
        raise HTTPException(status_code=400, detail="Ruta de archivo inválida")
    return candidate


def resolve_upload_path(stored_filename: str) -> Path:
    """Ruta local de un PDF ya subido, para LEERLO. El disco local es una caché: si el archivo no está
    (contenedor reiniciado) se recupera del Volume de Unity Catalog antes de devolver la ruta."""
    from app import storage

    path = upload_target_path(stored_filename)
    storage.ensure_local(stored_filename, path)
    return path


async def validate_and_store_pdf(upload: UploadFile) -> tuple[str, str, int]:
    """Valida tipo, cabecera mágica y tamaño; guarda el archivo con nombre
    generado por el servidor. Devuelve (stored_filename, original_filename_sano, size_bytes)."""
    original_name = sanitize_filename(upload.filename or "documento.pdf")

    if not original_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF (.pdf)")

    content_type = (upload.content_type or "").lower()
    if content_type and content_type not in {"application/pdf", "application/x-pdf", "binary/octet-stream"}:
        raise HTTPException(status_code=400, detail="Tipo de contenido no permitido, se esperaba application/pdf")

    max_bytes = settings.max_upload_bytes
    stored_name = new_stored_filename(original_name)
    dest = upload_target_path(stored_name)

    size = 0
    header_checked = False
    chunk_size = 1024 * 1024
    try:
        with open(dest, "wb") as f:
            while True:
                chunk = await upload.read(chunk_size)
                if not chunk:
                    break
                if not header_checked:
                    if not chunk.startswith(PDF_MAGIC):
                        raise HTTPException(status_code=400, detail="El archivo no es un PDF válido")
                    header_checked = True
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"El archivo excede el tamaño máximo permitido ({settings.max_upload_mb} MB)",
                    )
                f.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="No se pudo procesar el archivo subido")

    if size == 0 or not header_checked:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="El archivo está vacío o no es un PDF válido")

    return stored_name, original_name, size
