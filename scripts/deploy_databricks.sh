#!/usr/bin/env bash
# Construye el frontend, valida el bundle, lo despliega y (re)inicia la app.
# Uso: scripts/deploy_databricks.sh [dev|prod] [--profile NOMBRE]
# Requiere: databricks CLI autenticado (databricks auth login) y Node 20+. Sin Lakebase ni Volume.
# Variable del bundle: BUNDLE_VAR_foundry_secret_scope (scope con el token de Foundry; clave por defecto foundry_ai_token).
set -euo pipefail

TARGET="${1:-dev}"
shift || true
cd "$(dirname "$0")/.."

: "${BUNDLE_VAR_foundry_secret_scope:?Define BUNDLE_VAR_foundry_secret_scope=<scope de secretos con el token de Foundry>}"

echo "==> Frontend: instalación reproducible, pruebas y build"
(cd frontend && npm ci && npm test && npm run build)

echo "==> Bundle: validar y desplegar ($TARGET)"
databricks bundle validate -t "$TARGET" "$@"
databricks bundle deploy -t "$TARGET" "$@"

echo "==> Arrancar la app con el código recién desplegado"
databricks bundle run contract_analyzer -t "$TARGET" "$@"
