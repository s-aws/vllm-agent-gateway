from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig1_protocol_auth_schema_matrix import (
    DEFAULT_MATRIX_PATH,
    EIG1ProtocolAuthSchemaConfig,
    run_eig1_protocol_auth_schema_validation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def matrix_pack() -> dict[str, object]:
    return json.loads((REPO_ROOT / DEFAULT_MATRIX_PATH).read_text(encoding="utf-8"))


def run_with_matrix(tmp_path: Path, matrix: dict[str, object]) -> dict[str, object]:
    matrix_path = write_json(tmp_path / "matrix.json", matrix)
    return run_eig1_protocol_auth_schema_validation(
        EIG1ProtocolAuthSchemaConfig(
            config_root=REPO_ROOT,
            matrix_path=matrix_path,
            output_path=tmp_path / "report.json",
        )
    )


def error_ids(report: dict[str, object]) -> set[str]:
    errors = report["validation_errors"]
    assert isinstance(errors, list)
    return {str(item["id"]) for item in errors if isinstance(item, dict)}


def report_by_case(report: dict[str, object], section: str, case_id: str) -> dict[str, object]:
    values = report[section]
    assert isinstance(values, list)
    for value in values:
        assert isinstance(value, dict)
        if value.get("case_id") == case_id:
            return value
    raise AssertionError(f"missing case {case_id}")


def test_eig1_protocol_auth_schema_matrix_passes(tmp_path: Path) -> None:
    report = run_eig1_protocol_auth_schema_validation(
        EIG1ProtocolAuthSchemaConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["protocol_case_count"] == 4
    assert report["summary"]["auth_case_count"] == 6
    assert report["summary"]["schema_case_count"] == 13
    assert report["summary"]["only_executable_protocol"] == "local_stub"
    assert report["summary"]["non_executable_protocols_fail_at_mediation"] is True
    assert report["summary"]["deferred_schema_case_count"] == 1
    assert report["summary"]["runtime_registry_changed"] is False
    assert report["summary"]["external_network_called"] is False
    assert report["summary"]["phase291_ready"] is True

    assert report_by_case(report, "protocol_reports", "EIG1-PROTO-HTTPS-VALIDATION")["mediation_status"] == "connector_protocol_not_executable"
    assert report_by_case(report, "auth_reports", "EIG1-AUTH-STUB-HTTPS")["validation_status"] == "unsafe_connector_auth"
    assert report_by_case(report, "schema_reports", "EIG1-SCHEMA-MALFORMED-INTEGER")["actual_status"] == "invalid_connector_argument"


def test_eig1_protocol_auth_schema_rejects_missing_protocol_case(tmp_path: Path) -> None:
    matrix = matrix_pack()
    mutated = copy.deepcopy(matrix)
    protocol_cases = mutated["protocol_cases"]
    assert isinstance(protocol_cases, list)
    mutated["protocol_cases"] = [
        item for item in protocol_cases if not (isinstance(item, dict) and item.get("protocol") == "mcp_mediated")
    ]

    report = run_with_matrix(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "matrix.protocol_cases" in error_ids(report)


def test_eig1_protocol_auth_schema_rejects_wrong_nonlocal_expectation(tmp_path: Path) -> None:
    matrix = matrix_pack()
    mutated = copy.deepcopy(matrix)
    protocol_cases = mutated["protocol_cases"]
    assert isinstance(protocol_cases, list)
    for item in protocol_cases:
        if isinstance(item, dict) and item.get("id") == "EIG1-PROTO-HTTPS-VALIDATION":
            item["expected_mediation_error"] = "allowed"

    report = run_with_matrix(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "protocol.mediation_error" in error_ids(report)


def test_eig1_protocol_auth_schema_rejects_missing_schema_shape(tmp_path: Path) -> None:
    matrix = matrix_pack()
    mutated = copy.deepcopy(matrix)
    schema_cases = mutated["schema_cases"]
    assert isinstance(schema_cases, list)
    mutated["schema_cases"] = [
        item for item in schema_cases if not (isinstance(item, dict) and item.get("field_shape") == "malformed_object")
    ]

    report = run_with_matrix(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "matrix.schema_cases" in error_ids(report)
