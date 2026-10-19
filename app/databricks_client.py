"""Acceso perezoso al SDK de Databricks.

Dentro de Databricks Apps el SDK se autentica solo con el principal de servicio de la app
(DATABRICKS_HOST, DATABRICKS_CLIENT_ID y DATABRICKS_CLIENT_SECRET los inyecta la plataforma): no hay
tokens ni claves en el repo ni en la configuración. Se importa bajo demanda para que el modo local no
exija `databricks-sdk`.
"""
from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_client: Any = None


def workspace_client():
    global _client
    with _lock:
        if _client is None:
            from databricks.sdk import WorkspaceClient

            _client = WorkspaceClient()
        return _client


def oauth_token() -> str:
    """Token OAuth vigente del principal de servicio. El SDK lo renueva antes de que caduque."""
    return workspace_client().config.oauth_token().access_token
