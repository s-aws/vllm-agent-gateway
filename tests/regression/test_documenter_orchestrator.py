from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "run_documenter_orchestrator.py"


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


def run_orchestrator(*args: object, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(SCRIPT),
        "--config-root",
        str(REPO_ROOT),
        *[str(arg) for arg in args],
    ]
    return run_command(command, REPO_ROOT, check=check)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_target_repo(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    write_text(
        target / "README.md",
        "\n".join(
            [
                "# Sample Project",
                "",
                "Install with Docker.",
                "Configuration lives in docs/config.md.",
                "Runtime roles live in runtime/roles.json.",
                "The startup script is start-agent-prompt-proxies.sh.",
                "",
            ]
        ),
    )
    write_text(target / "docs" / "config.md", "# Configuration\n\nSet ports in runtime/roles.json.\n")
    write_text(target / "docs" / "guide.md", "# Guide\n\nUse the startup script.\n")
    write_text(target / "runtime" / "roles.json", '{"roles":[]}\n')
    write_text(target / "start-agent-prompt-proxies.sh", "#!/usr/bin/env bash\n")
    write_text(target / "assets" / "tool.exe", "not a real executable\n")
    write_text(target / "UNTRACKED.md", "# Untracked\n\nBootstrap-only documentation.\n")

    run_command(["git", "init"], target)
    run_command(
        [
            "git",
            "add",
            "README.md",
            "docs/config.md",
            "docs/guide.md",
            "runtime/roles.json",
            "start-agent-prompt-proxies.sh",
            "assets/tool.exe",
        ],
        target,
    )
    return target


def load_one_json(directory: Path, pattern: str) -> dict[str, Any]:
    paths = sorted(directory.glob(pattern))
    assert len(paths) == 1, f"Expected one {pattern} artifact, found {paths}"
    return json.loads(paths[0].read_text(encoding="utf-8"))


def artifact_path(directory: Path, pattern: str) -> Path:
    paths = sorted(directory.glob(pattern))
    assert len(paths) == 1, f"Expected one {pattern} artifact, found {paths}"
    return paths[0]


class FakeEndpoint:
    def __init__(self, response_for_packet: Callable[[dict[str, Any]], dict[str, Any]]):
        self.response_for_packet = response_for_packet
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/v1"

    def __enter__(self) -> "FakeEndpoint":
        self.thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        response_for_packet = self.response_for_packet

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                content = request["messages"][0]["content"]
                packet = json.loads(content[content.find("{") :])
                result = response_for_packet(packet)
                if "_http_status" in result:
                    body = result.get("body", "fake endpoint failure")
                    data = str(body).encode("utf-8")
                    self.send_response(int(result["_http_status"]))
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return

                response = {"choices": [{"message": {"content": json.dumps(result)}}]}
                data = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler


def default_result(packet: dict[str, Any], followups: list[str] | None = None) -> dict[str, Any]:
    return {
        "chunk_id": packet["chunk_id"],
        "facts_found": [],
        "criteria_satisfied": [],
        "criteria_remaining": packet.get("criteria_remaining", []),
        "doc_gaps": [],
        "followup_files": followups or [],
        "confidence": "medium",
    }


def test_tracked_and_all_document_scopes_write_manifest_and_tool_dependencies(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)

    tracked_out = tmp_path / "tracked-out"
    run_orchestrator(
        "--target-root",
        target,
        "--doc",
        "README.md",
        "--mode",
        "full",
        "--dry-run",
        "--max-chunks",
        "1",
        "--document-scope",
        "tracked",
        "--output-dir",
        tracked_out,
    )
    tracked_manifest = load_one_json(tracked_out, "document-manifest-*.json")
    tracked_paths = {entry["path"] for entry in tracked_manifest["documents"]}
    tracked_report = load_one_json(tracked_out, "documenter-*.json")

    assert tracked_manifest["schema_version"] == 1
    assert tracked_manifest["kind"] == "document_manifest"
    assert tracked_manifest["document_scope"] == "tracked"
    assert "README.md" in tracked_paths
    assert "UNTRACKED.md" not in tracked_paths
    assert tracked_report["tool_policy"]["controller_tool_dependencies"] == ["git_ls_files", "read_file"]

    all_out = tmp_path / "all-out"
    run_orchestrator(
        "--target-root",
        target,
        "--doc",
        "README.md",
        "--mode",
        "full",
        "--dry-run",
        "--max-chunks",
        "1",
        "--document-scope",
        "all",
        "--output-dir",
        all_out,
    )
    all_manifest = load_one_json(all_out, "document-manifest-*.json")
    all_paths = {entry["path"] for entry in all_manifest["documents"]}
    all_report = load_one_json(all_out, "documenter-*.json")

    assert all_manifest["document_scope"] == "all"
    assert "UNTRACKED.md" in all_paths
    assert all_manifest["untracked_document_count"] >= 1
    assert all_report["tool_policy"]["controller_tool_dependencies"] == [
        "git_ls_files",
        "read_file",
        "scan_files",
    ]


def test_review_plan_candidate_limits_are_reflected_in_packets(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "candidate-limit"

    run_orchestrator(
        "--target-root",
        target,
        "--doc",
        "README.md",
        "--mode",
        "full",
        "--dry-run",
        "--max-chunks",
        "1",
        "--visible-candidate-limit",
        "2",
        "--visible-candidate-token-limit",
        "10000",
        "--output-dir",
        output_dir,
    )

    report = load_one_json(output_dir, "documenter-*.json")
    review_plan = load_one_json(output_dir, "doc-review-plan-*.json")
    visible_candidates = report["chunks"][0]["visible_followup_candidates"]

    assert review_plan["kind"] == "documenter_review_plan"
    assert review_plan["candidate_policy"]["max_visible_candidates_per_packet"] == 2
    assert review_plan["candidate_pool_count"] > 2
    assert len(visible_candidates) <= 2
    assert all("path" in candidate and "reasons" in candidate for candidate in visible_candidates)


def test_followup_depth_count_limits_and_invalid_rejections_are_recorded(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "followups"

    def response(packet: dict[str, Any]) -> dict[str, Any]:
        if packet["doc_id"] == "README.md":
            visible = [
                candidate["path"]
                for candidate in packet.get("visible_followup_candidates", [])
                if candidate.get("path") != "README.md"
            ]
            return default_result(
                packet,
                [
                    *visible[:2],
                    "missing.md",
                    "assets/tool.exe",
                    "README.md",
                ],
            )
        return default_result(packet, ["README.md"])

    with FakeEndpoint(response) as endpoint:
        run_orchestrator(
            "--target-root",
            target,
            "--doc",
            "README.md",
            "--mode",
            "review",
            "--max-chunks",
            "1",
            "--include-followups",
            "--followup-depth",
            "1",
            "--max-followup-files",
            "1",
            "--role-base-url",
            endpoint.base_url,
            "--output-dir",
            output_dir,
        )

    report = load_one_json(output_dir, "documenter-*.json")
    followup_policy = report["followup_policy"]
    reasons = {item["reason"] for item in followup_policy["skipped_followups"]}

    assert len(followup_policy["accepted_followups"]) == 1
    assert len(report["reviewed_files"]) == 2
    assert "max_followup_files_reached" in reasons
    assert "not_in_document_scope" in reasons
    assert "unsupported_extension" in reasons
    assert "not_visible_to_packet" in reasons
    assert "depth_limit_reached" in reasons


def test_draft_artifacts_stay_under_output_dir_and_target_files_are_read_only(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "drafts"
    original_readme = (target / "README.md").read_text(encoding="utf-8")

    run_orchestrator(
        "--target-root",
        target,
        "--doc",
        "README.md",
        "--mode",
        "full",
        "--dry-run",
        "--max-chunks",
        "1",
        "--write-draft",
        "--output-dir",
        output_dir,
    )

    report = load_one_json(output_dir, "documenter-*.json")
    metadata_path = Path(report["artifacts"]["draft_metadata"])
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    draft_root = Path(metadata["draft_root"]).resolve()
    draft_metadata = Path(metadata["metadata_path"]).resolve()
    draft_index = Path(metadata["index_path"]).resolve()

    draft_root.relative_to(output_dir.resolve())
    draft_metadata.relative_to(output_dir.resolve())
    draft_index.relative_to(output_dir.resolve())
    assert (target / "README.md").read_text(encoding="utf-8") == original_readme
    assert metadata["write_policy"]["target_repo_read_only"] is True
    assert metadata["write_policy"]["overwrite_target_files"] is False


def test_resume_refuses_incompatible_arguments_and_skips_completed_chunks(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "resume"

    run_orchestrator(
        "--target-root",
        target,
        "--doc",
        "README.md",
        "--mode",
        "full",
        "--dry-run",
        "--max-chunks",
        "1",
        "--stop-after-chunks",
        "1",
        "--output-dir",
        output_dir,
    )
    state_path = artifact_path(output_dir, "run-state-*.json")

    incompatible = run_orchestrator(
        "--target-root",
        target,
        "--doc",
        "README.md",
        "--mode",
        "full",
        "--dry-run",
        "--max-chunks",
        "1",
        "--chunk-token-limit",
        "1200",
        "--resume",
        state_path,
        "--output-dir",
        output_dir,
        check=False,
    )
    assert incompatible.returncode != 0
    assert "Resume arguments are incompatible" in incompatible.stderr

    run_orchestrator(
        "--target-root",
        target,
        "--doc",
        "README.md",
        "--mode",
        "full",
        "--dry-run",
        "--max-chunks",
        "1",
        "--resume",
        state_path,
        "--output-dir",
        output_dir,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    report = load_one_json(output_dir, "documenter-*.json")
    assert state["status"] == "completed"
    assert state["completed_chunk_count"] == 1
    assert state["queue_index"] == 1
    assert len(report["chunks"]) == 1


def test_failed_packet_metadata_is_preserved_without_vllm(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "failure"

    with FakeEndpoint(lambda packet: {"_http_status": 500, "body": "planned failure"}) as endpoint:
        result = run_orchestrator(
            "--target-root",
            target,
            "--doc",
            "README.md",
            "--mode",
            "review",
            "--max-chunks",
            "1",
            "--role-base-url",
            endpoint.base_url,
            "--output-dir",
            output_dir,
            check=False,
        )

    assert result.returncode != 0
    state = load_one_json(output_dir, "run-state-*.json")
    failed_packet = state["failed_packets"][0]
    assert state["status"] == "failed"
    assert state["completed_chunk_count"] == 0
    assert failed_packet["packet_summary"]["task"] == "review_chunk_for_documentation"
    assert failed_packet["chunk_id"] == "README.md:0001"
    assert "HTTP 500" in failed_packet["error"]
