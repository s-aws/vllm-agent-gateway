from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.connector_user_scope_audit import (  # noqa: E402
    ConnectorUserScopeAuditError,
    read_json_object,
    validate_connector_invocation_audit_report,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a connector invocation user-scope audit artifact.")
    parser.add_argument("--report-path", required=True, help="Path to connector-invocation.json")
    parser.add_argument("--output-path", help="Optional path for the validation report")
    args = parser.parse_args()

    report = read_json_object(Path(args.report_path))
    validation = validate_connector_invocation_audit_report(report)
    if args.output_path:
        write_json(Path(args.output_path), validation)
    if validation["status"] != "passed":
        print(f"CONNECTOR USER SCOPE AUDIT FAIL {json.dumps(validation['summary'], sort_keys=True)}")
        raise ConnectorUserScopeAuditError(f"connector user scope audit failed with {len(validation['errors'])} error(s)")
    print(f"CONNECTOR USER SCOPE AUDIT PASS {json.dumps(validation['summary'], sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
