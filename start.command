#!/bin/bash
set -euo pipefail

# Cross-platform starter for macOS/Linux/WSL/MSYS. For native Windows (cmd/PowerShell),
# this script will attempt reasonable fallbacks if available.

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

uname_out="$(uname -s 2>/dev/null || echo Unknown)"
os="unknown"
case "$uname_out" in
  Darwin)
    os="mac";;
  Linux)
    os="linux";;
  MINGW*|MSYS*|CYGWIN*)
    os="windows_msys";;
  *)
    os="unknown";;
esac

# Detect WSL (Windows Subsystem for Linux)
if [ "$os" = "linux" ] && grep -qi 'microsoft' /proc/version 2>/dev/null; then
  os="wsl"
fi

run_start_sh() {
  if [ -f "start.sh" ]; then
    chmod +x "start.sh" || true
    exec bash "start.sh"
  else
    echo "start.sh not found in $DIR" >&2
    exit 1
  fi
}

case "$os" in
  mac|linux|wsl|windows_msys)
    run_start_sh
    ;;
  unknown)
    # Try Windows fallbacks if present
    if [ -f "start.ps1" ] && command -v powershell.exe >/dev/null 2>&1; then
      exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${DIR//\//\\}\\start.ps1"
    elif [ -f "start.bat" ] && command -v cmd.exe >/dev/null 2>&1; then
      exec cmd.exe /c "start.bat"
    else
      echo "Unsupported environment."
      echo "- If you're on Windows: run start.ps1 (PowerShell) or start.bat from a Command Prompt."
      echo "- If you're on macOS/Linux/WSL/MSYS: ensure Bash is available and run ./start.sh"
      exit 1
    fi
    ;;
esac
