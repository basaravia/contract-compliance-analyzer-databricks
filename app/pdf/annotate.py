"""Generación del PDF anotado de salida: dibuja un rectángulo por cada
hallazgo (finding) sobre la página y color correspondiente, con una nota
emergente (popup) con la justificación. Usa PyMuPDF, que soporta anotaciones
tipo `Rect` nativas del estándar PDF (visibles en cualquier lector).
"""
from __future__ import annotations

from dataclasses import dataclass

import fitz  # PyMuPDF

STATUS_COLORS = {
    "cumple": (0.13, 0.55, 0.13),  # verde
    "no_cumple": (0.80, 0.10, 0.10),  # rojo
    "parcial": (0.85, 0.55, 0.0),  # naranja
    "no_determinable": (0.45, 0.45, 0.45),  # gris
    "requiere_revision": (0.0, 0.35, 0.80),  # azul
}
DEFAULT_COLOR = (0.45, 0.45, 0.45)


@dataclass
class AnnotationSpec:
    page: int  # 1-indexed
    x0: float
    y0: float
    x1: float
    y1: float
    status: str
    label: str
    note: str


def build_annotated_pdf(source_pdf_path: str, annotations: list[AnnotationSpec]) -> bytes:
    doc = fitz.open(source_pdf_path)
    try:
        for spec in annotations:
            if spec.page < 1 or spec.page > doc.page_count:
                continue
            page = doc.load_page(spec.page - 1)
            rect = fitz.Rect(spec.x0, spec.y0, spec.x1, spec.y1)
            if rect.is_empty or rect.is_infinite:
                continue
            color = STATUS_COLORS.get(spec.status, DEFAULT_COLOR)

            annot = page.add_rect_annot(rect)
            annot.set_colors(stroke=color)
            annot.set_border(width=1.5)
            annot.set_opacity(0.9)
            annot.update()

            popup_text = f"[{spec.label}] {spec.status.upper()}\n{spec.note}"
            text_annot = page.add_text_annot(rect.top_left, popup_text)
            text_annot.set_info(title=spec.label, content=popup_text)
            text_annot.update()

        return doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()
