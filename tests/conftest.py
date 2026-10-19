"""Fixtures de PDFs reutilizables para las pruebas de `app.pdf.*`.

`demo_pdf_path` construye, con PyMuPDF (`fitz`), un PDF de 2 páginas en
tamaño A4 (595 x 842 puntos PDF; origen arriba-izquierda, eje Y hacia
abajo) y lo guarda en `tmp_path`:

- Página 1 (texto nativo real, en español): un título de cláusula y dos
  líneas de cuerpo, insertados con `page.insert_text(punto, texto, ...)`.
  Los puntos de inserción (esquina inferior-izquierda del texto, según la
  convención de `insert_text`) quedan documentados abajo en
  `TITLE_POINT` / `LINE1_POINT` / `LINE2_POINT`. Los tests NO hardcodean
  el bbox exacto resultante (depende de métricas de la fuente base14):
  en su lugar usan `page.search_for(texto)` sobre el propio PDF de fixture
  para obtener el rect real antes de aserar contra él, lo cual es más
  robusto y sigue siendo trazable a coordenadas conocidas.
- Página 2 (sin texto ni imágenes): completamente en blanco, para forzar
  el camino `is_scanned=True` / `any_scanned_without_ocr=True` de
  `extract_document` (dado que en este entorno no hay `pytesseract`/
  `Pillow` instalados y por tanto `ocr_available()` es `False`).
"""
from __future__ import annotations

import fitz
import pytest

PAGE_WIDTH = 595.0
PAGE_HEIGHT = 842.0

TITLE_TEXT = "Clausula 5. Tratamiento de datos personales"
LINE1_TEXT = (
    "El proveedor no podra subcontratar el tratamiento de datos personales "
    "sin autorizacion previa del cliente."
)
LINE2_TEXT = "El cliente conservara la titularidad de dichos datos en todo momento."

# Puntos de inserción (x, y) en puntos PDF, esquina inferior-izquierda del
# texto insertado (convención de `Page.insert_text`).
TITLE_POINT = (72, 100)
LINE1_POINT = (72, 140)
LINE2_POINT = (72, 160)

# Zona deliberadamente vacía de la página 1 (sin ningún texto insertado
# cerca), usada para probar `extract_text_in_bbox` sobre blanco.
BLANK_AREA_BBOX = (50.0, 700.0, 200.0, 750.0)


@pytest.fixture()
def demo_pdf_path(tmp_path) -> str:
    """Genera el PDF de fixture (2 páginas) y devuelve su ruta en tmp_path."""
    doc = fitz.open()
    try:
        page1 = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        page1.insert_text(TITLE_POINT, TITLE_TEXT, fontsize=14)
        page1.insert_text(LINE1_POINT, LINE1_TEXT, fontsize=11)
        page1.insert_text(LINE2_POINT, LINE2_TEXT, fontsize=11)

        # Página 2: en blanco a propósito (simula una página escaneada sin
        # capa de texto ni imagen incrustada).
        doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)

        path = tmp_path / "demo_contract.pdf"
        doc.save(str(path))
        return str(path)
    finally:
        doc.close()


@pytest.fixture(autouse=True)
def _offline_providers(monkeypatch):
    """Las pruebas nunca llaman a proveedores externos aunque el `.env` local tenga
    LLM_PROVIDER=groq, APP_ENV=production o claves reales: se fuerzan valores de desarrollo y proveedores locales."""
    from app.config import settings

    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "embedding_provider", "mock")
    monkeypatch.setattr(settings, "auth_mode", "local")
    monkeypatch.setattr(settings, "app_env", "development")  # el .env real puede decir production (cookies Secure)


@pytest.fixture(autouse=True)
def _legacy_ui_by_default(tmp_path_factory, monkeypatch):
    """Las pruebas no dependen de que exista `frontend/dist` (artefacto de build, ignorado por git):
    por defecto se sirve la UI clásica. Las pruebas de la SPA apuntan FRONTEND_DIST a un dist de juguete."""
    import app.main as main_module

    monkeypatch.setattr(main_module, "FRONTEND_DIST", tmp_path_factory.mktemp("sin-dist") / "dist")
