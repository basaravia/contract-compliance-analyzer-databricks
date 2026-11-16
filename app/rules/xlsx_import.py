"""Plantilla y lectura de criterios en Excel: es la forma más natural de cargarlos para quien audita.

Hoja «Criterios»: una fila por criterio, columnas fijas (Criterio, Descripción, Categoría, Importancia,
Jurisdicción, Referencia 1..3). Ninguna fila mal formada se descarta en silencio: cada error indica la fila."""
from __future__ import annotations

import io

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from app.rules.parser import ParseError, ParseResult
from app.schemas import RuleCreate, RuleReferenceIn

MAX_ROWS = 500
HEADERS = ["Criterio", "Descripción", "Categoría", "Importancia", "Jurisdicción", "Referencia 1", "Referencia 2", "Referencia 3"]
_SEVERITIES = {"alta": "alta", "media": "media", "baja": "baja"}


def build_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Criterios"
    ws.append(HEADERS)
    ws.append([
        "Protección de datos personales",
        "El contrato debe incluir una cláusula en la que el proveedor se compromete a tratar los datos personales conforme a la ley.",
        "proteccion_datos", "alta", "EC", "LOPDP Art. 5", "", "",
    ])
    ws.append([
        "Plazo de notificación de incidentes",
        "El contrato debe fijar un plazo máximo para notificar incidentes de seguridad.",
        "seguridad", "media", "EC", "LOPDP Art. 44", "", "",
    ])
    head_fill = PatternFill("solid", fgColor="1D4ED8")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head_fill
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for col, width in zip("ABCDEFGH", (34, 70, 18, 14, 14, 26, 26, 26)):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=2, max_row=3):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"

    guide = wb.create_sheet("Cómo llenarla")
    for line in [
        "Una fila por criterio. Borra las dos filas de ejemplo antes de cargar tus criterios.",
        "Criterio y Descripción son obligatorios.",
        "Descripción: qué debe cumplir el contrato, en una o dos frases claras. La IA evalúa el contrato contra este texto.",
        "Importancia: alta, media o baja (si la dejas vacía se usa media).",
        "Jurisdicción: código del país, por ejemplo EC (si la dejas vacía se usa EC).",
        "Referencia 1–3: norma o política que respalda el criterio, por ejemplo «LOPDP Art. 5».",
    ]:
        guide.append([line])
    guide.column_dimensions["A"].width = 120
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _cell(v: object) -> str:
    return "" if v is None else str(v).strip()


def parse_xlsx(data: bytes) -> ParseResult:
    result = ParseResult()
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - zip inválido, archivo corrupto, formato no soportado
        result.errors.append(ParseError("Archivo", "No se pudo leer el archivo. Debe ser un Excel (.xlsx), por ejemplo la plantilla descargada."))
        return result
    ws = wb["Criterios"] if "Criterios" in wb.sheetnames else wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [_cell(c).lower() for c in next(rows, ())]
    index = {name: header.index(name.lower()) for name in HEADERS if name.lower() in header}
    missing = [n for n in ("Criterio", "Descripción") if n not in index]
    if missing:
        result.errors.append(ParseError("Encabezados", f"Falta la columna {' y '.join(missing)}. Usa la plantilla para no equivocarte."))
        return result

    def get(row: tuple, name: str) -> str:
        i = index.get(name)
        return _cell(row[i]) if i is not None and i < len(row) else ""

    for n, row in enumerate(rows, start=2):
        if n - 1 > MAX_ROWS:
            result.errors.append(ParseError("Archivo", f"Hay más de {MAX_ROWS} filas; divide la carga en varios archivos."))
            break
        if not any(_cell(c) for c in row):
            continue  # fila vacía
        name, desc = get(row, "Criterio"), get(row, "Descripción")
        label = f"Fila {n}"
        if not name or not desc:
            result.errors.append(ParseError(label, "Falta " + ("el Criterio" if not name else "la Descripción") + ", que es obligatoria."))
            continue
        sev_raw = get(row, "Importancia").lower()
        if sev_raw and sev_raw not in _SEVERITIES:
            result.errors.append(ParseError(label, f"Importancia «{get(row, 'Importancia')}» no válida: usa alta, media o baja."))
            continue
        refs = [RuleReferenceIn(citation=get(row, k)[:300]) for k in ("Referencia 1", "Referencia 2", "Referencia 3") if get(row, k)]
        try:
            result.rules.append(RuleCreate(
                name=name[:200], description=desc[:5000], category=get(row, "Categoría")[:100] or None,
                severity=_SEVERITIES.get(sev_raw, "media"), jurisdiction=(get(row, "Jurisdicción") or "EC")[:10], references=refs,
            ))
        except ValueError:
            result.errors.append(ParseError(label, "Algún dato no es válido (revisa la longitud de los textos)."))
    if not result.rules and not result.errors:
        result.errors.append(ParseError("Archivo", "No hay criterios en el archivo: llena al menos una fila debajo de los encabezados."))
    return result
