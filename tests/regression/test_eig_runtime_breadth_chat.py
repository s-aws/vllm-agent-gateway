from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig_runtime_breadth_chat import (
    EIGRuntimeBreadthChatConfig,
    run_eig_runtime_breadth_chat_validation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def test_eig_runtime_breadth_chat_validation_passes_direct_controller_mode(tmp_path: Path) -> None:
    report = run_eig_runtime_breadth_chat_validation(
        EIGRuntimeBreadthChatConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
            controller_output_root=tmp_path / "controller-artifacts",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["case_count"] == 3
    assert report["summary"]["passed_case_count"] == 3
    assert report["summary"]["source_connector_registry_changed"] is False
    assert report["summary"]["phase296_ready"] is True
    assert {item["workflow"] for item in report["case_results"]} == {"connector.invoke"}
    assert all("connector_invocation" in item["artifact_keys"] for item in report["case_results"])
    assert (tmp_path / "report.json").is_file()


def test_eig_runtime_breadth_chat_validation_fails_when_expected_result_fragment_is_missing(tmp_path: Path) -> None:
    source_pack = json.loads((REPO_ROOT / "runtime" / "eig_runtime_breadth_chat_cases.json").read_text(encoding="utf-8"))
    source_pack["cases"][0]["expected_result_fragments"].append("not-present-in-chat")
    cases_path = tmp_path / "cases.json"
    write_json(cases_path, source_pack)

    report = run_eig_runtime_breadth_chat_validation(
        EIGRuntimeBreadthChatConfig(
            config_root=REPO_ROOT,
            cases_path=cases_path,
            output_path=tmp_path / "report.json",
            controller_output_root=tmp_path / "controller-artifacts",
        )
    )

    assert report["status"] == "failed"
    assert report["summary"]["failed_case_count"] == 1
    first_errors = report["case_results"][0]["errors"]
    assert {"code": "missing_chat_fragment", "message": "not-present-in-chat"} in first_errors
