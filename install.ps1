#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Cross-platform Windows installer (PowerShell)
# - Creates venv
# - Runs install_dependencies.py (installs gradio, playwright, etc.)
# - If data.zip exists: extract to ./data, normalize, build index
# - Else: run crawler, then build index
# - Finally: launch app.py

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

function Find-Python {
  try {
    $v = & python -V 2>$null
    if ($LASTEXITCODE -eq 0) { return 'python' }
  } catch {}
  try {
    $v = & py -3 -V 2>$null
    if ($LASTEXITCODE -eq 0) { return 'py -3' }
  } catch {}
  throw 'Python 3 not found in PATH. Please install Python 3 and try again.'
}

$PythonCmd = Find-Python
$VenvDir   = Join-Path $ProjectDir 'venv'
$VenvPy    = Join-Path $VenvDir 'Scripts\python.exe'

# 1) Ensure venv
if (-not (Test-Path $VenvPy)) {
  Write-Host 'Creating virtual environment...'
  & $PythonCmd -m venv $VenvDir
}

# 2) Upgrade pip via venv
& $VenvPy -m pip install --upgrade pip

# 3) Install deps using the shared installer
Write-Host 'Installing dependencies (install_dependencies.py)...'
& $VenvPy "$ProjectDir\install_dependencies.py"

# 4) Data handling
$DataZip = Join-Path $ProjectDir 'data.zip'
$DataDir = Join-Path $ProjectDir 'data'

function Normalize-DataLayout {
  $Nested = Join-Path $DataDir 'data'
  if (Test-Path $Nested) {
    Write-Host 'Normalizing extracted layout (flattening nested data/)...'
    if (-not (Test-Path $DataDir)) { New-Item -ItemType Directory -Path $DataDir | Out-Null }
    Get-ChildItem -Force -Path $Nested | ForEach-Object {
      Move-Item -Force -Path $_.FullName -Destination $DataDir
    }
    Remove-Item -Recurse -Force $Nested -ErrorAction SilentlyContinue
  }
  if (-not (Test-Path (Join-Path $DataDir 'docs'))) { New-Item -ItemType Directory -Path (Join-Path $DataDir 'docs') | Out-Null }
}

if (Test-Path $DataZip) {
  Write-Host 'Extracting data.zip to ./data ...'
  if (-not (Test-Path $DataDir)) { New-Item -ItemType Directory -Path $DataDir | Out-Null }
  try {
    Expand-Archive -Path $DataZip -DestinationPath $DataDir -Force
  } catch {
    Write-Warning "Expand-Archive failed. Falling back to Python unzip. $_"
    & $VenvPy -m zipfile -e $DataZip $DataDir
  }
  Normalize-DataLayout
} else {
  Write-Host 'No data.zip found. Running crawler...'
  & $VenvPy "$ProjectDir\crawler.py"
}

# 5) Build index
Write-Host 'Building ChromaDB index from ./data/docs ...'
& $VenvPy -c "import query; query.build_index()"

# 6) Launch app
Write-Host 'Launching app.py ...'
& $VenvPy "$ProjectDir\app.py"
