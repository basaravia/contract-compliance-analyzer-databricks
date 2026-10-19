# Desplegar en Databricks Apps

```
Usuario ──SSO del workspace──► proxy de Databricks Apps ──► app (FastAPI + React, run.py)
                               (inyecta X-Forwarded-Email)     │
                                                               ├─► SQLite en /tmp        reglas, análisis, hallazgos (efímero)
                                                               ├─► /tmp/ccap/uploads     PDF subidos (efímero)
                                                               └─► Azure AI Foundry      evaluación de reglas (token por recurso secreto)
```

La app **no tiene login propio**: la plataforma autentica (`AUTH_MODE=databricks`) y la app solo lee la identidad
de las cabeceras que el proxy añade. Se autentica contra los demás servicios como su **principal de servicio**
(sin tokens ni claves en el repo). Los permisos de ese principal son exactamente los recursos de `databricks.yml`.

## Qué trae el repo
| Archivo | Para qué |
|---|---|
| `app.yaml` | Comando de arranque y variables (`valueFrom` apunta a los recursos). |
| `databricks.yml` | Bundle: la app + recursos (secreto del token de Foundry, `READ`). |
| `run.py` | Escucha en `0.0.0.0:$DATABRICKS_APP_PORT`, 1 worker. |
| `frontend/` | React + Vite + TypeScript. `npm run build` → `frontend/dist`, que FastAPI sirve. |
| `scripts/deploy_databricks.sh` | Build + pruebas del frontend + `bundle validate/deploy/run`. |

## Requisitos previos (una sola vez)
1. **Databricks CLI** ≥ 0.250 autenticado: `databricks auth login --host https://<workspace>`.
2. Nada más: sin Lakebase ni Volume. Todo vive en el disco del contenedor.
3. **Token de Azure AI Foundry** en un scope de secretos (p. ej. `databricks secrets create-scope contratos` y
   `databricks secrets put-secret contratos foundry_ai_token`). El bundle lo expone a la app como recurso `foundry-token`.
4. En `app.yaml`, reemplaza los `REEMPLAZAR-…` (endpoint, api-version, deployment). No se versionan datos reales.
   `FOUNDRY_OMIT_TEMPERATURE=true` para GPT-5.x; `false` con GPT-4.x.
5. Node 20+ en la máquina que despliega.

## Desplegar
```bash
export BUNDLE_VAR_foundry_secret_scope=contratos
scripts/deploy_databricks.sh dev            # o prod
```
El script falla si falta alguna variable. Equivale a: `npm ci && npm test && npm run build` →
`databricks bundle validate|deploy|run`. La URL de la app aparece en la salida y en *Compute → Apps*.

**Quién entra:** en *Compute → Apps → la app → Permissions* concede `CAN_USE` solo a las personas/grupos que deban
usarla. Por defecto nadie más que el propietario puede abrirla.

## Verificar tras el primer despliegue
1. *Compute → Apps → Logs*: debe verse `Application startup complete` y ningún `RuntimeError: Configuración insegura`.
2. Abre la URL: arriba a la derecha debe mostrar `modo: databricks` y tu correo.
3. Sube `data/demo/contrato_demo.pdf` y comprueba que aparece en la lista.
4. Importa `data/demo/reglas_demo.json`, ejecuta un análisis y abre la revisión visual.
5. Comprueba que los hallazgos no salen todos «requiere revisión» (si es así, revisa los logs: variable o despliegue de Foundry mal puestos).

## Operación
| Tarea | Comando |
|---|---|
| Redesplegar | `scripts/deploy_databricks.sh <target>` |
| Logs | `databricks apps logs <target>-contract-analyzer` |
| Parar / arrancar | `databricks apps stop|start <target>-contract-analyzer` |
| Quitar todo | `databricks bundle destroy -t <target>` |

## Decisiones y límites conocidos
- **Datos efímeros.** BD y PDF están en el disco del contenedor; ver «Persistencia».
- **Un solo worker y un análisis a la vez.** El bloqueo «un análisis a la vez» vive en memoria del proceso.
- **El análisis es síncrono.** Con muchas reglas puede acercarse al tiempo máximo de petición del proxy de Apps.
  Si pasa, el siguiente paso es ejecutarlo como trabajo en segundo plano (Job o hilo + sondeo desde React).
- **Un solo tenant.** Toda persona con `CAN_USE` ve todos los documentos y análisis (igual que en la versión actual).
- **Sin login propio.** La autenticación es el SSO del workspace; esta rama no incluye login con contraseña.
- **`SECRET_KEY` no se usa** con `AUTH_MODE=databricks` (no se firma ninguna cookie de sesión).
- **CSRF se mantiene** (cookie doble-envío) en todas las escrituras.
- **Embeddings** son el proveedor local determinista (`mock`). Para calidad real, el siguiente paso es un
  deployment de embeddings de Foundry (`FOUNDRY_AI_EMBED_DEPLOYMENT`).

## Sin verificar contra un workspace real
Este despliegue se preparó sin un workspace autenticado (el perfil `DEFAULT` del CLI estaba caducado). Se comprobó
contra el esquema oficial del CLI (nombres de recursos y permisos), con pruebas del backend/frontend y con la SPA
en un navegador local, pero **no se ha ejecutado `databricks bundle deploy`**. Puntos a mirar en el primer despliegue:
- Si el deployment no admite `response_format: json_object`, los hallazgos saldrán como «requiere revisión» (se degrada, no inventa).
- Si Postgres rechaza `CREATE TABLE`, concede al principal de servicio de la app `CREATE` sobre el esquema `public`.
- Versión de Python del runtime de Apps: el código usa sintaxis de Python 3.10+.

## Persistencia (importante)

Esta configuración **no usa almacenamiento especial**: la BD (SQLite) y los PDF están en `/tmp/ccap` del
contenedor. Se pierden al reiniciar, redesplegar o cuando Databricks apaga la app por inactividad. Las reglas se
pueden reimportar desde la pantalla de reglas y los contratos volver a subir.

Persistencia opcional (el código ya la soporta, solo falta declarar el recurso en `databricks.yml` y `app.yaml`):
- PDF: recurso `uc_securable` (VOLUME, `WRITE_VOLUME`) + `UPLOAD_VOLUME_PATH` con `valueFrom`.
- BD: recurso `database` (Lakebase, `CAN_CONNECT_AND_CREATE`); al existir `PGHOST` la app deja SQLite.
