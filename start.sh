#!/usr/bin/env bash
set -euo pipefail

# Disable analytics/telemetry and silence tokenizers warnings
export POSTHOG_DISABLED=1
export TOKENIZERS_PARALLELISM=false
export HF_HUB_DISABLE_TELEMETRY=1

# Project root is this script's directory
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON_BIN="$VENV_DIR/bin/python"

# Create venv and install deps if needed
if [ ! -x "$PYTHON_BIN" ]; then
  echo "📦 Setting up virtual environment and dependencies..."
  (cd "$PROJECT_DIR" && python3 install_dependencies.py)
fi

# Launch the app
exec "$PYTHON_BIN" "$PROJECT_DIR/app.py"
