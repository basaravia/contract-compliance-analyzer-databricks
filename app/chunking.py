"""Fragmentación estructural del texto de un contrato.

En vez de cortar cada N caracteres, se respeta la estructura del documento:

* **Cláusulas completas.** Un fragmento empieza en un encabezado («PRIMERA.», «CLÁUSULA 3», «Artículo 12», «1.»)
  y llega hasta el siguiente, aunque la cláusula tenga viñetas, sangrías o varios párrafos. Las cláusulas muy
  largas se parten solo entre párrafos.
* **Cláusulas que cruzan páginas.** El fragmento guarda una región (página + recuadro) por cada página que ocupa,
  de modo que el hallazgo se pueda marcar completo.
* **Sellos, firmas y márgenes aparte.** El texto de encabezados, pies, laterales rotados, anotaciones y texto
  sobrepuesto forma sus propios fragmentos: ni se mezcla con la cláusula vecina ni se pierde.
* **Referencias cruzadas.** Las citas a otras cláusulas («conforme a la cláusula quinta») se resuelven contra los
  encabezados del propio contrato, para poder darle al evaluador el texto citado, y las que no se encuentran
  se marcan para que el auditor las revise.
"""
from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass, field

from app.pdf.coords import BBoxPoints
from app.pdf.extract import DocumentExtraction, TextBlock

MAX_CLAUSE_CHARS = 3500  # una cláusula más larga se parte entre párrafos
PART_TARGET_CHARS = 3000
SOFT_GROUP_CHARS = 1200  # sin encabezados: se agrupan párrafos hasta este tamaño
MIN_PAGES_REPEATED_NOISE = 3  # encabezado/pie idéntico en tantas páginas = membrete o número de página
PARA_GAP_FACTOR = 0.45  # salto de párrafo si el hueco vertical supera esta fracción de la altura de línea
STAMP_JOIN_GAP = 25.0  # puntos PDF: líneas de sello más cerca que esto forman un mismo sello


@dataclass
class Region:
    page: int
    bbox: BBoxPoints


@dataclass
class Chunk:
    chunk_id: str
    page: int
    text: str
    bbox: BBoxPoints
    regions: list[Region] = field(default_factory=list)
    label: str | None = None
    kind: str = "clause"  # clause | preamble | paragraph | header | footer | side | stamp
    refs: list[str] = field(default_factory=list)  # ids de fragmentos citados que se encontraron
    unresolved_refs: list[str] = field(default_factory=list)  # citas internas que no existen en el documento

    def __post_init__(self) -> None:
        if not self.regions:
            self.regions = [Region(self.page, self.bbox)]

    @property
    def extra_regions(self) -> list[Region]:
        """Regiones que continúan en otras páginas (la primera es `page`/`bbox`)."""
        return self.regions[1:]


# ---------------------------------------------------------------------------
# Geometría y párrafos
# ---------------------------------------------------------------------------
def _union_bbox(blocks: list[TextBlock]) -> BBoxPoints:
    return BBoxPoints(
        x0=min(b.bbox.x0 for b in blocks),
        y0=min(b.bbox.y0 for b in blocks),
        x1=max(b.bbox.x1 for b in blocks),
        y1=max(b.bbox.y1 for b in blocks),
    )


@dataclass
class _Para:
    page: int
    blocks: list[TextBlock]

    @property
    def text(self) -> str:
        return " ".join(b.text.strip() for b in self.blocks if b.text.strip())

    @property
    def first_line(self) -> str:
        return self.blocks[0].text.strip()


_BULLET_RE = re.compile(r"^\s*(?:[•·▪●○◦\-–—*]|\(?[a-zA-Z0-9]{1,3}[\.\)])\s+")


