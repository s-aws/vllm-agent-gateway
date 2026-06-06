#!/usr/bin/env python3
"""Check that project markdown docs are linked from docs/README.md."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.docs_index import docs_index_report  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--index-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root)
    report = docs_index_report(
        repo_root,
        Path(args.index_path) if args.index_path else None,
    )
    print("DOCS INDEX SUMMARY " + json.dumps(report, ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("DOCS INDEX FAIL")
        return 1
    print("DOCS INDEX PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
