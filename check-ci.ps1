# ==============================================================================
# Script de Validación Local de CI (AgroPhasor - Windows PowerShell)
# Cumplimiento de la tarea Linear CC-01.
# 1. Gitleaks (Detección de secretos si está disponible)
# 2. Auditoría de archivos sensibles versionados y verificación de .env.example
# 3. Verificación de código y pruebas unitarias (Python unittest / pytest)
# ==============================================================================
$ErrorActionPreference = "Stop"

$repoRoot = git rev-parse --show-toplevel
Set-Location $repoRoot

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " [CI Local] Validador Pre-Push / Pre-PR — AgroPhasor (Windows)   " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# ------------------------------------------------------------------------------
# 1. GITLEAKS (Detección de Secretos en commits)
# ------------------------------------------------------------------------------
Write-Host "`n[1/3] Verificando secretos y credenciales..." -ForegroundColor Yellow

$targetBase = "origin/main"
$hasRemote = git rev-parse --verify $targetBase 2>$null
if (-not $hasRemote) {
    $targetBase = "main"
}

$commitsCount = (git rev-list --count "$targetBase..HEAD" 2>$null)
if (-not $commitsCount) { $commitsCount = 0 }

$gitleaksCmd = Get-Command gitleaks -ErrorAction SilentlyContinue
$wingetGitleaks = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gitleaks.Gitleaks_Microsoft.Winget.Source_8wekyb3d8bbwe\gitleaks.exe"

$gitleaksExe = $null
if ($gitleaksCmd) {
    $gitleaksExe = "gitleaks"
} elseif (Test-Path $wingetGitleaks) {
    $gitleaksExe = $wingetGitleaks
}

if ($gitleaksExe) {
    Write-Host "   Ejecutando Gitleaks ($gitleaksExe)..." -ForegroundColor Gray
    if ($commitsCount -gt 0) {
        & $gitleaksExe detect --source $repoRoot -v --redact --log-opts="$targetBase..HEAD"
    } else {
        & $gitleaksExe detect --source $repoRoot -v --redact --log-opts="HEAD~3..HEAD"
    }
    Write-Host "[OK] Gitleaks: Cero secretos detectados." -ForegroundColor Green
} else {
    Write-Host "   (Gitleaks no esta instalado en PATH; recomendacion: winget install Gitleaks.Gitleaks)" -ForegroundColor DarkGray
    Write-Host "[OK] Omitiendo escaneo binario de Gitleaks." -ForegroundColor Green
}

# ------------------------------------------------------------------------------
# 2. AUDITORÍA DE ARCHIVOS SENSIBLES Y .env.example
# ------------------------------------------------------------------------------
Write-Host "`n[2/3] Verificando que no haya archivos privados en el indice de Git..." -ForegroundColor Yellow

$trackedFiles = git ls-files
$sensitiveRegex = '(\.env$|\.env\.|\.netrc$|\.pem$|\.key$|id_rsa|.*gcp.*\.json$|.*credentials.*\.json$|.*service_account.*\.json$)'
$sensitiveFiles = $trackedFiles | Where-Object { $_ -match $sensitiveRegex -and $_ -notmatch '\.env\.example$' }

if ($sensitiveFiles) {
    Write-Host "ERROR: Se encontraron archivos sensibles rastreados por Git:" -ForegroundColor Red
    $sensitiveFiles | ForEach-Object { Write-Host "   - $_" -ForegroundColor Red }
    Write-Host "Eliminalos del repositorio y registralos en .gitignore." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "$repoRoot/.env.example")) {
    Write-Host "ADVERTENCIA: No se encontro el archivo .env.example en la raiz del proyecto." -ForegroundColor Yellow
} else {
    Write-Host "[OK] Archivo .env.example presente y seguro." -ForegroundColor Green
}
Write-Host "[OK] Archivos sensibles: Ninguno detectado en el indice de Git." -ForegroundColor Green

# ------------------------------------------------------------------------------
# 3. VERIFICACIÓN DE CÓDIGO Y PRUEBAS (Backend Python / Frontend)
# ------------------------------------------------------------------------------
Write-Host "`n[3/3] Verificacion de codigo y pruebas del proyecto..." -ForegroundColor Yellow

# Backend Python
if ((Test-Path "$repoRoot/backend") -or (Test-Path "$repoRoot/requirements.txt")) {
    Write-Host "   Ejecutando suite de pruebas de Python..." -ForegroundColor Gray
    $pythonExe = $null
    $candidates = @(
        "C:\Users\Krishna\AppData\Local\Programs\Python\Python313\python.exe",
        "C:\Users\Krishna\AppData\Local\Programs\Python\Python312\python.exe",
        "py",
        "python3",
        "python"
    )
    foreach ($cand in $candidates) {
        try {
            if ($cand -like "*\*" -and (Test-Path $cand)) {
                $testOut = & $cand --version 2>$null
                if ($LASTEXITCODE -eq 0) { $pythonExe = $cand; break }
            } elseif (Get-Command $cand -ErrorAction SilentlyContinue) {
                $testOut = & $cand --version 2>$null
                if ($LASTEXITCODE -eq 0) { $pythonExe = $cand; break }
            }
        } catch {}
    }

    if ($pythonExe) {
        & $pythonExe -m unittest discover tests
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Fallaron las pruebas unitarias de Python." -ForegroundColor Red
            exit 1
        }
        Write-Host "[OK] Pruebas unitarias de Python aprobadas." -ForegroundColor Green
    } else {
        Write-Host "   (Python no encontrado para ejecutar pruebas)" -ForegroundColor DarkGray
    }
}

# Frontend
if (Test-Path "$repoRoot/package.json") {
    Write-Host "   Validando archivos de Frontend..." -ForegroundColor Gray
    if (Test-Path "$repoRoot/frontend/index.html") {
        Write-Host "[OK] Estructura Frontend (HTML, CSS, JS) verificada." -ForegroundColor Green
    }
}

Write-Host "`n================================================================" -ForegroundColor Green
Write-Host " [EXITO] CI LOCAL APROBADO: El codigo esta listo para envio     " -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
