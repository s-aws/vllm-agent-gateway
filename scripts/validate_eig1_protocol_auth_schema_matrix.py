#!/usr/bin/env python3
"""Validate EIG-1 protocol, auth, and schema matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.eig1_protocol_auth_schema_matrix import (  # noqa: E402
    DEFAULT_MATRIX_PATH,
    EIG1ProtocolAuthSchemaConfig,
    run_eig1_protocol_auth_schema_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=str(REPO_ROOT))
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX_PATH))
    parser.add_argument("--output-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_eig1_protocol_auth_schema_validation(
        EIG1ProtocolAuthSchemaConfig(
            config_root=Path(args.config_root),
            matrix_path=Path(args.matrix),
            output_path=Path(args.output_path) if args.output_path else None,
        )
    )
    print(f"EIG1 PROTOCOL AUTH SCHEMA REPORT {report['report_path']}")
    print(
        "EIG1 PROTOCOL AUTH SCHEMA SUMMARY "
        + json.dumps(
            {
                "status": report["status"],
                "protocol_case_count": report.get("summary", {}).get("protocol_case_count"),
                "auth_case_count": report.get("summary", {}).get("auth_case_count"),
                "schema_case_count": report.get("summary", {}).get("schema_case_count"),
                "validation_error_count": report.get("summary", {}).get("validation_error_count"),
                "phase291_ready": report.get("summary", {}).get("phase291_ready"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] != "passed":
        print("EIG1 PROTOCOL AUTH SCHEMA FAILURES " + json.dumps(report.get("validation_errors", []), ensure_ascii=True, sort_keys=True))
        return 1
    print("EIG1 PROTOCOL AUTH SCHEMA PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
