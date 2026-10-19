# Arquitectura · Analizador de cumplimiento contractual

Documento de trabajo para revisar **juntos** el diseño antes de seguir construyendo. Sigue la misma
estructura de una especificación de comparador normativo.

| # | Documento | Contenido |
|---|---|---|
| 01 | [Contexto y alcance](01-contexto-alcance.md) | Problema, idea central, qué entra y qué no |
| 02 | [Arquitectura](02-arquitectura.md) | C4 nivel 1 y 2, componentes, stack, flujo extremo a extremo |
| 03 | [Motor de búsqueda y validación](03-motor-busqueda-validacion.md) | Cómo se busca cada regla en el contrato y cuándo se declara «no encontrado» |
| 04 | [Papel de trabajo](04-papel-de-trabajo.md) | Formato Excel (Hoja 1 y Hoja 2), marcas y reglas de formato |
| 05 | [API](05-api.md) | Endpoints REST |
| 06 | [Pruebas end-to-end](06-pruebas.md) | Qué se prueba, cómo correrlo y qué se verificó |
| 07 | [Diferencias con v2 y puntos abiertos](07-diferencias-y-abiertos.md) | Decisiones a revisar contigo |
| 08 | Seguridad y despliegue | Ver `deploy/databricks/README.md` (SSO del workspace, CSRF, CSP estricta, límites conocidos) |

**Estado:** versión actual. Lo descrito está implementado y probado salvo lo marcado
como *propuesta* en el documento 07.
