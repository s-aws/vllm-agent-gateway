#!/usr/bin/env python3
"""Validate a task decomposition artifact against the Phase 113 quality contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.task_decomposition_quality import (  # noqa: E402
    evaluate_task_decomposition_plan,
    load_plan,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path, help="Path to task-decomposition.json.")
    parser.add_argument("--output-path", type=Path, help="Optional report output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = evaluate_task_decomposition_plan(load_plan(args.artifact))
    if args.output_path:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("TASK DECOMPOSITION QUALITY " + json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
