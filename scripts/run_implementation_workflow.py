#!/usr/bin/env python3
"""Run the controlled implementation workflow."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SCRIPT_CONFIG_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_CONFIG_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_CONFIG_ROOT))

from implementation_workflow import (  # noqa: E402
    DEFAULT_MAX_CONTEXT_TOKENS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STRUCTURE_MAX_FILE_BYTES,
    DEFAULT_STRUCTURE_SLICE_RECORDS,
    DEFAULT_VERIFICATION_TIMEOUT_SECONDS,
    IMPLEMENTATION_MODES,
    ImplementationWorkflowError,
    normalize_verification_commands,
    pytest_verification_command,
    run_implementation_workflow,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded implementation packets with draft/apply policy.")
    parser.add_argument("--target-root", default=".", help="Target repository root.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for implementation artifacts.")
    parser.add_argument("--mode", choices=sorted(IMPLEMENTATION_MODES), default="draft")
    parser.add_argument("--packet-file", default=None, help="Explicit implementation packet JSON file.")
    parser.add_argument("--from-report", default=None, help="Documenter report JSON artifact to derive approved packets from.")
    parser.add_argument(
        "--approve-change-plan-item",
        action="append",
        default=[],
        help="Approved change-plan item ID from --from-report. May be repeated.",
    )
    parser.add_argument(
        "--approve-all-safe",
        action="store_true",
        help="Approve all safe_documentation_edit items when deriving packets from --from-report.",
    )
    parser.add_argument(
        "--verification-command-json",
        action="append",
        default=[],
        help='Verification command as JSON, for example {"id":"tests","command":["python","-m","pytest","tests"]}.',
    )
    parser.add_argument(
        "--verification-pytest",
        action="append",
        default=[],
        help="Add a controller-declared pytest verification path relative to the target root.",
    )
    parser.add_argument("--verification-timeout-seconds", type=int, default=DEFAULT_VERIFICATION_TIMEOUT_SECONDS)
    parser.add_argument("--max-context-tokens", type=int, default=DEFAULT_MAX_CONTEXT_TOKENS)
    parser.add_argument("--structure-slice-records", type=int, default=DEFAULT_STRUCTURE_SLICE_RECORDS)
    parser.add_argument("--structure-max-file-bytes", type=int, default=DEFAULT_STRUCTURE_MAX_FILE_BYTES)
    parser.add_argument("--no-structure-index", action="store_true", help="Do not attach Phase 12 structure slices.")
    parser.add_argument("--resume", default=None, help="Resume from an implementation state or report artifact.")
    parser.add_argument("--resume-allow-arg-changes", action="store_true")
    parser.add_argument("--stop-after-packets", type=int, default=None)
    return parser.parse_args()


def command_json_values(values: list[str]) -> list[dict[str, object]]:
    import json

    raw: list[object] = []
    for value in values:
        try:
            raw.append(json.loads(value))
        except json.JSONDecodeError as exc:
            raise ImplementationWorkflowError(f"Invalid --verification-command-json value: {exc}") from exc
    return normalize_verification_commands(raw)


def main() -> int:
    args = parse_args()
    commands = command_json_values(args.verification_command_json)
    commands.extend(
        pytest_verification_command(path, args.verification_timeout_seconds)
        for path in args.verification_pytest
    )
    report, paths = run_implementation_workflow(
        target_root=Path(args.target_root),
        output_dir=Path(args.output_dir),
        mode=args.mode,
        packet_file=Path(args.packet_file) if args.packet_file else None,
        report_path=Path(args.from_report) if args.from_report else None,
        approved_item_ids=args.approve_change_plan_item,
        approve_all_safe=bool(args.approve_all_safe),
        verification_commands=commands,
        max_context_tokens=args.max_context_tokens,
        build_structure_index_enabled=not args.no_structure_index,
        structure_slice_records=args.structure_slice_records,
        structure_max_file_bytes=args.structure_max_file_bytes,
        resume_path=Path(args.resume) if args.resume else None,
        resume_allow_arg_changes=bool(args.resume_allow_arg_changes),
        stop_after_packets=args.stop_after_packets,
    )
    print(f"Wrote {paths.plan_path}")
    print(f"Wrote {paths.state_path}")
    print(f"Wrote {paths.report_path}")
    if report.get("status") == "failed":
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImplementationWorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
