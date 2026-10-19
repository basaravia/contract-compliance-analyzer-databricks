# 05 · API

Todas las mutaciones exigen la cabecera `X-CSRF-Token` igual a la cookie `ccap_csrf` (se obtiene con
`GET /`). Con `AUTH_MODE=databricks` u `oidc` **toda** ruta `/api/*` exige sesión (`401` sin ella); `AUTH_MODE=local` no pide login (solo desarrollo y la app se niega a arrancar así fuera de `development`).

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/healthz` | Estado (público) |
| GET | `/login` | Redirige a `/` (SSO de Databricks) o a `/auth/login` (OIDC) |
| POST | `/auth/logout` | Cierra la sesión en el navegador |
| GET | `/auth/me` | Usuario de la sesión (`401` sin sesión) |
| POST | `/api/documents` | Sube PDF (`multipart`: `doc_type` = `contrato`\|`normativa`, `file`). Valida firma `%PDF`, tamaño y legibilidad |
| GET | `/api/documents`, `/api/documents/{id}` | Lista / detalle |
| GET | `/api/documents/{id}/pages/{n}.png` | Página renderizada |
| DELETE | `/api/documents/{id}` | Borra |
| POST | `/api/rules`, `/api/rules/import`, `/api/rules/import-text` | Crea una regla / importa JSON `{"rules":[…]}` / importa texto natural |
| GET/PUT/DELETE | `/api/rules`, `/api/rules/{id}` | CRUD |
| POST | `/api/analyses` | `{contract_document_id, rule_ids?}` (vacío = todas las activas). **Síncrono** |
| GET | `/api/analyses`, `/api/analyses/{id}` | Lista / detalle con hallazgos y trazas |
| GET | `/api/analyses/{id}/export.pdf` | PDF anotado con los bbox |
| GET | `/api/analyses/{id}/export.json` | Detalle en JSON |
| **GET** | **`/api/analyses/{id}/papel-trabajo.xlsx`** | **Papel de trabajo (nuevo en esta rama)** |
| POST/PATCH/DELETE | `/api/findings`, `/api/findings/{id}` | Anotación manual / corrección (con `recalculate`) / borrado |

Errores comunes: `400` PDF inválido, documento que no es contrato o sin reglas activas · `403` CSRF ·
`404` análisis/documento inexistente.

Formato de una regla importada:
```json
{"rules":[{"name":"…","description":"…","severity":"alta|media|baja","category":"…",
           "references":[{"citation":"LOPDP Art. 5","page":null}]}]}
```
