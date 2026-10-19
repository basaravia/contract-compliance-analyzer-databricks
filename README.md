# Analizador de Cumplimiento Contractual (MVP)

Aviso legal: esta herramienta es un MVP técnico de apoyo a la revisión de contratos.
**No constituye asesoría legal.** Sus resultados (`cumple`, `no_cumple`, `parcial`,
`no_determinable`, `requiere_revision`) son evaluaciones automatizadas o mock,
explicables y editables por una persona, pero siempre deben ser revisadas y
validadas por un profesional del derecho antes de tomar cualquier decisión. Los
datos de ejemplo incluidos en `data/demo/` son ficticios y las referencias a la
LOPDP de Ecuador son ilustrativas, no un catálogo normativo verificado.

## Qué es

Permite subir un documento normativo y un contrato en PDF, definir reglas de
cumplimiento (manualmente, en JSON o en texto natural), ejecutar un análisis que
evalúa cada regla contra el contrato, y revisar/corregir cada hallazgo de forma
visual sobre el propio PDF: cada hallazgo queda anclado a una página y a un
recuadro (bbox) concreto, de modo que la evidencia siempre es trazable hasta el
texto exacto del contrato que la sustenta. Las correcciones manuales del bbox
disparan un recálculo real de la evidencia y del estado del hallazgo (no se
copia el resultado anterior).

Componentes principales:

- **Ingestión y extracción**: PyMuPDF para texto/páginas/coordenadas; OCR opcional
  para PDFs escaneados.
- **Reglas**: CRUD + importación masiva (JSON o texto en lenguaje natural),
  versionadas y editables, con referencias normativas (cita + página opcional).
- **Recuperación (RAG)**: fragmentación del contrato + índice FAISS para acercar
  el texto relevante a cada regla antes de evaluarla.
- **Evaluación**: salida estructurada validada con Pydantic
  (`app/schemas.py::RuleEvaluationResult`); si la evidencia falta o la salida no
  es válida, se degrada a `no_determinable`/`requiere_revision` en vez de
  inventar una conclusión.
- **Persistencia**: SQLite por defecto (migrable a PostgreSQL sin cambios de
  esquema).
- **Anotación**: edición manual de hallazgos (mover/redimensionar/crear/eliminar
  bbox) con recálculo real de evidencia, y exportación a PDF anotado y JSON.
- **Frontend**: SPA en JavaScript vanilla (sin frameworks ni CDNs), servida por
  el propio backend, compatible con la CSP estricta del proyecto.

## Arranque en local (sin credenciales)

Requisitos: Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env             # valores por defecto ya sirven para desarrollo local

uvicorn app.main:app --reload
```

Abre `http://localhost:8000`. Por defecto `AUTH_MODE=local`: no hace falta ninguna
credencial, todas las peticiones se atribuyen a un usuario de desarrollo fijo.
**Nunca uses `AUTH_MODE=local` en producción.**

### Datos de demostración

Para probar el flujo completo rápidamente:

1. En la pestaña **Documentos**, sube `data/demo/contrato_demo.pdf` como tipo
   `contrato` (regenéralo con `python data/demo/generate_demo.py` si quieres
   modificarlo).
2. En la pestaña **Reglas → Importar JSON**, sube `data/demo/reglas_demo.json`
   (reglas de ejemplo ilustrativas, no un catálogo normativo verificado).
3. En la pestaña **Análisis**, elige el contrato subido y ejecuta el análisis.
4. Abre **Revisión visual** para ver los hallazgos anclados sobre el PDF, mover o
   redimensionar sus recuadros (dispara un recálculo real de evidencia/estado),
   crear anotaciones nuevas o eliminarlas, y exportar el PDF anotado o el JSON.

## Frontend (React) y Databricks Apps

El frontend nuevo vive en `frontend/` (React + Vite + TypeScript). Si existe `frontend/dist`, FastAPI lo sirve en `/`;
si no, cae a la UI clásica de `app/static`.

```bash
cd frontend && npm ci && npm run build      # genera frontend/dist
npm run dev                                 # desarrollo con recarga (proxy al backend en :8000, AUTH_MODE=local)
npm test                                    # vitest
```

Para desplegar en Databricks Apps (SSO del workspace y Azure AI Foundry; sin Lakebase ni Volume, datos efímeros) ver
[`deploy/databricks/README.md`](deploy/databricks/README.md).

## Tests

```bash
.venv/bin/python -m pytest -q
```

Cubren extracción/OCR/coordenadas/render/anotación de PDF, parseo de reglas en
texto natural, recuperación (FAISS), el evaluador mock y el motor de análisis
completo, incluido el recálculo de hallazgos tras editar un bbox.

