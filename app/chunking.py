"""Fragmentación (chunking) del texto extraído de un PDF en unidades del
tamaño adecuado para recuperación por embeddings, preservando la bbox de
cada fragmento (unión de las bboxes de línea que lo componen) para poder
resaltarlo en el PDF de salida."""
from __future__ import annotations

from dataclasses import dataclass

from app.pdf.coords import BBoxPoints
from app.pdf.extract import DocumentExtraction, PageExtraction, TextBlock

MAX_CHUNK_CHARS = 800
LINE_GAP_THRESHOLD = 14.0  # puntos PDF: salto de párrafo si el hueco vertical lo supera


@dataclass
class Chunk:
    chunk_id: str
    page: int
    text: str
    bbox: BBoxPoints


def _union_bbox(blocks: list[TextBlock]) -> BBoxPoints:
    return BBoxPoints(
        x0=min(b.bbox.x0 for b in blocks),
        y0=min(b.bbox.y0 for b in blocks),
        x1=max(b.bbox.x1 for b in blocks),
        y1=max(b.bbox.y1 for b in blocks),
    )


def chunk_page(page: PageExtraction) -> list[Chunk]:
    blocks = sorted(page.blocks, key=lambda b: (round(b.bbox.y0, 1), b.bbox.x0))
    chunks: list[Chunk] = []
    current: list[TextBlock] = []
    current_chars = 0
    prev_bottom: float | None = None

    def flush() -> None:
        nonlocal current, current_chars
        if current:
            text = " ".join(b.text.strip() for b in current if b.text.strip())
            if text:
                chunks.append(
                    Chunk(
                        chunk_id=f"p{page.page}-c{len(chunks)}",
                        page=page.page,
                        text=text,
                        bbox=_union_bbox(current),
                    )
                )
        current = []
        current_chars = 0

    for block in blocks:
        if not block.text.strip():
            continue
        gap = None if prev_bottom is None else block.bbox.y0 - prev_bottom
        if current and (current_chars + len(block.text) > MAX_CHUNK_CHARS or (gap is not None and gap > LINE_GAP_THRESHOLD)):
            flush()
        current.append(block)
        current_chars += len(block.text)
        prev_bottom = block.bbox.y1

    flush()
    return chunks


def chunk_document(extraction: DocumentExtraction) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in extraction.pages:
        chunks.extend(chunk_page(page))
    return chunks
