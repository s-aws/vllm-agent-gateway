#!/usr/bin/env python3
"""Build a deterministic code structure index artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_CONFIG_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_CONFIG_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_CONFIG_ROOT))

from vllm_agent_gateway.structure_index.indexer import (  # noqa: E402
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_OUTPUT_DIR,
    FILE_SCOPES,
    StructureIndexError,
    build_code_structure_index,
    build_index_slice,
    write_index_artifact,
    write_slice_artifact,
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
    target_root = Path(args.target_root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir

    index = build_code_structure_index(
        target_root=target_root,
        file_scope=args.file_scope,
        max_file_bytes=args.max_file_bytes,
    )
    index_path = write_index_artifact(output_dir, target_root.name, index)
    index["artifact_path"] = str(index_path)
    index_path.write_text(json.dumps(index, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {index_path}")

    if args.slice_path or args.slice_symbol or args.slice_key_path or args.slice_reference_target:
        index_slice = build_index_slice(
            index,
            paths=args.slice_path or None,
            symbol_query=args.slice_symbol,
            key_path_prefix=args.slice_key_path,
            reference_target=args.slice_reference_target,
            max_records=args.slice_max_records,
        )
        slice_path = write_slice_artifact(output_dir, target_root.name, index_slice)
        print(f"Wrote {slice_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StructureIndexError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
