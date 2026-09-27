#!/usr/bin/env bash
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PACKAGE="$ROOT/plugins/rdb-design"
TOOLS="$ROOT/../harness-tools/tools"
TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/rdb-design-validation.XXXXXX") || exit 2
trap 'rm -rf "$TMP_ROOT"' EXIT
status=0

[ -d "$TOOLS" ] || { echo "[error] 兄弟checkout harness-toolsが無い: $TOOLS" >&2; exit 2; }

python3 "$TOOLS/validate-plugin-repository.py" "$ROOT" || status=1
python3 "$TOOLS/validate-plugin-repository.py" --self-test || status=1

python3 "$PACKAGE/skills/design-rdb-physical/scripts/physical_design.py" --self-test >/dev/null || status=1

# 正例は、この repository の fixture（write-doc の見本の抜粋）で持ち、兄弟の write-doc の見本を読まない
fixtures="$ROOT/tests/fixtures/library-lending"
python3 "$PACKAGE/skills/design-rdb-physical/scripts/physical_design.py" \
  --command-model-file "$fixtures/command-data-model.md" --design-file "$fixtures/rdb-physical-design.md" >/dev/null || status=1

while IFS= read -r script; do
  PYTHONPYCACHEPREFIX="$TMP_ROOT/pycache" python3 -m py_compile "$script" || status=1
done < <(find "$PACKAGE" -type f -name '*.py' | sort)

while IFS= read -r script; do
  bash -n "$script" || status=1
done < <(find "$ROOT/scripts" -type f -name '*.sh' | sort)

if [ "$status" -eq 0 ]; then
  echo 'Validation: passed'
else
  echo 'Validation: failed'
fi
exit "$status"
