# 01 · Contexto y alcance

## Problema
Un auditor tiene un **conjunto de reglas** (obligaciones normativas, p. ej. LOPDP de Ecuador) y un
**contrato** en PDF. Necesita saber, regla por regla, si el contrato la atiende, con la evidencia
exacta, y **dejar constancia expresa de las reglas cuya cláusula no existe en el contrato**.

## Idea central
```
Reglas  ──►  buscar en el contrato  ──►  validar lo hallado  ──►  papel de trabajo (Excel)
              (recuperación)             (evaluador + control        2 hojas, 0 tokens
                                          de cita literal)
                       └── si no hay cláusula: «NO SE ENCONTRÓ» (resultado explícito)
```

Principios (heredados de v2, `CLAUDE.md` de ese repo):
1. **El modelo produce campos, el código produce formato.** El LLM solo devuelve JSON validado con
   Pydantic; marcas, conteos y Excel son Python determinista.
2. **Texto literal siempre.** Toda evidencia citada debe ser subcadena del texto extraído del
   contrato; si no, se marca y pasa a revisión. Nunca se parafrasea ni se inventa.
3. **No encontrar es un resultado, no un error.** Se distingue de «no cumple» y de «no se pudo buscar».
4. **Cada regla se evalúa una vez** por análisis y todas quedan en el anexo (sin selección sesgada).
5. **Trazable:** cada hallazgo guarda qué se recuperó, con qué score y con qué proveedor.

## Alcance del MVP (hoy)
| Entra | No entra (ver doc 07) |
|---|---|
| Subir contrato (PDF) y reglas (JSON / texto natural / formulario) | Cola de trabajos asíncrona (el análisis es síncrono) |
| Búsqueda RAG (fragmentos + FAISS) y evaluación por regla | Embeddings semánticos reales (hoy `mock`; Groq no ofrece embeddings) |
| Evaluador `mock` (local), `groq` (probado) o `vertex` (sin probar) | Comparar la norma contra el contrato (la regla es la fuente de verdad) |
| Revisión visual sobre el PDF y edición de hallazgos | Roles/permisos (un solo tenant; `AUTH_MODE=local` sin login) |
| Papel de trabajo Excel de 2 hojas, generado sin modelo | Conclusión redactada por LLM (hoy es determinista) |

> Aviso: herramienta de apoyo; no constituye asesoría legal. Todo resultado debe validarlo un profesional del derecho.
