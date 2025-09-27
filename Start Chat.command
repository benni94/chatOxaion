#!/bin/bash
# macOS double-clickable launcher
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
# Ensure script is executable
chmod +x "start.sh"
exec ./start.sh
