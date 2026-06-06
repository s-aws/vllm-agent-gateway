#!/usr/bin/env python3
"""Validate metadata-only skill selector scale and stability."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.skills.selector_scale import (  # noqa: E402
    DEFAULT_10000_THRESHOLD_SECONDS,
    DEFAULT_MAX_SELECTED,
    DEFAULT_REPETITIONS,
    DEFAULT_SKILL_COUNTS,
    build_skill_selector_scale_report,
)


def parse_skill_counts(value: str) -> tuple[int, ...]:
    counts = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not counts:
        raise argparse.ArgumentTypeError("at least one skill count is required")
    if any(count < 4 for count in counts):
        raise argparse.ArgumentTypeError("skill counts must be at least 4")
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--output-path", default=None)
    parser.add_argument(
        "--skill-counts",
        type=parse_skill_counts,
        default=DEFAULT_SKILL_COUNTS,
        help="Comma-separated synthetic catalog sizes. Defaults to 100,1000,10000.",
    )
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--max-selected", type=int, default=DEFAULT_MAX_SELECTED)
    parser.add_argument("--threshold-10000-seconds", type=float, default=DEFAULT_10000_THRESHOLD_SECONDS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_skill_selector_scale_report(
        Path(args.config_root),
        output_path=Path(args.output_path) if args.output_path else None,
        skill_counts=args.skill_counts,
        repetitions=args.repetitions,
        max_selected=args.max_selected,
        threshold_10000_seconds=args.threshold_10000_seconds,
    )
    print(f"SKILL SELECTOR SCALE REPORT {report['report_path']}")
    print("SKILL SELECTOR SCALE SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("SKILL SELECTOR SCALE FAILURES " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        return 1
    print("SKILL SELECTOR SCALE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