def _paragraphs(page_number: int, blocks: list[TextBlock]) -> list[_Para]:
    body = sorted((b for b in blocks if b.text.strip()), key=lambda b: (round(b.bbox.y0, 1), b.bbox.x0))
    if not body:
        return []
    heights = [b.bbox.y1 - b.bbox.y0 for b in body if b.bbox.y1 > b.bbox.y0]
    line_h = statistics.median(heights) if heights else 10.0
    gap_limit = max(3.0, PARA_GAP_FACTOR * line_h)
    paras: list[_Para] = []
    prev_bottom: float | None = None
    for b in body:
        gap = None if prev_bottom is None else b.bbox.y0 - prev_bottom
        starts_new = not paras or (gap is not None and gap > gap_limit) or bool(_BULLET_RE.match(b.text))
        if paras and gap is not None and gap < 0 and not _BULLET_RE.match(b.text):
            starts_new = False  # comparte altura con la anterior (celdas de una misma fila)
        if starts_new:
            paras.append(_Para(page_number, [b]))
        else:
            paras[-1].blocks.append(b)
        prev_bottom = b.bbox.y1
    return paras


# ---------------------------------------------------------------------------
# Encabezados de cláusula y referencias
# ---------------------------------------------------------------------------
def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


_UNITS = {
    "primer": 1, "segund": 2, "tercer": 3, "cuart": 4, "quint": 5, "sext": 6, "septim": 7, "octav": 8, "noven": 9,
    "undecim": 11, "duodecim": 12, "decim": 10, "vigesim": 20, "trigesim": 30,
}
_UNIT_RE = r"(?:primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|quint[oa]|sext[oa]|s[eé]ptim[oa]|octav[oa]|noven[oa])"
_ORD_WORDS = (
    rf"(?:{_UNIT_RE}|und[eé]cim[oa]|duod[eé]cim[oa]|d[eé]cim[oa](?:\s*{_UNIT_RE})?|"
    rf"vig[eé]sim[oa](?:\s*{_UNIT_RE})?|trig[eé]sim[oa](?:\s*{_UNIT_RE})?)"
)
_KEYWORD = r"(?:cl[aá]usula|art[ií]culo|art\.|cap[ií]tulo|secci[oó]n|anexo|apartado|numeral)(?:es|s)?"
_ROMAN_RE = re.compile(r"^[ivxlc]+$")


def _ordinal_value(word: str) -> int | None:
    w = _strip_accents(word.lower()).strip()
    total = 0
    for stem, value in sorted(_UNITS.items(), key=lambda kv: -len(kv[0])):
        if w.startswith(stem):
            total = value
            w = w[len(stem):].lstrip("oa ")
            break
    else:
        return None
    if total >= 10:  # «décimo tercera», «vigésima primera»: se suma la unidad
        for stem, value in _UNITS.items():
            if value < 10 and w.startswith(stem):
                return total + value
    return total


def _roman_value(token: str) -> int:
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
    total = 0
    for i, ch in enumerate(token):
        v = values[ch]
        total += -v if i + 1 < len(token) and values[token[i + 1]] > v else v
    return total


def _norm_token(token: str) -> str:
    t = _strip_accents(token.strip().strip(".,;:)(").lower())
    if re.fullmatch(r"\d+(?:\.\d+)*", t):
        return t
    ordinal = _ordinal_value(t)
    if ordinal is not None:
        return str(ordinal)
    if _ROMAN_RE.fullmatch(t):
        return str(_roman_value(t))
    return t


def _norm_kind(word: str) -> str:
    w = _strip_accents(word.lower())
    for prefix, kind in (("clausula", "clausula"), ("articulo", "articulo"), ("capitulo", "capitulo"),
                         ("seccion", "seccion"), ("anexo", "anexo"), ("apartado", "numeral"),
                         ("numeral", "numeral"), ("art", "articulo")):
        if w.startswith(prefix):
            return kind
    return w


