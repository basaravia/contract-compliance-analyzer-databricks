"""Tests de `app.analysis_engine`: pipeline completo de análisis
(`run_analysis`) y, sobre todo, `recalculate_finding`, que es el
requisito crítico de "editar un bbox recalcula el hallazgo de verdad" (no
simplemente vuelve a guardar el valor anterior).

Usa un motor SQLite en memoria propio y autocontenido (no toca
`app.db.engine`/`SessionLocal` globales) y un PDF generado con `fitz` dentro
de `tmp_path`, sin depender de fixtures compartidas de otros equipos.
"""
from __future__ import annotations

import fitz
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.analysis_engine as analysis_engine_module
import app.models as models
from app.analysis_engine import recalculate_finding, run_analysis
from app.db import Base
from app.models import (
    Analysis,
    AnalysisStatus,
    Document,
    DocumentType,
    ExtractionStatus,
    Finding,
    Rule,
)

DATA_PROTECTION_TEXT = (
    "Clausula de Proteccion de Datos Personales. El proveedor se compromete a "
    "proteger los datos personales de los usuarios y garantiza el cumplimiento "
    "de la normativa de proteccion de datos conforme a la LOPDP en todo momento."
)
CONFIDENTIALITY_TEXT = (
    "Clausula de Confidencialidad. Las partes acuerdan mantener confidencialidad "
    "sobre la informacion tecnica y comercial compartida durante la vigencia del "
    "contrato y por cinco anios despues de su terminacion."
)

# Rectángulos elegidos deliberadamente al insertar el texto, así conocemos
# de antemano una región (en puntos PDF) que rodea cada párrafo, y una región
# en blanco donde no se insertó ningún texto.
RECT_DATA_PROTECTION = fitz.Rect(50, 50, 545, 200)
RECT_CONFIDENTIALITY = fitz.Rect(50, 300, 545, 450)
RECT_BLANK = fitz.Rect(50, 700, 545, 780)


