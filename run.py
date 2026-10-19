"""Punto de entrada para Databricks Apps.

app.yaml arranca con `uvicorn app.main:app` directamente; este script queda para uso local. El puerto es UVICORN_PORT o DATABRICKS_APP_PORT y exige escuchar en 0.0.0.0. Un
arranque en Python evita depender de que `app.yaml` expanda variables dentro de `command`.
Un solo worker: el bloqueo de intentos y el "un análisis a la vez" viven en memoria del proceso.
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("UVICORN_HOST", "0.0.0.0"),
        port=int(os.environ.get("UVICORN_PORT") or os.environ.get("DATABRICKS_APP_PORT") or "8000"),
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips="*",  # detrás del proxy de la plataforma, que es la única vía de entrada
        server_header=False,
    )
