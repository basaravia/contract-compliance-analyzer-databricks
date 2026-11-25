"""Fragmentación estructural: cláusulas completas, cruce de páginas, sellos/firmas y referencias cruzadas."""
from __future__ import annotations

import fitz
import pytest

from app.chunking import chunk_document
from app.pdf.extract import extract_document

LONG_BULLETS = [
    "a) El Proveedor mantendrá registros de acceso durante todo el plazo contractual.",
    "b) El Proveedor notificará al Cliente cualquier incidente de seguridad en menos de 72 horas.",
    "c) El Proveedor permitirá auditorías anuales a cargo del Cliente o de un tercero designado.",
]


def _write(page, y, text, size=10):
    page.insert_text((72, y), text, fontsize=size)
    return y + size * 1.4


@pytest.fixture()
def contract_pdf(tmp_path):
    doc = fitz.open()
    p1 = doc.new_page()
    y = 120
    y = _write(p1, y, "CONTRATO DE SERVICIOS", 12)
    y += 14
    y = _write(p1, y, "PRIMERA. OBJETO")
    y = _write(p1, y, "El Proveedor prestara servicios de alojamiento en la nube al Cliente.")
    y += 16
    y = _write(p1, y, "SEGUNDA. DATOS PERSONALES")
    y = _write(p1, y, "El Proveedor tratara los datos personales conforme a la clausula tercera y")
    y = _write(p1, y, "a la clausula decima segunda de este contrato.")
    y += 16
    # Cláusula larga que empieza en la mitad inferior de la página 1 y continúa en la 2.
    y = 560
    y = _write(p1, y, "TERCERA. SEGURIDAD")
    y = _write(p1, y, "El Proveedor aplicara medidas tecnicas y organizativas, entre ellas:")
    for line in LONG_BULLETS[:2]:
        y += 4
        y = _write(p1, y, line)
    p1.insert_text((72, 820), "Pagina 1 de 3", fontsize=8)

    p2 = doc.new_page()
    y = 90
    y = _write(p2, y, LONG_BULLETS[2])
    y += 16
    y = _write(p2, y, "CUARTA. CONFIDENCIALIDAD")
    y = _write(p2, y, "Las partes guardaran reserva sobre la informacion intercambiada, segun el articulo 12 de la Ley de Datos.")
    p2.insert_text((72, 830), "Pagina 2 de 3", fontsize=8)

    p3 = doc.new_page()
    y = 90
    y = _write(p3, y, "QUINTA. FIRMAS")
    y = _write(p3, y, "Las partes suscriben el presente contrato en dos ejemplares.")
    # Sello rotado en el margen y firma digital agregada como anotación, ambos fuera del cuerpo.
    p3.insert_text((22, 500), "Sello de validacion digital 998877", fontsize=8, rotate=90)
    a = p3.add_freetext_annot(fitz.Rect(300, 770, 560, 800), "Firmado electronicamente por MARIA LOPEZ", fontsize=9)
    a.update()
    p3.insert_text((72, 835), "Pagina 3 de 3", fontsize=8)
    path = tmp_path / "contrato.pdf"
    doc.save(path)
    return str(path)


def _chunks(path):
    return chunk_document(extract_document(path))


def test_clausulas_completas_con_su_encabezado(contract_pdf):
    clauses = {c.label.split(".")[0]: c for c in _chunks(contract_pdf) if c.kind == "clause"}
    assert {"PRIMERA", "SEGUNDA", "TERCERA", "CUARTA", "QUINTA"} <= set(clauses)
    # Una cláusula corta (un párrafo) no se mezcla con la siguiente.
    assert "alojamiento" in clauses["PRIMERA"].text and "SEGUNDA" not in clauses["PRIMERA"].text


def test_clausula_que_cruza_pagina_conserva_todo_el_texto_y_una_region_por_pagina(contract_pdf):
    tercera = next(c for c in _chunks(contract_pdf) if c.label and c.label.startswith("TERCERA"))
    for bullet in LONG_BULLETS:  # las tres viñetas, aunque la última esté en la página siguiente
        assert bullet.split(")")[1].strip()[:30] in tercera.text
    assert [r.page for r in tercera.regions] == [1, 2]
    assert tercera.page == 1 and tercera.bbox == tercera.regions[0].bbox
    assert tercera.extra_regions[0].page == 2
    assert "CUARTA" not in tercera.text


def test_sellos_y_firmas_son_fragmentos_aparte_y_no_ensucian_la_clausula(contract_pdf):
    chunks = _chunks(contract_pdf)
    stamps = [c for c in chunks if c.kind not in ("clause", "preamble", "paragraph")]
    texts = " ".join(c.text for c in stamps)
    assert "998877" in texts and "MARIA LOPEZ" in texts
    quinta = next(c for c in chunks if c.label and c.label.startswith("QUINTA"))
    assert "998877" not in quinta.text and "MARIA LOPEZ" not in quinta.text
    assert all(c.page == 3 for c in stamps)


def test_numeracion_de_pagina_repetida_se_descarta_como_ruido(contract_pdf):
    chunks = _chunks(contract_pdf)
    assert not [c for c in chunks if c.kind == "footer" and "Pagina" in c.text]


def test_referencias_cruzadas_se_resuelven_y_las_inexistentes_se_marcan(contract_pdf):
    chunks = _chunks(contract_pdf)
    segunda = next(c for c in chunks if c.label and c.label.startswith("SEGUNDA"))
    tercera = next(c for c in chunks if c.label and c.label.startswith("TERCERA"))
    assert tercera.chunk_id in segunda.refs
    assert any("decima segunda" in u for u in segunda.unresolved_refs)  # esa cláusula no existe
    # «artículo 12 de la Ley de Datos» es una norma externa: no es un enlace interno roto.
    cuarta = next(c for c in chunks if c.label and c.label.startswith("CUARTA"))
    assert cuarta.unresolved_refs == []


def test_sin_encabezados_agrupa_parrafos_sin_partirlos(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    y = 100
    for i in range(30):
        y = _write(page, y + 8, f"Parrafo numero {i} con texto suficiente para ocupar espacio en la pagina del documento.")
    path = tmp_path / "plano.pdf"
    doc.save(path)
    chunks = _chunks(str(path))
    assert chunks and all(c.kind == "paragraph" for c in chunks)
    assert all(len(c.text) <= 1300 for c in chunks)
    joined = " ".join(c.text for c in chunks)
    assert "numero 0 " in joined and "numero 29 " in joined


def test_clausula_gigante_se_parte_solo_entre_parrafos(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    y = 90
    y = _write(page, y, "PRIMERA. OBLIGACIONES")
    for i in range(80):
        y = _write(page, y + 14, f"{i + 1}. El Proveedor cumplira la obligacion numero {i + 1} descrita con detalle suficiente aqui.")
        if y > 780:
            page = doc.new_page()
            y = 90
    page.insert_text((72, 800), "SEGUNDA. FIN", fontsize=10)
    path = tmp_path / "larga.pdf"
    doc.save(path)
    parts = [c for c in _chunks(str(path)) if c.label and c.label.startswith("PRIMERA")]
    assert len(parts) >= 2
    assert all("parte" in c.label for c in parts)
    assert all(len(c.text) <= 3600 for c in parts)
