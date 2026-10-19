# 04 · Papel de trabajo (salida Excel)

Entregable de auditoría. Mismo formato que v2 (`docs/10-papel-de-trabajo.md` de ese repo), adaptado a
**reglas vs. contrato**. Generado **100 % en Python** (openpyxl); `app/output/workpaper.py` no importa
nada de `app.llm`: **cero tokens**. Endpoint: `GET /api/analyses/{id}/papel-trabajo.xlsx`.

## Marcas de verificación
| Marca | Significado | Se origina cuando |
|---|---|---|
| **A** | Sí cumple | `cumple` con cita literal verificada |
| **L** | Parcialmente | `parcial` con cita literal verificada |
| **R** | No cumple | la cláusula **existe** y no satisface la regla |
| **N** | **No se encontró en el contrato** | sin evidencia y el contrato sí se leyó |
| **V** | Requiere revisión del auditor | no determinable, salida no confiable, cita no verificada |

Colores suaves: A verde `C6EFCE`, L ámbar `FFEB9C`, R rojo `F8CBAD`, N naranja `FCE4D6`, V azul `DDEBF7`.

## Hoja 1 — «Papel de trabajo»
**Encabezado** (10 filas, etiqueta fija + valor combinado): Nombre de la revisión *(en blanco)* ·
Nombre del papel *«Evaluación de cumplimiento contractual — {contrato}»* · Objetivo *(texto estándar)* ·
Corte o periodo *(en blanco)* · Fuente *(n.º de reglas, citas normativas y contrato)* · Marcas
*(leyenda)* · Conclusiones *(borrador determinista con prefijo «[Borrador generado automáticamente — validar]»)*
· Elaborado por / Revisado por *(en blanco)* · Fecha de ejecución.

**Matriz** — una fila por regla, en el orden en que se definió el análisis:

| # | Columna | Contenido |
|---|---|---|
| 1 | Regla / Referencia normativa | Nombre de la regla + citas (p. ej. «LOPDP Art. 5») |
| 2 | Requisito a validar | Descripción de la regla |
| 3 | Contrato (evidencia literal) | Cita literal y `(p. N)`. Si es N: «— No se encontró en el contrato una cláusula que atienda esta regla —». Si es no determinable: «— No se pudo buscar… —» |
| 4 | Verificación | Marca A/L/R/N/V, centrada, con color |
| 5 | Comentario | Justificación del evaluador |
| 6 | Referencias / Evidencias | Contrato y página, fragmentos revisados y mejor similitud, resultado de la segunda pasada («Ausencia confirmada: se revisó todo el contrato (N de N)», «Hallado al ampliar la búsqueda…», «búsqueda NO exhaustiva…»), confianza, avisos (cita no verificada, requiere revisión, editado manualmente) |

Formato: encabezado verde `1F6F4A` con texto blanco, `wrap_text`, alineación superior, paneles
congelados bajo el encabezado de la matriz (fila 12), anchos 30/45/50/12/45/32.

## Hoja 2 — «Anexo técnico»
Registra **todas** las reglas evaluadas (defiende que no hubo selección sesgada). Cabecera con
proveedores, modelo, `top_k`, id de análisis y limitaciones. Columnas: ID regla · Regla · Categoría ·
Severidad · Estado del evaluador · Resultado de la búsqueda · Marca · Fragmentos revisados · Mejor
similitud · Páginas revisadas · Página de la evidencia · Cita verificada · Confianza · Banderas ·
**Segunda pasada** · **Fragmentos escaneados / total**.

Al final, tres bloques: **Reglas sin cláusula encontrada** · **Reglas que no se pudieron buscar** ·
**Reglas que requieren revisión**, y un **conteo por marca** que debe coincidir con la Hoja 1.

## Seguridad del archivo (el contrato y la salida del LLM son entrada no confiable)
- Todo texto pasa por una única función de escritura (`put`).
- Texto que empieza por `=`, `+`, `-`, `@`, tab o CR se guarda como cadena con `quotePrefix`
  (Excel no lo evalúa; CWE-1236). El texto no se altera.
- Caracteres ilegales de XML se eliminan; tope de 32.767 caracteres con aviso `[texto truncado, ver página N]`.

## Criterios de aceptación (todos cubiertos por pruebas, doc 06)
- Dos hojas con esos nombres; columnas en el orden indicado; leyenda presente; paneles congelados.
- Conteos por marca de la Hoja 1 = Hoja 2.
- Toda evidencia es subcadena del texto del contrato, o está marcada.
- Una regla sin cláusula aparece como **N** con el texto explícito; contrato ilegible → **V**, nunca N.
- Ninguna llamada al modelo al generar el archivo.