_TOKEN = rf"(?:\d+(?:\.\d+)*|{_ORD_WORDS})"
_HEAD_KEYWORD_RE = re.compile(rf"^\s*(?P<kw>{_KEYWORD})\s+(?P<tok>{_TOKEN}|\S+)", re.I)
_HEAD_ORDINAL_RE = re.compile(rf"^\s*(?P<tok>{_ORD_WORDS})\s*(?:[\.\-–—:\)]|$)", re.I)
_HEAD_NUMERAL_RE = re.compile(r"^\s*(?P<tok>\d{1,2})\s*[\.\)\-]\s+\S")
_HEAD_ROMAN_RE = re.compile(r"^\s*(?P<tok>[IVXLC]{1,6})\s*[\.\)\-]\s+\S")
_SUBNUMERAL_RE = re.compile(r"^\s*(?P<tok>\d{1,2}(?:\.\d{1,2})+)[\.\)]?\s")
_STYLE_PRIORITY = ["keyword", "ordinal", "numeral", "roman"]
_SENTENCE_END = (".", ";", ":", "!", "?", "")


def _heading_style(first_line: str) -> tuple[str, str, str] | None:
    """(estilo, tipo, token) si la línea abre una cláusula; el estilo permite usar uno solo por documento."""
    m = _HEAD_KEYWORD_RE.match(first_line)
    if m:
        return "keyword", _norm_kind(m.group("kw")), _norm_token(m.group("tok"))
    m = _HEAD_ORDINAL_RE.match(first_line)
    if m:
        return "ordinal", "clausula", _norm_token(m.group("tok"))
    m = _HEAD_NUMERAL_RE.match(first_line)
    if m:
        return "numeral", "clausula", m.group("tok")
    m = _HEAD_ROMAN_RE.match(first_line)
    if m:
        return "roman", "clausula", _norm_token(m.group("tok").lower())
    return None


_REF_RE = re.compile(
    rf"\b(?P<kw>{_KEYWORD})\s+(?P<tok>{_TOKEN}|[A-Za-z]{{1,6}}(?![A-Za-zÁ-ú]))(?P<more>(?:\s*(?:,|y|e|o)\s*{_TOKEN})*)",
    re.I,
)
_EXTERNAL_RE = re.compile(
    r"^\s*(?:,\s*)?(?:de|del)\s+(?:la\s+|el\s+|los\s+|las\s+)?"
    r"(?:(?i:ley|c[oó]digo|reglamento|constituci[oó]n|norma|resoluci[oó]n|decreto|estatuto|convenio|tratado|directiva|acuerdo ministerial)|[A-ZÁÉÍÓÚ]{3,}\b)"
)


def _is_external(text: str, end: int) -> bool:
    """«artículo 12 de la Ley…» cita una norma externa: no es un enlace interno que deba resolverse."""
    return bool(_EXTERNAL_RE.match(text[end:end + 80]))


def _ref_keys(kind: str, token: str) -> list[tuple[str, str]]:
    """Claves a probar, de la más exacta a la más laxa (una «cláusula 3» puede estar numerada como «3.»)."""
    keys = [(kind, token)]
    if kind in ("clausula", "numeral", "articulo"):
        keys += [(k, token) for k in ("clausula", "numeral", "articulo") if k != kind]
    if "." in token:  # «numeral 3.2»: si no existe, cae a la cláusula 3
        keys.append(("clausula", token.split(".")[0]))
    return keys


def _lookup(index: dict[tuple[str, str], list[str]], kind: str, token: str) -> list[str]:
    for key in _ref_keys(kind, token):
        if key in index:
            return index[key]
    return []


# ---------------------------------------------------------------------------
# Construcción de fragmentos
# ---------------------------------------------------------------------------
def _regions_of(paras: list[_Para]) -> list[Region]:
    by_page: dict[int, list[TextBlock]] = {}
    for p in paras:
        by_page.setdefault(p.page, []).extend(p.blocks)
    return [Region(page, _union_bbox(blocks)) for page, blocks in sorted(by_page.items())]


