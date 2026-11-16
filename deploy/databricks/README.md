# Desplegar en Databricks Apps

```
Usuario ──SSO del workspace──► proxy de Databricks Apps ──► app (FastAPI + React, uvicorn)
                               (inyecta X-Forwarded-Email)     │
                                                               ├─► SQLite en /tmp/ccap   reglas, análisis, hallazgos (efímero)
                                                               ├─► /tmp/ccap/uploads     PDF subidos (efímero)
                                                               └─► Azure AI Foundry      LLM y embeddings (token por recurso secreto)
```

La app **no tiene login propio**: la plataforma autentica (`AUTH_MODE=databricks`) y la app solo lee la identidad
de las cabeceras del proxy. CSRF (cookie doble-envío) se mantiene en todas las escrituras.

## Archivos

| Archivo | Para qué |
|---|---|
| `app.yaml` | Comando de arranque (`uvicorn app.main:app --workers 1`) y variables de entorno. |
| `deploy/databricks/deploy_app.py` | Notebook (SDK de Python): carpeta Git, app + recurso secreto y `deploy_and_wait`. |
| `frontend/dist/` | Build de React, versionado para no necesitar Node en el workspace. |

## Antes de desplegar

1. **Secreto con el token de Foundry** en un scope de secretos (solo CLI/API; la UI no crea secretos):
   `databricks secrets put-secret <scope> <clave>`.
2. **Valores de Foundry en `app.yaml`**: reemplaza los `REEMPLAZAR-…` (endpoint, api-version, deployment del LLM y
   deployment de embeddings `text-embedding-3-large`). Con placeholders la app se niega a arrancar. El repo es
   público: edita estos valores solo en la copia del workspace.
3. **Recurso de la app**: tipo secreto, *Resource key* `foundry-token` (debe coincidir con `valueFrom` de `app.yaml`),
   permiso *Can read*.

## Desplegar

Importa `deploy/databricks/deploy_app.py` como notebook y ejecútalo, o hazlo a mano: *Create → Git folder* con la URL
del repo (público, sin token), *Compute → Apps → Create app* con el recurso secreto y *Deploy* desde la carpeta Git.
El notebook crea la app solo si no existe y muestra el error del despliegue si falla. Los logs: `databricks apps logs <app>`.
El workspace permite un máximo de apps; si el alta falla por cupo, elimina una.

## Operación

- **Datos efímeros.** BD y PDF viven en el disco del contenedor y se pierden al reiniciar, redesplegar o cuando
  Databricks apaga la app por inactividad. Las reglas se reimportan desde la pantalla de reglas y los contratos se
  vuelven a subir.
- **Un solo worker y un análisis a la vez** (el bloqueo vive en memoria del proceso).
- **El análisis es síncrono**: con muchas reglas puede acercarse al tiempo máximo de petición del proxy.
- **Un solo tenant**: toda persona con `CAN_USE` ve todos los documentos y análisis.
- **Embeddings** de Foundry (3072 dim) indexados con FAISS dentro de la app. Si falta configuración o Foundry falla,
  el análisis falla con error visible; no hay respaldo silencioso a `mock`. Con otro modelo, ajusta `FOUNDRY_EMBED_DIM`.
- Si el deployment no admite `response_format: json_object`, los hallazgos saldrán como «requiere revisión».
- Con GPT-5.x deja `FOUNDRY_OMIT_TEMPERATURE=true`; con GPT-4.x ponlo en `false`.
