#!/usr/bin/env python3
"""Validate explicitly supplied document paths without interpreting their contents."""

import json
import os
import sys
import tempfile


def emit(value):
    print(json.dumps(value, ensure_ascii=False))


def fail(message, code):
    emit({"error": message})
    raise SystemExit(code)


def validate_path(label, value, problems, seen):
    if not isinstance(value, str) or not value:
        problems.append(f"{label}: 空でない文字列が必要")
        return
    if not os.path.isabs(value):
        problems.append(f"{label}: 絶対pathではない: {value}")
        return
    if os.path.islink(value):
        problems.append(f"{label}: symlinkは受理しない: {value}")
        return
    if not os.path.isfile(value):
        problems.append(f"{label}: 既存の通常fileではない: {value}")
        return
    resolved = os.path.realpath(value)
    if resolved in seen:
        problems.append(f"{label}: 同じ実体が重複: {value}")
        return
    seen.add(resolved)


def check(payload):
    if not isinstance(payload, dict):
        fail("入力はobjectである必要がある", 2)
    required = payload.get("required_paths")
    optional = payload.get("optional_paths", {})
    lists = payload.get("path_lists", {})
    if not isinstance(required, dict) or not isinstance(optional, dict) or not isinstance(lists, dict):
        fail("required_paths / optional_paths / path_lists はobjectである必要がある", 2)
    problems = []
    seen = set()
    for label, value in required.items():
        validate_path(label, value, problems, seen)
    for label, value in optional.items():
        if value is not None:
            validate_path(label, value, problems, seen)
    for label, values in lists.items():
        if not isinstance(values, list):
            problems.append(f"{label}: listが必要")
            continue
        for index, value in enumerate(values):
            validate_path(f"{label}[{index}]", value, problems, seen)
    if problems:
        for problem in problems:
            emit({"problem": problem})
        raise SystemExit(1)
    emit({"validated": True, "files": len(seen)})


def self_test():
    with tempfile.TemporaryDirectory() as directory:
        first = os.path.join(directory, "first.md")
        second = os.path.join(directory, "second.md")
        with open(first, "w", encoding="utf-8") as stream:
            stream.write("first")
        with open(second, "w", encoding="utf-8") as stream:
            stream.write("second")
        check({"required_paths": {"logical": first}, "optional_paths": {"quality": None}, "path_lists": {"evidence": [second]}})
        cases = [
            ({"required_paths": {"logical": "relative.md"}}, 1),
            ({"required_paths": {"logical": os.path.join(directory, "missing.md")}}, 1),
            ({"required_paths": {"logical": first}, "path_lists": {"evidence": [first]}}, 1),
            ({"required_paths": []}, 2),
        ]
        for payload, expected in cases:
            try:
                check(payload)
            except SystemExit as exc:
                assert exc.code == expected
            else:
                raise AssertionError(f"expected exit {expected}")
    emit({"self_test": "passed", "cases": 5})


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"check", "self-test"}:
        fail("usage: input_paths.py check|self-test", 2)
    if sys.argv[1] == "self-test":
        self_test()
        return
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            fail("標準入力が空", 2)
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"JSONを読めない: {exc}", 2)
    check(payload)


if __name__ == "__main__":
    main()
