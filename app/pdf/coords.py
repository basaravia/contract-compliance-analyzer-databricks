"""Transformaciones de coordenadas entre puntos PDF y píxeles de imagen.

Convención interna (y la de PyMuPDF/fitz): el origen de la página está en la
esquina superior izquierda, con el eje Y creciendo hacia abajo, en puntos
(1 punto = 1/72 pulgada). Todas las bboxes se almacenan en la base de datos
en puntos PDF, independientemente del DPI usado para renderizar la imagen
que ve el usuario en el frontend.

El frontend siempre debe indicar el DPI usado para pintar la página cuando
envía coordenadas de píxeles, de modo que el backend pueda convertirlas de
vuelta a puntos PDF de forma exacta.
"""
from __future__ import annotations

from dataclasses import dataclass

POINTS_PER_INCH = 72.0


@dataclass(frozen=True)
class BBoxPoints:
    x0: float
    y0: float
    x1: float
    y1: float

    def clamp(self, page_width: float, page_height: float) -> "BBoxPoints":
        return BBoxPoints(
            x0=max(0.0, min(self.x0, page_width)),
            y0=max(0.0, min(self.y0, page_height)),
            x1=max(0.0, min(self.x1, page_width)),
            y1=max(0.0, min(self.y1, page_height)),
        )

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


@dataclass(frozen=True)
class BBoxPixels:
    x0: float
    y0: float
    x1: float
    y1: float


def dpi_scale(dpi: float) -> float:
    """Factor de escala de puntos PDF a píxeles para un DPI dado."""
    return dpi / POINTS_PER_INCH


def pdf_to_pixels(bbox: BBoxPoints, dpi: float) -> BBoxPixels:
    scale = dpi_scale(dpi)
    return BBoxPixels(
        x0=bbox.x0 * scale,
        y0=bbox.y0 * scale,
        x1=bbox.x1 * scale,
        y1=bbox.y1 * scale,
    )


def pixels_to_pdf(bbox: BBoxPixels, dpi: float) -> BBoxPoints:
    scale = dpi_scale(dpi)
    if scale <= 0:
        raise ValueError("dpi debe ser positivo")
    return BBoxPoints(
        x0=bbox.x0 / scale,
        y0=bbox.y0 / scale,
        x1=bbox.x1 / scale,
        y1=bbox.y1 / scale,
    )


def normalize_bbox(x0: float, y0: float, x1: float, y1: float) -> BBoxPoints:
    """Garantiza x0<=x1 y y0<=y1 sin importar el orden de arrastre del usuario."""
    return BBoxPoints(
        x0=min(x0, x1),
        y0=min(y0, y1),
        x1=max(x0, x1),
        y1=max(y0, y1),
    )
