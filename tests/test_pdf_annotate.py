"""Pruebas de `app.pdf.annotate`: generación del PDF anotado a partir de
`AnnotationSpec`, incluyendo páginas fuera de rango y rects vacíos, que
deben ignorarse sin lanzar excepción."""
from __future__ import annotations

import fitz

from app.pdf.annotate import AnnotationSpec, build_annotated_pdf
from app.pdf.extract import get_page_count


def test_build_annotated_pdf_valid_annotation_is_readable(demo_pdf_path):
    spec = AnnotationSpec(
        page=1,
        x0=50,
        y0=90,
        x1=400,
        y1=180,
        status="no_cumple",
        label="Clausula 5",
        note="Justificacion de prueba: el texto contradice la politica.",
    )
    pdf_bytes = build_annotated_pdf(demo_pdf_path, [spec])

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        assert doc.page_count == get_page_count(demo_pdf_path)
        page = doc.load_page(0)
        annots = list(page.annots())
        assert len(annots) >= 1
    finally:
        doc.close()


def test_build_annotated_pdf_multiple_specs_two_pages(demo_pdf_path):
    specs = [
        AnnotationSpec(page=1, x0=50, y0=90, x1=400, y1=180, status="cumple", label="A", note="ok"),
        AnnotationSpec(page=2, x0=50, y0=90, x1=400, y1=180, status="requiere_revision", label="B", note="revisar"),
    ]
    pdf_bytes = build_annotated_pdf(demo_pdf_path, specs)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        assert doc.page_count == 2
        assert len(list(doc.load_page(0).annots())) >= 1
        assert len(list(doc.load_page(1).annots())) >= 1
    finally:
        doc.close()


def test_build_annotated_pdf_out_of_range_page_is_skipped(demo_pdf_path):
    spec_bad = AnnotationSpec(page=99, x0=10, y0=10, x1=50, y1=50, status="cumple", label="x", note="n")
    pdf_bytes = build_annotated_pdf(demo_pdf_path, [spec_bad])

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        assert doc.page_count == get_page_count(demo_pdf_path)
        for page in doc:
            assert list(page.annots()) == []
    finally:
        doc.close()


def test_build_annotated_pdf_empty_rect_is_skipped(demo_pdf_path):
    spec_empty = AnnotationSpec(page=1, x0=100, y0=100, x1=100, y1=200, status="cumple", label="x", note="n")
    pdf_bytes = build_annotated_pdf(demo_pdf_path, [spec_empty])

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc.load_page(0)
        assert list(page.annots()) == []
    finally:
        doc.close()


def test_build_annotated_pdf_empty_annotation_list_still_generates_pdf(demo_pdf_path):
    pdf_bytes = build_annotated_pdf(demo_pdf_path, [])
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        assert doc.page_count == get_page_count(demo_pdf_path)
    finally:
        doc.close()
