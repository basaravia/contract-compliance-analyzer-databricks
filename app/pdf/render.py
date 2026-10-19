"""Renderizado de páginas PDF a imágenes PNG.

Decisión de diseño: en vez de depender de PDF.js (requiere cargar una
librería JS externa, típicamente vía CDN, y complica el offline), el MVP
renderiza cada página a PNG en el servidor con PyMuPDF y el frontend
superpone un <canvas> con las bboxes editables sobre esa imagen. Esto es
funcional (permite mover/redimensionar/crear/eliminar anotaciones) y
funciona completamente offline. PDF.js queda documentado como alternativa
futura si se requiere renderizado 100% client-side.
"""
from __future__ import annotations

import fitz  # PyMuPDF

DEFAULT_DPI = 150


def render_page_png(pdf_path: str, page_number: int, dpi: int = DEFAULT_DPI) -> bytes:
    """Renderiza una página (1-indexed) a PNG en el DPI solicitado."""
    doc = fitz.open(pdf_path)
    try:
        if page_number < 1 or page_number > doc.page_count:
            raise ValueError(f"Número de página fuera de rango: {page_number}")
        page = doc.load_page(page_number - 1)
        scale = dpi / 72.0
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix)
        return pix.tobytes("png")
    finally:
        doc.close()


def get_page_size(pdf_path: str, page_number: int) -> tuple[float, float]:
    doc = fitz.open(pdf_path)
    try:
        if page_number < 1 or page_number > doc.page_count:
            raise ValueError(f"Número de página fuera de rango: {page_number}")
        rect = doc.load_page(page_number - 1).rect
        return rect.width, rect.height
    finally:
        doc.close()
