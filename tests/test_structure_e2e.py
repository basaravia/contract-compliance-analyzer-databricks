"""Extremo a extremo de la fragmentación estructural: una cláusula que cruza páginas se marca completa, las
referencias cruzadas llegan al evaluador y las rotas quedan avisadas en la traza."""
from __future__ import annotations

import fitz

from tests.test_e2e_backend import client  # noqa: F401  (fixture)

RULE = {
    "rules": [
        {
            "name": "Notificacion de incidentes de seguridad",
            "description": "El proveedor debe notificar incidentes de seguridad al cliente dentro de un plazo maximo.",
            "category": "Seguridad",
            "severity": "alta",
            "jurisdiction": "EC",
            "references": [],
        }
    ]
}


def _contract_with_cross_page_clause() -> bytes:
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 120), "PRIMERA. OBJETO", fontsize=10)
    p1.insert_text((72, 134), "El Proveedor prestara servicios de alojamiento.", fontsize=10)
    p1.insert_text((72, 560), "SEGUNDA. SEGURIDAD", fontsize=10)
    p1.insert_text((72, 574), "El Proveedor notificara incidentes de seguridad al Cliente segun la clausula tercera", fontsize=10)
    p1.insert_text((72, 588), "y la clausula decima quinta de este contrato, dentro de un plazo maximo, y ademas:", fontsize=10)
    p2 = doc.new_page()
    p2.insert_text((72, 100), "a) mantendra un registro de cada incidente de seguridad notificado.", fontsize=10)
    p2.insert_text((72, 140), "TERCERA. PLAZO", fontsize=10)
    p2.insert_text((72, 154), "El plazo maximo de notificacion es de setenta y dos horas.", fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def test_hallazgo_de_clausula_que_cruza_pagina_guarda_las_dos_regiones_y_avisa_enlaces_rotos(client):  # noqa: F811
    r = client.post("/api/documents", data={"doc_type": "contrato"}, files={"file": ("c.pdf", _contract_with_cross_page_clause(), "application/pdf")})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert client.post("/api/rules/import", json=RULE).status_code == 201
    an = client.post("/api/analyses", json={"contract_document_id": doc["id"]})
    assert an.status_code == 202, an.text
    detail = client.get(f"/api/analyses/{an.json()['id']}").json()
    f = detail["findings"][0]

    assert f["page"] == 1
    assert [e["page"] for e in f["extra_regions"]] == [2], "la continuación en la página 2 queda registrada"
    assert "registro de cada incidente" in f["evidence_text"], "la evidencia incluye el texto de la página siguiente"
    limitations = " ".join(f["trace"]["limitations"])
    assert "decima quinta" in limitations and "no se encontró en el documento" in limitations
    assert "TERCERA" in f["trace"]["method_summary"], "se avisa de que se añadió el texto de la cláusula citada"


def test_mover_o_redimensionar_el_recuadro_no_ejecuta_la_ia_y_refresca_la_evidencia(client, monkeypatch):  # noqa: F811
    import app.analysis_engine as engine

    r = client.post("/api/documents", data={"doc_type": "contrato"}, files={"file": ("c.pdf", _contract_with_cross_page_clause(), "application/pdf")})
    client.post("/api/rules/import", json=RULE)
    an = client.post("/api/analyses", json={"contract_document_id": r.json()["id"]}).json()
    f = client.get(f"/api/analyses/{an['id']}").json()["findings"][0]

    def _no_llm():
        raise AssertionError("mover el recuadro no debe invocar al modelo")

    monkeypatch.setattr(engine, "get_rule_evaluator", _no_llm)
    # Se reduce el recuadro a la línea «PRIMERA. OBJETO»… en la página 1 (zona alta).
    patched = client.patch(
        f"/api/findings/{f['id']}",
        json={"bbox": {"x0": 60, "y0": 108, "x1": 300, "y1": 140}, "recalculate": False},
    )
    assert patched.status_code == 200, patched.text
    g = patched.json()
    assert g["status"] == f["status"] and g["justification"] == f["justification"], "el veredicto no cambia sin IA"
    assert g["edited"] is True and g["evidence_text"] != f["evidence_text"]
    assert "OBJETO" in g["evidence_text"]


def test_analisis_con_mas_contexto_envia_la_clausula_completa_y_las_citadas(client, monkeypatch):  # noqa: F811
    import app.analysis_engine as engine
    from app.schemas import RuleEvaluationResult

    r = client.post("/api/documents", data={"doc_type": "contrato"}, files={"file": ("c.pdf", _contract_with_cross_page_clause(), "application/pdf")})
    client.post("/api/rules/import", json=RULE)
    an = client.post("/api/analyses", json={"contract_document_id": r.json()["id"]}).json()
    f = client.get(f"/api/analyses/{an['id']}").json()["findings"][0]
    seen: list[list] = []

    class Spy:
        def evaluate(self, rule, chunks):
            seen.append(list(chunks))
            return RuleEvaluationResult(status="cumple", justification="ok", confidence=0.8)

    monkeypatch.setattr(engine, "get_rule_evaluator", lambda: Spy())
    body = {"analysis_id": an["id"], "rule_id": f["rule_id"], "page": 1, "instructions": "",
            "bbox": {"x0": 60, "y0": 565, "x1": 540, "y1": 580}}
    assert client.post("/api/findings/analyze", json=body).status_code == 200
    assert len(seen[-1]) == 1, "sin «más contexto» solo viaja el texto del recuadro"
    assert client.post("/api/findings/analyze", json={**body, "deep": True}).status_code == 200
    ctx = seen[-1]
    assert len(ctx) >= 2 and any("SEGUNDA" in c.text and "registro de cada incidente" in c.text for c in ctx)
    assert any(c.cited_from and "TERCERA" in c.text for c in ctx), "también viaja la cláusula que la sección cita"


def test_un_recuadro_nuevo_dibujado_a_mano_no_ejecuta_la_ia_al_guardarse_ni_al_moverse(client, monkeypatch):  # noqa: F811
    import app.analysis_engine as engine

    r = client.post("/api/documents", data={"doc_type": "contrato"}, files={"file": ("c.pdf", _contract_with_cross_page_clause(), "application/pdf")})
    client.post("/api/rules/import", json=RULE)
    an = client.post("/api/analyses", json={"contract_document_id": r.json()["id"]}).json()
    rule_id = client.get(f"/api/analyses/{an['id']}").json()["findings"][0]["rule_id"]

    def _no_llm():
        raise AssertionError("la IA solo debe ejecutarse con el botón «Reprocesar con IA»")

    monkeypatch.setattr(engine, "get_rule_evaluator", _no_llm)
    created = client.post(
        "/api/findings",
        json={"analysis_id": an["id"], "rule_id": rule_id, "page": 1, "bbox": {"x0": 60, "y0": 108, "x1": 300, "y1": 140}},
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "requiere_revision" and created.json()["is_manual"] is True
    moved = client.patch(f"/api/findings/{created.json()['id']}", json={"bbox": {"x0": 60, "y0": 120, "x1": 320, "y1": 150}})
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "requiere_revision"
