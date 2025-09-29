#requires -Version 5.0
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Cross-platform (Windows/PowerShell) installer
# - If data.zip exists: unzip concurrently with dependency install, wait for both, then start the app
# - If data.zip does not exist: install deps, then run crawler, then start the app

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$dataZip = Join-Path $Root 'data.zip'
$dataDir = Join-Path $Root 'data'
$venvDir = Join-Path $Root 'venv'
$venvPy  = Join-Path $venvDir 'Scripts\python.exe'

function Find-Python {
    if (Get-Command python3 -ErrorAction SilentlyContinue) { return 'python3' }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { return 'python' }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { return 'py' }
    throw 'No Python interpreter found in PATH.'
}

$python = Find-Python

function Unzip-Data {
    param([string]$ZipPath, [string]$Dest)
    if (-not (Test-Path $Dest)) { New-Item -ItemType Directory -Path $Dest | Out-Null }
    if (Get-Command Expand-Archive -ErrorAction SilentlyContinue) {
        Write-Host "📦 Unzipping data.zip to ./data (Expand-Archive)..."
        Expand-Archive -Path $ZipPath -DestinationPath $Dest -Force
    } else {
        Write-Host "📦 Unzipping data.zip to ./data (python -m zipfile)..."
        & $python -m zipfile -e $ZipPath $Dest
    }
}

function Install-Deps {
    Write-Host "🧰 Installing dependencies (install_dependencies.py)..."
    & $python install_dependencies.py
}

function Normalize-DataLayout {
    # If archive extracted into data/data/*, move contents up one level
    $nested = Join-Path $dataDir 'data'
    if (Test-Path $nested) {
        Write-Host "🧹 Normalizing extracted layout (flattening nested data/)..."
        Get-ChildItem -Force -Path $nested | ForEach-Object {
            Move-Item -Force -Path $_.FullName -Destination $dataDir
        }
        Remove-Item -Force -Recurse $nested
    }
    $docs = Join-Path $dataDir 'docs'
    if (-not (Test-Path $docs)) { New-Item -ItemType Directory -Path $docs | Out-Null }
}

function Build-ChromaIndex {
    Write-Host "🧱 Building ChromaDB index from ./data/docs..."
    $pyToUse = if (Test-Path $venvPy) { $venvPy } else { $python }
    $code = @'
import query
query.build_index()
'@
    & $pyToUse - << $code
}

function Run-Crawler {
    Write-Host "🕷️  Running crawler (no data.zip present)..."
    $pyToUse = if (Test-Path $venvPy) { $venvPy } else { $python }
    & $pyToUse crawler.py
}

function Start-App {
    Write-Host "🚀 Launching start.cmd..."
    $startCmd = Join-Path $Root 'start.cmd'
    $startCommandFile = Join-Path $Root 'Start Chat.command'
    if (Test-Path $startCmd) {
        Start-Process -FilePath cmd.exe -ArgumentList '/c', 'start.cmd' -WorkingDirectory $Root -WindowStyle Normal
    } elseif (Test-Path $startCommandFile) {
        # Fallback: attempt to run the .command via bash if available (Git Bash)
        if (Get-Command bash -ErrorAction SilentlyContinue) {
            Start-Process -FilePath bash -ArgumentList '"Start Chat.command"' -WorkingDirectory $Root -WindowStyle Normal
        } else {
            Write-Warning 'No start.cmd found and bash is unavailable to run Start Chat.command. Start the app manually.'
        }
    } else {
        Write-Warning 'No start script found (start.cmd / Start Chat.command).'
    }
}

if (Test-Path $dataZip) {
    Write-Host 'Found data.zip. Unzipping and installing in parallel...'
    $jobUnzip = Start-Job -ScriptBlock {
        param($zip, $dest, $py)
        $ErrorActionPreference = 'Stop'
        if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest | Out-Null }
        if (Get-Command Expand-Archive -ErrorAction SilentlyContinue) {
            Expand-Archive -Path $zip -DestinationPath $dest -Force
        } else {
            & $py -m zipfile -e $zip $dest
        }
    } -ArgumentList $dataZip, $dataDir, $python

    $jobInstall = Start-Job -ScriptBlock {
        param($py)
        $ErrorActionPreference = 'Stop'
        & $py install_dependencies.py
    } -ArgumentList $python

    Wait-Job -Job $jobUnzip, $jobInstall | Out-Null
    Receive-Job -Job $jobUnzip | Out-Null
    Receive-Job -Job $jobInstall | Out-Null

    Write-Host '✅ Data unzip and dependency install complete.'
    Normalize-DataLayout
    Build-ChromaIndex
    Start-App
} else {
    Write-Host 'No data.zip found. Installing dependencies, then running crawler...'
    Install-Deps
    Run-Crawler
    Build-ChromaIndex
    Start-App
}
