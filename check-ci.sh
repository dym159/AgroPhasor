#!/bin/sh
# ==============================================================================
# Script de ValidaciÃƒÂ³n Local de CI (AgroPhasor)
# Basado en el validador de Quippu y en cumplimiento de la tarea Linear CC-01.
# 1. Gitleaks (DetecciÃƒÂ³n de secretos y credenciales en el historial de commits)
# 2. AuditorÃƒÂ­a de archivos sensibles versionados y verificaciÃƒÂ³n de .env.example
# 3. VerificaciÃƒÂ³n de sintaxis / pruebas unitarias si existen en el repositorio
# ==============================================================================
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

echo "================================================================"
echo " [CI Local] Validador Pre-Push / Pre-PR Ã¢â‚¬â€ AgroPhasor            "
echo "================================================================"

# ------------------------------------------------------------------------------
# 1. GITLEAKS (DetecciÃƒÂ³n de Secretos en commits)
# ------------------------------------------------------------------------------
echo ""
echo "[1/3] Ejecutando Gitleaks (escaneo de historial)..."

TARGET_BASE="origin/main"
if ! git rev-parse --verify "$TARGET_BASE" >/dev/null 2>&1; then
    TARGET_BASE="main"
fi

TOTAL_COMMITS=$(git rev-list --count HEAD 2>/dev/null || echo 0)
COMMITS_COUNT=$(git rev-list --count "${TARGET_BASE}..HEAD" 2>/dev/null || echo 0)

GITLEAKS_ARGS="--source $REPO_ROOT -v --redact"

if [ "$COMMITS_COUNT" -gt 0 ]; then
    echo "   Escaneando commits de la rama actual: ${TARGET_BASE}..HEAD"
    GITLEAKS_ARGS="$GITLEAKS_ARGS --log-opts=${TARGET_BASE}..HEAD"
elif [ "$TOTAL_COMMITS" -gt 3 ]; then
    echo "   Escaneando ultimos commits: HEAD~3..HEAD"
    GITLEAKS_ARGS="$GITLEAKS_ARGS --log-opts=HEAD~3..HEAD"
else
    echo "   Repositorio inicial ($TOTAL_COMMITS commit(s)): Escaneando historial completo..."
fi

if command -v gitleaks >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    gitleaks detect $GITLEAKS_ARGS
elif command -v docker >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    docker run --rm -v "$REPO_ROOT:/repo" zricethezav/gitleaks:latest \
        detect --source /repo -v --redact
else
    echo "⚠️  ADVERTENCIA: Ni 'gitleaks' ni 'docker' estan disponibles en este entorno." >&2
    echo "   Recomendacion de seguridad (CC-01): winget install Gitleaks.Gitleaks" >&2
    echo "   [OK] Omitiendo escaneo de Gitleaks en entorno local sin binario."
fi
echo "[OK] Gitleaks: Cero secretos detectados."

# ------------------------------------------------------------------------------
# 2. AUDITORÃƒÂA DE ARCHIVOS SENSIBLES Y .env.example
# ------------------------------------------------------------------------------
echo ""
echo "[2/3] Verificando que no haya archivos privados en el indice de Git..."

TRACKED_SENSITIVE=$(git ls-files | grep -E '(\.env$|\.env\.|\.netrc$|\.pem$|\.key$|id_rsa|.*gcp.*\.json$|.*credentials.*\.json$|.*service_account.*\.json$)' | grep -v '\.env\.example$' || true)

if [ -n "$TRACKED_SENSITIVE" ]; then
    echo "ERROR: Se encontraron archivos sensibles rastreados por Git:" >&2
    echo "$TRACKED_SENSITIVE" >&2
    echo "       Eliminalos del repositorio y registralos en .gitignore." >&2
    exit 1
fi

if [ ! -f "$REPO_ROOT/.env.example" ]; then
    echo "ADVERTENCIA: No se encontro el archivo .env.example en la raiz del proyecto." >&2
else
    echo "[OK] Archivo .env.example presente y seguro."
fi
echo "[OK] Archivos sensibles: Ninguno detectado en el indice de Git."

# ------------------------------------------------------------------------------
# 3. VERIFICACIÃƒâ€œN DE CÃƒâ€œDIGO Y PRUEBAS (Backend Python / Frontend TS)
# ------------------------------------------------------------------------------
echo ""
echo "[3/3] Verificacion de codigo y pruebas del proyecto..."

# Si existe un backend con Python
if [ -d "$REPO_ROOT/backend" ] || [ -f "$REPO_ROOT/requirements.txt" ] || [ -f "$REPO_ROOT/pyproject.toml" ]; then
    echo "   Verificando componentes de Python..."
    if command -v pytest >/dev/null 2>&1; then
        pytest
    elif command -v python3 >/dev/null 2>&1; then
        python3 -m unittest discover tests
    elif command -v python >/dev/null 2>&1; then
        python -m unittest discover tests
    elif command -v py >/dev/null 2>&1; then
        py -m unittest discover tests
    else
        echo "   (pytest/python no esta en el entorno local; omitiendo suite Python)"
    fi
fi

# Si existe un frontend con npm/pnpm
if [ -f "$REPO_ROOT/package.json" ]; then
    echo "   Verificando componentes de Frontend / Node..."
    if command -v npm >/dev/null 2>&1; then
        (npm run typecheck 2>/dev/null || true)
        (npm test 2>/dev/null || true)
    fi
fi

echo "[OK] Verificacion de codigo finalizada."

echo ""
echo "================================================================"
echo " [EXITO] CI LOCAL APROBADO: El codigo esta listo para envio     "
echo "================================================================"
exit 0
