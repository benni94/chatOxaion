#!/usr/bin/env bash
set -euo pipefail

# Cross-platform (Unix) installer
# - If data.zip exists: unzip concurrently with dependency install, wait for both, then start the app
# - If data.zip does not exist: install deps, then run crawler, then start the app

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

DATA_ZIP="${PROJECT_DIR}/data.zip"
DATA_DIR="${PROJECT_DIR}/data"
VENV_DIR="${PROJECT_DIR}/venv"

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo python3
  elif command -v python >/dev/null 2>&1; then
    echo python
  else
    echo "No python found in PATH" >&2
    return 1
  fi
}

PYTHON_CMD=$(find_python)

unzip_data_bg() {
  mkdir -p "$DATA_DIR"
  if command -v unzip >/dev/null 2>&1; then
    echo "📦 Unzipping data.zip to ./data (using unzip)..."
    unzip -o "$DATA_ZIP" -d "$DATA_DIR"
  else
    echo "📦 Unzipping data.zip to ./data (using python -m zipfile)..."
    "$PYTHON_CMD" -m zipfile -e "$DATA_ZIP" "$DATA_DIR"
  fi
}

install_deps_bg() {
  echo "🧰 Installing dependencies (install_dependencies.py)..."
  "$PYTHON_CMD" install_dependencies.py
}

normalize_data_layout() {
  # Some archives contain a top-level 'data/' directory, leading to data/data/* after extraction.
  # If so, move contents up one level into data/ and remove the nested folder.
  if [ -d "$DATA_DIR/data" ]; then
    echo "🧹 Normalizing extracted layout (flattening nested data/)..."
    shopt -s dotglob nullglob
    mv "$DATA_DIR/data"/* "$DATA_DIR/" 2>/dev/null || true
    shopt -u dotglob nullglob
    rmdir "$DATA_DIR/data" 2>/dev/null || true
  fi
  mkdir -p "$DATA_DIR/docs"
}

build_chromadb_index() {
  echo "🧱 Building ChromaDB index from ./data/docs..."
  # Prefer venv python if available
  if [ -x "$VENV_DIR/bin/python" ]; then
    "$VENV_DIR/bin/python" - <<'PY'
import query
query.build_index()
PY
  else
    "$PYTHON_CMD" - <<'PY'
import query
query.build_index()
PY
  fi
}

run_crawler() {
  echo "🕷️  Running crawler (no data.zip present)..."
  # Prefer venv python if available
  if [ -x "$VENV_DIR/bin/python" ]; then
    "$VENV_DIR/bin/python" crawler.py
  else
    "$PYTHON_CMD" crawler.py
  fi
}

start_app() {
  echo "🚀 Launching app.py (Gradio UI)..."
  # Prefer venv python if available
  if [ -x "$VENV_DIR/bin/python" ]; then
    exec "$VENV_DIR/bin/python" app.py
  else
    exec "$PYTHON_CMD" app.py
  fi
}

if [ -f "$DATA_ZIP" ]; then
  echo "Found data.zip. Unzipping and installing in parallel..."
  unzip_data_bg &
  PID_UNZIP=$!

  install_deps_bg &
  PID_INSTALL=$!

  # Wait for both background jobs
  wait "$PID_UNZIP"
  wait "$PID_INSTALL"

  echo "✅ Data unzip and dependency install complete."
  normalize_data_layout
  build_chromadb_index
  start_app
else
  echo "No data.zip found. Installing dependencies, then running crawler..."
  install_deps_bg
  run_crawler
  build_chromadb_index
  start_app
fi
