#!/usr/bin/env python3
"""RDB物理設計の資料が、論理設計と構造上揃っているかを検査する。

基準資料: write-doc の公開契約が rdb-logical-data-modeling 型と rdb-physical-design 型について宣言した「検査が読む目印」。
  見出しの文言は読まない。
入力: fingerprint は --model-file の論理データモデル。check は同じ論理データモデルと、標準入力の物理設計本文、--product と --version。
正規化: 論理データモデルからは、erDiagram の Mermaid ブロックの実体と属性の行と、`#### 業務制約: <名前>` の名前を読み、
  JSONへ並べ替えて sha256 を取る（論理構造の指紋）。物理設計からは、`- <ラベル>:` の行、`### 分離性判断:` `### 機能:` `### 検証:` の小見出しの下の行、
  見出し行が契約の形の三つの表（物理制約、index、代表的な読み取り）を読む。表のセルは前後の空白と backtick を除いて比べる。
合格述語: 対象DBMSと版、論理モデルのファイル名、現在の指紋、入力根拠の各行が一行ずつあり空でない。BDDを複製していない。
  物理制約の表の制約名の集合が、論理設計の業務制約の名前の集合と一致する。index と Read の表が一つずつあり、行が一件以上、セルが空でなく、
  名前が重複しない。Read の名前は Read- と3桁以上の数字。index が支える Read と、Read を支える index が互いの表にある。
  分離性判断と検証が一件以上ある。分離性判断は `検証状態:` の行を一つ、検証は `- 状態:` の行を一つ持つ。機能は名前が重複せず、
  `- 利用可能な版:` `- 根拠:` `- 検証状態:` の行を一つずつ持ち、根拠は https か local: で始まる。検証状態と状態は verified か planned。
失敗時の診断: {"problem"} のJSONを1行ずつ標準出力へ。終了code 1。入力や引数が不正なら {"error"} と終了code 2。
正例: self-test の sample と write-doc の rdb-physical-design の見本。
反例: self-test の、入力根拠の名前の違い、許されない検証状態、https でない機能の根拠、BDDの混入、分離性判断の検証状態の欠落、
  index の表の空のセル、Read の名前の違反、表に無い Read への参照、物理制約の表に無い業務制約、論理構造の変更。
境界例: 見出しに結論を入れた資料は通る。すべて verified にした資料は ready になる。支えるindex が「なし」の Read は拒まない。
意味評価として残す範囲: 物理制約が業務制約を本当に守るか、物理写像が論理上の意味を保つか、検証証拠が verified を支えるか、
  index と Read の根拠と費用の妥当性、分離レベルと再試行の判断、CHECK を置くかの判断、導いた値を保存する判断。
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
BDD = re.compile(r"^(?:###\s+Scenario\b|\s*(?:Given|When|Then|And):?\s)", re.MULTILINE)
ISOLATION = re.compile(r"^###\s+分離性判断:\s*(.+?)\s*$")
FEATURE = re.compile(r"^###\s+機能:\s*(.+?)\s*$")
VERIFICATION = re.compile(r"^###\s+検証:\s*(.+?)\s*$")
READ_ID = re.compile(r"^Read-[0-9]{3,}$")
READ_REFERENCE = re.compile(r"Read-[0-9]+")
ER_ENTITY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\{$")
ER_ATTRIBUTE = re.compile(r"^([A-Za-z_][A-Za-z0-9_\[\]]*)\s+([A-Za-z_][A-Za-z0-9_]*)\b")

SOURCE_FIELDS = (
    "- 要求資料:",
    "- 利用・負荷モデル:",
    "- 品質要求資料:",
    "- 基盤構成資料:",
    "- 検証証拠:",
)
CONSTRAINT_COLUMNS = ("制約名", "対象", "実現方法", "適用時点", "違反時の扱い")
INDEX_COLUMNS = ("index", "対象", "種類", "支えるRead・更新", "更新費用", "検証状態")
READ_COLUMNS = ("Read", "利用者", "並び順と上限", "鮮度と一貫性", "想定件数", "SLO", "支えるindex")
FEATURE_FIELDS = ("- 利用可能な版:", "- 根拠:", "- 検証状態:")
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


def outside_code(text):
    """コードブロックの外の行と、Mermaid ブロックごとの中身の行を返す。"""
    prose, blocks = [], []
    fence, language = None, ""
    for line in text.splitlines():
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith("```"):
                if language == "mermaid":
                    blocks.append(fence)
                fence = None
            else:
                fence.append(stripped)
            continue
        if stripped.startswith("```"):
            fence, language = [], stripped[3:].strip()
            continue
        prose.append(line)
    return prose, blocks


def logical_signature(text, problems):
    """論理データモデルの目印（erDiagram の実体と属性、業務制約の名前）から論理構造を取り出す。"""
    prose, blocks = outside_code(text)
    entities = {}
    for block in blocks:
        content = [line for line in block if line and not line.startswith("%%")]
        if not content or content[0] != "erDiagram":
            continue
        entity = None
        for line in content[1:]:
            opened = ER_ENTITY.match(line)
            if opened:
                entity = opened.group(1)
                if entity in entities:
                    problems.append(f"論理モデルの erDiagram で実体『{entity}』が重複")
                entities.setdefault(entity, [])
                continue
            if line == "}":
                entity = None
                continue
            if entity:
                attribute = ER_ATTRIBUTE.match(line)
                if attribute:
                    entities[entity].append(line)
    constraints = []
    for line in prose:
        constraint = BUSINESS_CONSTRAINT.match(line)
        if constraint:
            name = constraint.group(1).replace("`", "").strip()
            if name in constraints:
                problems.append(f"論理モデルで業務制約『{name}』が重複")
            constraints.append(name)
    if not entities:
        problems.append("論理モデルに erDiagram の実体が1件も無い")
    return {"entities": entities, "constraints": constraints}


def digest(signature):
    canonical = {
        "entities": {name: sorted(lines) for name, lines in sorted(signature["entities"].items())},
        "constraints": sorted(signature["constraints"]),
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


def one_value(kind, name, body, field, problems):
    matches = [line[len(field):].strip() for line in body if line.startswith(field)]
    if len(matches) != 1:
        problems.append(f"{kind}『{name}』の『{field}』が{len(matches)}件（1件必要）")
        return None
    if not matches[0]:
        problems.append(f"{kind}『{name}』の『{field}』が空")
        return None
    return matches[0]


def split_row(line):
    return [cell.strip().replace("`", "").strip() for cell in line.strip().strip("|").split("|")]


def marked_table(lines, columns, kind, problems):
    """見出し行が columns と一致する表を資料全体から一つ探し、行を返す。"""
    found = []
    index = 0
    while index < len(lines):
        if lines[index].startswith("|") and tuple(split_row(lines[index])) == columns:
            rows = []
            cursor = index + 2
            while cursor < len(lines) and lines[cursor].startswith("|"):
                rows.append(split_row(lines[cursor]))
                cursor += 1
            found.append(rows)
            index = cursor
            continue
        index += 1
    if len(found) != 1:
        problems.append(f"見出し行が『| {' | '.join(columns)} |』の{kind}の表が{len(found)}個（1個必要）")
        return []
    result = []
    for cells in found[0]:
        if len(cells) != len(columns):
            problems.append(f"{kind}の表の行の列数が{len(cells)}（{len(columns)}必要）: {cells[0]}")
            continue
        row = dict(zip(columns, cells))
        for column in columns:
            if not row[column]:
                problems.append(f"{kind}『{cells[0]}』の『{column}』が空")
        result.append(row)
    if not result:
        problems.append(f"{kind}の表に行が1件も無い")
    names = [row[columns[0]] for row in result]
    for name in sorted({name for name in names if names.count(name) > 1}):
        problems.append(f"{kind}『{name}』が重複")
    return result


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
        "tables": len(signature["entities"]),
        "columns": sum(len(lines) for lines in signature["entities"].values()),
        "business_constraints": len(signature["constraints"]),
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
    problems = []
    signature = logical_signature(model, problems)
    lines, _ = outside_code(design)
    for expected in (f"- 対象DBMS: {product}", f"- 対象バージョン: {version}"):
        if lines.count(expected) != 1:
            problems.append(f"『{expected}』の行が1件必要")
    basename = os.path.basename(args.model_file)
    if not any(line.startswith("- 論理モデル:") and basename in line for line in lines):
        problems.append(f"『- 論理モデル:』の行に論理モデル『{basename}』が無い")
    fingerprint = f"- 論理構造の指紋: sha256:{digest(signature)}"
    if lines.count(fingerprint) != 1:
        problems.append(f"現在の論理構造の指紋『{fingerprint}』が1件必要")
    for field in SOURCE_FIELDS:
        matches = [line for line in lines if line.startswith(field)]
        if len(matches) != 1 or matches[0].strip() == field:
            problems.append(f"入力根拠『{field}』が空または1件でない")
    if BDD.search(design):
        problems.append("物理設計へBDDを複製しない")

    physical_constraints = marked_table(lines, CONSTRAINT_COLUMNS, "物理制約", problems)
    named = {row["制約名"] for row in physical_constraints}
    logical = set(signature["constraints"])
    for name in sorted(logical - named):
        problems.append(f"論理設計の業務制約『{name}』が物理制約の表に無い")
    for name in sorted(named - logical):
        problems.append(f"物理制約の表の『{name}』は論理設計の業務制約に無い")

    index_rows = marked_table(lines, INDEX_COLUMNS, "index", problems)
    read_rows = marked_table(lines, READ_COLUMNS, "Read", problems)
    index_names = {row["index"] for row in index_rows}
    read_names = {row["Read"] for row in read_rows}
    for row in read_rows:
        if not READ_ID.match(row["Read"]):
            problems.append(f"Readの名前はRead-と3桁以上の数字にする: {row['Read']}")
        for name in (part.strip() for part in re.split(r"[、,]", row["支えるindex"])):
            if name and name != "なし" and name not in index_names:
                problems.append(f"Read『{row['Read']}』の支えるindex『{name}』がindexの表に無い")
    for row in index_rows:
        if row["検証状態"] not in VALID_STATES:
            problems.append(f"index『{row['index']}』の検証状態はverifiedまたはplanned: {row['検証状態']}")
        for reference in READ_REFERENCE.findall(row["支えるRead・更新"]):
            if reference not in read_names:
                problems.append(f"index『{row['index']}』の支えるRead『{reference}』が代表的な読み取りの表に無い")

    isolations = sections(lines, ISOLATION)
    features = sections(lines, FEATURE)
    verifications = sections(lines, VERIFICATION)
    for kind, values in (("分離性判断", isolations), ("検証", verifications)):
        if not values:
            problems.append(f"### {kind}: の項目が1件も無い")
    states = [row["検証状態"] for row in index_rows]
    for name, body in isolations:
        states.append(one_value("分離性判断", name, body, "検証状態:", problems))
    for name, body in verifications:
        states.append(one_value("検証", name, body, "- 状態:", problems))
    feature_names = [name for name, _ in features]
    if len(feature_names) != len(set(feature_names)):
        problems.append("採用機能名が重複")
    for name, body in features:
        one_value("機能", name, body, "- 利用可能な版:", problems)
        evidence = one_value("機能", name, body, "- 根拠:", problems)
        if evidence is not None and not (evidence.startswith("https://") or evidence.startswith("local:")):
            problems.append(f"機能『{name}』の根拠は公式https URLまたはlocal:の実機証拠にする")
        states.append(one_value("機能", name, body, "- 検証状態:", problems))
    for state in states:
        if state is not None and state not in VALID_STATES:
            problems.append(f"検証状態はverifiedまたはplanned: {state}")
    if problems:
        for problem in problems:
            emit({"problem": problem})
        raise SystemExit(1)
    planned = sum(1 for state in states if state == "planned")
    emit({
        "check": "aligned",
        "status": "unresolved" if planned else "ready",
        "database": {"product": product, "version": version},
        "logical_schema_sha256": digest(signature),
        "business_constraints": len(logical),
        "indexes": len(index_rows),
        "isolation_cases": len(isolations),
        "read_scenarios": len(read_rows),
        "verification_items": len(verifications),
        "planned_items": planned,
    })


def sample(digest_value):
    return "\n".join((
        "# RDB物理設計", "予約を PostgreSQL 16 で実現する。",
        "## 論理設計を変えずに PostgreSQL 16 へ写す", "- 対象DBMS: PostgreSQL", "- 対象バージョン: 16",
        "- 論理モデル: logical.md", f"- 論理構造の指紋: sha256:{digest_value}",
        "- 要求資料: requirements.md", "- 利用・負荷モデル: workload.md", "- 品質要求資料: quality.md",
        "- 基盤構成資料: architecture.md", "- 検証証拠: 未実施（初期設計）",
        "## 重複予約は排他制約で拒む",
        "| 制約名 | 対象 | 実現方法 | 適用時点 | 違反時の扱い |", "|---|---|---|---|---|",
        "| 同じ利用枠に有効な予約は一つ | reservation(slot) | 排他制約 | 即時 | 利用者へ拒否を返す |",
        "## index",
        "| index | 対象 | 種類 | 支えるRead・更新 | 更新費用 | 検証状態 |", "|---|---|---|---|---|---|",
        "| `reservation_slot_excl` | `reservation (slot)` | GiST | Read-001、予約作成 | 書込みごとに更新 | planned |",
        "## トランザクションと分離レベル", "### 分離性判断: 同時予約",
        "予約Aと予約Bが同じ枠へ同時に進むと二重予約が起きうるので、排他制約で一方を拒む。", "検証状態: planned",
        "## 採用するRDB機能", "### 機能: 排他制約", "- 利用可能な版: 9.0",
        "- 根拠: https://www.postgresql.org/docs/16/", "- 検証状態: planned",
        "## 物理設計の完了条件", "### 検証: 同時予約", "二transactionを交差実行し、一方だけ成立することを確かめる。", "- 状態: planned",
        "## 代表的な読み取り",
        "| Read | 利用者 | 並び順と上限 | 鮮度と一貫性 | 想定件数 | SLO | 支えるindex |", "|---|---|---|---|---|---|---|",
        "| Read-001 | 予約者 | 開始時刻、100 | primary | 1000 | p95 100ms | `reservation_slot_excl` |", "",
    ))


def self_test():
    logical_text = "\n".join((
        "# 論理設計", "```mermaid", "erDiagram", "    reservation {", "        uuid id PK", "        text slot", "    }", "```",
        "### `reservation`（予約）", "#### 業務制約: 同じ利用枠に有効な予約は一つ", "",
    ))
    with tempfile.TemporaryDirectory() as directory:
        logical = os.path.join(directory, "logical.md")
        with open(logical, "w", encoding="utf-8") as stream:
            stream.write(logical_text)
        fingerprint = subprocess.run([sys.executable, __file__, "fingerprint", "--model-file", logical], text=True, capture_output=True)
        assert fingerprint.returncode == 0, fingerprint.stdout
        design = sample(json.loads(fingerprint.stdout)["digest"])
        command = [sys.executable, __file__, "check", "--model-file", logical, "--product", "PostgreSQL", "--version", "16"]
        run = lambda body: subprocess.run(command, input=body, text=True, capture_output=True)
        good = run(design)
        assert good.returncode == 0 and json.loads(good.stdout)["status"] == "unresolved", good.stdout
        cases = 1
        for bad in (
            design.replace("- 要求資料:", "- 要求の基準資料:"),
            design.replace("- 検証状態: planned", "- 検証状態: maybe", 1),
            design.replace("https://www.postgresql.org/docs/16/", "記憶"),
            design.replace("### 分離性判断: 同時予約", "### Scenario: 混入"),
            design.replace("検証状態: planned\n## 採用", "\n## 採用"),
            design.replace("| 書込みごとに更新 |", "|  |"),
            design.replace("| Read-001 |", "| Read-1 |"),
            design.replace("Read-001、予約作成", "Read-002、予約作成"),
            design.replace("| 同じ利用枠に有効な予約は一つ |", "| 予約は重ならない |"),
        ):
            assert run(bad).returncode == 1, bad
            cases += 1
        assert run("").returncode == 2
        cases += 1
        concluded = design.replace("## index", "## 重複予約の判定は GiST の index 一つで支える")
        assert run(concluded).returncode == 0
        cases += 1
        ready = run(design.replace("planned", "verified"))
        assert ready.returncode == 0 and json.loads(ready.stdout)["status"] == "ready", ready.stdout
        cases += 1
        with open(logical, "a", encoding="utf-8") as stream:
            stream.write("#### 業務制約: 予約は開始より前に取り消せる\n")
        assert run(design).returncode == 1
        cases += 1
    emit({"self_test": "passed", "cases": cases})


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
