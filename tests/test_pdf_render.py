"""Pruebas de `app.pdf.render`: renderizado de página a PNG y dimensiones
de página."""
from __future__ import annotations

import pytest

from app.pdf.render import get_page_size, render_page_png
from tests.conftest import PAGE_HEIGHT, PAGE_WIDTH

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_render_page_png_returns_valid_png_signature(demo_pdf_path):
    data = render_page_png(demo_pdf_path, 1, dpi=150)
    assert isinstance(data, bytes)
    assert data[:8] == PNG_SIGNATURE


def test_render_page_png_scanned_page_also_renders(demo_pdf_path):
    # La página 2 no tiene texto, pero sigue siendo una página PDF válida
    # renderizable a imagen.
    data = render_page_png(demo_pdf_path, 2, dpi=150)
    assert data[:8] == PNG_SIGNATURE


def test_render_page_png_higher_dpi_yields_larger_bytes(demo_pdf_path):
    low_dpi = render_page_png(demo_pdf_path, 1, dpi=72)
    high_dpi = render_page_png(demo_pdf_path, 1, dpi=300)
    assert len(high_dpi) > len(low_dpi)


def test_render_page_png_out_of_range_raises(demo_pdf_path):
    with pytest.raises(ValueError):
        render_page_png(demo_pdf_path, 0)
    with pytest.raises(ValueError):
        render_page_png(demo_pdf_path, 99)


def test_get_page_size_matches_fixture(demo_pdf_path):
    width, height = get_page_size(demo_pdf_path, 1)
    assert width == pytest.approx(PAGE_WIDTH)
    assert height == pytest.approx(PAGE_HEIGHT)
    assert width > 0
    assert height > 0


def test_get_page_size_out_of_range_raises(demo_pdf_path):
    with pytest.raises(ValueError):
        get_page_size(demo_pdf_path, 0)
    with pytest.raises(ValueError):
        get_page_size(demo_pdf_path, 99)
