#!/usr/bin/env python3
"""Validate the Phase 196 V1 product readiness reassessment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.v1_product_readiness_reassessment import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    V1ProductReadinessReassessmentConfig,
    run_v1_product_readiness_reassessment,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    parser.add_argument("--no-require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_v1_product_readiness_reassessment(
        V1ProductReadinessReassessmentConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
            require_artifacts=not args.no_require_artifacts,
        )
    )
    print(f"PHASE196 V1 PRODUCT READINESS REASSESSMENT REPORT {report['report_path']}")
    print(
        "PHASE196 V1 PRODUCT READINESS REASSESSMENT SUMMARY "
        + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True)
    )
    if report["status"] != "passed":
        print(
            "PHASE196 V1 PRODUCT READINESS REASSESSMENT BLOCKERS "
            + json.dumps(report.get("release_blockers", []), ensure_ascii=True, sort_keys=True)
        )
        return 1
    print("PHASE196 V1 PRODUCT READINESS REASSESSMENT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
