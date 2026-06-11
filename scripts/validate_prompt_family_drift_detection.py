#!/usr/bin/env python3
"""Build and validate the Phase 191 prompt-family drift detection report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.prompt_family_drift_detection import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    PromptFamilyDriftDetectionConfig,
    run_prompt_family_drift_detection,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_OUTPUT_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_prompt_family_drift_detection(
        PromptFamilyDriftDetectionConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
        )
    )
    print(f"PHASE191 PROMPT FAMILY DRIFT DETECTION REPORT {report['report_path']}")
    print("PHASE191 PROMPT FAMILY DRIFT DETECTION SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("PHASE191 PROMPT FAMILY DRIFT DETECTION ERRORS " + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("PHASE191 PROMPT FAMILY DRIFT DETECTION PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
