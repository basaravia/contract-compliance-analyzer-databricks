"""Extracción de texto de PDFs con PyMuPDF (extracción nativa primero).

Para páginas sin texto extraíble (probablemente escaneadas), se intenta un
fallback opcional de OCR (ver `app.pdf.ocr`). Si el OCR no está disponible
(dependencias no instaladas), la página se marca como `scanned_no_ocr` y
las reglas que dependan de ella deben degradar a `no_determinable`, nunca
inventar texto o coordenadas.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import fitz  # PyMuPDF

from app.pdf.ocr import ocr_available, ocr_page_text
from app.pdf.coords import BBoxPoints

MIN_CHARS_FOR_NATIVE_TEXT = 20


@dataclass
class TextBlock:
    page: int  # 1-indexed
    text: str
    bbox: BBoxPoints
    source: str = "native"  # native | ocr


@dataclass
class PageExtraction:
    page: int
    width: float
    height: float
    blocks: list[TextBlock] = field(default_factory=list)
    is_scanned: bool = False
    ocr_used: bool = False

    @property
    def full_text(self) -> str:
        return "\n".join(b.text for b in self.blocks if b.text.strip())


@dataclass
class DocumentExtraction:
    page_count: int
    pages: list[PageExtraction]
    any_scanned_without_ocr: bool


def extract_document(pdf_path: str) -> DocumentExtraction:
    doc = fitz.open(pdf_path)
    try:
        pages: list[PageExtraction] = []
        any_scanned_without_ocr = False
        for i in range(doc.page_count):
            page = doc.load_page(i)
            page_num = i + 1
            rect = page.rect
            page_data = PageExtraction(page=page_num, width=rect.width, height=rect.height)

            raw = page.get_text("dict")
            native_chars = 0
            for block in raw.get("blocks", []):
                if block.get("type") != 0:  # 0 = texto, 1 = imagen
                    continue
                for line in block.get("lines", []):
                    line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                    if not line_text.strip():
                        continue
                    bx0, by0, bx1, by1 = line["bbox"]
                    page_data.blocks.append(
                        TextBlock(page=page_num, text=line_text, bbox=BBoxPoints(bx0, by0, bx1, by1))
                    )
                    native_chars += len(line_text)

            if native_chars < MIN_CHARS_FOR_NATIVE_TEXT:
                page_data.is_scanned = True
                if ocr_available():
                    ocr_blocks = ocr_page_text(page, dpi=200)
                    if ocr_blocks:
                        page_data.blocks = ocr_blocks
                        page_data.ocr_used = True
                    else:
                        any_scanned_without_ocr = True
                else:
                    any_scanned_without_ocr = True

            pages.append(page_data)

        return DocumentExtraction(
            page_count=doc.page_count,
            pages=pages,
            any_scanned_without_ocr=any_scanned_without_ocr,
        )
    finally:
        doc.close()


def get_page_count(pdf_path: str) -> int:
    doc = fitz.open(pdf_path)
    try:
        return doc.page_count
    finally:
        doc.close()


def extract_text_in_bbox(pdf_path: str, page_number: int, bbox: BBoxPoints) -> str:
    """Extrae el texto nativo contenido en una bbox (puntos PDF) de una página.
    Usado para recalcular evidencia tras una corrección manual del bbox."""
    doc = fitz.open(pdf_path)
    try:
        if page_number < 1 or page_number > doc.page_count:
            return ""
        page = doc.load_page(page_number - 1)
        clip = fitz.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
        text = page.get_text("text", clip=clip)
        return text.strip()
    finally:
        doc.close()
