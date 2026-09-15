#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

python3 -m pip install -r requirements.txt
python3 -m PyInstaller --noconfirm condition_scanner_macos.spec

echo "완료: dist/주도픽 조건검색.app"

