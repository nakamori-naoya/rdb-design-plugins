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

version=$(jq -r '.plugins[0].version' "$ROOT/.agents/plugins/marketplace.json")
jq -e --arg version "$version" '.name=="rdb-design" and .plugins[0].name=="rdb-design" and .plugins[0].source.path=="./plugins/rdb-design" and .plugins[0].version==$version' "$ROOT/.agents/plugins/marketplace.json" >/dev/null || status=1
jq -e --arg version "$version" '.name=="rdb-design" and .plugins[0].name=="rdb-design" and .plugins[0].source=="./plugins/rdb-design" and .plugins[0].version==$version' "$ROOT/.claude-plugin/marketplace.json" >/dev/null || status=1
jq -e --arg version "$version" '.name=="rdb-design" and .version==$version and .skills==["./skills/design-rdb-physical"]' "$PACKAGE/.claude-plugin/plugin.json" "$PACKAGE/.codex-plugin/plugin.json" >/dev/null || status=1
diff <(jq -S 'del(.interface)' "$PACKAGE/.claude-plugin/plugin.json") <(jq -S 'del(.interface)' "$PACKAGE/.codex-plugin/plugin.json") >/dev/null || status=1

python3 "$PACKAGE/skills/design-rdb-physical/scripts/physical_design.py" --self-test >/dev/null || status=1

write_doc_examples="$ROOT/../write-doc-plugins/plugins/write-doc/skills/write-doc/assets/examples"
physical_example="$write_doc_examples/rdb-physical-design.example.md"
command_example="$write_doc_examples/command-data-model.example.md"
if [ -f "$physical_example" ] && [ -f "$command_example" ]; then
  python3 "$PACKAGE/skills/design-rdb-physical/scripts/physical_design.py" \
    --command-model-file "$command_example" --design-file "$physical_example" >/dev/null || status=1
else
  echo '[error] write-docのRDB物理設計・コマンドデータモデルの見本が無い' >&2
  status=1
fi

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
