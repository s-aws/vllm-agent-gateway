#!/usr/bin/env python3
"""Validate the Phase 149 contextless audit scorecard."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.contextless_audit_scorecard import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    ContextlessAuditScorecardConfig,
    run_contextless_audit_scorecard,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--policy-path", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument(
        "--output-path",
        default="runtime-state/contextless-audit-scorecard/phase149/phase149-contextless-audit-scorecard-report.json",
    )
    parser.add_argument(
        "--markdown-output-path",
        default="runtime-state/contextless-audit-scorecard/phase149/phase149-contextless-audit-scorecard-report.md",
    )
    parser.add_argument("--require-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_contextless_audit_scorecard(
        ContextlessAuditScorecardConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path) if args.markdown_output_path else None,
            require_artifacts=args.require_artifacts,
        )
    )
    print("CONTEXTLESS AUDIT SCORECARD SUMMARY " + json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))
    if report["status"] != "passed":
        print("CONTEXTLESS AUDIT SCORECARD ERRORS " + json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))
        print(
            "CONTEXTLESS AUDIT SCORECARD BLOCKERS "
            + json.dumps(report["scorecard"]["hard_blockers"], ensure_ascii=True, sort_keys=True)
        )
        return 1
    print("CONTEXTLESS AUDIT SCORECARD PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
