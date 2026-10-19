# Databricks notebook source
# MAGIC %md
# MAGIC # Despliegue de analista-contractual en Databricks Apps (SDK de Python)
# MAGIC Clona/actualiza la carpeta Git, crea la app solo si no existe (con el recurso secreto `foundry-token`) y
# MAGIC despliega con `deploy_and_wait`, mostrando el error si falla. No contiene secretos: el token ya vive en un scope.

# COMMAND ----------

# MAGIC %pip install -q --upgrade databricks-sdk
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os
import sys

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.apps import (
    App, AppDeployment, AppDeploymentMode, AppResource, AppResourceSecret,
    AppResourceSecretSecretPermission,
)

APP_NAME = os.environ.get("APP_NAME", "analista-contractual")
GIT_URL = os.environ.get("GIT_URL", "https://github.com/basaravia/contract-compliance-analyzer-databricks")
GIT_BRANCH = os.environ.get("GIT_BRANCH", "main")
SECRET_SCOPE = os.environ.get("SECRET_SCOPE", "comparador")   # scope que ya contiene el token
SECRET_KEY = os.environ.get("SECRET_KEY", "foundry-token")    # clave dentro del scope
RESOURCE_KEY = "foundry-token"                                 # debe coincidir con `valueFrom` de app.yaml

w = WorkspaceClient()
me = w.current_user.me().user_name
REPO_PATH = os.environ.get("REPO_PATH", f"/Workspace/Users/{me}/contract-compliance-analyzer-databricks")
print("Usuario:", me, "| Carpeta Git:", REPO_PATH)

# COMMAND ----------

# 1) Carpeta Git: crear si no existe; si existe, traer el último commit de la rama.
repo = next((r for r in w.repos.list(path_prefix=REPO_PATH) if r.path == REPO_PATH), None)
if repo is None:
    repo = w.repos.create(url=GIT_URL, provider="gitHub", path=REPO_PATH)
    print("Carpeta Git creada")
w.repos.update(repo_id=repo.id, branch=GIT_BRANCH)
repo = w.repos.get(repo.id)
print("Rama:", repo.branch, "| commit:", repo.head_commit_id)

# COMMAND ----------

# 2) Validar que el secreto exista (solo la clave, nunca el valor).
keys = [s.key for s in w.secrets.list_secrets(SECRET_SCOPE)]
assert SECRET_KEY in keys, f"No existe la clave {SECRET_KEY!r} en el scope {SECRET_SCOPE!r}: {keys}"
print(f"Secreto {SECRET_SCOPE}/{SECRET_KEY}: OK")

# COMMAND ----------

# 3) Crear la app SOLO si no existe.
try:
    app = w.apps.get(APP_NAME)
    print("La app ya existe; no se crea de nuevo:", app.name, "|", app.app_status.state if app.app_status else None)
except NotFound:
    app = w.apps.create_and_wait(app=App(
        name=APP_NAME,
        description="Analizador de cumplimiento contractual",
        resources=[AppResource(
            name=RESOURCE_KEY,
            secret=AppResourceSecret(scope=SECRET_SCOPE, key=SECRET_KEY,
                                     permission=AppResourceSecretSecretPermission.READ),
        )],
    ))
    print("App creada:", app.name)

# COMMAND ----------

# 4) Desplegar y esperar; si falla, mostrar el estado y el mensaje de error.
try:
    dep = w.apps.deploy_and_wait(APP_NAME, app_deployment=AppDeployment(
        source_code_path=REPO_PATH, mode=AppDeploymentMode.SNAPSHOT))
    print("Despliegue:", dep.status.state, "-", dep.status.message)
except Exception as e:                                    # noqa: BLE001 — queremos ver cualquier fallo
    print("FALLÓ EL DESPLIEGUE:", type(e).__name__, e)
    app = w.apps.get(APP_NAME)
    print("app_status:    ", app.app_status.state, "-", app.app_status.message)
    print("compute_status:", app.compute_status.state, "-", app.compute_status.message)
    if app.pending_deployment:
        print("pending:", app.pending_deployment.status.state, "-", app.pending_deployment.status.message)
    if app.active_deployment:
        print("active: ", app.active_deployment.status.state, "-", app.active_deployment.status.message)
    print("Logs: ", app.url + "/logz" if app.url else "(sin URL)")
    if "dbutils" not in globals():
        sys.exit(1)

app = w.apps.get(APP_NAME)
print("URL:", app.url, "|", app.app_status.state, "-", app.app_status.message)
