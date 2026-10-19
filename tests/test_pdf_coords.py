"""Pruebas de `app.pdf.coords`: transformaciones puntos PDF <-> píxeles,
normalización de bboxes con orden invertido y recorte a límites de página.
"""
from __future__ import annotations

import pytest

from app.pdf.coords import (
    BBoxPixels,
    BBoxPoints,
    dpi_scale,
    normalize_bbox,
    pdf_to_pixels,
    pixels_to_pdf,
)


@pytest.mark.parametrize("dpi", [72, 150, 300])
def test_pdf_pixels_roundtrip(dpi):
    bbox = BBoxPoints(x0=10.5, y0=20.25, x1=200.75, y1=300.0)
    pixels = pdf_to_pixels(bbox, dpi)
    back = pixels_to_pdf(pixels, dpi)
    assert back.x0 == pytest.approx(bbox.x0)
    assert back.y0 == pytest.approx(bbox.y0)
    assert back.x1 == pytest.approx(bbox.x1)
    assert back.y1 == pytest.approx(bbox.y1)


def test_dpi_scale_72_is_identity():
    assert dpi_scale(72) == pytest.approx(1.0)


def test_pdf_to_pixels_scales_up_with_higher_dpi():
    bbox = BBoxPoints(x0=0, y0=0, x1=100, y1=100)
    px_72 = pdf_to_pixels(bbox, 72)
    px_300 = pdf_to_pixels(bbox, 300)
    assert px_300.x1 > px_72.x1
    assert px_300.y1 > px_72.y1


def test_pixels_to_pdf_raises_for_non_positive_dpi():
    px = BBoxPixels(x0=0, y0=0, x1=10, y1=10)
    with pytest.raises(ValueError):
        pixels_to_pdf(px, 0)
    with pytest.raises(ValueError):
        pixels_to_pdf(px, -10)


def test_normalize_bbox_fixes_x_order():
    b = normalize_bbox(100, 10, 20, 50)
    assert (b.x0, b.x1) == (20, 100)
    assert (b.y0, b.y1) == (10, 50)


def test_normalize_bbox_fixes_y_order():
    b = normalize_bbox(10, 100, 50, 20)
    assert (b.y0, b.y1) == (20, 100)
    assert (b.x0, b.x1) == (10, 50)


def test_normalize_bbox_fixes_both_axes():
    b = normalize_bbox(100, 200, 10, 20)
    assert (b.x0, b.y0, b.x1, b.y1) == (10, 20, 100, 200)


def test_normalize_bbox_already_ordered_is_noop():
    b = normalize_bbox(1, 2, 3, 4)
    assert (b.x0, b.y0, b.x1, b.y1) == (1, 2, 3, 4)


def test_clamp_partially_outside_page():
    bbox = BBoxPoints(x0=-10, y0=-5, x1=50, y1=60)
    clamped = bbox.clamp(page_width=100, page_height=100)
    assert (clamped.x0, clamped.y0, clamped.x1, clamped.y1) == (0, 0, 50, 60)


def test_clamp_totally_outside_page():
    bbox = BBoxPoints(x0=200, y0=300, x1=250, y1=350)
    clamped = bbox.clamp(page_width=100, page_height=100)
    assert (clamped.x0, clamped.y0, clamped.x1, clamped.y1) == (100, 100, 100, 100)


def test_clamp_negative_bbox_clips_to_zero():
    bbox = BBoxPoints(x0=-50, y0=-50, x1=-10, y1=-10)
    clamped = bbox.clamp(page_width=100, page_height=100)
    assert (clamped.x0, clamped.y0, clamped.x1, clamped.y1) == (0, 0, 0, 0)


def test_clamp_bbox_fully_inside_is_unchanged():
    bbox = BBoxPoints(x0=10, y0=10, x1=50, y1=50)
    clamped = bbox.clamp(page_width=100, page_height=100)
    assert (clamped.x0, clamped.y0, clamped.x1, clamped.y1) == (10, 10, 50, 50)