def _split_parts(paras: list[_Para]) -> list[list[_Para]]:
    """Parte una sección demasiado larga solo entre párrafos; un párrafo gigante se parte entre líneas."""
    pieces: list[_Para] = []
    for p in paras:
        if len(p.text) <= MAX_CLAUSE_CHARS:
            pieces.append(p)
            continue
        acc: list[TextBlock] = []
        size = 0
        for b in p.blocks:
            if acc and size + len(b.text) > PART_TARGET_CHARS:
                pieces.append(_Para(p.page, acc))
                acc, size = [], 0
            acc.append(b)
            size += len(b.text)
        if acc:
            pieces.append(_Para(p.page, acc))
    total = sum(len(p.text) for p in pieces)
    if total <= MAX_CLAUSE_CHARS:
        return [pieces] if pieces else []
    parts: list[list[_Para]] = [[]]
    size = 0
    for p in pieces:
        if parts[-1] and size + len(p.text) > PART_TARGET_CHARS:
            parts.append([])
            size = 0
        parts[-1].append(p)
        size += len(p.text)
    return [p for p in parts if p]


def _page_noise_key(text: str) -> str:
    return re.sub(r"\d+", "#", _strip_accents(text.lower())).strip()


def _cluster(blocks: list[TextBlock]) -> list[list[TextBlock]]:
    """Agrupa líneas cercanas entre sí (un sello o una firma suele ser varias líneas pegadas)."""
    clusters: list[list[TextBlock]] = []
    for b in sorted(blocks, key=lambda x: (x.bbox.y0, x.bbox.x0)):
        for cl in clusters:
            u = _union_bbox(cl)
            near_y = b.bbox.y0 - u.y1 <= STAMP_JOIN_GAP and u.y0 - b.bbox.y1 <= STAMP_JOIN_GAP
            near_x = b.bbox.x0 - u.x1 <= 60 and u.x0 - b.bbox.x1 <= 60
            if near_y and near_x:
                cl.append(b)
                break
        else:
            clusters.append([b])
    return clusters


def _margin_chunks(extraction: DocumentExtraction) -> list[Chunk]:
    """Encabezados, pies, laterales y sellos de cada página como fragmentos propios. Las líneas que se repiten
    igual en muchas páginas (membrete, «Página 3 de 10») son ruido y se omiten una por una."""
    noise_pages: dict[tuple[str, str], set[int]] = {}
    for page in extraction.pages:
        for b in page.blocks:
            if b.kind in ("header", "footer") and b.text.strip():
                noise_pages.setdefault((b.kind, _page_noise_key(b.text)), set()).add(page.page)

    def is_noise(b: TextBlock) -> bool:
        return b.kind in ("header", "footer") and len(noise_pages[(b.kind, _page_noise_key(b.text))]) >= MIN_PAGES_REPEATED_NOISE

    labels = {"header": "Encabezado", "footer": "Pie de página", "side": "Margen lateral", "stamp": "Sello o firma"}
    chunks: list[Chunk] = []
    for page in extraction.pages:
        zones: dict[str, list[TextBlock]] = {}
        for b in page.blocks:
            if b.kind != "body" and b.text.strip() and not is_noise(b):
                zones.setdefault(b.kind, []).append(b)
        k = 0
        for kind, blocks in zones.items():
            for cl in ([blocks] if kind == "side" else _cluster(blocks)):
                ordered = sorted(cl, key=lambda x: (round(x.bbox.y0, 1), x.bbox.x0))
                chunks.append(
                    Chunk(
                        chunk_id=f"p{page.page}-m{k}",
                        page=page.page,
                        text=" ".join(x.text.strip() for x in ordered),
                        bbox=_union_bbox(ordered),
                        label=labels[kind],
                        kind=kind,
                    )
                )
                k += 1
    return chunks


def _resolve_references(chunks: list[Chunk], index: dict[tuple[str, str], list[str]]) -> None:
    """Rellena `refs` (fragmentos citados que existen) y `unresolved_refs` (citas internas sin destino)."""
    known = {c.chunk_id for c in chunks}
    for chunk in chunks:
        resolved: list[str] = []
        unresolved: list[str] = []
        for m in _REF_RE.finditer(chunk.text):
            kind = _norm_kind(m.group("kw"))
            first = m.group("tok")
            plain = bool(re.fullmatch(_TOKEN, first, flags=re.I))
            # «anexo A», «capítulo II»: letra o número romano solo se aceptan en mayúsculas y para estos tipos.
            if not plain and not (kind in ("anexo", "capitulo", "seccion") and first.isupper()):
                continue
            if _is_external(chunk.text, m.end()):
                continue
            tokens = [first] + re.findall(_TOKEN, m.group("more") or "", flags=re.I)
            for tok in tokens:
                ids = _lookup(index, kind, _norm_token(tok))
                if chunk.chunk_id in ids:
                    continue  # se cita a sí misma («esta cláusula 3»): no es un error
                ids = [i for i in ids if i in known]
                if ids:
                    resolved.extend(i for i in ids if i not in resolved)
                else:
                    text = f"{kind.replace('clausula', 'cláusula').replace('articulo', 'artículo')} {tok}"
                    if text not in unresolved:
                        unresolved.append(text)
        chunk.refs = resolved
        chunk.unresolved_refs = unresolved


