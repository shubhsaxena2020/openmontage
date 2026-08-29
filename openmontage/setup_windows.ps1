<#
 .SYNOPSIS
    One-shot setup for OpenMontage Kinetic Studio on Windows (laptop).
    Installs ffmpeg (via winget), creates a Python venv, pip-installs the engine
    dependencies, and runs `npm install` for the Remotion HUD app.

 .USAGE
    powershell -ExecutionPolicy Bypass -File setup_windows.ps1

    Optional flags:
      -SkipFfmpeg      assume ffmpeg is already on PATH
      -SkipNpm         skip `npm install` (e.g. if you only want the Python engine)
      -PythonExe       path to python3.11 (default: python)
#>
[CmdletBinding()]
param(
    [switch]$SkipFfmpeg,
    [switch]$SkipNpm,
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $Root
Write-Host "OpenMontage setup — repo root: $Root" -ForegroundColor Cyan

# ── 1. ffmpeg ──────────────────────────────────────────────
if (-not $SkipFfmpeg) {
    $ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($ff) {
        Write-Host "[ffmpeg] already on PATH: $($ff.Source)" -ForegroundColor Green
    } else {
        Write-Host "[ffmpeg] not found — installing via winget..." -ForegroundColor Yellow
        winget install --exact --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
        # refresh PATH for this session
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
            Write-Warning "ffmpeg install finished but not on PATH. Add it manually and re-run, or use -SkipFfmpeg next time."
        }
    }
} else {
    Write-Host "[ffmpeg] skipped (-SkipFfmpeg)" -ForegroundColor DarkGray
}

# ── 2. Python venv ────────────────────────────────────────
$Venv = Join-Path $Root ".venv"
if (Test-Path $Venv) {
    Write-Host "[venv] $Venv already exists" -ForegroundColor Green
} else {
    Write-Host "[venv] creating virtualenv with $PythonExe ..." -ForegroundColor Yellow
    & $PythonExe -m venv $Venv
}
$Activate = Join-Path $Venv "Scripts\Activate.ps1"
if (-not (Test-Path $Activate)) { throw "venv activate script missing at $Activate" }
. $Activate
python -m pip install --upgrade pip

# ── 3. pip install engine deps ────────────────────────────
$Req = Join-Path $Root "kinetic_studio\requirements.txt"
if (-not (Test-Path $Req)) { throw "requirements not found at $Req" }
Write-Host "[pip] installing engine deps from kinetic_studio\requirements.txt ..." -ForegroundColor Yellow
# torch/torchvision install faster from their own index; fall back to PyPI if needed.
pip install -r $Req
if ($LASTEXITCODE -ne 0) {
    Write-Warning "pip install returned non-zero. If torch failed, install the CUDA wheel manually:
      pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
    then re-run this script (deps already partially installed will be skipped)."
}

# ── 4. npm install (Remotion HUD) ─────────────────────────
if (-not $SkipNpm) {
    $Remotion = Join-Path $Root "remotion"
    if (Test-Path (Join-Path $Remotion "package.json")) {
        Write-Host "[npm] installing Remotion app deps in remotion/ ..." -ForegroundColor Yellow
        Push-Location $Remotion
        npm install
        Pop-Location
    } else {
        Write-Warning "remotion/package.json not found — skipped npm install."
    }
} else {
    Write-Host "[npm] skipped (-SkipNpm)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next: .venv\Scripts\Activate.ps1 ; set PYTHONPATH=. ; python -m kinetic_studio run <video> ..." -ForegroundColor Cyan
Write-Host "Then: cd remotion ; npm run studio   (or npm run render-studio for headless)" -ForegroundColor Cyan
