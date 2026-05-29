from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

import pytest

from vllm_agent_gateway.controllers.documenter.orchestrator import (
    Chunk,
    DocumenterInvocationRequest,
    ReviewTarget,
    build_packet,
    build_doc_change_plan,
    build_summary_packet,
    estimate_tokens,
    invoke_documenter,
    normalize_result_policy,
    parse_result,
)
from vllm_agent_gateway.invocation import WorkflowStatus


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
    write_text(target / ".aider.chat.history.md", "# Chat History\n\ntransient model session log\n")
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
            ".aider.chat.history.md",
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


def test_documenter_invocation_contract_runs_without_shelling_out(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "contract"

    result = invoke_documenter(
        DocumenterInvocationRequest(
            config_root=REPO_ROOT,
            target_root=target,
            output_dir=output_dir,
            doc="README.md",
            mode="full",
            dry_run=True,
            max_chunks=1,
        )
    )

    assert result.status == WorkflowStatus.COMPLETED
    assert result.workflow == "documenter.review"
    assert "json_report" in result.artifact_paths
    assert "run_state" in result.artifact_paths
    assert result.resume_key is not None
    assert result.report is not None
    assert result.report["kind"] == "documenter_orchestrator_report"
    assert Path(result.artifact_paths["json_report"]).exists()


def test_documenter_cli_uses_repo_config_root_by_default(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "reports"

    result = run_command(
        [
            sys.executable,
            str(SCRIPT),
            "--target-root",
            str(target),
            "--doc",
            "README.md",
            "--mode",
            "full",
            "--dry-run",
            "--max-chunks",
            "1",
            "--output-dir",
            str(output_dir),
        ],
        REPO_ROOT,
    )

    assert "Missing JSON file" not in result.stderr
    assert "Wrote" in result.stdout
    report = load_one_json(output_dir, "documenter-*.json")
    assert report["role_id"] == "documenter/default"


def test_seed_doc_cli_alias_selects_seed_document(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "seed-doc-alias"

    run_orchestrator(
        "--target-root",
        target,
        "--seed-doc",
        "README.md",
        "--mode",
        "full",
        "--dry-run",
        "--max-chunks",
        "1",
        "--output-dir",
        output_dir,
    )

    report = load_one_json(output_dir, "documenter-*.json")
    assert report["seed_doc_id"] == "README.md"
    assert report["doc_id"] == "README.md"


def test_packet_contract_includes_bounded_output_limits() -> None:
    packet = build_packet(
        ReviewTarget(doc_id="README.md", source="seed", depth=0),
        Chunk(
            chunk_id="README.md:0001",
            start_line=1,
            end_line=1,
            text="# Title\n",
            token_estimate=2,
            overlap_previous_lines=0,
        ),
        ["installation steps documented"],
        [],
    )

    assert packet["output_limits"]["max_items"]["facts_found"] == 5
    assert packet["output_limits"]["max_items"]["doc_gaps"] == 5
    assert packet["output_limits"]["max_string_chars"] == 240
    assert packet["criteria_policy"]["scope"] == "run_level"
    assert packet["criteria_policy"]["applies_to_this_doc"] is True


def test_parse_result_reports_likely_truncated_json() -> None:
    with pytest.raises(Exception) as exc_info:
        parse_result('{"chunk_id":"README.md:0001","facts_found":["unterminated', "README.md:0001")

    message = str(exc_info.value)
    assert "README.md:0001" in message
    assert "appears truncated" in message
    assert "--max-output-tokens" in message


def test_result_policy_trims_model_output_to_contract_limits() -> None:
    result = {
        "chunk_id": "README.md:0001",
        "facts_found": [f"fact {index}" for index in range(8)],
        "criteria_satisfied": ["installation steps documented"],
        "criteria_remaining": ["configuration documented"],
        "doc_gaps": ["x" * 260],
        "followup_files": [f"docs/{index}.md" for index in range(8)],
        "confidence": "medium",
    }

    warnings = normalize_result_policy(
        result,
        {f"docs/{index}.md" for index in range(8)},
        ["installation steps documented", "configuration documented"],
    )

    assert len(result["facts_found"]) == 5
    assert len(result["followup_files"]) == 5
    assert result["doc_gaps"][0].endswith("...")
    assert {warning["reason"] for warning in warnings} >= {"trimmed_to_output_limit", "trimmed_long_strings"}


def test_result_policy_filters_run_level_gaps_from_feature_docs() -> None:
    result = {
        "chunk_id": "api_reference/README.md:0001",
        "facts_found": ["API schemas are grouped by category."],
        "criteria_satisfied": ["installation steps documented"],
        "criteria_remaining": ["configuration documented"],
        "doc_gaps": [
            "No explicit installation steps documented for using the API reference library",
            "Endpoint category examples should mention account and order schemas.",
        ],
        "followup_files": [],
        "confidence": "medium",
    }

    warnings = normalize_result_policy(
        result,
        set(),
        ["installation steps documented", "configuration documented"],
        "api_reference/README.md",
    )

    assert result["criteria_satisfied"] == []
    assert result["criteria_remaining"] == []
    assert result["doc_gaps"] == ["Endpoint category examples should mention account and order schemas."]
    assert {warning["reason"] for warning in warnings} >= {
        "removed_run_level_criteria_from_non_entrypoint_doc",
        "removed_global_criteria_gaps_from_non_entrypoint_doc",
    }


def test_summary_packet_is_bounded_for_large_manifest_reports() -> None:
    reviewed_files = [
        {
            "doc_id": f"test_runtime/public-candidate-{index}/docs/architecture.md",
            "source": "manifest",
            "depth": 0,
            "chunks_total": 4,
            "chunks_processed": 4,
            "truncated_after_chunks": False,
        }
        for index in range(500)
    ]
    skipped_followups = [
        {
            "path": f"docs/generated/{index}.md",
            "source_doc_id": f"docs/source-{index}.md",
            "source_chunk_id": f"docs/source-{index}.md:0001",
            "reason": "followups_disabled",
            "visible_candidate": True,
        }
        for index in range(500)
    ]
    report = {
        "doc_id": "AGENTS.md",
        "seed_doc_id": "AGENTS.md",
        "target_root": "/repo",
        "document_scope": "all",
        "review_scope": "manifest",
        "reviewed_files": reviewed_files,
        "review_plan": {"candidate_pool_count": 5000},
        "followup_policy": {"include_followups": False, "skipped_followups": skipped_followups},
        "chunks_processed": 2500,
        "chunks_total": 2500,
        "truncated_after_chunks": False,
        "criteria_initial": ["installation steps documented"],
    }
    aggregate = {
        "facts_found": [f"fact {index} " + ("x" * 300) for index in range(500)],
        "criteria_satisfied": ["installation steps documented"],
        "criteria_remaining": [],
        "doc_gaps": [f"gap {index} " + ("x" * 300) for index in range(500)],
        "followup_files": [f"docs/{index}.md" for index in range(500)],
        "reported_followup_files": [f"docs/{index}.md" for index in range(500)],
        "accepted_followup_files": [],
        "validation_warnings": [
            {"chunk_id": f"docs/{index}.md:0001", "field": "facts_found", "reason": "trimmed_to_output_limit"}
            for index in range(500)
        ],
        "confidence_counts": {"low": 1, "medium": 2, "high": 3},
        "confidence": "low",
    }

    packet = build_summary_packet(report, aggregate)
    packet_tokens = estimate_tokens(json.dumps(packet, ensure_ascii=True, separators=(",", ":")))

    assert packet["reviewed_files"]["total_count"] == 500
    assert packet["reviewed_files"]["retained_count"] == 80
    assert packet["aggregate"]["facts_found"]["retained_count"] == 30
    assert packet["aggregate"]["doc_gaps"]["retained_count"] == 30
    assert packet["followup_policy"]["skipped_followups"]["retained_count"] == 20
    assert packet_tokens < 24000


def test_tracked_and_all_document_scopes_write_manifest_and_tool_dependencies(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    write_text(target / ".venv-1" / "Lib" / "site-packages" / "vendor" / "README.md", "# Vendor\n")
    write_text(target / ".tmp_pytest" / "candidate" / "README.md", "# Pytest Artifact\n")
    write_text(target / "docs" / "archive" / "v2" / "runtime-output" / "startup_output.txt", "ticker log\n" * 200)
    write_text(target / "test_runtime" / "candidate" / "README.md", "# Generated\n")

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
    assert ".aider.chat.history.md" not in tracked_paths
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
    assert ".aider.chat.history.md" not in all_paths
    assert ".venv-1/Lib/site-packages/vendor/README.md" not in all_paths
    assert ".tmp_pytest/candidate/README.md" not in all_paths
    assert "docs/archive/v2/runtime-output/startup_output.txt" not in all_paths
    assert "test_runtime/candidate/README.md" not in all_paths
    assert all_manifest["untracked_document_count"] >= 1
    assert all_report["review_scope"] == "manifest"
    reviewed_doc_ids = {item["doc_id"] for item in all_report["reviewed_files"]}
    assert {"README.md", "UNTRACKED.md", "docs/config.md", "docs/guide.md"} <= reviewed_doc_ids
    assert ".aider.chat.history.md" not in reviewed_doc_ids
    assert all_report["tool_policy"]["controller_tool_dependencies"] == [
        "git_ls_files",
        "read_file",
        "scan_files",
    ]

    seed_only_out = tmp_path / "seed-only-out"
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
        "--review-scope",
        "seed",
        "--output-dir",
        seed_only_out,
    )
    seed_only_report = load_one_json(seed_only_out, "documenter-*.json")
    assert seed_only_report["review_scope"] == "seed"
    assert [item["doc_id"] for item in seed_only_report["reviewed_files"]] == ["README.md"]


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


def test_parallelism_reviews_chunks_concurrently_and_preserves_report_order(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "parallel"
    active_requests = 0
    max_active_requests = 0
    lock = threading.Lock()

    def response(packet: dict[str, Any]) -> dict[str, Any]:
        nonlocal active_requests, max_active_requests
        with lock:
            active_requests += 1
            max_active_requests = max(max_active_requests, active_requests)
        try:
            time.sleep(0.05)
            return default_result(packet)
        finally:
            with lock:
                active_requests -= 1

    with FakeEndpoint(response) as endpoint:
        run_orchestrator(
            "--target-root",
            target,
            "--doc",
            "README.md",
            "--mode",
            "review",
            "--review-scope",
            "manifest",
            "--parallelism",
            "3",
            "--role-base-url",
            endpoint.base_url,
            "--output-dir",
            output_dir,
        )

    report = load_one_json(output_dir, "documenter-*.json")
    state = load_one_json(output_dir, "run-state-*.json")
    chunk_ids = [item["chunk_id"] for item in report["chunks"]]

    assert report["parallelism"] == 3
    assert state["parallelism"] == 3
    assert len(chunk_ids) >= 3
    assert chunk_ids == sorted(chunk_ids)
    assert {"README.md:0001", "docs/config.md:0001", "docs/guide.md:0001"} <= set(chunk_ids)
    assert max_active_requests >= 2


def test_change_plan_groups_validated_findings_and_does_not_modify_target_docs(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "change-plan"
    original_readme = (target / "README.md").read_text(encoding="utf-8")

    def response(packet: dict[str, Any]) -> dict[str, Any]:
        if packet.get("task") == "summarize_documentation_review":
            return {"summary": "fake summary"}
        return {
            "chunk_id": packet["chunk_id"],
            "facts_found": ["Install with Docker is documented."],
            "criteria_satisfied": ["installation steps documented"],
            "criteria_remaining": packet.get("criteria_remaining", []),
            "doc_gaps": ["Runtime port examples need a user decision."],
            "followup_files": ["docs/config.md"],
            "confidence": "medium",
        }

    with FakeEndpoint(response) as endpoint:
        run_orchestrator(
            "--target-root",
            target,
            "--doc",
            "README.md",
            "--mode",
            "full",
            "--max-chunks",
            "1",
            "--role-base-url",
            endpoint.base_url,
            "--output-dir",
            output_dir,
        )

    report = load_one_json(output_dir, "documenter-*.json")
    change_plan_path = Path(report["artifacts"]["doc_change_plan"])
    change_plan = change_plan_path.read_text(encoding="utf-8")

    assert change_plan_path.exists()
    assert (target / "README.md").read_text(encoding="utf-8") == original_readme
    assert "## Safe Documentation Edits" in change_plan
    assert "## Needs User Decision" in change_plan
    assert "## Insufficient Evidence" in change_plan
    assert "CP-0001" in change_plan
    assert "CP-0002" in change_plan
    assert "CP-0003" in change_plan
    assert "## Agent Execution Contract" in change_plan
    assert "## Patch Contracts" in change_plan
    assert "## Executable Work Packages" in change_plan
    assert change_plan.index("## Patch Contracts") < change_plan.index("## Executable Work Packages")
    assert change_plan.index("## Executable Work Packages") < change_plan.index("## Safe Documentation Edits")
    assert "This artifact contains patch contracts followed by raw evidence." in change_plan
    assert "Start with `Patch Contracts`; do not create a second implementation plan unless a contract is blocked." in change_plan
    assert '"id": "PC-0001"' in change_plan
    assert '"id": "WP-0001"' in change_plan
    assert '"target_files": [\n        "README.md",\n        "docs/README.md"\n      ]' in change_plan
    assert (
        "Check whether the current documentation already preserves this source-backed fact; "
        "edit only if it is missing, contradicted, or buried: Install with Docker is documented."
    ) in change_plan
    assert "Decide how to address reported documentation gap: Runtime port examples need a user decision." in change_plan
    assert "Validation warning from report field criteria_satisfied" in change_plan
    assert "### Reported By Documenter" in change_plan
    assert "- docs/config.md" in change_plan


def test_change_plan_work_packages_exclude_chat_history_sources() -> None:
    report = {
        "generated_at": "2026-05-29T00:00:00Z",
        "target_root": "/repo",
        "seed_doc_id": "README.md",
        "doc_id": "README.md",
        "mode": "full",
        "dry_run": False,
        "document_scope": "all",
        "review_scope": "manifest",
        "chunks_processed": 2,
        "chunks_total": 2,
        "truncated_after_chunks": False,
        "chunks": [
            {
                "doc_id": ".aider.chat.history.md",
                "chunk_id": ".aider.chat.history.md:0001",
                "lines": [1, 10],
                "result": {
                    "chunk_id": ".aider.chat.history.md:0001",
                    "facts_found": ["aider session used a model name"],
                    "criteria_satisfied": [],
                    "criteria_remaining": [],
                    "doc_gaps": ["chat transcript has no product overview"],
                    "followup_files": [],
                    "confidence": "high",
                },
            },
            {
                "doc_id": "README.md",
                "chunk_id": "README.md:0001",
                "lines": [1, 8],
                "result": {
                    "chunk_id": "README.md:0001",
                    "facts_found": ["README documents Docker installation"],
                    "criteria_satisfied": [],
                    "criteria_remaining": [],
                    "doc_gaps": [],
                    "followup_files": [],
                    "confidence": "high",
                },
            },
        ],
    }

    change_plan = build_doc_change_plan(report)
    patch_section = change_plan.split("## Patch Contracts", 1)[1].split("## Executable Work Packages", 1)[0]
    work_section = change_plan.split("## Executable Work Packages", 1)[1].split("## Safe Documentation Edits", 1)[0]

    assert "PC-0001" in patch_section
    assert "DO NOT TOUCH" in patch_section
    assert '"target_files": [\n        "README.md"\n      ]' in work_section
    assert ".aider.chat.history.md: 2 CP items" in work_section
    assert '"target_files": [\n        ".aider.chat.history.md"\n      ]' not in work_section


def test_change_plan_routes_agent_context_global_gaps_to_primary_docs() -> None:
    report = {
        "generated_at": "2026-05-29T00:00:00Z",
        "target_root": "/repo",
        "seed_doc_id": "AGENTS.md",
        "doc_id": "AGENTS.md",
        "mode": "full",
        "dry_run": False,
        "document_scope": "all",
        "review_scope": "manifest",
        "chunks_processed": 1,
        "chunks_total": 1,
        "truncated_after_chunks": False,
        "criteria_remaining": ["installation steps documented", "configuration documented"],
        "reviewed_files": [{"doc_id": "AGENTS.md"}],
        "chunks": [
            {
                "doc_id": "AGENTS.md",
                "chunk_id": "AGENTS.md:0001",
                "lines": [1, 40],
                "result": {
                    "chunk_id": "AGENTS.md:0001",
                    "facts_found": ["Project requires Windows 11 and VS Code."],
                    "criteria_satisfied": [],
                    "criteria_remaining": [],
                    "doc_gaps": ["No clear installation steps for the project beyond OS and IDE requirements."],
                    "followup_files": [],
                    "confidence": "high",
                },
            }
        ],
    }

    change_plan = build_doc_change_plan(report)
    patch_section = change_plan.split("## Patch Contracts", 1)[1].split("## Executable Work Packages", 1)[0]
    work_section = change_plan.split("## Executable Work Packages", 1)[1].split("## Safe Documentation Edits", 1)[0]

    assert "### PC-0001: Update README setup and documentation index" in patch_section
    assert "ADD: README.md section `Setup`" in patch_section
    assert "ADD: README.md section `Configuration`" in patch_section
    assert "ADD: docs/README.md section `ordered documentation index`" in patch_section
    assert "DO NOT TOUCH:" in patch_section
    assert "AGENTS.md" in patch_section
    assert "api_reference/**" in patch_section
    assert "Stop after completing this contract" in patch_section
    assert "### WP-0001: primary documentation" in work_section
    assert '"target_files": [\n        "README.md",\n        "docs/README.md"\n      ]' in work_section
    assert '"run_criteria": [\n        "installation steps documented",\n        "configuration documented"\n      ]' in work_section
    assert "AGENTS.md: 2 CP items" in work_section
    assert '"target_files": [\n        "AGENTS.md"\n      ]' not in work_section


def test_dry_run_change_plan_records_insufficient_evidence_instead_of_safe_edits(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    output_dir = tmp_path / "dry-run-change-plan"

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
        "--output-dir",
        output_dir,
    )

    report = load_one_json(output_dir, "documenter-*.json")
    change_plan = Path(report["artifacts"]["doc_change_plan"]).read_text(encoding="utf-8")

    assert "## Safe Documentation Edits" in change_plan
    assert "## Insufficient Evidence" in change_plan
    assert "Dry run produced no model-backed edits" in change_plan
    assert "No model-backed review results are available; dry-run produced packets only." in change_plan
    safe_section = change_plan.split("## Safe Documentation Edits", 1)[1].split("## Needs User Decision", 1)[0]
    assert "- None recorded." in safe_section


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
