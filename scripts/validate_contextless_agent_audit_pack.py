#!/usr/bin/env python3
"""Validate the Phase 185 contextless-agent audit pack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.contextless_agent_audit_pack import (  # noqa: E402
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    DEFAULT_SAMPLE_REPORTS_PATH,
    ContextlessAgentAuditPackConfig,
    run_contextless_agent_audit_pack,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--sample-reports-path", default=str(DEFAULT_SAMPLE_REPORTS_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_contextless_agent_audit_pack(
        ContextlessAgentAuditPackConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            sample_reports_path=Path(args.sample_reports_path),
            output_path=Path(args.output_path),
        )
    )
    print(f"CONTEXTLESS AGENT AUDIT PACK REPORT {report['report_path']}")
    print("CONTEXTLESS AGENT AUDIT PACK SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print(
            "CONTEXTLESS AGENT AUDIT PACK ERRORS "
            + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True)
        )
        return 1
    print("CONTEXTLESS AGENT AUDIT PACK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
