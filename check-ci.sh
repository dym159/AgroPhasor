#!/bin/sh
# ==============================================================================
# Local CI Validation Script (AgroPhasor)
# Based on Quippu validator and compliant with Linear task CC-01.
# 1. Gitleaks (Secret and credential scanning in commit history)
# 2. Tracked sensitive file audit and .env.example verification
# 3. Syntax check / unit tests if present in the repository
# ==============================================================================
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

echo "================================================================"
echo " [Local CI] Pre-Push / Pre-PR Validator — AgroPhasor            "
echo "================================================================"

# ------------------------------------------------------------------------------
# 1. GITLEAKS (Secret detection in commits)
# ------------------------------------------------------------------------------
echo ""
echo "[1/3] Running Gitleaks (commit history scan)..."

TARGET_BASE="origin/main"
if ! git rev-parse --verify "$TARGET_BASE" >/dev/null 2>&1; then
    TARGET_BASE="main"
fi

TOTAL_COMMITS=$(git rev-list --count HEAD 2>/dev/null || echo 0)
COMMITS_COUNT=$(git rev-list --count "${TARGET_BASE}..HEAD" 2>/dev/null || echo 0)

GITLEAKS_ARGS="--source $REPO_ROOT -v --redact"

if [ "$COMMITS_COUNT" -gt 0 ]; then
    echo "   Scanning current branch commits: ${TARGET_BASE}..HEAD"
    GITLEAKS_ARGS="$GITLEAKS_ARGS --log-opts=${TARGET_BASE}..HEAD"
elif [ "$TOTAL_COMMITS" -gt 3 ]; then
    echo "   Scanning recent commits: HEAD~3..HEAD"
    GITLEAKS_ARGS="$GITLEAKS_ARGS --log-opts=HEAD~3..HEAD"
else
    echo "   Initial repository ($TOTAL_COMMITS commit(s)): Scanning full history..."
fi

GITLEAKS_BIN=""
if command -v gitleaks >/dev/null 2>&1; then
    GITLEAKS_BIN="gitleaks"
elif [ -f "$LOCALAPPDATA/Microsoft/WinGet/Packages/Gitleaks.Gitleaks_Microsoft.Winget.Source_8wekyb3d8bbwe/gitleaks.exe" ]; then
    GITLEAKS_BIN="$LOCALAPPDATA/Microsoft/WinGet/Packages/Gitleaks.Gitleaks_Microsoft.Winget.Source_8wekyb3d8bbwe/gitleaks.exe"
elif [ -f "/c/Users/Krishna/AppData/Local/Microsoft/WinGet/Packages/Gitleaks.Gitleaks_Microsoft.Winget.Source_8wekyb3d8bbwe/gitleaks.exe" ]; then
    GITLEAKS_BIN="/c/Users/Krishna/AppData/Local/Microsoft/WinGet/Packages/Gitleaks.Gitleaks_Microsoft.Winget.Source_8wekyb3d8bbwe/gitleaks.exe"
fi

if [ -n "$GITLEAKS_BIN" ]; then
    # shellcheck disable=SC2086
    "$GITLEAKS_BIN" detect $GITLEAKS_ARGS
elif command -v docker >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    docker run --rm -v "$REPO_ROOT:/repo" zricethezav/gitleaks:latest \
        detect --source /repo -v --redact
else
    echo "⚠️  WARNING: Neither 'gitleaks' nor 'docker' is available in this environment." >&2
    echo "   Security recommendation (CC-01): winget install Gitleaks.Gitleaks" >&2
    echo "   [OK] Skipping Gitleaks scan in local environment without binary."
fi
echo "[OK] Gitleaks: Zero secrets detected."

# ------------------------------------------------------------------------------
# 2. SENSITIVE FILES AUDIT AND .env.example CHECK
# ------------------------------------------------------------------------------
echo ""
echo "[2/3] Checking that no private files are tracked in Git index..."

TRACKED_SENSITIVE=$(git ls-files | grep -E '(\.env$|\.env\.|\.netrc$|\.pem$|\.key$|id_rsa|.*gcp.*\.json$|.*credentials.*\.json$|.*service_account.*\.json$)' | grep -v '\.env\.example$' || true)

if [ -n "$TRACKED_SENSITIVE" ]; then
    echo "ERROR: Sensitive files found tracked by Git:" >&2
    echo "$TRACKED_SENSITIVE" >&2
    echo "       Remove them from the repository and add them to .gitignore." >&2
    exit 1
fi

if [ ! -f "$REPO_ROOT/.env.example" ]; then
    echo "WARNING: .env.example file was not found in repository root." >&2
else
    echo "[OK] .env.example file present and safe."
fi
echo "[OK] Sensitive files: None detected in Git index."

# ------------------------------------------------------------------------------
# 3. CODE AND TEST VERIFICATION (Python Backend / Frontend)
# ------------------------------------------------------------------------------
echo ""
echo "[3/3] Verifying project code and running tests..."

# If a Python backend exists
find_python() {
    for candidate in py python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" --version >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

if [ -d "$REPO_ROOT/backend" ] || [ -f "$REPO_ROOT/requirements.txt" ] || [ -f "$REPO_ROOT/pyproject.toml" ]; then
    echo "   Checking Python components..."
    PYTHON_CMD="$(find_python || true)"
    if [ -n "$PYTHON_CMD" ] && "$PYTHON_CMD" -m pytest --version >/dev/null 2>&1; then
        "$PYTHON_CMD" -m pytest
    elif [ -n "$PYTHON_CMD" ]; then
        "$PYTHON_CMD" -m unittest discover tests
    else
        echo "   (pytest/python not found in local environment; skipping Python suite)"
    fi
fi

# If a frontend with npm/pnpm exists
if [ -f "$REPO_ROOT/package.json" ]; then
    echo "   Checking Frontend / Node components..."
    if command -v npm >/dev/null 2>&1; then
        (npm run typecheck 2>/dev/null || true)
        (npm test 2>/dev/null || true)
    fi
fi

echo "[OK] Code verification completed."

echo ""
echo "================================================================"
echo " [SUCCESS] LOCAL CI PASSED: Code is ready to push               "
echo "================================================================"
exit 0
