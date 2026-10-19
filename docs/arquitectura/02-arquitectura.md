# 02 · Arquitectura

## C4 nivel 1 — Contexto
Un auditor usa la app desde el navegador. En ejecución hay **una dependencia externa opcional**: el
proveedor del LLM (Groq hoy). Con `LLM_PROVIDER=mock` no sale nada de la máquina.

```mermaid
flowchart LR
    auditor(["👤 Auditor<br/><i>Sube contrato y reglas,<br/>revisa hallazgos, descarga el papel</i>"])
    app["<b>Analizador de Cumplimiento</b><br/>[FastAPI, 1 proceso]<br/>Extracción, búsqueda, evaluación<br/>y papel de trabajo"]
    llm["<b>Proveedor LLM</b><br/>[Groq · API OpenAI-compatible]<br/><i>opcional; vertex sin probar</i>"]
    xlsx[/"<b>Papel de trabajo .xlsx</b><br/>Entregable de auditoría"/]
    auditor -- "HTTPS" --> app
    app -- "Reglas + fragmentos recuperados<br/>(HTTPS, solo con LLM_PROVIDER=groq)" --> llm
    app -- "Genera (0 tokens)" --> xlsx
    xlsx -- "Descarga" --> auditor
```
**Dato que sale a Groq:** la regla y los (máx. 5) fragmentos del contrato recuperados para ella; no el PDF completo.

## C4 nivel 2 — Contenedores y componentes
```mermaid
flowchart TB
    auditor(["👤 Auditor"])
    subgraph APP["Proceso uvicorn · app.main"]
        spa["<b>SPA</b> JS vanilla<br/>app/static + templates<br/>CSP estricta, sin CDN"]
        api["<b>Routers FastAPI</b><br/>documents · rules · analyses · findings"]
        ext["<b>Extracción</b> app/pdf/extract.py<br/>PyMuPDF · OCR opcional"]
        chk["<b>Fragmentación</b> app/chunking.py<br/>≤800 car. con bbox"]
        idx["<b>Recuperación</b> app/retrieval<br/>embeddings (mock|vertex) + FAISS IndexFlatIP"]
        eng["<b>Motor</b> app/analysis_engine.py<br/>orquesta; escribe trazas"]
        ev["<b>Evaluador</b> app/llm<br/>mock | groq | vertex<br/>salida validada (Pydantic)"]
        wp["<b>Papel de trabajo</b> app/output<br/>assemble.py + workpaper.py · openpyxl · 0 tokens"]
        db[("<b>SQLite</b> data/app.db<br/>documents · rules · analyses · findings")]
        fs[("<b>Subidas</b> data/uploads/*.pdf")]
    end
    groq["Groq API"]
    auditor --> spa --> api
    api --> ext --> chk --> idx --> eng --> ev
    api <--> db
    api <--> fs
    ev -. "solo si LLM_PROVIDER=groq" .-> groq
    eng --> db
    api --> wp
    wp -- "lee hallazgos + texto del PDF" --> db
    wp --> fs
```

| Componente | Responsabilidad | Tecnología |
|---|---|---|
| Routers | REST `/api/*`, validación, CSRF doble-cookie, cabeceras de seguridad | FastAPI, Pydantic v2 |
| Extracción | Texto por bloque con bbox (puntos PDF, origen arriba-izquierda); marca páginas escaneadas | PyMuPDF; Tesseract opcional |
| Fragmentación | Párrafos ≤ 800 caracteres, cada uno con su bbox | `app/chunking.py` |
| Recuperación | Un índice FAISS por análisis; consulta = «nombre. descripción» de la regla; `top_k = 5` | numpy, faiss-cpu |
| Evaluador | Veredicto por regla sobre los fragmentos; degrada a `requiere_revision` ante error | `app/llm/*` |
| Motor | Orquesta y persiste un `Finding` por regla con su `FindingTrace` y el `AnalysisTrace` | `app/analysis_engine.py` |
| **Papel de trabajo** | Clasifica el resultado de la búsqueda, verifica citas y arma el Excel | `app/output/*`, openpyxl |
| Persistencia | SQLite (migrable a PostgreSQL) + PDFs en disco | SQLAlchemy 2 |

## Flujo extremo a extremo
```mermaid
sequenceDiagram
    actor U as Auditor
    participant API as API
    participant E as Motor
    participant R as Recuperación (FAISS)
    participant L as Evaluador (LLM)
    participant W as Papel de trabajo
    U->>API: POST /api/documents (contrato.pdf)
    API->>API: valida PDF, extrae texto + páginas
    U->>API: POST /api/rules/import (reglas)
    U->>API: POST /api/analyses {contrato}
    API->>E: run_analysis
    E->>E: fragmenta + embeddings + índice FAISS
    loop por cada regla activa
        E->>R: buscar top-5 fragmentos
        R-->>E: fragmentos + score
        E->>L: regla + fragmentos
        L-->>E: {status, evidencia, página, bbox, justificación}
        E->>E: valida anclaje (página citada ∈ fragmentos) y guarda Finding + traza
    end
    U->>API: GET /api/analyses/{id}/papel-trabajo.xlsx
    API->>W: build_input → enrich → build_workpaper
    W->>W: classify_search + verify_literal (sin modelo)
    W-->>U: .xlsx (Hoja 1 + Hoja 2)
```

## Stack
| Capa | Elección | Notas |
|---|---|---|
| Runtime | Python 3.13 en desarrollo (el proyecto pide ≥ 3.12) | Docker `python:3.12-slim` |
| API | fastapi, uvicorn (1 worker), pydantic v2 | Estado en BD, no en memoria |
| PDF | PyMuPDF | texto, bbox, render, PDF anotado |
| Vectores | faiss-cpu + numpy | `IndexFlatIP` sobre vectores normalizados ≈ coseno |
| LLM | `httpx` directo a Groq (OpenAI-compatible) | sin SDK; sin dependencias nuevas |
| Excel | **openpyxl** (dependencia nueva de esta rama) | justificada: el papel es el entregable |
| Pruebas | pytest, httpx/TestClient | 140 pasan + 1 opt-in |
