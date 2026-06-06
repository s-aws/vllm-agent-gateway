#!/usr/bin/env python3
"""Validate, snapshot, set up, or clean up managed test fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.fixtures.manager import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    DEFAULT_OUTPUT_ROOT,
    FixtureCommand,
    run_fixture_manager,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[command.value for command in FixtureCommand],
        help="Fixture manager command.",
    )
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--fixture-id", action="append", dest="fixture_ids", default=[])
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--cleanup-after", action="store_true")
    parser.add_argument("--include-tree-hashes", action="store_true")
    parser.add_argument("--report-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_fixture_manager(
        config_root=Path(args.config_root),
        command=FixtureCommand(args.command),
        manifest_path=Path(args.manifest),
        fixture_ids=tuple(args.fixture_ids),
        output_root=Path(args.output_root),
        run_id=args.run_id,
        cleanup_after=args.cleanup_after,
        include_tree_hashes=args.include_tree_hashes,
        report_path=Path(args.report_path) if args.report_path else None,
    )
    print(f"FIXTURE MANAGER REPORT {report['report_path']}")
    print(
        "FIXTURE MANAGER SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "command": report["command"],
                "fixture_count": len(report.get("fixtures", [])),
                "setup_count": len(report.get("setup", [])),
                "cleanup_removed": report.get("cleanup", {}).get("removed")
                if isinstance(report.get("cleanup"), dict)
                else None,
                "error_count": len(report.get("errors", [])),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("FIXTURE MANAGER FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("FIXTURE MANAGER PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
