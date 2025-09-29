#!/bin/bash
set -euo pipefail

# Cross-platform installer entrypoint for macOS/Linux/WSL/MSYS.
# On native Windows, use install.ps1 via PowerShell.

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

# Detect WSL
if [ "$os" = "linux" ] && grep -qi 'microsoft' /proc/version 2>/dev/null; then
  os="wsl"
fi

run_install_sh() {
  if [ -f "install.sh" ]; then
    chmod +x install.sh || true
    exec bash install.sh
  else
    echo "install.sh not found in $DIR" >&2
    exit 1
  fi
}

case "$os" in
  mac|linux|wsl|windows_msys)
    run_install_sh
    ;;
  unknown)
    if [ -f "install.ps1" ] && command -v powershell.exe >/dev/null 2>&1; then
      exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${DIR//\//\\}\\install.ps1"
    else
      echo "Unsupported environment. Use install.ps1 from PowerShell on Windows, or install.sh from Bash on macOS/Linux/WSL."
      exit 1
    fi
    ;;
 esac
