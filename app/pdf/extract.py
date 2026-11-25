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
HEADER_FRACTION = 0.05  # franja superior/inferior de la página donde viven encabezados, pies y sellos
SIDE_FRACTION = 0.10
OVERLAP_FRACTION = 0.4  # una línea cubierta en más de este % por otra se considera texto sobrepuesto


@dataclass
class TextBlock:
    page: int  # 1-indexed
    text: str
    bbox: BBoxPoints
    source: str = "native"  # native | ocr | annot
    # Zona lógica de la línea: body (cuerpo) | header | footer | side (lateral/rotado) | stamp (sello, firma o texto
    # sobrepuesto). Solo `body` forma las cláusulas; el resto se agrupa aparte para no mezclarse con ellas.
    kind: str = "body"


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
                    dx, dy = line.get("dir", (1.0, 0.0))
                    rotated = abs(dy) > 0.3 or dx < 0.7
                    page_data.blocks.append(
                        TextBlock(
                            page=page_num,
                            text=line_text,
                            bbox=BBoxPoints(bx0, by0, bx1, by1),
                            kind="side" if rotated else "body",
                        )
                    )
                    native_chars += len(line_text)

            _add_annotation_text(page, page_data)
            if not page_data.is_scanned:
                classify_blocks(page_data)

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


def _norm(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _add_annotation_text(page, page_data: PageExtraction) -> None:
    """Rescata el texto de anotaciones (sellos de texto, firmas, campos) que algunos lectores no devuelven con el
    texto de la página. Solo añade lo que todavía no está extraído, para no duplicar."""
    present = _norm(" ".join(b.text for b in page_data.blocks))
    found: list[tuple[str, tuple[float, float, float, float]]] = []
    rects: list[BBoxPoints] = []
    try:
        for annot in page.annots() or []:
            if annot.type[1] in ("FreeText", "Stamp"):
                r = annot.rect
                rects.append(BBoxPoints(r.x0, r.y0, r.x1, r.y1))
                content = (annot.info or {}).get("content", "") or ""
                if content.strip():
                    found.append((content, (r.x0, r.y0, r.x1, r.y1)))
        for widget in page.widgets() or []:
            r = widget.rect
            rects.append(BBoxPoints(r.x0, r.y0, r.x1, r.y1))
            value = widget.field_value
            if isinstance(value, str) and value.strip():
                found.append((value, (r.x0, r.y0, r.x1, r.y1)))
    except Exception:  # noqa: BLE001 - un PDF con anotaciones rotas no debe impedir leer el texto principal
        return
    # Algunos lectores ya devuelven el texto de la anotación junto al de la página: se reconoce por su posición
    # (la línea cae dentro del recuadro de un sello, firma o campo) y se separa del cuerpo.
    for b in page_data.blocks:
        area = _area(b.bbox)
        if area > 0 and any(_intersection(b.bbox, r) / area > 0.5 for r in rects):
            b.kind = "stamp"
    for text, (x0, y0, x1, y1) in found:
        key = _norm(text)
        if key and key not in present:
            page_data.blocks.append(
                TextBlock(page=page_data.page, text=text.strip(), bbox=BBoxPoints(x0, y0, x1, y1), source="annot", kind="stamp")
            )
            present += key


def _area(b: BBoxPoints) -> float:
    return max(0.0, b.x1 - b.x0) * max(0.0, b.y1 - b.y0)


def _intersection(a: BBoxPoints, b: BBoxPoints) -> float:
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return w * h if w > 0 and h > 0 else 0.0


def classify_blocks(page: PageExtraction) -> None:
    """Asigna a cada línea su zona lógica (`kind`) sin perder texto: encabezado, pie, lateral, o sello/sobrepuesto.
    Las firmas y estampas digitales suelen caer en bordes, rotadas o encima del cuerpo: separarlas evita que
    se mezclen con la cláusula vecina y permite analizarlas por sí solas."""
    h, w = page.height or 1.0, page.width or 1.0
    body = [b for b in page.blocks if b.kind == "body"]
    for b in page.blocks:
        cy, cx = (b.bbox.y0 + b.bbox.y1) / 2, (b.bbox.x0 + b.bbox.x1) / 2
        if b.kind == "side":
            b.kind = "side" if (cx < SIDE_FRACTION * w or cx > (1 - SIDE_FRACTION) * w) else "stamp"
        elif b.kind == "body":
            if cy < HEADER_FRACTION * h:
                b.kind = "header"
            elif cy > (1 - HEADER_FRACTION) * h:
                b.kind = "footer"
    # Texto encima de otro texto (firma sobre una línea, sello sobre el cuerpo): la línea más corta es la sobrepuesta.
    for i, a in enumerate(body):
        if a.kind != "body":
            continue
        for c in body[i + 1 :]:
            if c.kind != "body":
                continue
            inter = _intersection(a.bbox, c.bbox)
            smaller = min(_area(a.bbox), _area(c.bbox))
            if smaller > 0 and inter / smaller > OVERLAP_FRACTION and _norm(a.text) != _norm(c.text):
                (a if len(a.text.strip()) <= len(c.text.strip()) else c).kind = "stamp"


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
