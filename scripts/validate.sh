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
jq -e --arg version "$version" '.name=="rdb-design" and .version==$version and .skills==["./skills/design-rdb-physical","./skills/revise-rdb-physical"]' "$PACKAGE/.claude-plugin/plugin.json" "$PACKAGE/.codex-plugin/plugin.json" >/dev/null || status=1
diff <(jq -S 'del(.interface)' "$PACKAGE/.claude-plugin/plugin.json") <(jq -S 'del(.interface)' "$PACKAGE/.codex-plugin/plugin.json") >/dev/null || status=1

cmp -s "$PACKAGE/skills/design-rdb-physical/scripts/input_paths.py" "$PACKAGE/skills/revise-rdb-physical/scripts/input_paths.py" || status=1
python3 "$PACKAGE/skills/design-rdb-physical/scripts/input_paths.py" self-test >/dev/null || status=1
python3 "$PACKAGE/skills/revise-rdb-physical/scripts/update-guard.py" self-test >/dev/null || status=1
python3 "$PACKAGE/internal/physical-design/scripts/physical_design.py" self-test >/dev/null || status=1

write_doc_examples="$ROOT/../write-doc-plugins/plugins/write-doc/skills/write-doc/assets/examples"
physical_example="$write_doc_examples/rdb-physical-design.example.md"
logical_example="$write_doc_examples/rdb-logical-data-modeling.example.md"
if [ -f "$physical_example" ] && [ -f "$logical_example" ]; then
  python3 "$PACKAGE/internal/physical-design/scripts/physical_design.py" check \
    --model-file "$logical_example" --product PostgreSQL --version 16.4 \
    < "$physical_example" >/dev/null || status=1
else
  echo '[error] write-docのRDB物理設計・論理設計の配布例が無い' >&2
  status=1
fi

while IFS= read -r script; do
  PYTHONPYCACHEPREFIX="$TMP_ROOT/pycache" python3 -m py_compile "$script" || status=1
done < <(find "$PACKAGE" -type f -name '*.py' | sort)

while IFS= read -r script; do
  bash -n "$script" || status=1
done < <(find "$ROOT/scripts" -type f -name '*.sh' | sort)

grill_root="$ROOT/../grill-plugins/plugins/grill"
write_doc_root="$ROOT/../write-doc-plugins/plugins/write-doc"
if [ -d "$grill_root" ] && [ -d "$write_doc_root" ]; then
  dev_map="$TMP_ROOT/real-roots.json"
  jq -n --arg grill "$(cd "$grill_root" && pwd -P)" --arg doc "$(cd "$write_doc_root" && pwd -P)" \
    '{schema:1,dependencies:{"grill/grill":$grill,"write-doc/write-doc":$doc}}' > "$dev_map"
  for runtime in codex claude; do
    HARNESS_PLUGIN_DEV_ROOTS="$dev_map" python3 "$TOOLS/lint-consumer-contract.py" --repo "$ROOT" --runtime "$runtime" || status=1
  done
else
  echo '[error] grillまたはwrite-docの兄弟checkoutが無い' >&2
  status=1
fi

if [ "$status" -eq 0 ]; then
  echo 'Validation: passed'
else
  echo 'Validation: failed'
fi
exit "$status"
