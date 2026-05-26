#!/usr/bin/env python3
"""Build a deterministic code structure index artifact."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SCRIPT_CONFIG_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_CONFIG_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_CONFIG_ROOT))

from vllm_agent_gateway.structure_index.indexer import (  # noqa: E402
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_OUTPUT_DIR,
    FILE_SCOPES,
    CodeStructureIndexInvocationRequest,
    StructureIndexError,
    invoke_code_structure_index,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic code/document structure indexes.")
    parser.add_argument("--target-root", default=".", help="Repository to index.")
    parser.add_argument(
        "--file-scope",
        choices=sorted(FILE_SCOPES),
        default="tracked",
        help="Use tracked files by default, or scan all supported files.",
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for index artifacts.")
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=DEFAULT_MAX_FILE_BYTES,
        help="Skip individual files larger than this byte limit.",
    )
    parser.add_argument(
        "--slice-path",
        action="append",
        default=[],
        help="Also emit a bounded packet-ready slice for a specific repo-relative path. May be repeated.",
    )
    parser.add_argument("--slice-symbol", default=None, help="Filter slice symbol records by name/qualified name.")
    parser.add_argument("--slice-key-path", default=None, help="Filter slice config records by dotted key path prefix.")
    parser.add_argument("--slice-reference-target", default=None, help="Filter slice reference edges by target text/path.")
    parser.add_argument("--slice-max-records", type=int, default=50, help="Maximum records in the optional slice artifact.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = invoke_code_structure_index(CodeStructureIndexInvocationRequest.from_namespace(args))
    print(f"Wrote {result.artifact_paths['code_structure_index']}")
    if "code_structure_slice" in result.artifact_paths:
        print(f"Wrote {result.artifact_paths['code_structure_slice']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StructureIndexError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
