#!/usr/bin/env python3
"""Summarize the latest controller run without opening artifact trees by hand."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.run_inspector import (  # noqa: E402
    InspectorOutputFormat,
    RunInspectorConfig,
    format_run_inspection,
    inspect_run,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--controller-output-root", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--workflow", default=None)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--format", choices=[item.value for item in InspectorOutputFormat], default=InspectorOutputFormat.TEXT.value)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = inspect_run(
            RunInspectorConfig(
                config_root=Path(args.config_root),
                controller_output_root=Path(args.controller_output_root) if args.controller_output_root else None,
                run_id=args.run_id,
                workflow=args.workflow,
                output_path=Path(args.output_path) if args.output_path else None,
                output_format=InspectorOutputFormat(args.format),
            )
        )
    except Exception as exc:  # noqa: BLE001
        print(f"RUN INSPECTOR FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if args.format == InspectorOutputFormat.JSON.value:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        print(format_run_inspection(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
