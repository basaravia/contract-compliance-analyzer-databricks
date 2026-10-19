"""Tests de `app.rules.parser.parse_natural_language_rules`.

Cubren: parseo correcto de múltiples reglas separadas por '---', continuación
de línea por sangría, múltiples referencias por regla, y que los errores de
un bloque (campo obligatorio faltante, severidad inválida, campo desconocido)
se acumulen en `ParseResult.errors` con el `block_index` correcto sin abortar
el parseo de los demás bloques válidos.
"""
from __future__ import annotations

from app.rules.parser import parse_natural_language_rules


def test_parses_multiple_valid_rules_with_wrapped_description_and_references():
    text = (
        "Regla: Clausula de proteccion de datos personales\n"
        "Descripcion: El contrato debe incluir una clausula donde el proveedor\n"
        "  se compromete a tratar datos personales conforme a la LOPDP.\n"
        "Categoria: proteccion_datos\n"
        "Severidad: alta\n"
        "Jurisdiccion: EC\n"
        "Referencia: LOPDP Art. 5 (principios de tratamiento)\n"
        "Referencia: LOPDP Art. 9\n"
        "---\n"
        "Regla: Plazo de notificacion de incidentes\n"
        "Descripcion: El contrato debe establecer un plazo maximo para notificar "
        "incidentes de seguridad.\n"
        "Severidad: alta\n"
        "Referencia: LOPDP Art. 44\n"
    )

    result = parse_natural_language_rules(text)

    assert result.errors == []
    assert len(result.rules) == 2

    rule1 = result.rules[0]
    assert rule1.name == "Clausula de proteccion de datos personales"
    assert rule1.description == (
        "El contrato debe incluir una clausula donde el proveedor "
        "se compromete a tratar datos personales conforme a la LOPDP."
    )
    assert rule1.category == "proteccion_datos"
    assert rule1.severity == "alta"
    assert rule1.jurisdiction == "EC"
    assert [r.citation for r in rule1.references] == [
        "LOPDP Art. 5 (principios de tratamiento)",
        "LOPDP Art. 9",
    ]

    rule2 = result.rules[1]
    assert rule2.name == "Plazo de notificacion de incidentes"
    assert "plazo maximo" in rule2.description
    assert rule2.severity == "alta"
    # jurisdiction no especificada -> valor por defecto
    assert rule2.jurisdiction == "EC"
    assert [r.citation for r in rule2.references] == ["LOPDP Art. 44"]


def test_missing_rule_name_field_generates_error_without_aborting_other_blocks():
    text = (
        "Regla: Regla valida uno\n"
        "Descripcion: Descripcion valida uno.\n"
        "---\n"
        # Bloque invalido: falta 'Regla:'
        "Descripcion: Bloque invalido sin nombre de regla.\n"
        "Severidad: media\n"
        "---\n"
        "Regla: Regla valida dos\n"
        "Descripcion: Descripcion valida dos.\n"
    )

    result = parse_natural_language_rules(text)

    assert len(result.rules) == 2
    assert result.rules[0].name == "Regla valida uno"
    assert result.rules[1].name == "Regla valida dos"

    assert len(result.errors) == 1
    assert result.errors[0].block_index == 1
    assert "Regla" in result.errors[0].message


def test_missing_description_field_generates_error_with_correct_block_index():
    text = (
        "Regla: Regla valida\n"
        "Descripcion: Descripcion valida.\n"
        "---\n"
        # Bloque invalido: falta 'Descripcion:'
        "Regla: Regla sin descripcion\n"
        "Severidad: baja\n"
    )

    result = parse_natural_language_rules(text)

    assert len(result.rules) == 1
    assert result.rules[0].name == "Regla valida"

    assert len(result.errors) == 1
    assert result.errors[0].block_index == 1
    assert "Descripción" in result.errors[0].message or "Descripcion" in result.errors[0].message


def test_invalid_severity_generates_error():
    text = (
        "Regla: Regla con severidad invalida\n"
        "Descripcion: Descripcion cualquiera.\n"
        "Severidad: urgente\n"
    )

    result = parse_natural_language_rules(text)

    assert result.rules == []
    assert len(result.errors) == 1
    assert result.errors[0].block_index == 0
    assert "Severidad inválida" in result.errors[0].message


def test_unknown_field_generates_error():
    text = (
        "Regla: Regla con campo desconocido\n"
        "Descripcion: Descripcion cualquiera.\n"
        "Campo Raro: bar\n"
    )

    result = parse_natural_language_rules(text)

    assert result.rules == []
    assert len(result.errors) == 1
    assert result.errors[0].block_index == 0
    assert "desconocido" in result.errors[0].message.lower()


def test_multiple_errors_accumulate_with_correct_indices_and_valid_rules_survive():
    text = (
        "Regla: Regla valida\n"
        "Descripcion: Descripcion valida.\n"
        "---\n"
        "Descripcion: Sin nombre de regla.\n"
        "---\n"
        "Regla: Regla severidad mala\n"
        "Descripcion: Descripcion cualquiera.\n"
        "Severidad: extrema\n"
        "---\n"
        "Regla: Regla campo raro\n"
        "Descripcion: Descripcion cualquiera.\n"
        "Foo: bar\n"
    )

    result = parse_natural_language_rules(text)

    assert len(result.rules) == 1
    assert result.rules[0].name == "Regla valida"

    assert len(result.errors) == 3
    assert [e.block_index for e in result.errors] == [1, 2, 3]


def test_empty_text_returns_empty_lists_without_exception():
    result = parse_natural_language_rules("")
    assert result.rules == []
    assert result.errors == []


def test_only_separators_returns_empty_lists_without_exception():
    result = parse_natural_language_rules("---\n---\n---\n")
    assert result.rules == []
    assert result.errors == []


def test_whitespace_only_text_returns_empty_lists_without_exception():
    result = parse_natural_language_rules("   \n\t\n   \n")
    assert result.rules == []
    assert result.errors == []
