#!/usr/bin/env python3
"""Allow an update only when existing and output resolve to the same regular file."""

import argparse
import json
import os
import subprocess
import sys
import tempfile


def emit(value):
    print(json.dumps(value, ensure_ascii=False))


def check(existing, output):
    problems = []
    for label, path in (("existing", existing), ("output", output)):
        if not os.path.isabs(path):
            problems.append(f"{label}は絶対pathではない: {path}")
        elif os.path.islink(path):
            problems.append(f"{label}はsymlink: {path}")
    if not problems and not os.path.isfile(existing):
        problems.append(f"existingは既存の通常fileではない: {existing}")
    if not problems and os.path.realpath(existing) != os.path.realpath(output):
        problems.append("既存の物理設計資料と更新先が同じ実体ではない")
    if problems:
        for problem in problems:
            emit({"error": problem})
        raise SystemExit(1)
    emit({"update_target": os.path.realpath(existing)})


def self_test():
    with tempfile.TemporaryDirectory() as directory:
        existing = os.path.join(directory, "physical.md")
        other = os.path.join(directory, "other.md")
        with open(existing, "w", encoding="utf-8") as stream:
            stream.write("physical")
        assert subprocess.run([sys.executable, __file__, "check", "--existing", existing, "--output", existing], capture_output=True).returncode == 0
        assert subprocess.run([sys.executable, __file__, "check", "--existing", existing, "--output", other], capture_output=True).returncode == 1
        assert subprocess.run([sys.executable, __file__, "check", "--existing", other, "--output", other], capture_output=True).returncode == 1
    emit({"self_test": "passed", "cases": 3})


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("check")
    command.add_argument("--existing", required=True)
    command.add_argument("--output", required=True)
    sub.add_parser("self-test")
    args = parser.parse_args()
    if args.command == "self-test":
        self_test()
    else:
        check(args.existing, args.output)


if __name__ == "__main__":
    main()
