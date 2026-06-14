#!/usr/bin/env python3
"""Validate Phase 206 evidence relevance audit pack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.evidence_relevance_audit_pack import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_POLICY_PATH,
    EvidenceRelevanceAuditPackConfig,
    validate_evidence_relevance_audit_pack,
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
    report = validate_evidence_relevance_audit_pack(
        EvidenceRelevanceAuditPackConfig(
            config_root=Path(args.config_root),
            policy_path=Path(args.policy_path),
            output_path=Path(args.output_path),
            markdown_output_path=Path(args.markdown_output_path),
        )
    )
    print("PHASE206 EVIDENCE RELEVANCE AUDIT PACK SUMMARY " + json.dumps(report.get("summary", {}), sort_keys=True))
    if report.get("status") != "passed":
        print("PHASE206 EVIDENCE RELEVANCE AUDIT PACK FAILURES " + json.dumps(report.get("errors", []), sort_keys=True))
        return 1
    print("PHASE206 EVIDENCE RELEVANCE AUDIT PACK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
