#!/usr/bin/env python3
"""Validate and report skill-library scale readiness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.skills.scale import build_skill_scale_report  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_skill_scale_report(
        Path(args.config_root),
        output_path=Path(args.output_path) if args.output_path else None,
    )
    print(f"SKILL SCALE REPORT {report['report_path']}")
    print("SKILL SCALE SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("SKILL SCALE FAILURES " + json.dumps(report.get("errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("SKILL SCALE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
