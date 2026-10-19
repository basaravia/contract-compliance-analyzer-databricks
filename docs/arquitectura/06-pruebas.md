# 06 · Pruebas end-to-end del backend

## Cómo correrlas
```bash
.venv/bin/python -m pytest -q                       # todo, offline, ~4 s, sin red ni claves
RUN_GROQ_E2E=1 .venv/bin/python -m pytest -q tests/test_e2e_backend.py -k real_groq   # opt-in: Groq real
```
**Resultado actual:** 140 pasan, 1 omitida (la de Groq real, opt-in; también pasa cuando se activa).

Las pruebas **nunca** llaman a proveedores externos aunque el `.env` tenga `LLM_PROVIDER=groq`:
`tests/conftest.py` fuerza `mock` en cada prueba (`_offline_providers`). Usan BD SQLite y carpeta de
subidas temporales; no tocan `data/app.db`.

## Qué cubren
| Archivo | Nivel | Qué verifica |
|---|---|---|
| `tests/test_workpaper.py` (24) | Unitario | `classify_search` (12 combinaciones), `verify_literal` (espacios, mayúsculas, cita inventada, página mal indicada), baja a V si la cita no es literal, conteos y conclusión deterministas, estructura del Excel, Hoja 1 = Hoja 2, inyección de fórmulas (4 cargas), truncado y caracteres ilegales |
| `tests/test_e2e_backend.py` (25) | HTTP real (TestClient) | ver tabla siguiente |
| `tests/test_llm_groq.py` (5) | Unitario | adaptador Groq con transporte simulado: éxito, HTTP 429, JSON inválido, página fuera de los fragmentos, sin clave → mock |

### Escenarios end-to-end
| Escenario | Esperado |
|---|---|
| Subir contrato → importar 3 reglas → analizar | 201; 3 hallazgos; cada uno con traza (`extraction.method=native`, fragmentos recuperados); `analysis_trace` con proveedor y `rules_evaluated=3` |
| Contrato con 2 cláusulas y 1 regla **ausente** (garantía de hardware) | papel: la regla ausente = **N** con «No se encontró en el contrato…»; las presentes ≠ N y con `(p. 1)` |
| Contrato **sin relación** con las reglas | las 3 reglas = **N** |
| Contrato **escaneado** (página en blanco) | las 3 reglas = **V**, «no se pudo buscar» (no se afirma que algo «no está») |
| Toda evidencia citada | es subcadena literal del texto del PDF |
| Coherencia entre hojas | misma marca por regla en Hoja 1 y Hoja 2; proveedor en la cabecera del anexo |
| Editar un hallazgo (PATCH) | el papel lo refleja («editado manualmente») |
| Errores | análisis inexistente 404; sin reglas activas 400; documento no-contrato 400; no-PDF y PDF corrupto 400; sin token CSRF 403 |
| UI | la página servida incluye el botón «Descargar papel de trabajo (Excel)» |
| **2ª pasada: halla lo que la 1ª perdió** | cláusula fuera del top-2 → `found`, marca A; llamadas al evaluador `[2, 9]` |
| 2ª pasada: ausencia confirmada | recorre los 8 fragmentos → `confirmed_absent`, marca N, anexo «8 / 8» |
| 2ª pasada: no se gasta si no hace falta | contrato de 3 fragmentos ya visto entero → 1 sola llamada |
| 2ª pasada: contrato mayor que el tope | `partial_scan`, marca N con aviso «NO exhaustiva» |
| 2ª pasada desactivada / regla con evidencia | 1 sola llamada, sin `second_pass` |
| 2ª pasada que falla | marca **V**, nunca N |
| **Groq real** (opt-in) | cláusula ausente → N o V; cláusula de datos personales → A o L |

## Verificación de que las pruebas detectan fallos (mutaciones)
Se sabotearon dos decisiones a propósito y se comprobó que las pruebas fallan; luego se restauró:

| Sabotaje | Resultado |
|---|---|
| «No encontrado» devuelve R en vez de N | 7 pruebas fallan |
| `verify_literal` siempre responde «verificada» | 2 pruebas fallan |
| La segunda pasada nunca se activa | 5 pruebas fallan |

## Lo que NO prueban (límites honestos)
- La **calidad semántica** de la búsqueda: con embeddings `mock` la recuperación es léxica. La prueba
  de Groq real usa un contrato de 2 páginas donde casi todo cabe en el `top_k`.
- Contratos largos (decenas de páginas) ni rendimiento: el análisis es síncrono.
- PDFs escaneados **con** OCR (Tesseract no está instalado en el entorno de pruebas).
- Apertura del `.xlsx` en Excel/LibreOffice (se valida con openpyxl; ver doc 07).
- Docker (`docker compose up`) y la SPA en un navegador (solo se verifica por HTTP).
