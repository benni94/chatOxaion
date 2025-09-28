@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Project root is this script's directory
set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%venv"
set "PYTHON_BIN=%VENV_DIR%\Scripts\python.exe"

REM Create venv and install deps if needed
if not exist "%PYTHON_BIN%" (
  echo 📦 Setting up virtual environment and dependencies...
  python -V >NUL 2>&1
  if errorlevel 1 (
    echo Python 3 not found in PATH. Please install Python 3 and retry.
    pause
    exit /b 1
  )
  python "%PROJECT_DIR%install_dependencies.py"
)

REM Launch the crawler
"%PYTHON_BIN%" "%PROJECT_DIR%crawler.py"