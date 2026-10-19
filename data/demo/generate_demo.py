"""Genera un PDF de contrato ficticio para demostrar el Analizador de
Cumplimiento Contractual.

Este documento y sus cláusulas son enteramente inventados con fines de
demostración técnica. NO son un contrato real, NO constituyen asesoría legal
y NO deben usarse como plantilla contractual. Las referencias a la LOPDP de
Ecuador son solo temáticas/ilustrativas: este script no reproduce artículos
verificados de ninguna norma.

Uso::

    python data/demo/generate_demo.py

Genera ``data/demo/contrato_demo.pdf`` (2-3 páginas, español) con cláusulas
deliberadamente variadas para poder demostrar los distintos estados de
hallazgo del motor de análisis:

- Una cláusula que cumple razonablemente una regla típica de protección de
  datos (compromiso explícito de tratamiento conforme a la normativa).
- Una cláusula ambigua (plazo de notificación de incidentes "razonable",
  sin cifra concreta).
- Una obligación completamente ausente (no se menciona transferencia
  internacional de datos en ningún punto del contrato).
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

OUTPUT_PATH = Path(__file__).resolve().parent / "contrato_demo.pdf"

PAGE_1 = """CONTRATO DE PRESTACIÓN DE SERVICIOS DE PROCESAMIENTO DE DATOS
(DOCUMENTO FICTICIO DE DEMOSTRACIÓN — NO ES UN CONTRATO REAL)

Entre COMPRADOR DEMO S.A., con domicilio en Quito, Ecuador (en adelante, "el Cliente"),
y PROVEEDOR DEMO CLOUD CIA. LTDA. (en adelante, "el Proveedor"), se celebra el presente
contrato de prestación de servicios de procesamiento de datos, sujeto a las siguientes
cláusulas:

PRIMERA. OBJETO DEL CONTRATO
El Proveedor prestará al Cliente servicios de alojamiento y procesamiento de datos en
la nube para la operación de la plataforma administrativa del Cliente, según el Anexo
Técnico A.

SEGUNDA. PROTECCIÓN DE DATOS PERSONALES
El Proveedor se compromete a tratar los datos personales a los que tenga acceso con
motivo de la prestación de los servicios exclusivamente para las finalidades descritas
en este contrato, conforme a los principios de licitud, finalidad, proporcionalidad y
transparencia establecidos en la Ley Orgánica de Protección de Datos Personales
(LOPDP) del Ecuador. El Proveedor implementará medidas técnicas y organizativas
razonables para garantizar la confidencialidad, integridad y disponibilidad de los
datos tratados, y no los utilizará para fines distintos a los aquí pactados.

TERCERA. ENCARGADO DEL TRATAMIENTO
Para efectos de este contrato, el Proveedor actuará como Encargado del Tratamiento y
el Cliente como Responsable del Tratamiento, en los términos de la normativa de
protección de datos aplicable. El Proveedor únicamente tratará los datos siguiendo
las instrucciones documentadas del Cliente.
"""

PAGE_2 = """CUARTA. NOTIFICACIÓN DE INCIDENTES DE SEGURIDAD
En caso de que el Proveedor detecte un incidente de seguridad que afecte datos
personales tratados en virtud de este contrato, notificará al Cliente en un plazo
razonable, considerando la naturaleza del incidente y las circunstancias del caso.
Las partes acuerdan colaborar de buena fe para mitigar los efectos del incidente.

QUINTA. ELIMINACIÓN DE DATOS AL FINALIZAR EL CONTRATO
Al término de la vigencia de este contrato, cualquiera sea su causa, el Proveedor
eliminará de forma segura todos los datos personales del Cliente que obren en su
poder en un plazo máximo de treinta (30) días calendario, salvo obligación legal de
conservación, y entregará constancia escrita de dicha eliminación al Cliente.

SEXTA. DERECHO DE AUDITORÍA
El Cliente podrá solicitar información al Proveedor sobre las medidas de seguridad
implementadas para el tratamiento de los datos personales, la cual será proporcionada
por el Proveedor dentro de un plazo razonable a solicitud escrita del Cliente.

SÉPTIMA. CONFIDENCIALIDAD
Ambas partes se obligan a mantener confidencialidad respecto de la información no
pública a la que tengan acceso con motivo de la ejecución de este contrato, obligación
que subsistirá por dos (2) años después de finalizado el mismo.
"""

PAGE_3 = """OCTAVA. VIGENCIA Y TERMINACIÓN
El presente contrato tendrá una vigencia de doce (12) meses, renovable
automáticamente por períodos iguales salvo notificación en contrario de cualquiera
de las partes con al menos treinta (30) días de anticipación al vencimiento.

NOVENA. LEY APLICABLE Y JURISDICCIÓN
Este contrato se rige por las leyes de la República del Ecuador. Cualquier
controversia derivada de su interpretación o ejecución se someterá a los jueces
competentes del domicilio del Cliente.

DÉCIMA. DISPOSICIONES GENERALES
Este documento no contiene cláusula alguna relativa a transferencias internacionales
de datos personales fuera del territorio ecuatoriano, dado que, para efectos de esta
demostración, el Proveedor declara prestar los servicios íntegramente desde
infraestructura ubicada en el país.

Firmado por las partes en Quito, a los efectos de esta demostración técnica.


_____________________________          _____________________________
Por EL CLIENTE (documento ficticio)     Por EL PROVEEDOR (documento ficticio)
"""


def build_pdf(output_path: Path = OUTPUT_PATH) -> Path:
    doc = fitz.open()
    for page_text in (PAGE_1, PAGE_2, PAGE_3):
        page = doc.new_page(width=595, height=842)  # A4 en puntos
        rect = fitz.Rect(56, 56, 595 - 56, 842 - 56)
        page.insert_textbox(rect, page_text, fontsize=10.5, fontname="helv", align=0)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    doc.close()
    return output_path


if __name__ == "__main__":
    path = build_pdf()
    print(f"PDF de demostración generado en: {path}")
