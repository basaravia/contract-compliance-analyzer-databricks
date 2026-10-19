# 07 · Diferencias con v2 y puntos abiertos (para decidir juntos)

## A. Diferencias deliberadas con el papel de v2
| Tema | v2 (normas vs. manual) | Aquí (reglas vs. contrato) | Motivo |
|---|---|---|---|
| Marcas | A, L, R, X, P | **A, L, R, N, V** | X («no aplica») y P («información de la norma») no tienen sentido aquí; se añaden **N** (no encontrado) y **V** (revisar) |
| Unidad de la fila | un artículo de la norma | una regla | la regla es la fuente de verdad |
| Fila ↔ respaldo | norma → sección del manual | regla → cita del contrato | |
| Doble vía | norma→manual y manual→norma | solo regla→contrato | el contrato no tiene «controles sin base» que rastrear |
| Celdas combinadas col. 1 | por normativa/libro | no hay (una regla por fila) | |
| Conclusión | 1 llamada al LLM (120–220 palabras) | **determinista** (cifras + reglas por atender) | cero tokens; ver B3 |
| Modelos en pruebas | reales, nunca simulados | mock por defecto + 1 prueba opt-in con Groq real | el contrato de demo es ficticio y la Pi comparte recursos |
| Estado | en memoria | SQLite | ya existía |

## B. Puntos abiertos
| # | Pregunta | Recomendación |
|---|---|---|
| B1 | **¿«No encontrado» (N) separado de «No cumple» (R)?** Hoy N = no existe la cláusula; R = existe y no basta | Mantener separados: el auditor actúa distinto (pedir cláusula vs. renegociarla) |
| B2 | ~~Falso «no encontrado»~~ **Implementado** (doc 03, §3b): segunda pasada con hasta 40 fragmentos antes de declarar N | Pendiente de medir con contratos reales: ¿cuántos N de la 1ª pasada se convierten en hallazgos? (el campo `second_pass` lo permite). Con embeddings reales (B4) debería necesitarse menos |
| B3 | ¿Conclusión redactada por LLM como v2? | Opcional y editable; con el prefijo de borrador. No urgente |
| B4 | **Embeddings reales.** Groq no ofrece embeddings | Ollama `bge-m3` como en el sandbox de v2, **o** Vertex. Ojo con la RAM de la Pi (modelo ≈ 1–1,5 GB) |
| B5 | Reglas desde la norma: hoy se escriben a mano / JSON / texto natural | Extraer reglas de un PDF normativo con el seccionado de v2 (hito aparte) |
| B6 | Agrupar filas del papel por categoría o por norma (celdas combinadas) | Si el banco lo pide |
| B7 | Plantilla oficial del banco (brand kit, textos del encabezado) | Hoy: verde `1F6F4A` y objetivo estándar editable |
| B8 | Apertura sin advertencias en Excel real | Verificar a mano en Excel/LibreOffice (aquí solo se validó con openpyxl) |

## C. Hallazgos al validar el repo (para que quede constancia)
| # | Hallazgo | Estado |
|---|---|---|
| C1 | `FindingTrace` y `AnalysisTrace` existían en el esquema pero **el motor nunca los escribía** (la columna `trace` quedaba vacía) | **Corregido** en esta rama (`analysis_engine.py`) |
| C2 | Con `LLM_PROVIDER=groq` en `.env`, las pruebas existentes habrían llamado a Groq | **Corregido**: `conftest.py` fuerza mock |
| C3 | El prompt de Vertex/Groq pide `no_determinable`/`requiere_revision` si no hay evidencia; no existía el concepto «no se encuentra» | **Resuelto** en el papel con `classify_search` (sin cambiar el esquema ni la BD) |
| C4 | Sin login (`AUTH_MODE=local`) y con la clave de Groq en el servidor: cualquiera con acceso a la red puede gastar la clave | **Resuelto** en Databricks Apps: el SSO del workspace autentica antes de llegar a la app (ver `deploy/databricks/README.md`) |
| C5 | Los textos del contrato salen a Groq (reglas + hasta 5 fragmentos por regla) | Abierto: confirmar que está permitido con contratos reales |
| C6 | `datetime.utcnow()` y `import fitz` obsoletos | Abierto, menor |
| C7 | Tesseract no instalado: PDFs escaneados quedan en V | Abierto |
| C8 | Docker no probado (no se construyó la imagen por memoria) | Abierto |

## D. Cambios de esta rama (resumen)
Segunda pasada en `analysis_engine.py` (+ campos en `FindingTrace`, ajustes `SECOND_PASS_ENABLED` / `FULL_SCAN_MAX_CHUNKS`) · `app/output/{workpaper,assemble}.py` (nuevo) · `GET …/papel-trabajo.xlsx` · trazas del motor ·
botón en la SPA · dependencia `openpyxl` · `tests/{test_workpaper,test_e2e_backend}.py` ·
`tests/conftest.py` (proveedores offline) · esta carpeta `docs/arquitectura/`.