def chunk_document(extraction: DocumentExtraction) -> list[Chunk]:
    # 1) Párrafos del cuerpo de todo el documento, en orden de lectura, sin cortar por página.
    paras: list[_Para] = []
    for page in extraction.pages:
        paras.extend(_paragraphs(page.page, [b for b in page.blocks if b.kind == "body"]))

    # 2) Un solo estilo de encabezado por documento: el primero, por prioridad, que aparece al menos dos veces.
    heads = [_heading_style(p.first_line) for p in paras]
    counts: dict[str, int] = {}
    for h in heads:
        if h:
            counts[h[0]] = counts.get(h[0], 0) + 1
    style = next((s for s in _STYLE_PRIORITY if counts.get(s, 0) >= 2), None)

    # (etiqueta, tipo, párrafos, claves de referencia)
    sections: list[tuple[str | None, str, list[_Para], list[tuple[str, str]]]] = []
    if style is None:
        group: list[_Para] = []
        size = 0
        for p in paras:
            # Una página nueva abre grupo, salvo que el párrafo anterior haya quedado cortado (sin punto final).
            page_break = bool(group) and p.page != group[-1].page and group[-1].text.rstrip()[-1:] in _SENTENCE_END
            if group and (size + len(p.text) > SOFT_GROUP_CHARS or page_break):
                sections.append((None, "paragraph", group, []))
                group, size = [], 0
            group.append(p)
            size += len(p.text)
        if group:
            sections.append((None, "paragraph", group, []))
    else:
        current: tuple[str | None, str, list[_Para], list[tuple[str, str]]] = (None, "preamble", [], [])
        for p, h in zip(paras, heads):
            if h and h[0] == style:
                if current[2]:
                    sections.append(current)
                keys = [(h[1], h[2])]
                if style in ("numeral", "roman"):
                    keys.append(("numeral", h[2]))
                current = (p.first_line[:90], "clause", [p], keys)
            else:
                current[2].append(p)
        if current[2]:
            sections.append(current)

    # 3) Fragmentos (partiendo las secciones largas) y registro de claves para resolver referencias.
    chunks: list[Chunk] = []
    index: dict[tuple[str, str], list[str]] = {}
    per_page: dict[int, int] = {}
    for label, kind, section_paras, keys in sections:
        parts = _split_parts(section_paras)
        for n, part in enumerate(parts, start=1):
            text = "\n".join(p.text for p in part if p.text)
            if not text.strip():
                continue
            regions = _regions_of(part)
            first = regions[0]
            k = per_page.get(first.page, 0)
            per_page[first.page] = k + 1
            chunk_id = f"p{first.page}-c{k}"
            part_label = label if len(parts) == 1 or label is None else f"{label} (parte {n} de {len(parts)})"
            chunks.append(
                Chunk(chunk_id=chunk_id, page=first.page, text=text, bbox=first.bbox, regions=regions, label=part_label, kind=kind)
            )
            for key in keys:
                index.setdefault(key, []).append(chunk_id)
            for p in part:
                m = _SUBNUMERAL_RE.match(p.first_line)
                if m:
                    index.setdefault(("numeral", m.group("tok")), []).append(chunk_id)

    # 4) Referencias entre cláusulas y, aparte, sellos, firmas y márgenes.
    _resolve_references(chunks, index)
    chunks.extend(_margin_chunks(extraction))
    return chunks