## Proveedores opcionales

Por defecto el sistema funciona íntegramente con proveedores **mock/locales**
(sin llamadas externas ni credenciales), tanto para embeddings como para el LLM
evaluador. Esto es lo recomendado para desarrollo y para esta demo.

### Vertex AI (Gemini) para embeddings y evaluación LLM real

1. Instala las dependencias opcionales (comentadas en `requirements.txt`):
   ```bash
   pip install google-cloud-aiplatform langchain-google-vertexai
   ```
2. En `.env`, configura:
   ```
   EMBEDDING_PROVIDER=vertex
   LLM_PROVIDER=vertex
   GOOGLE_CLOUD_PROJECT=<tu-proyecto>
   GOOGLE_CLOUD_LOCATION=us-central1
   VERTEX_EMBEDDING_MODEL=gemini-embedding-001
   VERTEX_LLM_MODEL=gemini-3.6-flash
   GOOGLE_APPLICATION_CREDENTIALS=/ruta/a/tu/credencial.json
   ```
3. Ninguna credencial se guarda en el repositorio; `.env` está en `.gitignore`.
   Si las dependencias o credenciales no están disponibles, el sistema debe
   seguir arrancando usando los proveedores mock (no debe romper el arranque).

### OCR para PDFs escaneados

1. Instala Tesseract a nivel de sistema operativo (paquete `tesseract-ocr`) y
   las dependencias Python opcionales:
   ```bash
   pip install pytesseract Pillow
   ```
2. Sin estas dependencias, las páginas sin texto extraíble se marcan como
   `scanned_no_ocr` y las reglas correspondientes quedan en `no_determinable`
   en vez de fallar o inventar evidencia.

### Autenticación OIDC (Microsoft Entra ID)

Para un despliegue real (no solo demo local), cambia `AUTH_MODE=oidc` y
configura `OIDC_TENANT_ID`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` y
`OIDC_REDIRECT_URI` en `.env`. El backend valida la firma del `id_token`
contra el JWKS publicado por Entra ID; nunca confía en el token sin verificar
su firma, `iss`, `aud`, `exp` y `nonce`.

## Modelo de datos / estados de hallazgo

Cada hallazgo (`Finding`) queda asociado a una regla y a un análisis, y tiene:

- `status`: uno de `cumple`, `no_cumple`, `parcial`, `no_determinable`,
  `requiere_revision`.
- `justification` / `evidence_text`: explicación y texto literal citado del
  contrato.
- `page` + `bbox_x0/y0/x1/y1`: ubicación exacta en el PDF (coordenadas en
  puntos PDF, origen esquina superior izquierda), o `null` si no hay evidencia
  localizable.
- `confidence`, `severity`, `is_manual`, `edited`: metadatos de trazabilidad.
- `normative_refs`: referencias normativas heredadas de la regla evaluada.

Editar el bbox de un hallazgo y enviar `recalculate: true` hace que el backend
vuelva a extraer el texto bajo el nuevo recuadro y reevalúe realmente la regla
con esa evidencia (no reutiliza el resultado anterior); si el área queda vacía
o es solo imagen sin OCR, el hallazgo se marca `requiere_revision`.

## Docker

```bash
cp .env.example .env   # ajusta según necesites
docker compose up --build
```

Monta `./data` como volumen para persistir `data/app.db` y `data/uploads` fuera
del contenedor. No se incluyen secretos en la imagen; las variables de entorno
se leen de `.env` (fuera del control de versiones).

## Limitaciones conocidas del MVP

- El análisis se ejecuta de forma **síncrona** dentro de la petición HTTP
  (`POST /api/analyses`); para contratos muy largos o muchas reglas, esto puede
  tardar y no hay cola de trabajos en segundo plano.
- El proveedor por defecto de embeddings/LLM es **mock**: para evaluaciones
  reales con un modelo de lenguaje hace falta configurar Vertex AI (ver
  arriba); el resultado de un LLM real debe seguir tratándose como apoyo, no
  como conclusión jurídica definitiva.
- El OCR es opcional y best-effort: sin `pytesseract`/`Pillow`/`tesseract-ocr`
  instalados, las páginas escaneadas sin texto quedan en
  `scanned_no_ocr` / `no_determinable`.
- No hay control de acceso por roles (todo usuario autenticado tiene acceso a
  todos los documentos/reglas/análisis); es un MVP de un solo tenant.
- La base de datos por defecto es SQLite (adecuada para demo/single-node); para
  producción con concurrencia alta se recomienda migrar a PostgreSQL (el
  esquema ya usa tipos estándar compatibles).
- Los datos de `data/demo/` son ficticios y no deben usarse como fuente
  normativa ni como plantilla contractual real.
