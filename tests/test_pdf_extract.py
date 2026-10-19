"""Pruebas de `app.pdf.extract`: extracción nativa, detección de página
"escaneada" (sin texto) y degradación limpia cuando no hay OCR disponible,
conteo de páginas y extracción de texto dentro de una bbox.

En este entorno `pytesseract`/`Pillow` no están instalados, por lo que
`app.pdf.ocr.ocr_available()` debe devolver `False`; esa premisa se
confirma explícitamente en `test_ocr_not_available_in_this_environment`
porque el resto de las aserciones sobre `any_scanned_without_ocr` dependen
de ella.
"""
from __future__ import annotations

import fitz
import pytest

from app.pdf.coords import BBoxPoints
from app.pdf.extract import extract_document, extract_text_in_bbox, get_page_count
from app.pdf.ocr import ocr_available
from tests.conftest import (
    BLANK_AREA_BBOX,
    LINE1_TEXT,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    TITLE_TEXT,
)


def test_ocr_not_available_in_this_environment():
    assert ocr_available() is False


def test_get_page_count(demo_pdf_path):
    assert get_page_count(demo_pdf_path) == 2


def test_extract_document_page_count_and_native_page(demo_pdf_path):
    result = extract_document(demo_pdf_path)
    assert result.page_count == 2
    assert len(result.pages) == 2

    page1 = result.pages[0]
    assert page1.page == 1
    assert page1.is_scanned is False
    assert page1.ocr_used is False
    assert page1.width == pytest.approx(PAGE_WIDTH)
    assert page1.height == pytest.approx(PAGE_HEIGHT)

    full_text = page1.full_text
    assert full_text.strip() != ""
    assert "Clausula" in full_text
    assert "personales" in full_text

    assert len(page1.blocks) >= 3
    for block in page1.blocks:
        assert block.source == "native"
        assert 0.0 <= block.bbox.x0 <= PAGE_WIDTH
        assert 0.0 <= block.bbox.x1 <= PAGE_WIDTH
        assert 0.0 <= block.bbox.y0 <= PAGE_HEIGHT
        assert 0.0 <= block.bbox.y1 <= PAGE_HEIGHT
        assert block.bbox.x0 <= block.bbox.x1
        assert block.bbox.y0 <= block.bbox.y1


def test_extract_document_scanned_page_without_ocr(demo_pdf_path):
    result = extract_document(demo_pdf_path)
    page2 = result.pages[1]
    assert page2.page == 2
    assert page2.is_scanned is True
    assert page2.ocr_used is False
    assert page2.blocks == []
    assert page2.full_text == ""

    # Dado que en este entorno no hay OCR disponible, la página escaneada
    # debe propagar el flag a nivel de documento.
    assert result.any_scanned_without_ocr is True


def test_extract_text_in_bbox_returns_inserted_text(demo_pdf_path):
    doc = fitz.open(demo_pdf_path)
    try:
        rects = doc[0].search_for(LINE1_TEXT)
        assert rects, "el texto de fixture debería ser localizable con search_for"
        rect = rects[0]
    finally:
        doc.close()

    # Pequeño margen alrededor del rect real detectado por PyMuPDF.
    bbox = BBoxPoints(x0=rect.x0 - 2, y0=rect.y0 - 2, x1=rect.x1 + 2, y1=rect.y1 + 2)
    text = extract_text_in_bbox(demo_pdf_path, 1, bbox)
    assert "no podra subcontratar" in text
    assert "tratamiento de datos personales" in text


def test_extract_text_in_bbox_title_only(demo_pdf_path):
    doc = fitz.open(demo_pdf_path)
    try:
        rect = doc[0].search_for(TITLE_TEXT)[0]
    finally:
        doc.close()
    bbox = BBoxPoints(x0=rect.x0 - 2, y0=rect.y0 - 2, x1=rect.x1 + 2, y1=rect.y1 + 2)
    text = extract_text_in_bbox(demo_pdf_path, 1, bbox)
    assert "Clausula 5" in text
    # No debe filtrarse texto de las líneas de cuerpo, que están más abajo.
    assert "subcontratar" not in text


def test_extract_text_in_bbox_blank_area_returns_empty(demo_pdf_path):
    x0, y0, x1, y1 = BLANK_AREA_BBOX
    bbox = BBoxPoints(x0=x0, y0=y0, x1=x1, y1=y1)
    text = extract_text_in_bbox(demo_pdf_path, 1, bbox)
    assert text == ""


def test_extract_text_in_bbox_out_of_range_page_returns_empty(demo_pdf_path):
    bbox = BBoxPoints(x0=0, y0=0, x1=100, y1=100)
    assert extract_text_in_bbox(demo_pdf_path, 0, bbox) == ""
    assert extract_text_in_bbox(demo_pdf_path, 99, bbox) == ""
