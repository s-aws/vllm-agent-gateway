from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from vllm_agent_gateway.acceptance.runtime_state_hygiene import (
    CommandExecutionResult,
    RuntimeStateHygieneConfig,
    validate_runtime_state_hygiene,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_minimal_runtime_state_contract(
    root: Path,
    *,
    proof: dict[str, object] | None = None,
    manifest_profile: str | None = None,
    manifest_boundary: str | None = None,
) -> None:
    (root / "docs" / "examples").mkdir(parents=True, exist_ok=True)
    (root / "README.runtime-state.md").write_text("Runtime state policy\n", encoding="utf-8")
    (root / "docs" / "examples" / "runtime-state.md").write_text("Runtime state examples\n", encoding="utf-8")
    (root / "docs" / "README.md").write_text(
        (
            "[Runtime State](../README.runtime-state.md)\n"
            "[Examples Index](examples/README.md)\n"
            "[Runtime State Examples](examples/runtime-state.md)\n"
        ),
        encoding="utf-8",
    )
    (root / "docs" / "examples" / "README.md").write_text(
        "[Runtime State](runtime-state.md)\n",
        encoding="utf-8",
    )
    stable_boundary = "Stable boundary keeps advanced broad refactor orchestration deferred."
    proof_value = proof or {
        "schema_version": 1,
        "kind": "v1_acceptance_report",
        "status": "passed",
        "profile": "v1.1-release-candidate",
        "proof_kind": "stable_channel_activation_proof",
        "source_report": "runtime-state/v1-acceptance/source.json",
        "retention_reason": "runtime-state is local-only.",
        "known_boundary": stable_boundary,
    }
    write_json(
        root / "runtime" / "release_proofs" / "v1-1-release-candidate-stable-proof.json",
        proof_value,
    )
    write_json(
        root / "runtime" / "release_channels.json",
        {
            "schema_version": 1,
            "kind": "release_channel_manifest",
            "channels": [
                {
                    "id": "stable",
                    "status": "active",
                    "stable_readiness": {
                        "activated_from_report": "runtime/release_proofs/v1-1-release-candidate-stable-proof.json",
                        "activated_profile": manifest_profile or str(proof_value.get("profile")),
                        "known_boundary": manifest_boundary or str(proof_value.get("known_boundary")),
                    },
                }
            ],
        },
    )


def successful_git_runner(command: list[str], _timeout: int) -> CommandExecutionResult:
    if command[-2:] == ["ls-files", "runtime-state"]:
        return CommandExecutionResult(0, "", "")
    if command[-3:-1] == ["check-ignore", "-v"]:
        return CommandExecutionResult(0, ".gitignore:14:runtime-state/ runtime-state/hygiene-sample.json\n", "")
    return CommandExecutionResult(1, "", f"unexpected command: {command}")


def test_current_runtime_state_hygiene_contract_passes(tmp_path: Path) -> None:
    report = validate_runtime_state_hygiene(
        RuntimeStateHygieneConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "runtime-state-hygiene.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["failed_check_ids"] == []
    by_id = {item["id"]: item for item in report["checks"]}
    assert by_id["runtime_state.tracked_files"]["status"] == "passed"
    assert by_id["runtime_state.gitignore"]["status"] == "passed"
    assert by_id["proof.stable_activation"]["status"] == "passed"
    assert by_id["docs.runtime_state_policy"]["status"] == "passed"
    assert Path(report["report_path"]).exists()


def test_runtime_state_hygiene_rejects_tracked_runtime_state_files(tmp_path: Path) -> None:
    write_minimal_runtime_state_contract(tmp_path)

    def runner(command: list[str], _timeout: int) -> CommandExecutionResult:
        if command[-2:] == ["ls-files", "runtime-state"]:
            return CommandExecutionResult(0, "runtime-state/old-report.json\n", "")
        if command[-3:-1] == ["check-ignore", "-v"]:
            return CommandExecutionResult(0, ".gitignore:14:runtime-state/ runtime-state/hygiene-sample.json\n", "")
        return CommandExecutionResult(1, "", f"unexpected command: {command}")

    report = validate_runtime_state_hygiene(
        RuntimeStateHygieneConfig(config_root=tmp_path, output_path=tmp_path / "report.json"),
        command_runner=runner,
    )

    assert report["status"] == "failed"
    by_id = {item["id"]: item for item in report["checks"]}
    assert by_id["runtime_state.tracked_files"]["status"] == "failed"
    assert by_id["runtime_state.tracked_files"]["details"]["tracked_files"] == ["runtime-state/old-report.json"]


def test_runtime_state_hygiene_rejects_unignored_runtime_state(tmp_path: Path) -> None:
    write_minimal_runtime_state_contract(tmp_path)

    def runner(command: list[str], _timeout: int) -> CommandExecutionResult:
        if command[-2:] == ["ls-files", "runtime-state"]:
            return CommandExecutionResult(0, "", "")
        if command[-3:-1] == ["check-ignore", "-v"]:
            return CommandExecutionResult(1, "", "")
        return CommandExecutionResult(1, "", f"unexpected command: {command}")

    report = validate_runtime_state_hygiene(
        RuntimeStateHygieneConfig(config_root=tmp_path, output_path=tmp_path / "report.json"),
        command_runner=runner,
    )

    assert report["status"] == "failed"
    by_id = {item["id"]: item for item in report["checks"]}
    assert by_id["runtime_state.gitignore"]["status"] == "failed"


def test_runtime_state_hygiene_rejects_too_narrow_ignore_coverage(tmp_path: Path) -> None:
    write_minimal_runtime_state_contract(tmp_path)

    def runner(command: list[str], _timeout: int) -> CommandExecutionResult:
        if command[-2:] == ["ls-files", "runtime-state"]:
            return CommandExecutionResult(0, "", "")
        if command[-3:-1] == ["check-ignore", "-v"]:
            sample_path = command[-1]
            if sample_path == "runtime-state/hygiene-sample.json":
                return CommandExecutionResult(0, ".gitignore:14:runtime-state/hygiene-sample.json\n", "")
            return CommandExecutionResult(1, "", "")
        return CommandExecutionResult(1, "", f"unexpected command: {command}")

    report = validate_runtime_state_hygiene(
        RuntimeStateHygieneConfig(config_root=tmp_path, output_path=tmp_path / "report.json"),
        command_runner=runner,
    )

    assert report["status"] == "failed"
    gitignore_check = next(item for item in report["checks"] if item["id"] == "runtime_state.gitignore")
    assert gitignore_check["status"] == "failed"
    assert "runtime-state/runtime-state-hygiene/current.json" in gitignore_check["details"]["unignored"]


def test_runtime_state_hygiene_rejects_invalid_committed_stable_proof(tmp_path: Path) -> None:
    write_minimal_runtime_state_contract(
        tmp_path,
        proof={
            "schema_version": 1,
            "kind": "v1_acceptance_report",
            "status": "failed",
            "profile": "v1.1-release-candidate",
            "proof_kind": "stable_channel_activation_proof",
            "source_report": "runtime-state/v1-acceptance/source.json",
            "retention_reason": "runtime-state is local-only.",
            "known_boundary": "Stable boundary keeps advanced broad refactor orchestration deferred.",
        },
    )

    report = validate_runtime_state_hygiene(
        RuntimeStateHygieneConfig(config_root=tmp_path, output_path=tmp_path / "report.json"),
        command_runner=successful_git_runner,
    )

    assert report["status"] == "failed"
    proof_check = next(item for item in report["checks"] if item["id"] == "proof.stable_activation")
    assert proof_check["status"] == "failed"
    assert "stable proof status must be passed" in proof_check["details"]["errors"]


def test_runtime_state_hygiene_rejects_missing_stable_proof_retention_metadata(tmp_path: Path) -> None:
    write_minimal_runtime_state_contract(
        tmp_path,
        proof={
            "schema_version": 1,
            "kind": "v1_acceptance_report",
            "status": "passed",
            "profile": "v1.1-release-candidate",
            "proof_kind": "stable_channel_activation_proof",
        },
        manifest_boundary="",
    )

    report = validate_runtime_state_hygiene(
        RuntimeStateHygieneConfig(config_root=tmp_path, output_path=tmp_path / "report.json"),
        command_runner=successful_git_runner,
    )

    assert report["status"] == "failed"
    proof_check = next(item for item in report["checks"] if item["id"] == "proof.stable_activation")
    assert proof_check["status"] == "failed"
    assert "stable proof source_report must be a non-empty string" in proof_check["details"]["errors"]
    assert "stable proof retention_reason must be a non-empty string" in proof_check["details"]["errors"]
    assert "stable proof known_boundary must be a non-empty string" in proof_check["details"]["errors"]


def test_runtime_state_hygiene_rejects_stable_manifest_profile_mismatch(tmp_path: Path) -> None:
    write_minimal_runtime_state_contract(tmp_path, manifest_profile="release-candidate")

    report = validate_runtime_state_hygiene(
        RuntimeStateHygieneConfig(config_root=tmp_path, output_path=tmp_path / "report.json"),
        command_runner=successful_git_runner,
    )

    assert report["status"] == "failed"
    proof_check = next(item for item in report["checks"] if item["id"] == "proof.stable_activation")
    assert proof_check["status"] == "failed"
    assert "stable channel activated_profile must match the committed stable proof profile" in proof_check["details"]["errors"]


def test_runtime_state_hygiene_rejects_broken_docs_index(tmp_path: Path) -> None:
    write_minimal_runtime_state_contract(tmp_path)
    (tmp_path / "docs" / "README.md").write_text(
        "[Runtime State](../README.runtime-state.md)\n[Runtime State Examples](examples/runtime-state.md)\n",
        encoding="utf-8",
    )

    report = validate_runtime_state_hygiene(
        RuntimeStateHygieneConfig(config_root=tmp_path, output_path=tmp_path / "report.json"),
        command_runner=successful_git_runner,
    )

    assert report["status"] == "failed"
    docs_check = next(item for item in report["checks"] if item["id"] == "docs.runtime_state_policy")
    assert docs_check["status"] == "failed"
    assert "docs index validation did not pass" in docs_check["details"]["docs_index_errors"]


def test_runtime_state_hygiene_cli_writes_report(tmp_path: Path) -> None:
    output_path = tmp_path / "runtime-state-hygiene-cli.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_runtime_state_hygiene.py",
            "--output-path",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert "RUNTIME STATE HYGIENE PASS" in result.stdout
