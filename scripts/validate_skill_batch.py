#!/usr/bin/env python3
"""Validate a proposed skill batch without mutating runtime registries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.skills.batches import build_skill_batch_report  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--batch-file", required=True)
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_skill_batch_report(
        Path(args.config_root),
        Path(args.batch_file),
        output_path=Path(args.output_path) if args.output_path else None,
    )
    print(f"SKILL BATCH REPORT {report['report_path']}")
    print(
        "SKILL BATCH SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "batch_id": report["batch_id"],
                "skill_count": report["summary"]["skill_count"],
                "eval_case_count": report["summary"]["eval_case_count"],
                "route_key_count": report["summary"]["route_key_count"],
                "error_count": len(report["errors"]),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("SKILL BATCH FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("SKILL BATCH PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
