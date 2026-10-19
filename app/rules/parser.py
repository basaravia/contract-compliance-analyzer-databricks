"""Importación de reglas en dos formatos:

- JSON estructurado: ver `app.schemas.RuleImportPayload` (usado directamente
  por el router, no requiere este módulo).
- Texto en lenguaje natural: un formato simple de líneas clave: valor,
  pensado para que un cumplimiento/legal no técnico pueda escribir reglas
  en un editor de texto plano sin aprender JSON. Ejemplo::

    Regla: Cláusula de protección de datos personales
    Descripción: El contrato debe incluir una cláusula donde el proveedor
      se compromete a tratar datos personales conforme a la LOPDP.
    Categoría: proteccion_datos
    Severidad: alta
    Referencia: LOPDP Art. 5 (principios de tratamiento)
    ---
    Regla: Plazo de notificación de incidentes de seguridad
    Descripción: El contrato debe establecer un plazo máximo para notificar
      incidentes de seguridad que afecten datos personales.
    Severidad: alta
    Referencia: LOPDP Art. 44

Cada regla se separa de la siguiente con una línea que contenga solo
``---``. Los campos ``Regla`` y ``Descripción`` son obligatorios; el resto
son opcionales. Puede haber varias líneas ``Referencia:`` por regla.
Ninguna entrada mal formada se descarta silenciosamente: se recolectan
errores por bloque y se devuelven junto a las reglas válidas para que el
usuario pueda corregirlas.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import RuleCreate, RuleReferenceIn, SeverityLiteral

_FIELD_ALIASES = {
    "regla": "name",
    "nombre": "name",
    "descripcion": "description",
    "descripción": "description",
    "categoria": "category",
    "categoría": "category",
    "severidad": "severity",
    "jurisdiccion": "jurisdiction",
    "jurisdicción": "jurisdiction",
    "referencia": "reference",
}
_VALID_SEVERITIES: set[SeverityLiteral] = {"alta", "media", "baja"}


@dataclass
class ParseError:
    block_index: int
    message: str


@dataclass
class ParseResult:
    rules: list[RuleCreate] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)


def parse_natural_language_rules(text: str) -> ParseResult:
    blocks = _split_blocks(text)
    result = ParseResult()
    for i, block in enumerate(blocks):
        if not block.strip():
            continue
        try:
            rule = _parse_block(block)
        except ValueError as e:
            result.errors.append(ParseError(block_index=i, message=str(e)))
            continue
        if rule is not None:
            result.rules.append(rule)
    return result


def _split_blocks(text: str) -> list[str]:
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[list[str]] = [[]]
    for line in lines:
        if line.strip() == "---":
            blocks.append([])
        else:
            blocks[-1].append(line)
    return ["\n".join(b) for b in blocks]


def _parse_block(block: str) -> RuleCreate | None:
    fields: dict[str, str] = {}
    references: list[str] = []
    current_key: str | None = None

    for raw_line in block.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            continue
        stripped = line.lstrip()
        indented = len(line) - len(stripped) > 0 and current_key is not None

        if ":" in stripped and not indented:
            key_raw, _, value = stripped.partition(":")
            key = _FIELD_ALIASES.get(key_raw.strip().lower())
            if key is None:
                raise ValueError(f"Campo desconocido: '{key_raw.strip()}'")
            value = value.strip()
            if key == "reference":
                if value:
                    references.append(value)
                current_key = "reference"
            else:
                fields[key] = value
                current_key = key
        elif current_key is not None:
            # continuación de línea (texto envuelto con sangría)
            if current_key == "reference" and references:
                references[-1] = f"{references[-1]} {stripped}".strip()
            elif current_key in fields:
                fields[current_key] = f"{fields[current_key]} {stripped}".strip()
        else:
            raise ValueError(f"Línea sin campo asociado: '{line}'")

    if not fields and not references:
        return None

    if "name" not in fields or not fields["name"]:
        raise ValueError("Falta el campo 'Regla' (nombre)")
    if "description" not in fields or not fields["description"]:
        raise ValueError("Falta el campo 'Descripción'")

    severity = fields.get("severity", "media").strip().lower()
    if severity not in _VALID_SEVERITIES:
        raise ValueError(f"Severidad inválida: '{severity}' (use alta|media|baja)")

    return RuleCreate(
        name=fields["name"],
        description=fields["description"],
        jurisdiction=fields.get("jurisdiction", "EC") or "EC",
        category=fields.get("category") or None,
        severity=severity,  # type: ignore[arg-type]
        active=True,
        references=[RuleReferenceIn(citation=c) for c in references],
    )
