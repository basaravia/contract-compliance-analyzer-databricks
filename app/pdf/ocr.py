"""Fallback OCR opcional para páginas escaneadas.

Este módulo NUNCA hace que el arranque de la aplicación dependa de pesos
grandes ni de dependencias pesadas: si `pytesseract`/`Pillow`/el binario
`tesseract` no están instalados, `ocr_available()` devuelve False y el
resto del sistema degrada limpiamente a `scanned_no_ocr`.

Para habilitarlo: instalar `pytesseract` + `Pillow` (requirements.txt) y el
paquete de sistema `tesseract-ocr` con datos de idioma español (`spa`).
"""
from __future__ import annotations

from functools import lru_cache

from app.pdf.coords import BBoxPoints


@lru_cache(maxsize=1)
def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return False
    return True


def ocr_page_text(page, dpi: int = 200) -> list:
    """Ejecuta OCR sobre una página de PyMuPDF y devuelve TextBlocks con
    bboxes en puntos PDF. Import perezoso para no requerir las dependencias
    cuando OCR no se usa."""
    from app.pdf.extract import TextBlock  # import perezoso, evita ciclo

    if not ocr_available():
        return []

    import io

    import pytesseract
    from PIL import Image

    scale = dpi / 72.0
    matrix = _matrix(scale)
    pix = page.get_pixmap(matrix=matrix)
    img = Image.open(io.BytesIO(pix.tobytes("png")))

    data = pytesseract.image_to_data(img, lang="spa+eng", output_type=pytesseract.Output.DICT)

    blocks = []
    n = len(data.get("text", []))
    for i in range(n):
        text = data["text"][i].strip()
        if not text:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        bbox = BBoxPoints(x0=x / scale, y0=y / scale, x1=(x + w) / scale, y1=(y + h) / scale)
        blocks.append(TextBlock(page=page.number + 1, text=text, bbox=bbox, source="ocr"))
    return blocks


def _matrix(scale: float):
    import fitz

    return fitz.Matrix(scale, scale)
