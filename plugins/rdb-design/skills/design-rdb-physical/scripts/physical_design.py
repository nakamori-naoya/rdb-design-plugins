#!/usr/bin/env python3
"""RDB物理設計の物理制約が、論理データモデルの業務制約と名前で一対一に対応するかを検査する。

目印: write-doc の rdb-logical-data-modeling 型の `#### 業務制約: <名前>` の行と、rdb-physical-design 型の
  見出し行が `| 制約名 | 対象 | 実現方法 | 適用時点 | 違反時の扱い |` の表。見出しの文言は読まない。
入力: --model-file に論理データモデル資料、--design-file に物理設計資料の絶対パス。
合格述語: 物理制約の表がちょうど一つあり、その制約名の集合が業務制約の名前の集合と一致する。名前は前後の空白と backtick を除いて比べる。
失敗時の診断: {"problem"} の JSON を1行ずつ標準出力へ出し、終了コード 1。入力を読めなければ {"error"} と終了コード 2。
正例: self-test の sample と、write-doc の rdb-physical-design の見本。
反例: self-test の、物理制約の表に無い業務制約、業務制約に無い物理制約、物理制約の表が無い資料。
境界例: 見出しに結論を入れた資料は通る。
意味評価として残す範囲: 物理制約が業務制約を本当に守るか、物理写像、index と Read、分離レベルと繰り返しの回数、検証状態の妥当性。
"""

import argparse
import json
import os
import re

BUSINESS_CONSTRAINT = re.compile(r"^####\s+業務制約:\s*(.+?)\s*$")
CONSTRAINT_COLUMNS = ("制約名", "対象", "実現方法", "適用時点", "違反時の扱い")


def emit(value):
    print(json.dumps(value, ensure_ascii=False))


def read_text(path, label):
    if not os.path.isabs(path) or os.path.islink(path) or not os.path.isfile(path):
        emit({"error": f"{label}は symlink でない既存ファイルの絶対パスにする: {path}"})
        raise SystemExit(2)
    with open(path, encoding="utf-8") as stream:
        return stream.read()


def prose_lines(text):
    """コードブロックの外の行を返す。"""
    lines, fenced = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            lines.append(line)
    return lines


def cells(line):
    return [cell.strip().replace("`", "").strip() for cell in line.strip().strip("|").split("|")]


def business_constraints(text):
    return {m.group(1).replace("`", "").strip() for line in prose_lines(text) if (m := BUSINESS_CONSTRAINT.match(line))}


def physical_constraints(text, problems):
    lines = prose_lines(text)
    tables = []
    for index, line in enumerate(lines):
        if line.startswith("|") and tuple(cells(line)) == CONSTRAINT_COLUMNS:
            rows, cursor = [], index + 2
            while cursor < len(lines) and lines[cursor].startswith("|"):
                rows.append(cells(lines[cursor])[0])
                cursor += 1
            tables.append(rows)
    if len(tables) != 1:
        problems.append(f"見出し行が『| {' | '.join(CONSTRAINT_COLUMNS)} |』の物理制約の表が{len(tables)}個（1個必要）")
        return set()
    return set(tables[0])


def check(model_text, design_text):
    problems = []
    logical = business_constraints(model_text)
    physical = physical_constraints(design_text, problems)
    if not problems:
        problems += [f"論理データモデルの業務制約『{n}』が物理制約の表に無い" for n in sorted(logical - physical)]
        problems += [f"物理制約の表の『{n}』は論理データモデルの業務制約に無い" for n in sorted(physical - logical)]
    return problems


def self_test():
    logical = "# 論理\n### `reservation`\n#### 業務制約: 同じ利用枠に有効な予約は一つ\n"
    header = "| 制約名 | 対象 | 実現方法 | 適用時点 | 違反時の扱い |\n|---|---|---|---|---|\n"
    design = "# 物理\n## 重複予約は排他制約で拒む\n" + header + "| 同じ利用枠に有効な予約は一つ | reservation | 排他制約 | 即時 | 拒否 |\n"
    assert check(logical, design) == []
    assert check(logical + "#### 業務制約: 取消は開始前まで\n", design)
    assert check(logical, design.replace("| 同じ利用枠に有効な予約は一つ |", "| 予約は重ならない |"))
    assert check(logical, "# 物理\n")
    emit({"self_test": "passed", "cases": 4})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-file")
    parser.add_argument("--design-file")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.model_file or not args.design_file:
        emit({"error": "--model-file と --design-file を渡す"})
        raise SystemExit(2)
    problems = check(read_text(args.model_file, "論理データモデル資料"), read_text(args.design_file, "物理設計資料"))
    for problem in problems:
        emit({"problem": problem})
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
