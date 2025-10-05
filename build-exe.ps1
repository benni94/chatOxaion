# build-exe.ps1
# Builds a simple folder-based exe: dist/OxaionChat/OxaionChat.exe

# Stop on errors
$ErrorActionPreference = 'Stop'

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

Write-Host "Project: $ProjectDir"

function Ensure-Venv {
  $venvPy = Join-Path $ProjectDir 'venv\Scripts\python.exe'
  if (-not (Test-Path $venvPy)) {
    Write-Host 'Creating virtual environment...'
    try {
      & py -3 -m venv (Join-Path $ProjectDir 'venv')
    } catch {
      & python -m venv (Join-Path $ProjectDir 'venv')
    }
  }
}

Ensure-Venv

$Py = Join-Path $ProjectDir 'venv\Scripts\python.exe'
$Pip = Join-Path $ProjectDir 'venv\Scripts\pip.exe'

# Upgrade pip and install deps
& $Pip install --upgrade pip
# Install project dependencies via the shared installer
& $Py (Join-Path $ProjectDir 'install_dependencies.py')
# Install PyInstaller
& $Pip install --upgrade pyinstaller

# Build arguments (folder-based; more reliable with ML deps)
$Args = @(
  '--noconfirm','--clean',
  '--name','OxaionChat',
  '--collect-all','sentence_transformers',
  '--collect-all','chromadb'
)

# Optionally include data directory if present
$DataDir = Join-Path $ProjectDir 'data'
if (Test-Path $DataDir) {
  # Use ; as separator (Windows). Destination folder name: data
  $Args += @('--add-data', "$DataDir;data")
}

# Entry script
$Entry = 'app.py'

Write-Host 'Running PyInstaller...'
& $Py -m PyInstaller @Args $Entry

$ExePath = Join-Path $ProjectDir 'dist\OxaionChat\OxaionChat.exe'
if (Test-Path $ExePath) {
  Write-Host "`n✅ Built: $ExePath"
  Write-Host 'Run:'
  Write-Host '  .\dist\OxaionChat\OxaionChat.exe'
  Write-Host 'The app serves at http://127.0.0.1:7860'
} else {
  Write-Error 'Build failed: executable not found.'
  exit 1
}
