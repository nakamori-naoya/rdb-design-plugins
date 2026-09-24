#!/usr/bin/env python3
"""RDB物理設計の資料が、論理設計と構造上揃っているかを検査する。

基準資料: 同梱の内部skill physical-design の SKILL.md と references（物理写像、分離性、CHECKの基準）。記法は write-doc の rdb-physical-design 型。
入力: fingerprint は --model-file の論理データモデル。check は同じ論理データモデルと、標準入力の物理設計本文、--product と --version。
正規化: 論理データモデルは「論理データモデル図」の erDiagram の実体と属性行、「論理テーブル定義」の ### と #### 業務制約: の名前を読み、
  JSONへ並べ替えて sha256 を取る（論理構造の指紋）。物理設計は ## と ### の見出し、「- 項目: 値」の行、
  「index」と「代表的な読み取り」の節の最初の表を読む。表のセルは前後の空白を除き、index の名前は backtick を外して比べる。
合格述語: 必須の見出しが一度ずつある。対象DBMSと版、論理モデルのファイル名、現在の指紋が一行ずつある。入力根拠の欄が空でない。
  BDDを複製していない。物理写像・分離性判断・機能・検証が一件以上あり、決まった欄が空でない。index と Read の表の列名が決まった並びで、
  行が一件以上あり、セルが空でなく、名前が重複しない。Read の名前は Read- と3桁以上の数字。index が支える Read と、Read を支える index が
  互いの表にある。検証状態は verified か planned。機能の根拠は https か local:。論理設計の業務制約の名前が本文に現れる。
失敗時の診断: {"problem"} のJSONを1行ずつ標準出力へ。終了code 1。入力や引数が不正なら {"error"} と終了code 2。
正例: self-test の sample と write-doc の rdb-physical-design の見本。
反例: self-test の、旧い入力根拠の名前、物理写像の欄の欠落、許されない検証状態、https でない機能の根拠、BDDの混入、分離性判断の検証状態の欠落、
  index の表の空のセルと列名の違い、Read の名前の違反と空のセル、表に無い Read や index への参照、業務制約の名前の欠落、論理構造の変更。
境界例: すべて verified にした資料は ready になる。支えるindex が「なし」の Read は拒まない。
意味評価として残す範囲: 物理制約が業務制約を本当に守るか、検証証拠が verified を支えるか、index と Read の根拠と費用の妥当性、
  分離レベルと再試行の判断、CHECK を置くかの判断、導いた値を保存する判断。
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile


BUSINESS_CONSTRAINT = re.compile(r"^####\s+業務制約:\s*(.+?)\s*$")
CONTENT_TABLE = re.compile(r"^###\s+(.+?)\s*$")
BDD = re.compile(r"^(?:###\s+Scenario\b|\s*(?:Given|When|Then|And):?\s)", re.MULTILINE)
MAPPING = re.compile(r"^###\s+物理写像:\s*(.+?)\s*$")
ISOLATION = re.compile(r"^###\s+分離性判断:\s*(.+?)\s*$")
FEATURE = re.compile(r"^###\s+機能:\s*(.+?)\s*$")
READ_ID = re.compile(r"^Read-[0-9]{3,}$")
VERIFICATION = re.compile(r"^###\s+検証:\s*(.+?)\s*$")
ER_ENTITY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\{$")
ER_ATTRIBUTE = re.compile(r'^([A-Za-z_][A-Za-z0-9_\[\]]*)\s+([A-Za-z_][A-Za-z0-9_]*)\b')

REQUIRED_HEADINGS = (
    "## 対象と論理設計",
    "## 物理制約",
    "## 物理化の方針",
    "## index",
    "## トランザクションと分離レベル",
    "## パーティションと配置",
    "## 容量・性能・運用",
    "## 採用するRDB機能",
    "## 物理設計の完了条件",
    "## 未決",
    "## 代表的な読み取り",
)
SOURCE_FIELDS = (
    "- 要求資料:",
    "- 利用・負荷モデル:",
    "- 品質要求資料:",
    "- 基盤構成資料:",
    "- 検証証拠:",
)
MAPPING_FIELDS = (
    "- 論理上の意味:",
    "- 物理実装:",
    "- 一次データと同期:",
    "- 再構築・撤去:",
    "- 不変条件の保存:",
)
INDEX_COLUMNS = ("index", "対象", "種類", "支えるRead・更新", "更新費用", "検証状態")
ISOLATION_FIELDS = ("検証状態:",)
READ_COLUMNS = ("Read", "利用者", "並び順と上限", "鮮度と一貫性", "想定件数", "SLO", "支えるindex")
READ_REFERENCE = re.compile(r"Read-[0-9]+")
CODE_NAME = re.compile(r"`([^`]+)`")
FEATURE_FIELDS = ("- 利用可能な版:", "- 根拠:", "- 検証状態:")
VERIFICATION_FIELDS = (
    "- 対象:", "- 状態:", "- 方法:", "- 合格条件:", "- 見直し条件:", "- 根拠:",
)
VALID_STATES = {"verified", "planned"}


def emit(value):
    print(json.dumps(value, ensure_ascii=False))


def fail(message, code=2):
    emit({"error": message})
    raise SystemExit(code)


def read_text(path, label):
    if not os.path.isabs(path):
        fail(f"{label}は絶対pathではない: {path}")
    if os.path.islink(path) or not os.path.isfile(path):
        fail(f"{label}はsymlinkではない既存通常fileである必要がある: {path}")
    try:
        with open(path, encoding="utf-8") as stream:
            return stream.read()
    except OSError as exc:
        fail(f"{label}を読めない: {exc}")


def logical_signature(text, problems):
    signature = {}
    current = None
    source_lines = text.splitlines()
    # 論理データモデルの型: 列は「論理データモデル図」の erDiagram だけにあり、「論理テーブル定義」は ### と業務制約を持つ。
    er_start = source_lines.index("## 論理データモデル図") + 1 if "## 論理データモデル図" in source_lines else -1
    if er_start >= 0:
        er_end = next((i for i in range(er_start, len(source_lines)) if source_lines[i].startswith("## ")), len(source_lines))
        in_er = False
        entity = None
        for line in source_lines[er_start:er_end]:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_er, entity = False, None
                continue
            if stripped == "erDiagram":
                in_er = True
                continue
            if not in_er:
                continue
            opened = ER_ENTITY.match(stripped)
            if opened:
                entity = opened.group(1)
                signature.setdefault(entity, {"columns": [], "constraints": [], "definitions": []})
                continue
            if stripped == "}":
                entity = None
                continue
            if entity:
                attribute = ER_ATTRIBUTE.match(stripped)
                if attribute and attribute.group(2) not in signature[entity]["columns"]:
                    signature[entity]["columns"].append(attribute.group(2))
                    signature[entity]["definitions"].append(stripped)
    try:
        start = source_lines.index("## 論理テーブル定義") + 1
    except ValueError:
        start = -1
    if start >= 0:
        end = next(
            (index for index in range(start, len(source_lines)) if source_lines[index].startswith("## ")),
            len(source_lines),
        )
        current = None
        for line in source_lines[start:end]:
            heading = CONTENT_TABLE.match(line)
            if heading:
                code_names = re.findall(r"`([^`]+)`", heading.group(1))
                current = code_names[0] if code_names else heading.group(1).strip()
                signature.setdefault(current, {"columns": [], "constraints": [], "definitions": []})
                continue
            constraint = BUSINESS_CONSTRAINT.match(line)
            if constraint and current:
                signature[current]["constraints"].append(constraint.group(1))
    if not signature:
        problems.append("論理モデルに論理テーブル定義が1件も無い")
    return signature


def digest(signature):
    canonical = {
        name: {
            "columns": sorted(values["columns"]),
            "constraints": sorted(values["constraints"]),
            "definitions": sorted(values.get("definitions", [])),
        }
        for name, values in sorted(signature.items())
    }
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sections(lines, pattern):
    found = []
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue
        end = index + 1
        while end < len(lines) and not lines[end].startswith("### ") and not lines[end].startswith("## "):
            end += 1
        found.append((match.group(1), lines[index + 1:end]))
    return found


def split_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def section_table(lines, heading, columns, kind, problems):
    """見出しの節の最初の表を、列名が columns と一致する表として読む。"""
    if heading not in lines:
        return []
    start = lines.index(heading) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = lines[start:end]
    first = next((i for i, line in enumerate(body) if line.startswith("|")), None)
    if first is None:
        problems.append(f"{kind}の表が無い")
        return []
    header = split_row(body[first])
    if tuple(header) != columns:
        problems.append(f"{kind}の表の列が『{' | '.join(columns)}』でない")
        return []
    rows = []
    for line in body[first + 2:]:
        if not line.startswith("|"):
            break
        cells = split_row(line)
        if len(cells) != len(columns):
            problems.append(f"{kind}の表の行の列数が{len(cells)}（{len(columns)}必要）: {cells[0]}")
            continue
        row = dict(zip(columns, cells))
        for column in columns:
            if not row[column]:
                problems.append(f"{kind}『{cells[0]}』の『{column}』が空")
        rows.append(row)
    if not rows:
        problems.append(f"{kind}の表に行が1件も無い")
    names = [row[columns[0]] for row in rows]
    for name in sorted({name for name in names if names.count(name) > 1}):
        problems.append(f"{kind}『{name}』が重複")
    return rows


def require_fields(kind, values, fields, problems):
    for name, body in values:
        for field in fields:
            matches = [line for line in body if line.startswith(field)]
            if len(matches) != 1:
                problems.append(f"{kind}『{name}』の『{field}』が{len(matches)}件（1件必要）")
            elif matches[0].strip() == field:
                problems.append(f"{kind}『{name}』の『{field}』が空")


def require_states(kind, values, problems, field="- 検証状態:"):
    for name, body in values:
        matches = [line[len(field):].strip() for line in body if line.startswith(field)]
        for value in matches:
            if value not in VALID_STATES:
                problems.append(f"{kind}『{name}』の検証状態はverifiedまたはplanned: {value}")


def cmd_fingerprint(args):
    model = read_text(args.model_file, "論理モデル")
    problems = []
    signature = logical_signature(model, problems)
    if problems:
        for problem in problems:
            emit({"problem": problem})
        raise SystemExit(1)
    emit({
        "algorithm": "sha256",
        "digest": digest(signature),
        "tables": len(signature),
        "columns": sum(len(set(value["columns"])) for value in signature.values()),
        "business_constraints": sum(len(set(value["constraints"])) for value in signature.values()),
    })


def cmd_check(args):
    product = str(args.product or "").strip()
    version = str(args.version or "").strip()
    if not product or not version:
        fail("--productと--versionは空にできない")
    model = read_text(args.model_file, "論理モデル")
    design = sys.stdin.read()
    if not design.strip():
        fail("標準入力が空。物理設計本文を渡す")
    lines = design.splitlines()
    problems = []
    signature = logical_signature(model, problems)
    for heading in REQUIRED_HEADINGS:
        count = lines.count(heading)
        if count != 1:
            problems.append(f"見出し『{heading}』が{count}件（1件必要）")
    for expected in (f"- 対象DBMS: {product}", f"- 対象バージョン: {version}"):
        if expected not in lines:
            problems.append(f"対象と論理設計に『{expected}』が無い")
    basename = os.path.basename(args.model_file)
    if not any(line.startswith("- 論理モデル:") and basename in line for line in lines):
        problems.append(f"対象と論理設計に論理モデル『{basename}』が無い")
    fingerprint = f"- 論理構造の指紋: sha256:{digest(signature)}"
    if lines.count(fingerprint) != 1:
        problems.append(f"現在の論理構造の指紋『{fingerprint}』が1件必要")
    for field in SOURCE_FIELDS:
        matches = [line for line in lines if line.startswith(field)]
        if len(matches) != 1 or matches[0].strip() == field:
            problems.append(f"入力根拠『{field}』が空または1件でない")
    if BDD.search(design):
        problems.append("物理設計へBDDを複製しない")
    mappings = sections(lines, MAPPING)
    indexes = section_table(lines, "## index", INDEX_COLUMNS, "index", problems)
    isolations = sections(lines, ISOLATION)
    reads = section_table(lines, "## 代表的な読み取り", READ_COLUMNS, "Read", problems)
    features = sections(lines, FEATURE)
    verifications = sections(lines, VERIFICATION)
    for kind, values in (("物理写像", mappings), ("分離性判断", isolations), ("機能", features), ("検証", verifications)):
        if not values:
            problems.append(f"### {kind}: の項目が1件も無い")
    require_fields("物理写像", mappings, MAPPING_FIELDS, problems)
    require_fields("分離性判断", isolations, ISOLATION_FIELDS, problems)
    for row in reads:
        if not READ_ID.match(row["Read"]):
            problems.append(f"Readの名前はRead-と3桁以上の数字: {row['Read']}")
    read_names = {row["Read"] for row in reads}
    index_names = {CODE_NAME.sub(r"\1", row["index"]) for row in indexes}
    for row in indexes:
        for reference in READ_REFERENCE.findall(row["支えるRead・更新"]):
            if reference not in read_names:
                problems.append(f"index『{row['index']}』が支える『{reference}』が代表的な読み取りの表に無い")
    for row in reads:
        if row["支えるindex"] == "なし":
            continue
        for name in CODE_NAME.findall(row["支えるindex"]) or [row["支えるindex"]]:
            if name not in index_names:
                problems.append(f"Read『{row['Read']}』を支える『{name}』がindexの表に無い")
    for row in indexes:
        if row["検証状態"] and row["検証状態"] not in VALID_STATES:
            problems.append(f"index『{row['index']}』の検証状態はverifiedまたはplanned: {row['検証状態']}")
    require_fields("機能", features, FEATURE_FIELDS, problems)
    require_fields("検証", verifications, VERIFICATION_FIELDS, problems)
    require_states("機能", features, problems)
    require_states("分離性判断", isolations, problems, field="検証状態:")
    for name, body in verifications:
        state_lines = [line[len("- 状態:"):].strip() for line in body if line.startswith("- 状態:")]
        for state in state_lines:
            if state not in VALID_STATES:
                problems.append(f"検証『{name}』の状態はverifiedまたはplanned: {state}")
    feature_names = [name for name, _ in features]
    if len(feature_names) != len(set(feature_names)):
        problems.append("採用機能名が重複")
    for name, body in features:
        evidence = [line[len("- 根拠:"):].strip() for line in body if line.startswith("- 根拠:")]
        for value in evidence:
            if not (value.startswith("https://") or value.startswith("local:")):
                problems.append(f"機能『{name}』の根拠は公式https URLまたはlocal:の実機証拠にする")
    for table in signature.values():
        for constraint in set(table["constraints"]):
            if constraint not in design:
                problems.append(f"論理設計の業務制約『{constraint}』の名前が本文に現れない")
    if problems:
        for problem in problems:
            emit({"problem": problem})
        raise SystemExit(1)
    planned = sum(1 for row in indexes if row["検証状態"] == "planned") + sum(
        1 for _, body in isolations + features
        if any(line in {"- 検証状態: planned", "検証状態: planned"} for line in body)
    ) + sum(1 for _, body in verifications if any(line == "- 状態: planned" for line in body))
    emit({
        "check": "aligned",
        "status": "unresolved" if planned else "ready",
        "database": {"product": product, "version": version},
        "logical_schema_sha256": digest(signature),
        "physical_mappings": len(mappings),
        "indexes": len(indexes),
        "isolation_cases": len(isolations),
        "read_scenarios": len(reads),
        "verification_items": len(verifications),
        "planned_items": planned,
    })


def sample(digest_value):
    return "\n".join((
        "# RDB物理設計", "## 対象と論理設計", "- 対象DBMS: PostgreSQL", "- 対象バージョン: 16",
        "- 論理モデル: logical.md", f"- 論理構造の指紋: sha256:{digest_value}",
        "- 要求資料: requirements.md", "- 利用・負荷モデル: workload.md", "- 品質要求資料: quality.md",
        "- 基盤構成資料: architecture.md", "- 検証証拠: なし（初期設計）",
        "## 物理制約", "同じ利用枠に有効な予約は一つ を排他制約で守る",
        "## 物理化の方針", "### 物理写像: 検索用生成列", "- 論理上の意味: 予約枠",
        "- 物理実装: normalized_slot生成列", "- 一次データと同期: reservationから同一transactionで生成",
        "- 再構築・撤去: 再生成後にindexを再作成", "- 不変条件の保存: 排他制約の意味を変えない",
        "## index",
        "| index | 対象 | 種類 | 支えるRead・更新 | 更新費用 | 検証状態 |",
        "|---|---|---|---|---|---|",
        "| `reservation_slot_excl` | reservation(normalized_slot) | GiST | Read-001と予約作成 | 測定予定 | planned |",
        "", "`reservation_slot_excl`は重複予約を拒む。根拠は負荷仮説。", "",
        "## トランザクションと分離レベル", "### 分離性判断: 同時予約",
        "予約Aと予約Bが同じ利用枠へ同時に進むと二重予約になりうる。READ COMMITTED と排他制約で一方を拒む。",
        "検証状態: planned",
        "## パーティションと配置", "partitionなし。基盤構成に従う。", "## 容量・性能・運用", "測定予定。",
        "## 採用するRDB機能", "### 機能: 排他制約", "- 利用可能な版: 9.0",
        "- 根拠: https://www.postgresql.org/docs/16/", "- 検証状態: planned",
        "## 物理設計の完了条件", "### 検証: 同時予約", "- 対象: 排他制約", "- 状態: planned",
        "- 方法: 二transactionを交差実行", "- 合格条件: 一方だけ成立", "- 見直し条件: 競合率増加", "- 根拠: 初期設計",
        "## 未決", "実機結果", "## 代表的な読み取り",
        "| Read | 利用者 | 並び順と上限 | 鮮度と一貫性 | 想定件数 | SLO | 支えるindex |",
        "|---|---|---|---|---|---|---|",
        "| Read-001 | 予約者 | 開始時刻, 100 | primary | 1000 | p95 100ms | `reservation_slot_excl` |",
        "", "Read-001は、日付で空き枠を探す。", "",
    ))


def self_test():
    logical_text = "\n".join((
        "# 論理設計", "## 論理データモデル図", "```mermaid", "erDiagram", "    reservation {",
        '        uuid id PK "予約"', '        tstzrange slot "利用枠"', "    }", "```",
        "## 論理テーブル定義", "### `reservation`（予約）", "予約。", "#### 業務制約: 同じ利用枠に有効な予約は一つ", "",
    ))
    with tempfile.TemporaryDirectory() as directory:
        logical = os.path.join(directory, "logical.md")
        with open(logical, "w", encoding="utf-8") as stream:
            stream.write(logical_text)
        fingerprint = subprocess.run([sys.executable, __file__, "fingerprint", "--model-file", logical], text=True, capture_output=True)
        assert fingerprint.returncode == 0
        design = sample(json.loads(fingerprint.stdout)["digest"])
        command = [sys.executable, __file__, "check", "--model-file", logical, "--product", "PostgreSQL", "--version", "16"]
        run = lambda body: subprocess.run(command, input=body, text=True, capture_output=True)
        good = run(design)
        assert good.returncode == 0 and json.loads(good.stdout)["status"] == "unresolved"
        for current, deprecated in (
            ("- 要求資料:", "- 要求の基準資料:"),
            ("- 品質要求資料:", "- 品質要求の基準資料:"),
            ("- 基盤構成資料:", "- 基盤構成の基準資料:"),
        ):
            assert run(design.replace(current, deprecated)).returncode == 1
        assert run("").returncode == 2
        assert run(design.replace("- 論理上の意味: 予約枠\n", "")).returncode == 1
        assert run(design.replace("| 測定予定 | planned |", "| 測定予定 | maybe |")).returncode == 1
        assert run(design.replace("| 測定予定 | planned |", "| 測定予定 |  |")).returncode == 1
        assert run(design.replace("| index | 対象 |", "| 名前 | 対象 |")).returncode == 1
        assert run(design.replace("| Read-001 |", "| R1 |")).returncode == 1
        assert run(design.replace("| p95 100ms |", "| |")).returncode == 1
        assert run(design.replace("| Read-001と予約作成 |", "| Read-002と予約作成 |")).returncode == 1
        assert run(design.replace("| `reservation_slot_excl` |\n", "| `slot_idx` |\n")).returncode == 1
        missing = run(design.replace("同じ利用枠に有効な予約は一つ を排他制約で守る", "排他制約で守る"))
        assert missing.returncode == 1 and "の名前が本文に現れない" in missing.stdout
        assert run(design.replace("https://www.postgresql.org/docs/16/", "記憶")).returncode == 1
        assert run(design.replace("### 物理写像: 検索用生成列", "### Scenario: 混入")).returncode == 1
        assert run(design.replace("検証状態: planned\n## パーティション", "## パーティション")).returncode == 1
        verified = (
            design.replace("検証状態: planned", "検証状態: verified")
            .replace("- 状態: planned", "- 状態: verified")
            .replace("| 測定予定 | planned |", "| 測定予定 | verified |")
        )
        ready = run(verified)
        assert ready.returncode == 0 and json.loads(ready.stdout)["status"] == "ready"
        with open(logical, "w", encoding="utf-8") as stream:
            stream.write(logical_text.replace('        tstzrange slot "利用枠"', '        tstzrange slot "利用枠"\n        text note "メモ"'))
        assert run(design).returncode == 1
    emit({"self_test": "passed", "cases": 20})


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    fingerprint = sub.add_parser("fingerprint")
    fingerprint.add_argument("--model-file", required=True)
    check = sub.add_parser("check")
    check.add_argument("--model-file", required=True)
    check.add_argument("--product", required=True)
    check.add_argument("--version", required=True)
    sub.add_parser("self-test")
    args = parser.parse_args()
    if args.command == "fingerprint":
        cmd_fingerprint(args)
    elif args.command == "check":
        cmd_check(args)
    else:
        self_test()


if __name__ == "__main__":
    main()
