#!/usr/bin/env bash
# お題の要件とデータモデルの資料と別 package のファイルを、共通の準備で作業場所へ置く。
set -euo pipefail
CASE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec bash "$CASE_DIR/../../scaffold.sh" "$CASE_DIR/.."
