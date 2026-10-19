"""Copia durable de los PDF subidos en un Volume de Unity Catalog.

El disco de un contenedor de Databricks Apps es efímero: se pierde al reiniciar o redesplegar. El resto del
código (PyMuPDF, anotación, render) trabaja con archivos locales, así que el disco local pasa a ser una
caché y el Volume la fuente de verdad:

- al subir un PDF se copia al Volume (`push`),
- al leerlo, si no está en la caché local se descarga (`ensure_local`),
- al borrarlo se elimina de ambos (`remove`).

Sin `UPLOAD_VOLUME_PATH` (desarrollo local) todas las funciones son no-ops.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return bool(settings.upload_volume_path)


def _root() -> str:
    """Raíz del Volume. Acepta la ruta de archivos (/Volumes/cat/esq/vol[/sub]) o el nombre de tres partes
    (cat.esq.vol) que entrega un recurso de tipo Unity Catalog de la app."""
    value = settings.upload_volume_path.strip().rstrip("/")
    return value if value.startswith("/Volumes/") else "/Volumes/" + value.replace(".", "/")


def _remote(stored_filename: str) -> str:
    # `stored_filename` lo genera el servidor (uuid.pdf); aun así se rechaza cualquier separador de ruta.
    if "/" in stored_filename or "\\" in stored_filename or stored_filename.startswith("."):
        raise ValueError("Nombre de archivo almacenado inválido")
    return f"{_root()}/{stored_filename}"


def push(stored_filename: str, local: Path) -> None:
    if not enabled():
        return
    from app.databricks_client import workspace_client

    remote = _remote(stored_filename)
    with open(local, "rb") as f:
        workspace_client().files.upload(remote, f, overwrite=True)


def ensure_local(stored_filename: str, local: Path) -> None:
    """Deja el PDF en la caché local; si no existe en el Volume, deja que el llamador falle como siempre."""
    if local.exists() or not enabled():
        return
    from app.databricks_client import workspace_client

    try:
        resp = workspace_client().files.download(_remote(stored_filename))
        tmp = local.with_suffix(local.suffix + ".part")
        with open(tmp, "wb") as f:
            f.write(resp.contents.read())
        tmp.replace(local)
    except Exception as e:  # noqa: BLE001 - el SDK lanza varios tipos; el detalle puede incluir rutas internas
        logger.warning("No se pudo recuperar %s del Volume: %s", stored_filename, type(e).__name__)


def remove(stored_filename: str) -> None:
    if not enabled():
        return
    from app.databricks_client import workspace_client

    try:
        workspace_client().files.delete(_remote(stored_filename))
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo borrar %s del Volume: %s", stored_filename, type(e).__name__)
