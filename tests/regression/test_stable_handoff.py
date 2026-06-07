from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.stable_handoff import (
    CommandExecutionResult,
    StableHandoffConfig,
    build_stable_handoff_commands,
    validate_stable_handoff,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def passing_v1_1_report(tmp_path: Path) -> Path:
    return write_json(
        tmp_path / "v1-1-acceptance.json",
        {
            "schema_version": 1,
            "kind": "v1_acceptance_report",
            "status": "passed",
            "profile": "v1.1-release-candidate",
        },
    )


def stable_config(tmp_path: Path, report_path: Path | None) -> StableHandoffConfig:
    return StableHandoffConfig(
        config_root=REPO_ROOT,
        release_candidate_report_path=report_path,
        output_path=tmp_path / "stable-handoff.json",
        target_roots=("fixture-a", "fixture-b"),
        python_executable="python-test",
    )


def test_stable_handoff_command_plan_uses_existing_validation_gates(tmp_path: Path) -> None:
    config = stable_config(tmp_path, passing_v1_1_report(tmp_path))
    commands = build_stable_handoff_commands(
        config,
        output_path=tmp_path / "stable-handoff.json",
        release_candidate_report_path=tmp_path / "v1-1-acceptance.json",
    )

    by_id = {item["id"]: item["command"] for item in commands}
    assert list(by_id) == [
        "first_time_user_doctor",
        "stable_release_channel",
        "security_policy",
        "external_tester_onboarding_smoke",
    ]
    assert "run_first_time_user_doctor.py" in " ".join(by_id["first_time_user_doctor"])
    assert "validate_release_channels.py" in " ".join(by_id["stable_release_channel"])
    assert "--channel" in by_id["stable_release_channel"]
    assert "stable" in by_id["stable_release_channel"]
    assert "--release-candidate-report" in by_id["stable_release_channel"]
    assert "validate_security_policy.py" in " ".join(by_id["security_policy"])
    onboarding_command = by_id["external_tester_onboarding_smoke"]
    assert "validate_external_tester_onboarding.py" in " ".join(onboarding_command)
    assert "--live-anythingllm" in onboarding_command
    assert "--include-feedback" in onboarding_command
    assert "--case-id" in onboarding_command
    assert "ONB-001" in onboarding_command


def test_stable_handoff_fails_closed_without_release_candidate_report(tmp_path: Path) -> None:
    report = validate_stable_handoff(
        stable_config(tmp_path, tmp_path / "missing-v1-report.json"),
        command_runner=lambda _command, _timeout: CommandExecutionResult(0, "", ""),
        fixture_state_reader=lambda _roots: {},
    )

    assert report["status"] == "failed"
    assert report["summary"]["command_count"] == 0
    assert report["summary"]["failed_check_ids"] == ["release_candidate_report"]


def test_stable_handoff_passes_with_mocked_successful_commands_and_clean_fixtures(tmp_path: Path) -> None:
    commands_seen: list[list[str]] = []

    def runner(command: list[str], _timeout: int) -> CommandExecutionResult:
        commands_seen.append(command)
        return CommandExecutionResult(0, "PASS", "")

    fixture_state = {"fixture-a": {"hashes": {"file.py": "abc"}, "git_status": None}}
    report = validate_stable_handoff(
        stable_config(tmp_path, passing_v1_1_report(tmp_path)),
        command_runner=runner,
        fixture_state_reader=lambda _roots: fixture_state,
    )

    assert report["status"] == "passed"
    assert report["summary"]["command_count"] == 4
    assert report["summary"]["failed_check_ids"] == []
    assert len(commands_seen) == 4
    assert Path(report["report_path"]).exists()


def test_stable_handoff_fails_if_protected_fixture_state_changes(tmp_path: Path) -> None:
    states = [
        {"fixture-a": {"hashes": {"file.py": "before"}, "git_status": None}},
        {"fixture-a": {"hashes": {"file.py": "after"}, "git_status": None}},
    ]

    def state_reader(_roots: tuple[str, ...]) -> dict[str, dict[str, object]]:
        return states.pop(0)

    report = validate_stable_handoff(
        stable_config(tmp_path, passing_v1_1_report(tmp_path)),
        command_runner=lambda _command, _timeout: CommandExecutionResult(0, "PASS", ""),
        fixture_state_reader=state_reader,
    )

    assert report["status"] == "failed"
    assert "protected_fixture_state" in report["summary"]["failed_check_ids"]


def test_stable_handoff_reports_unreachable_fixture_state_without_crashing(tmp_path: Path) -> None:
    def state_reader(_roots: tuple[str, ...]) -> dict[str, dict[str, object]]:
        raise RuntimeError("fixture path is not reachable")

    report = validate_stable_handoff(
        stable_config(tmp_path, passing_v1_1_report(tmp_path)),
        command_runner=lambda _command, _timeout: CommandExecutionResult(0, "PASS", ""),
        fixture_state_reader=state_reader,
    )

    assert report["status"] == "failed"
    assert report["summary"]["command_count"] == 0
    assert report["summary"]["failed_check_ids"] == ["protected_fixture_state.preflight"]
    assert Path(report["report_path"]).exists()