def _build_test_pdf(path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_textbox(RECT_DATA_PROTECTION, DATA_PROTECTION_TEXT, fontsize=11)
    page.insert_textbox(RECT_CONFIDENTIALITY, CONFIDENTIALITY_TEXT, fontsize=11)
    doc.save(str(path))
    doc.close()


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture()
def contract_setup(tmp_path, monkeypatch, db_session):
    """Crea un Document apuntando a un PDF autocontenido en tmp_path, y
    parchea `resolve_upload_path` dentro del módulo `analysis_engine` (el
    nombre ya está vinculado ahí por `from app.security import
    resolve_upload_path`, así que parchear `app.security.resolve_upload_path`
    no bastaría) para que lea el PDF de prueba en vez de `settings.upload_dir`.
    """
    pdf_path = tmp_path / "contract.pdf"
    _build_test_pdf(pdf_path)

    monkeypatch.setattr(
        analysis_engine_module, "resolve_upload_path", lambda name: tmp_path / name
    )

    document = Document(
        doc_type=DocumentType.contrato,
        original_filename="contrato_original.pdf",
        stored_filename="contract.pdf",
        title="Contrato de prueba",
        jurisdiction="EC",
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    rule = Rule(
        name="Proteccion de datos personales",
        description=(
            "El contrato debe incluir una clausula donde el proveedor se compromete "
            "a proteger los datos personales de los usuarios conforme a la normativa "
            "de proteccion de datos (LOPDP)."
        ),
        jurisdiction="EC",
        severity="alta",
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)

    analysis = Analysis(
        contract_document_id=document.id,
        status=AnalysisStatus.pending.value,
        rule_ids=[rule.id],
    )
    db_session.add(analysis)
    db_session.commit()
    db_session.refresh(analysis)

    return {
        "session": db_session,
        "document": document,
        "rule": rule,
        "analysis": analysis,
        "tmp_path": tmp_path,
    }


def test_run_analysis_persists_one_finding_per_rule_with_literal_evidence(contract_setup):
    session = contract_setup["session"]
    document = contract_setup["document"]
    rule = contract_setup["rule"]
    analysis = contract_setup["analysis"]

    run_analysis(session, analysis, document, [rule])

    findings = session.query(Finding).filter(Finding.analysis_id == analysis.id).all()
    assert len(findings) == 1

    finding = findings[0]
    assert finding.rule_id == rule.id
    assert finding.status in (
        "cumple",
        "no_cumple",
        "parcial",
        "no_determinable",
        "requiere_revision",
    )
    # El párrafo de protección de datos comparte vocabulario fuerte con la
    # regla y contiene lenguaje afirmativo ("se compromete", "garantiza",
    # "conforme a") sin negación: se espera "cumple".
    assert finding.status == "cumple"
    assert finding.evidence_text is not None
    assert finding.evidence_text in DATA_PROTECTION_TEXT
    assert finding.page == 1
    assert finding.bbox_x0 is not None and finding.bbox_y0 is not None
    assert finding.confidence > 0.0

    # La extracción del documento debe haberse marcado como completada
    # (documento nativo, no escaneado).
    assert document.extraction_status == ExtractionStatus.done


def test_recalculate_finding_on_bbox_moved_to_different_paragraph_actually_changes_result(
    contract_setup,
):
    session = contract_setup["session"]
    document = contract_setup["document"]
    rule = contract_setup["rule"]
    analysis = contract_setup["analysis"]

    run_analysis(session, analysis, document, [rule])
    finding = session.query(Finding).filter(Finding.analysis_id == analysis.id).one()

    original_status = finding.status
    original_evidence = finding.evidence_text
    original_justification = finding.justification
    assert original_status == "cumple"
    assert original_evidence is not None and original_evidence in DATA_PROTECTION_TEXT

    # Edición manual: el usuario mueve el bbox hacia el párrafo de
    # confidencialidad (texto distinto al detectado originalmente).
    finding.bbox_x0 = RECT_CONFIDENTIALITY.x0
    finding.bbox_y0 = RECT_CONFIDENTIALITY.y0
    finding.bbox_x1 = RECT_CONFIDENTIALITY.x1
    finding.bbox_y1 = RECT_CONFIDENTIALITY.y1
    session.add(finding)
    session.commit()

    recalculate_finding(session, finding, document, rule)
    session.add(finding)
    session.commit()
    session.refresh(finding)

    # El hallazgo debe reflejar de verdad el nuevo bbox, no simplemente
    # volver a guardar el resultado anterior.
    assert finding.evidence_text != original_evidence
    assert finding.justification != original_justification
    assert finding.status != original_status

    assert finding.evidence_text is not None
    # `extract_text_in_bbox` preserva los saltos de línea del layout del PDF
    # (párrafo envuelto en varias líneas), así que se normaliza el espacio en
    # blanco antes de comparar el contenido literal recuperado.
    normalized_evidence = " ".join(finding.evidence_text.split())
    assert normalized_evidence in CONFIDENTIALITY_TEXT
    assert normalized_evidence not in DATA_PROTECTION_TEXT
    # El párrafo de confidencialidad no comparte vocabulario de cumplimiento
    # ni marcadores de negación/afirmación relevantes para esta regla, por lo
    # que el mock debe degradar de forma segura (nunca "cumple" inventado).
    assert finding.status in ("requiere_revision", "no_determinable")


def test_recalculate_finding_on_blank_bbox_forces_requiere_revision(contract_setup):
    session = contract_setup["session"]
    document = contract_setup["document"]
    rule = contract_setup["rule"]
    analysis = contract_setup["analysis"]

    run_analysis(session, analysis, document, [rule])
    finding = session.query(Finding).filter(Finding.analysis_id == analysis.id).one()

    # Edición manual hacia una zona en blanco de la página (sin texto).
    finding.bbox_x0 = RECT_BLANK.x0
    finding.bbox_y0 = RECT_BLANK.y0
    finding.bbox_x1 = RECT_BLANK.x1
    finding.bbox_y1 = RECT_BLANK.y1
    session.add(finding)
    session.commit()

    recalculate_finding(session, finding, document, rule)

    assert finding.status == "requiere_revision"
    assert finding.evidence_text is None
    assert finding.confidence == 0.0


def test_recalculate_finding_with_page_none_degrades_without_exception(contract_setup):
    session = contract_setup["session"]
    document = contract_setup["document"]
    rule = contract_setup["rule"]
    analysis = contract_setup["analysis"]

    finding = Finding(
        analysis_id=analysis.id,
        rule_id=rule.id,
        status="cumple",
        justification="Hallazgo previo con pagina definida.",
        evidence_text="algo",
        page=None,
        bbox_x0=RECT_DATA_PROTECTION.x0,
        bbox_y0=RECT_DATA_PROTECTION.y0,
        bbox_x1=RECT_DATA_PROTECTION.x1,
        bbox_y1=RECT_DATA_PROTECTION.y1,
        confidence=0.9,
        severity=rule.severity,
    )
    session.add(finding)
    session.commit()
    session.refresh(finding)

    # No debe lanzar excepción aunque falte 'page'.
    recalculate_finding(session, finding, document, rule)

    assert finding.status == "requiere_revision"
    assert finding.evidence_text is None
    assert finding.confidence == 0.0
