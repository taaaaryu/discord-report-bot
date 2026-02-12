#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$HERE/build"
ZIP="$OUT_DIR/lambda.zip"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/package"

python3 -m pip install -r "$HERE/requirements.txt" -t "$OUT_DIR/package" 1>&2
cp "$HERE/app.py" "$OUT_DIR/package/"

( cd "$OUT_DIR/package" && zip -qr "$ZIP" . )

echo "$ZIP"
