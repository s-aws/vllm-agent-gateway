from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig3_memory_lifecycle import (
    DEFAULT_MEMORY_FIXTURE_PATH,
    EIG3MemoryLifecycleConfig,
    run_eig3_memory_lifecycle_validation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def memory_pack() -> dict[str, object]:
    return json.loads((REPO_ROOT / DEFAULT_MEMORY_FIXTURE_PATH).read_text(encoding="utf-8"))


def record_by_id(pack: dict[str, object], record_id: str) -> dict[str, object]:
    records = pack["records"]
    assert isinstance(records, list)
    for record in records:
        assert isinstance(record, dict)
        if record["id"] == record_id:
            return record
    raise AssertionError(f"missing record {record_id}")


def run_with_pack(tmp_path: Path, pack: dict[str, object]) -> dict[str, object]:
    fixture_path = write_json(tmp_path / "memory.json", pack)
    return run_eig3_memory_lifecycle_validation(
        EIG3MemoryLifecycleConfig(
            config_root=REPO_ROOT,
            memory_fixture_path=fixture_path,
            output_path=tmp_path / "report.json",
        )
    )


def error_ids(report: dict[str, object]) -> set[str]:
    errors = report["validation_errors"]
    assert isinstance(errors, list)
    return {str(item["id"]) for item in errors if isinstance(item, dict)}


def test_eig3_memory_lifecycle_passes(tmp_path: Path) -> None:
    report = run_eig3_memory_lifecycle_validation(
        EIG3MemoryLifecycleConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["record_count"] == 8
    assert report["summary"]["allowed_record_count"] == 1
    assert report["summary"]["denied_record_count"] == 7
    assert report["summary"]["phase301_ready"] is True
    assert report["summary"]["raw_memory_content_retained_in_report"] is False
    serialized = json.dumps(report, sort_keys=True)
    assert "sk-synth-MEMORY1234567890" not in serialized
    assert "Raw synthetic value" not in serialized


def test_eig3_memory_lifecycle_rejects_hidden_memory_marked_allowed(tmp_path: Path) -> None:
    pack = copy.deepcopy(memory_pack())
    record = record_by_id(pack, "EIG3-MEM-N4")
    record["expected_decision"] = "allow"
    record["expected_influence_allowed"] = True

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "failed"
    assert "record.expected_decision" in error_ids(report)


def test_eig3_memory_lifecycle_rejects_stale_memory_marked_allowed(tmp_path: Path) -> None:
    pack = copy.deepcopy(memory_pack())
    record = record_by_id(pack, "EIG3-MEM-N3")
    record["expected_decision"] = "allow"
    record["expected_influence_allowed"] = True

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "failed"
    assert "record.expected_decision" in error_ids(report)


def test_eig3_memory_lifecycle_rejects_raw_sensitive_memory_marked_allowed(tmp_path: Path) -> None:
    pack = copy.deepcopy(memory_pack())
    record = record_by_id(pack, "EIG3-MEM-N7")
    record["expected_decision"] = "allow"
    record["expected_reason"] = "active_inspectable_scoped_memory"
    record["expected_influence_allowed"] = True

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "failed"
    assert "record.expected_decision" in error_ids(report)
    assert "record.expected_reason" in error_ids(report)


def test_eig3_memory_lifecycle_rejects_unknown_source_fixture(tmp_path: Path) -> None:
    pack = copy.deepcopy(memory_pack())
    record_by_id(pack, "EIG3-MEM-R1")["source_fixture_id"] = "missing-fixture"

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "failed"
    assert "record.source_fixture_id" in error_ids(report)
