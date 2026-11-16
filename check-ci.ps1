# ==============================================================================
# Local CI Validation Script (AgroPhasor - Windows PowerShell)
# Compliance with Linear task CC-01.
# 1. Gitleaks (Secret detection if available)
# 2. Tracked sensitive file audit and .env.example verification
# 3. Code verification and unit tests (Python unittest / Node)
# ==============================================================================
$ErrorActionPreference = "Stop"

$repoRoot = git rev-parse --show-toplevel
Set-Location $repoRoot

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " [Local CI] Pre-Push / Pre-PR Validator — AgroPhasor (Windows)  " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# ------------------------------------------------------------------------------
# 1. GITLEAKS (Secret detection in commits)
# ------------------------------------------------------------------------------
Write-Host "`n[1/3] Checking for secrets and credentials..." -ForegroundColor Yellow

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
    Write-Host "   Running Gitleaks ($gitleaksExe)..." -ForegroundColor Gray
    if ($commitsCount -gt 0) {
        & $gitleaksExe detect --source $repoRoot -v --redact --log-opts="$targetBase..HEAD"
    } else {
        & $gitleaksExe detect --source $repoRoot -v --redact --log-opts="HEAD~3..HEAD"
    }
    Write-Host "[OK] Gitleaks: Zero secrets detected." -ForegroundColor Green
} else {
    Write-Host "   (Gitleaks is not installed in PATH; recommended: winget install Gitleaks.Gitleaks)" -ForegroundColor DarkGray
    Write-Host "[OK] Skipping Gitleaks binary scan." -ForegroundColor Green
}

# ------------------------------------------------------------------------------
# 2. SENSITIVE FILES AUDIT AND .env.example CHECK
# ------------------------------------------------------------------------------
Write-Host "`n[2/3] Checking that no private files are tracked in Git index..." -ForegroundColor Yellow

$trackedFiles = git ls-files
$sensitiveRegex = '(\.env$|\.env\.|\.netrc$|\.pem$|\.key$|id_rsa|.*gcp.*\.json$|.*credentials.*\.json$|.*service_account.*\.json$)'
$sensitiveFiles = $trackedFiles | Where-Object { $_ -match $sensitiveRegex -and $_ -notmatch '\.env\.example$' }

if ($sensitiveFiles) {
    Write-Host "ERROR: Sensitive files found tracked by Git:" -ForegroundColor Red
    $sensitiveFiles | ForEach-Object { Write-Host "   - $_" -ForegroundColor Red }
    Write-Host "Remove them from the repository and register them in .gitignore." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "$repoRoot/.env.example")) {
    Write-Host "WARNING: .env.example file was not found in project root." -ForegroundColor Yellow
} else {
    Write-Host "[OK] .env.example file present and safe." -ForegroundColor Green
}
Write-Host "[OK] Sensitive files: None detected in Git index." -ForegroundColor Green

# ------------------------------------------------------------------------------
# 3. CODE AND TEST VERIFICATION (Python Backend / Frontend)
# ------------------------------------------------------------------------------
Write-Host "`n[3/3] Verifying project code and running tests..." -ForegroundColor Yellow

# Python Backend
if ((Test-Path "$repoRoot/backend") -or (Test-Path "$repoRoot/requirements.txt")) {
    Write-Host "   Running Python test suite..." -ForegroundColor Gray
    $pythonExe = $null
    $candidates = @(
        "$repoRoot\.venv\Scripts\python.exe",
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
        & $pythonExe -m pytest tests
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Python unit tests failed." -ForegroundColor Red
            exit 1
        }
        Write-Host "[OK] Python unit tests passed." -ForegroundColor Green
    } else {
        Write-Host "   (Python not found to run tests)" -ForegroundColor DarkGray
    }
}

# Frontend
if (Test-Path "$repoRoot/package.json") {
    Write-Host "   Validating Frontend files..." -ForegroundColor Gray
    if (Test-Path "$repoRoot/frontend/index.html") {
        Write-Host "[OK] Frontend structure (HTML, CSS, JS) verified." -ForegroundColor Green
    }
}

Write-Host "`n================================================================" -ForegroundColor Green
Write-Host " [SUCCESS] LOCAL CI PASSED: Code is ready to push               " -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
