from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from vllm_agent_gateway.implementation.workflow import (
    ImplementationWorkflowInvocationRequest,
    invoke_implementation_workflow,
)
from vllm_agent_gateway.invocation import WorkflowStatus


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "run_implementation_workflow.py"


def run_command(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if check and result.returncode != 0:
        pytest.fail(
            "Command failed with exit code "
            f"{result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def run_implementation(*args: object, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT), *[str(arg) for arg in args]]
    return run_command(command, REPO_ROOT, check=check)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def load_one_json(directory: Path, pattern: str) -> dict[str, Any]:
    paths = sorted(directory.glob(pattern))
    assert len(paths) == 1, f"Expected one {pattern} artifact, found {paths}"
    return json.loads(paths[0].read_text(encoding="utf-8"))


def artifact_path(directory: Path, pattern: str) -> Path:
    paths = sorted(directory.glob(pattern))
    assert len(paths) == 1, f"Expected one {pattern} artifact, found {paths}"
    return paths[0]


def make_target_repo(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    write_text(target / "README.md", "# Project\n\nInstall with Docker.\n")
    write_text(target / "docs" / "guide.md", "# Guide\n\nOriginal guide text.\n")
    write_text(
        target / "tests" / "test_docs.py",
        "from pathlib import Path\n\n\ndef test_readme_exists():\n    assert Path('README.md').exists()\n",
    )
    write_text(target / "UNTRACKED.md", "# Untracked\n")
    run_command(["git", "init"], target)
    run_command(["git", "add", "README.md", "docs/guide.md", "tests/test_docs.py"], target)
    return target


def write_documenter_report(path: Path, target: Path) -> None:
    write_json(
        path,
        {
            "schema_version": 1,
            "kind": "documenter_orchestrator_report",
            "generated_at": "2026-05-25T00:00:00Z",
            "target_root": str(target),
            "mode": "full",
            "dry_run": False,
            "document_scope": "tracked",
            "doc_id": "README.md",
            "seed_doc_id": "README.md",
            "chunks_processed": 1,
            "chunks_total": 1,
            "truncated_after_chunks": False,
            "artifacts": {},
            "chunks": [
                {
                    "doc_id": "README.md",
                    "chunk_id": "README.md:0001",
                    "lines": [1, 3],
                    "result": {
                        "chunk_id": "README.md:0001",
                        "facts_found": ["Install with Docker is documented."],
                        "criteria_satisfied": ["installation steps documented"],
                        "criteria_remaining": [],
                        "doc_gaps": [],
                        "followup_files": [],
                        "confidence": "medium",
                    },
                }
            ],
        },
    )


def write_packet_file(path: Path, packets: list[dict[str, Any]], verification_commands: list[dict[str, Any]] | None = None) -> None:
    write_json(path, {"schema_version": 1, "packets": packets, "verification_commands": verification_commands or []})


def test_implementation_invocation_contract_runs_without_shelling_out(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "contract"
    packet_file = tmp_path / "packets.json"
    write_packet_file(
        packet_file,
        [
            {
                "id": "IMP-0001",
                "target_files": ["README.md"],
                "operation": {"kind": "append_text", "path": "README.md", "content": "\nDraft note.\n"},
                "acceptance_criteria": ["README draft exists."],
                "max_context_tokens": 2000,
            }
        ],
    )

    result = invoke_implementation_workflow(
        ImplementationWorkflowInvocationRequest(
            target_root=target,
            output_dir=output_dir,
            packet_file=packet_file,
            no_structure_index=True,
        )
    )

    assert result.status == WorkflowStatus.COMPLETED
    assert result.workflow == "implementation.workflow"
    assert "implementation_plan" in result.artifact_paths
    assert "implementation_state" in result.artifact_paths
    assert "implementation_report" in result.artifact_paths
    assert result.resume_key is not None
    assert result.report is not None
    assert result.report["kind"] == "implementation_report"


def test_implementation_from_report_writes_draft_without_mutating_target(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    report_path = tmp_path / "documenter-report.json"
    output_dir = tmp_path / "out"
    original_readme = (target / "README.md").read_text(encoding="utf-8")
    write_documenter_report(report_path, target)

    run_implementation(
        "--target-root",
        target,
        "--from-report",
        report_path,
        "--approve-all-safe",
        "--output-dir",
        output_dir,
    )

    plan = load_one_json(output_dir, "implementation-plan-*.json")
    state = load_one_json(output_dir, "implementation-state-*.json")
    report = load_one_json(output_dir, "implementation-report-*.json")
    draft_path = Path(state["changed_artifacts"][0]["draft_path"])

    assert plan["kind"] == "implementation_plan"
    assert plan["source"]["type"] == "documenter_report"
    assert plan["packets"][0]["id"] == "IMP-CP-0001"
    assert plan["packets"][0]["structure_index_slice"]["packet_field"] == "structure_index_slice"
    assert plan["write_policy"]["target_repo_read_only"] is True
    assert draft_path.exists()
    draft_path.resolve().relative_to(output_dir.resolve())
    assert "Implementation Draft Note" in draft_path.read_text(encoding="utf-8")
    assert (target / "README.md").read_text(encoding="utf-8") == original_readme
    assert state["status"] == "completed"
    assert report["implementation_results"][0]["verification_decision"] == "not_run_no_verification_commands"


def test_implementation_resume_skips_completed_packets_and_captures_verification(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "resume"
    packet_file = tmp_path / "packets.json"
    write_packet_file(
        packet_file,
        [
            {
                "id": "IMP-0001",
                "target_files": ["README.md"],
                "operation": {"kind": "append_text", "path": "README.md", "content": "\nDraft note one.\n"},
                "acceptance_criteria": ["README draft exists."],
                "max_context_tokens": 2000,
            },
            {
                "id": "IMP-0002",
                "target_files": ["docs/guide.md"],
                "operation": {
                    "kind": "replace_text",
                    "path": "docs/guide.md",
                    "old": "Original guide text.",
                    "new": "Updated guide text.",
                },
                "acceptance_criteria": ["Guide draft contains updated text."],
                "max_context_tokens": 2000,
            },
        ],
    )

    run_implementation(
        "--target-root",
        target,
        "--packet-file",
        packet_file,
        "--verification-pytest",
        "tests",
        "--output-dir",
        output_dir,
        "--stop-after-packets",
        "1",
    )
    state_path = artifact_path(output_dir, "implementation-state-*.json")
    paused_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert paused_state["status"] == "paused"
    assert [item["packet_id"] for item in paused_state["completed_packets"]] == ["IMP-0001"]

    run_implementation(
        "--target-root",
        target,
        "--mode",
        "draft",
        "--output-dir",
        output_dir,
        "--resume",
        state_path,
    )

    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    report = load_one_json(output_dir, "implementation-report-*.json")
    assert final_state["status"] == "completed"
    assert [item["packet_id"] for item in final_state["completed_packets"]] == ["IMP-0001", "IMP-0002"]
    assert final_state["verification_results"][0]["status"] == "passed"
    assert final_state["verification_results"][0]["stdout"]["sha256"]
    assert all(item["verification_decision"] == "passed" for item in report["implementation_results"])
    assert (target / "docs" / "guide.md").read_text(encoding="utf-8") == "# Guide\n\nOriginal guide text.\n"


def test_implementation_failed_verification_is_preserved_in_state_and_report(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    write_text(target / "tests" / "test_failure.py", "def test_failure():\n    assert False\n")
    run_command(["git", "add", "tests/test_failure.py"], target)
    output_dir = tmp_path / "failure"
    packet_file = tmp_path / "packet.json"
    write_packet_file(
        packet_file,
        [
            {
                "id": "IMP-FAIL",
                "target_files": ["README.md"],
                "operation": {"kind": "append_text", "path": "README.md", "content": "\nDraft note.\n"},
                "acceptance_criteria": ["Draft exists."],
            }
        ],
    )

    result = run_implementation(
        "--target-root",
        target,
        "--packet-file",
        packet_file,
        "--verification-pytest",
        "tests",
        "--output-dir",
        output_dir,
        check=False,
    )

    assert result.returncode == 1
    state = load_one_json(output_dir, "implementation-state-*.json")
    report = load_one_json(output_dir, "implementation-report-*.json")
    assert state["status"] == "failed"
    assert state["failure"]["stage"] == "verification"
    assert state["verification_results"][0]["status"] == "failed"
    assert report["status"] == "failed"
    assert report["implementation_results"][0]["verification_decision"] == "failed"


def test_apply_mode_refuses_untracked_and_out_of_scope_writes(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "apply-refusal"
    untracked_packet = tmp_path / "untracked.json"
    write_packet_file(
        untracked_packet,
        [
            {
                "id": "IMP-UNTRACKED",
                "target_files": ["UNTRACKED.md"],
                "operation": {"kind": "append_text", "path": "UNTRACKED.md", "content": "\nApplied.\n"},
                "acceptance_criteria": ["Should be refused."],
            }
        ],
    )

    result = run_implementation(
        "--target-root",
        target,
        "--mode",
        "apply",
        "--packet-file",
        untracked_packet,
        "--output-dir",
        output_dir,
        check=False,
    )

    assert result.returncode == 1
    state = load_one_json(output_dir, "implementation-state-*.json")
    assert state["status"] == "failed"
    assert "Refusing apply to untracked file" in state["failure"]["error"]
    assert (target / "UNTRACKED.md").read_text(encoding="utf-8") == "# Untracked\n"

    outside_packet = tmp_path / "outside.json"
    write_packet_file(
        outside_packet,
        [
            {
                "id": "IMP-OUTSIDE",
                "target_files": ["../outside.md"],
                "operation": {"kind": "append_text", "path": "../outside.md", "content": "nope"},
                "acceptance_criteria": ["Should be refused."],
            }
        ],
    )
    outside = run_implementation(
        "--target-root",
        target,
        "--packet-file",
        outside_packet,
        "--output-dir",
        tmp_path / "outside-out",
        check=False,
    )
    assert outside.returncode == 2
    assert "outside target root" in outside.stderr


def test_explicit_apply_records_hashes_and_modifies_only_target_file(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "apply"
    packet_file = tmp_path / "apply.json"
    write_packet_file(
        packet_file,
        [
            {
                "id": "IMP-APPLY",
                "target_files": ["README.md"],
                "operation": {
                    "kind": "replace_text",
                    "path": "README.md",
                    "old": "Install with Docker.",
                    "new": "Install with Docker or Podman.",
                },
                "acceptance_criteria": ["README install sentence is updated."],
            }
        ],
    )

    run_implementation(
        "--target-root",
        target,
        "--mode",
        "apply",
        "--packet-file",
        packet_file,
        "--verification-pytest",
        "tests",
        "--output-dir",
        output_dir,
    )

    state = load_one_json(output_dir, "implementation-state-*.json")
    changed = state["changed_artifacts"][0]
    assert state["status"] == "completed"
    assert changed["target_modified"] is True
    assert changed["before_sha256"] != changed["after_sha256"]
    assert "Install with Docker or Podman." in (target / "README.md").read_text(encoding="utf-8")
    assert (target / "docs" / "guide.md").read_text(encoding="utf-8") == "# Guide\n\nOriginal guide text.\n"


def test_verification_command_json_is_policy_limited(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    packet_file = tmp_path / "unsafe-command.json"
    write_packet_file(
        packet_file,
        [
            {
                "id": "IMP-UNSAFE-COMMAND",
                "target_files": ["README.md"],
                "operation": {"kind": "append_text", "path": "README.md", "content": "\nDraft.\n"},
                "acceptance_criteria": ["Draft exists."],
            }
        ],
    )

    result = run_implementation(
        "--target-root",
        target,
        "--packet-file",
        packet_file,
        "--verification-command-json",
        '{"id":"unsafe","command":["python","-c","print(1)"]}',
        "--output-dir",
        tmp_path / "unsafe-out",
        check=False,
    )

    assert result.returncode == 2
    assert "outside controller policy" in result.stderr
