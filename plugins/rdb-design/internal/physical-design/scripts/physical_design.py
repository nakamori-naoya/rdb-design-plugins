#!/usr/bin/env python3
"""Validate the closed structural contract of an RDB physical-design document."""

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
INDEX = re.compile(r"^###\s+index:\s*(.+?)\s*$")
ISOLATION = re.compile(r"^###\s+分離性判断:\s*(.+?)\s*$")
FEATURE = re.compile(r"^###\s+機能:\s*(.+?)\s*$")
READ = re.compile(r"^###\s+Read-[0-9]+:\s*(.+?)\s*$")
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
INDEX_FIELDS = (
    "- 対象:", "- 種類:", "- 目的:", "- 列の順番:",
    "- 対象Read・更新:", "- 根拠:", "- 更新費用:", "- 検証状態:",
)
ISOLATION_FIELDS = ("検証状態:",)
READ_FIELDS = (
    "- 利用者と目的:", "- 入力・検索条件:", "- 結合:",
    "- 並び順と上限:", "- 返す情報:", "- 鮮度と一貫性:",
    "- 想定件数:", "- SLO:", "- 支えるindex:",
)
FEATURE_FIELDS = ("- 利用可能な版:", "- 根拠:", "- 検証状態:")
VERIFICATION_FIELDS = (
    "- 対象:", "- 状態:", "- 方法:", "- 合格条件:", "- 見直し条件:", "- 根拠:",
)
VALID_STATES = {"verified", "planned"}
ABSENT_EVIDENCE = re.compile(r"^\s*(?:なし|無し|未提供|未取得|未確認)(?:\s|[（(]|$)")


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
    indexes = sections(lines, INDEX)
    isolations = sections(lines, ISOLATION)
    reads = sections(lines, READ)
    features = sections(lines, FEATURE)
    verifications = sections(lines, VERIFICATION)
    for kind, values in (("物理写像", mappings), ("index", indexes), ("分離性判断", isolations), ("Read", reads), ("機能", features), ("検証", verifications)):
        if not values:
            problems.append(f"### {kind}: の項目が1件も無い")
    require_fields("物理写像", mappings, MAPPING_FIELDS, problems)
    require_fields("index", indexes, INDEX_FIELDS, problems)
    require_fields("分離性判断", isolations, ISOLATION_FIELDS, problems)
    require_fields("Read", reads, READ_FIELDS, problems)
    require_fields("機能", features, FEATURE_FIELDS, problems)
    require_fields("検証", verifications, VERIFICATION_FIELDS, problems)
    for kind, values in (("index", indexes), ("機能", features)):
        require_states(kind, values, problems)
    require_states("分離性判断", isolations, problems, field="検証状態:")
    for name, body in verifications:
        state_lines = [line[len("- 状態:"):].strip() for line in body if line.startswith("- 状態:")]
        for state in state_lines:
            if state not in VALID_STATES:
                problems.append(f"検証『{name}』の状態はverifiedまたはplanned: {state}")
    evidence_sources = [line[len("- 検証証拠:"):].strip() for line in lines if line.startswith("- 検証証拠:")]
    has_verified = any(
        line in {"- 検証状態: verified", "検証状態: verified", "- 状態: verified"}
        for line in lines
    )
    if has_verified and evidence_sources and ABSENT_EVIDENCE.search(evidence_sources[0]):
        problems.append("検証証拠が無い資料でverifiedを主張しない")
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
                problems.append(f"論理設計の業務制約『{constraint}』を物理制約で扱っていない")
    if problems:
        for problem in problems:
            emit({"problem": problem})
        raise SystemExit(1)
    planned = sum(
        1 for _, body in indexes + isolations + features
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
        "## index", "### index: reservation_slot_excl", "- 対象: reservation(normalized_slot)", "- 種類: GiST",
        "- 目的: 重複予約の拒否", "- 列の順番: 単一列", "- 対象Read・更新: Read-001と予約作成",
        "- 根拠: 負荷仮説", "- 更新費用: 測定予定", "- 検証状態: planned",
        "## トランザクションと分離レベル", "### 分離性判断: 同時予約",
        "予約Aと予約Bが同じ利用枠へ同時に進むと二重予約になりうる。READ COMMITTED と排他制約で一方を拒む。",
        "検証状態: planned",
        "## パーティションと配置", "partitionなし。基盤構成に従う。", "## 容量・性能・運用", "測定予定。",
        "## 採用するRDB機能", "### 機能: 排他制約", "- 利用可能な版: 9.0",
        "- 根拠: https://www.postgresql.org/docs/16/", "- 検証状態: planned",
        "## 物理設計の完了条件", "### 検証: 同時予約", "- 対象: 排他制約", "- 状態: planned",
        "- 方法: 二transactionを交差実行", "- 合格条件: 一方だけ成立", "- 見直し条件: 競合率増加", "- 根拠: 初期設計",
        "## 未決", "実機結果", "## 代表的な読み取り", "### Read-001: 空き枠を探す",
        "- 利用者と目的: 予約者", "- 入力・検索条件: 日付", "- 結合: なし", "- 並び順と上限: 開始時刻, 100",
        "- 返す情報: slot", "- 鮮度と一貫性: primary", "- 想定件数: 1000", "- SLO: p95 100ms",
        "- 支えるindex: reservation_slot_excl", "",
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
        assert run(design.replace("- 検証状態: planned", "- 検証状態: maybe", 1)).returncode == 1
        assert run(design.replace("https://www.postgresql.org/docs/16/", "記憶")).returncode == 1
        assert run(design.replace("### 物理写像: 検索用生成列", "### Scenario: 混入")).returncode == 1
        assert run(design.replace("検証状態: planned\n## パーティション", "## パーティション")).returncode == 1
        unsupported_verified = design.replace("検証状態: planned", "検証状態: verified").replace("- 状態: planned", "- 状態: verified")
        assert run(unsupported_verified).returncode == 1
        verified = unsupported_verified.replace(
            "- 検証証拠: なし（初期設計）",
            "- 検証証拠: local:/evidence/physical-verification.json",
        )
        ready = run(verified)
        assert ready.returncode == 0 and json.loads(ready.stdout)["status"] == "ready"
        with open(logical, "w", encoding="utf-8") as stream:
            stream.write(logical_text.replace('        tstzrange slot "利用枠"', '        tstzrange slot "利用枠"\n        text note "メモ"'))
        assert run(design).returncode == 1
    emit({"self_test": "passed", "cases": 13})


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
