from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

import pytest

from vllm_agent_gateway.controllers.documenter.streaming import (
    MODE_REGISTRY,
    StreamingDocumenterInvocationRequest,
    invoke_streaming_documenter,
)
from vllm_agent_gateway.invocation import WorkflowStatus


REPO_ROOT = Path(__file__).resolve().parents[2]
STREAMING_SCRIPT = REPO_ROOT / "scripts" / "run_streaming_documenter.py"
ORCHESTRATOR_SCRIPT = REPO_ROOT / "scripts" / "run_documenter_orchestrator.py"


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


def run_streaming(*args: object, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_command([sys.executable, str(STREAMING_SCRIPT), *[str(arg) for arg in args]], REPO_ROOT, check=check)


def run_orchestrator(*args: object, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(ORCHESTRATOR_SCRIPT),
        "--config-root",
        str(REPO_ROOT),
        *[str(arg) for arg in args],
    ]
    return run_command(command, REPO_ROOT, check=check)


def load_one_json(directory: Path, pattern: str) -> dict[str, Any]:
    paths = sorted(directory.glob(pattern))
    assert len(paths) == 1, f"Expected one {pattern} artifact, found {paths}"
    return json.loads(paths[0].read_text(encoding="utf-8"))


def artifact_path(directory: Path, pattern: str) -> Path:
    paths = sorted(directory.glob(pattern))
    assert len(paths) == 1, f"Expected one {pattern} artifact, found {paths}"
    return paths[0]


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


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
                response = {"choices": [{"message": {"content": json.dumps(result)}}]}
                data = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)
                self.wfile.flush()
                self.close_connection = True

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler


def make_large_doc_repo(tmp_path: Path, data: bytes) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    write_bytes(target / "large.md", data)
    return target


def test_streaming_invocation_contract_runs_without_shelling_out(tmp_path: Path) -> None:
    target = make_large_doc_repo(tmp_path, b"# Large\nneedle here\n")
    output_dir = tmp_path / "contract"

    result = invoke_streaming_documenter(
        StreamingDocumenterInvocationRequest(
            target_root=target,
            doc="large.md",
            query="needle",
            output_dir=output_dir,
            chunk_bytes=16,
            read_block_bytes=8,
        )
    )

    assert result.status == WorkflowStatus.COMPLETED
    assert result.workflow == "streaming_documenter.context_presence"
    assert "streaming_report" in result.artifact_paths
    assert "streaming_state" in result.artifact_paths
    assert result.resume_key is not None
    assert result.report is not None
    assert result.report["kind"] == "streaming_context_presence_report"


def test_context_presence_streaming_uses_bounded_reads_and_source_refs(tmp_path: Path) -> None:
    data = (b"# Large\n" + (b"alpha beta gamma\n" * 20000) + b"the unique streaming needle lives here\n")
    target = make_large_doc_repo(tmp_path, data)
    output_dir = tmp_path / "reports"

    run_streaming(
        "--target-root",
        target,
        "--doc",
        "large.md",
        "--query",
        "unique streaming needle",
        "--chunk-bytes",
        "4096",
        "--read-block-bytes",
        "512",
        "--output-dir",
        output_dir,
    )

    report = load_one_json(output_dir, "streaming-context-presence-*.json")
    manifest = load_one_json(output_dir, "streaming-manifest-*.json")
    match = report["matches"][0]

    assert report["quality_label"] == "source_verified"
    assert report["coverage"]["file_bytes"] > report["coverage"]["chunk_bytes"]
    assert report["coverage"]["max_read_block_bytes"] <= 512
    assert report["coverage"]["full_content_read"] is False
    assert report["coverage"]["skipped_bytes"] == 0
    assert report["coverage"]["reviewed_ranges"]
    assert match["quality_label"] == "source_verified"
    assert match["chunk_id"].startswith("large.md:")
    assert match["byte_range"][0] < match["byte_range"][1]
    assert match["line_range"][0] >= 1
    assert manifest["documents"][0]["full_content_read"] is False
    assert manifest["documents"][0]["byte_range"] == [0, len(data)]


def test_context_presence_reports_insufficient_evidence_for_bounded_partial_scan(tmp_path: Path) -> None:
    data = b"# Large\n" + (b"before budget\n" * 5000) + b"needle after the budget\n"
    target = make_large_doc_repo(tmp_path, data)
    output_dir = tmp_path / "partial"

    run_streaming(
        "--target-root",
        target,
        "--doc",
        "large.md",
        "--query",
        "needle after the budget",
        "--chunk-bytes",
        "1024",
        "--read-block-bytes",
        "128",
        "--max-bytes",
        "4096",
        "--output-dir",
        output_dir,
    )

    report = load_one_json(output_dir, "streaming-context-presence-*.json")

    assert report["quality_label"] == "insufficient_evidence"
    assert report["matches"] == []
    assert report["coverage"]["stop_reason"] == "max_bytes"
    assert report["coverage"]["reviewed_bytes"] == 4096
    assert report["coverage"]["skipped_bytes"] == len(data) - 4096
    assert report["coverage"]["skipped_ranges"][0]["reason"] == "max_bytes"
    assert report["coverage"]["summarized_bytes"] == 0


def test_context_presence_resume_continues_from_saved_byte_offsets(tmp_path: Path) -> None:
    data = b"# Large\n" + (b"ordinary line\n" * 1000) + b"resume finds this needle\n"
    target = make_large_doc_repo(tmp_path, data)
    output_dir = tmp_path / "resume"

    run_streaming(
        "--target-root",
        target,
        "--doc",
        "large.md",
        "--query",
        "resume finds this needle",
        "--chunk-bytes",
        "1024",
        "--read-block-bytes",
        "128",
        "--stop-after-chunks",
        "1",
        "--output-dir",
        output_dir,
    )
    state_path = artifact_path(output_dir, "streaming-state-*.json")
    paused_state = json.loads(state_path.read_text(encoding="utf-8"))

    assert paused_state["status"] == "paused"
    assert paused_state["next_start_byte"] > 0

    run_streaming(
        "--target-root",
        target,
        "--doc",
        "large.md",
        "--query",
        "resume finds this needle",
        "--chunk-bytes",
        "1024",
        "--read-block-bytes",
        "128",
        "--resume",
        state_path,
        "--output-dir",
        output_dir,
    )

    completed_state = json.loads(state_path.read_text(encoding="utf-8"))
    report = load_one_json(output_dir, "streaming-context-presence-*.json")
    assert completed_state["status"] == "completed"
    assert report["quality_label"] == "source_verified"
    assert report["coverage"]["review_complete"] is True


def test_context_presence_finds_query_split_across_chunk_boundary(tmp_path: Path) -> None:
    target = make_large_doc_repo(tmp_path, b"# Large\nabcXYZ\n")
    output_dir = tmp_path / "boundary"

    run_streaming(
        "--target-root",
        target,
        "--doc",
        "large.md",
        "--query",
        "abcXYZ",
        "--chunk-bytes",
        "10",
        "--read-block-bytes",
        "5",
        "--output-dir",
        output_dir,
    )

    report = load_one_json(output_dir, "streaming-context-presence-*.json")
    assert report["quality_label"] == "source_verified"
    assert report["matches"][0]["byte_range"] == [8, 14]


def test_context_presence_mode_registry_declares_lossless_source_refs() -> None:
    definition = MODE_REGISTRY["context_presence"]

    assert definition["lossy"] is False
    assert definition["requires_source_refs"] is True
    assert "byte_range" in definition["source_reference_requirements"]
    assert "max_bytes" in definition["budget_limits"]


def test_token_count_mode_reports_file_chunk_section_and_query_counts(tmp_path: Path) -> None:
    data = (
        b"# Intro\n"
        b"alpha token here\n"
        b"## Details\n"
        b"more alpha content\n"
        b"### Deep\n"
        b"final line\n"
    )
    target = make_large_doc_repo(tmp_path, data)
    output_dir = tmp_path / "token-count"

    run_streaming(
        "--target-root",
        target,
        "--doc",
        "large.md",
        "--mode",
        "token_count",
        "--query",
        "alpha",
        "--chunk-bytes",
        "24",
        "--read-block-bytes",
        "8",
        "--output-dir",
        output_dir,
    )

    report = load_one_json(output_dir, "streaming-token-count-*.json")
    token_count = report["token_count"]

    assert report["kind"] == "streaming_token_count_report"
    assert report["quality_label"] == "source_verified"
    assert token_count["file"]["byte_count"] == len(data)
    assert token_count["file"]["estimated_tokens"] > 0
    assert len(token_count["chunks"]) > 1
    assert all(chunk["byte_range"][0] < chunk["byte_range"][1] for chunk in token_count["chunks"])
    assert token_count["sections"]
    assert all(section["quality_label"] == "source_verified" for section in token_count["sections"])
    assert len(token_count["query_matches"]) == 2
    assert all(match["query"] == "alpha" for match in token_count["query_matches"])
    assert all(match["byte_range"][0] < match["byte_range"][1] for match in token_count["query_matches"])
    assert report["coverage"]["review_complete"] is True


def test_coverage_mode_reports_range_accounting_and_partial_budget(tmp_path: Path) -> None:
    data = b"# Coverage\n" + (b"line\n" * 100)
    target = make_large_doc_repo(tmp_path, data)
    output_dir = tmp_path / "coverage"

    run_streaming(
        "--target-root",
        target,
        "--doc",
        "large.md",
        "--mode",
        "coverage",
        "--chunk-bytes",
        "32",
        "--read-block-bytes",
        "8",
        "--max-bytes",
        "96",
        "--output-dir",
        output_dir,
    )

    report = load_one_json(output_dir, "streaming-coverage-*.json")

    assert report["kind"] == "streaming_coverage_report"
    assert report["quality_label"] == "source_verified"
    assert report["coverage"]["reviewed_bytes"] == 96
    assert report["coverage"]["skipped_bytes"] == len(data) - 96
    assert report["coverage"]["stop_reason"] == "max_bytes"
    assert report["coverage_report"]["reviewed_chunk_ranges"]
    assert report["coverage_report"]["skipped_ranges"][0]["reason"] == "max_bytes"
    assert report["coverage"]["summarized_ranges"] == []
    assert report["coverage"]["failed_ranges"] == []


def test_outline_mode_extracts_headings_and_sections_with_source_ranges(tmp_path: Path) -> None:
    data = (
        b"# Intro\n"
        b"intro text\n"
        b"## Install\n"
        b"install text\n"
        b"## Runtime\n"
        b"runtime text\n"
    )
    target = make_large_doc_repo(tmp_path, data)
    output_dir = tmp_path / "outline"

    run_streaming(
        "--target-root",
        target,
        "--doc",
        "large.md",
        "--mode",
        "outline",
        "--chunk-bytes",
        "32",
        "--read-block-bytes",
        "8",
        "--output-dir",
        output_dir,
    )

    report = load_one_json(output_dir, "streaming-outline-*.json")
    headings = report["outline"]["headings"]
    sections = report["outline"]["sections"]

    assert report["kind"] == "streaming_outline_report"
    assert report["quality_label"] == "source_verified"
    assert [heading["text"] for heading in headings] == ["Intro", "Install", "Runtime"]
    assert all(heading["byte_range"][0] < heading["byte_range"][1] for heading in headings)
    assert all(heading["line_range"][0] >= 1 for heading in headings)
    assert len(sections) == 3
    assert all(section["quality_label"] == "source_verified" for section in sections)
    assert report["coverage"]["review_complete"] is True


def test_outline_mode_handles_heading_split_across_byte_chunks(tmp_path: Path) -> None:
    data = b"# Split Heading\nbody\n"
    target = make_large_doc_repo(tmp_path, data)
    output_dir = tmp_path / "outline-boundary"

    run_streaming(
        "--target-root",
        target,
        "--doc",
        "large.md",
        "--mode",
        "outline",
        "--chunk-bytes",
        "4",
        "--read-block-bytes",
        "2",
        "--output-dir",
        output_dir,
    )

    report = load_one_json(output_dir, "streaming-outline-*.json")
    headings = report["outline"]["headings"]
    assert [heading["text"] for heading in headings] == ["Split Heading"]
    assert headings[0]["byte_range"] == [0, 16]


@pytest.mark.parametrize("mode", ["token_count", "coverage", "outline"])
def test_deterministic_modes_resume_from_saved_streaming_state(tmp_path: Path, mode: str) -> None:
    data = b"# Resume\n" + (b"alpha line\n" * 200) + b"## Final\nlast line\n"
    target = make_large_doc_repo(tmp_path, data)
    output_dir = tmp_path / f"{mode}-resume"
    base_args: list[object] = [
        "--target-root",
        target,
        "--doc",
        "large.md",
        "--mode",
        mode,
        "--chunk-bytes",
        "128",
        "--read-block-bytes",
        "32",
    ]
    if mode == "token_count":
        base_args.extend(["--query", "alpha"])

    run_streaming(
        *base_args,
        "--stop-after-chunks",
        "1",
        "--output-dir",
        output_dir,
    )
    state_path = artifact_path(output_dir, "streaming-state-*.json")
    paused_state = json.loads(state_path.read_text(encoding="utf-8"))

    assert paused_state["status"] == "paused"
    assert paused_state["next_start_byte"] > 0

    run_streaming(
        *base_args,
        "--resume",
        state_path,
        "--output-dir",
        output_dir,
    )

    completed_state = json.loads(state_path.read_text(encoding="utf-8"))
    report = load_one_json(output_dir, f"streaming-{mode.replace('_', '-')}*.json")
    assert completed_state["status"] == "completed"
    assert report["coverage"]["review_complete"] is True


def test_all_deterministic_mode_registry_entries_declare_budget_and_source_refs() -> None:
    for mode in ("coverage", "outline", "token_count"):
        definition = MODE_REGISTRY[mode]
        assert definition["lossy"] is False
        assert definition["requires_source_refs"] is True
        assert "byte_range" in definition["source_reference_requirements"]
        assert "max_bytes" in definition["budget_limits"]


def test_extract_facts_mode_source_validates_model_records(tmp_path: Path) -> None:
    data = (
        b"# Install\n"
        b"Install with Docker.\n"
        b"Configuration is not documented here.\n"
    )
    target = make_large_doc_repo(tmp_path, data)
    output_dir = tmp_path / "extract-facts"

    def response_for_packet(packet: dict[str, Any]) -> dict[str, Any]:
        chunk_text = packet["chunk"]
        base_byte = packet["byte_range"][0]
        install_start = base_byte + chunk_text.index("Install with Docker")
        install_end = install_start + len("Install with Docker")
        config_start = base_byte + chunk_text.index("Configuration")
        config_end = config_start + len("Configuration")
        valid_install_ref = {
            "doc_id": packet["doc_id"],
            "chunk_id": packet["chunk_id"],
            "byte_range": [install_start, install_end],
            "line_range": [2, 2],
        }
        valid_config_ref = {
            "doc_id": packet["doc_id"],
            "chunk_id": packet["chunk_id"],
            "byte_range": [config_start, config_end],
            "line_range": [3, 3],
        }
        invalid_ref = {
            "doc_id": packet["doc_id"],
            "chunk_id": packet["chunk_id"],
            "byte_range": [packet["byte_range"][1] + 1, packet["byte_range"][1] + 10],
            "line_range": [3, 3],
        }
        return {
            "chunk_id": packet["chunk_id"],
            "facts": [
                {
                    "text": "The document says to install with Docker.",
                    "confidence": "medium",
                    "evidence_refs": [valid_install_ref],
                },
                {
                    "text": "Low-confidence installation wording exists.",
                    "confidence": "low",
                    "evidence_refs": [valid_install_ref],
                },
                {
                    "text": "Unsupported invented fact.",
                    "confidence": "high",
                    "evidence_refs": [],
                },
            ],
            "gaps": [
                {
                    "text": "Configuration details are called out as missing.",
                    "confidence": "high",
                    "evidence_refs": [valid_config_ref],
                },
                {
                    "text": "Invalid evidence should not be accepted.",
                    "confidence": "high",
                    "evidence_refs": [invalid_ref],
                },
            ],
        }

    with FakeEndpoint(response_for_packet) as endpoint:
        run_streaming(
            "--target-root",
            target,
            "--doc",
            "large.md",
            "--mode",
            "extract_facts",
            "--role-base-url",
            endpoint.base_url,
            "--chunk-bytes",
            "4096",
            "--read-block-bytes",
            "512",
            "--output-dir",
            output_dir,
        )

    report = load_one_json(output_dir, "streaming-extract-facts-*.json")
    facts = report["extract_facts"]["facts"]
    gaps = report["extract_facts"]["gaps"]

    assert report["kind"] == "streaming_extract_facts_report"
    assert report["quality_label"] == "source_verified"
    assert facts[0]["quality_label"] == "source_verified"
    assert facts[1]["quality_label"] == "insufficient_evidence"
    assert facts[2]["quality_label"] == "insufficient_evidence"
    assert gaps[0]["quality_label"] == "source_verified"
    assert gaps[1]["quality_label"] == "insufficient_evidence"
    assert any(warning["reason"] == "evidence_refs_empty" for warning in report["validation_warnings"])
    assert any(warning["reason"] == "evidence_ref_byte_range_outside_chunk" for warning in report["validation_warnings"])


def test_classify_mode_validates_labels_risks_and_source_refs(tmp_path: Path) -> None:
    data = b"# Runtime\nRuntime ports are configured in runtime/roles.json.\n"
    target = make_large_doc_repo(tmp_path, data)
    output_dir = tmp_path / "classify"

    def response_for_packet(packet: dict[str, Any]) -> dict[str, Any]:
        chunk_text = packet["chunk"]
        base_byte = packet["byte_range"][0]
        runtime_start = base_byte + chunk_text.index("Runtime ports")
        runtime_end = runtime_start + len("Runtime ports")
        valid_ref = {
            "doc_id": packet["doc_id"],
            "chunk_id": packet["chunk_id"],
            "byte_range": [runtime_start, runtime_end],
            "line_range": [2, 2],
        }
        return {
            "chunk_id": packet["chunk_id"],
            "classifications": [
                {
                    "label": "runtime",
                    "confidence": "high",
                    "evidence_refs": [valid_ref],
                },
                {
                    "label": "made_up",
                    "confidence": "high",
                    "evidence_refs": [valid_ref],
                },
            ],
            "risks": [
                {
                    "label": "Runtime settings may be stale.",
                    "severity": "medium",
                    "confidence": "medium",
                    "evidence_refs": [valid_ref],
                },
                {
                    "label": "Bad severity should be downgraded.",
                    "severity": "critical",
                    "confidence": "high",
                    "evidence_refs": [valid_ref],
                },
            ],
        }

    with FakeEndpoint(response_for_packet) as endpoint:
        run_streaming(
            "--target-root",
            target,
            "--doc",
            "large.md",
            "--mode",
            "classify",
            "--role-base-url",
            endpoint.base_url,
            "--classification-label",
            "installation",
            "--classification-label",
            "runtime",
            "--chunk-bytes",
            "4096",
            "--read-block-bytes",
            "512",
            "--output-dir",
            output_dir,
        )

    report = load_one_json(output_dir, "streaming-classify-*.json")
    classifications = report["classify"]["classifications"]
    risks = report["classify"]["risks"]

    assert report["kind"] == "streaming_classify_report"
    assert report["quality_label"] == "source_verified"
    assert report["classify"]["allowed_labels"] == ["installation", "runtime"]
    assert report["classify"]["class_counts"] == {"runtime": 1}
    assert classifications[0]["quality_label"] == "source_verified"
    assert classifications[1]["quality_label"] == "insufficient_evidence"
    assert risks[0]["quality_label"] == "source_verified"
    assert risks[1]["quality_label"] == "insufficient_evidence"
    assert any(warning["reason"] == "label_not_allowed" for warning in report["validation_warnings"])
    assert any(warning["reason"] == "invalid_severity" for warning in report["validation_warnings"])


@pytest.mark.parametrize("mode", ["extract_facts", "classify"])
def test_model_assisted_modes_resume_from_saved_streaming_state(tmp_path: Path, mode: str) -> None:
    data = b"# First\nfirst chunk content\n# Second\nsecond chunk content\n"
    target = make_large_doc_repo(tmp_path, data)
    output_dir = tmp_path / f"{mode}-resume"

    def response_for_packet(packet: dict[str, Any]) -> dict[str, Any]:
        ref = {
            "doc_id": packet["doc_id"],
            "chunk_id": packet["chunk_id"],
            "byte_range": [packet["byte_range"][0], min(packet["byte_range"][0] + 1, packet["byte_range"][1])],
            "line_range": [packet["line_range"][0], packet["line_range"][0]],
        }
        if mode == "extract_facts":
            return {
                "chunk_id": packet["chunk_id"],
                "facts": [{"text": f"Fact {packet['chunk_index']}", "confidence": "medium", "evidence_refs": [ref]}],
                "gaps": [],
            }
        return {
            "chunk_id": packet["chunk_id"],
            "classifications": [{"label": "runtime", "confidence": "medium", "evidence_refs": [ref]}],
            "risks": [],
        }

    with FakeEndpoint(response_for_packet) as endpoint:
        base_args: list[object] = [
            "--target-root",
            target,
            "--doc",
            "large.md",
            "--mode",
            mode,
            "--role-base-url",
            endpoint.base_url,
            "--classification-label",
            "runtime",
            "--chunk-bytes",
            "24",
            "--read-block-bytes",
            "8",
        ]

        run_streaming(
            *base_args,
            "--stop-after-chunks",
            "1",
            "--output-dir",
            output_dir,
        )
        state_path = artifact_path(output_dir, "streaming-state-*.json")
        paused_state = json.loads(state_path.read_text(encoding="utf-8"))

        assert paused_state["status"] == "paused"
        assert paused_state["next_start_byte"] > 0

        run_streaming(
            *base_args,
            "--resume",
            state_path,
            "--output-dir",
            output_dir,
        )

    completed_state = json.loads(state_path.read_text(encoding="utf-8"))
    report = load_one_json(output_dir, f"streaming-{mode.replace('_', '-')}*.json")
    assert completed_state["status"] == "completed"
    assert report["coverage"]["review_complete"] is True
    assert report["quality_label"] == "source_verified"


def test_model_assisted_mode_requires_role_base_url(tmp_path: Path) -> None:
    target = make_large_doc_repo(tmp_path, b"# Missing Endpoint\n")

    result = run_streaming(
        "--target-root",
        target,
        "--doc",
        "large.md",
        "--mode",
        "extract_facts",
        "--output-dir",
        tmp_path / "missing-endpoint",
        check=False,
    )

    assert result.returncode != 0
    assert "--role-base-url is required for extract_facts" in result.stderr


def test_model_assisted_invalid_result_schema_records_failed_range(tmp_path: Path) -> None:
    target = make_large_doc_repo(tmp_path, b"# Bad Schema\ncontent\n")
    output_dir = tmp_path / "bad-schema"

    def response_for_packet(packet: dict[str, Any]) -> dict[str, Any]:
        return {
            "chunk_id": packet["chunk_id"],
            "facts": [],
        }

    with FakeEndpoint(response_for_packet) as endpoint:
        result = run_streaming(
            "--target-root",
            target,
            "--doc",
            "large.md",
            "--mode",
            "extract_facts",
            "--role-base-url",
            endpoint.base_url,
            "--output-dir",
            output_dir,
            check=False,
        )

    state_path = artifact_path(output_dir, "streaming-state-*.json")
    state = json.loads(state_path.read_text(encoding="utf-8"))

    assert result.returncode != 0
    assert "field 'gaps' must be a list" in result.stderr
    assert state["status"] == "failed"
    assert state["failed_chunks"] == 1
    assert state["failed_ranges"][0]["quality_label"] == "insufficient_evidence"


def test_summarize_mode_writes_lossy_summary_and_separate_source_records(tmp_path: Path) -> None:
    data = (
        b"# One\nfirst chunk has installation notes\n"
        b"# Two\nsecond chunk has runtime notes\n"
        b"# Three\nthird chunk has risk notes\n"
        b"# Four\nfourth chunk has reference notes\n"
    )
    target = make_large_doc_repo(tmp_path, data)
    output_dir = tmp_path / "summarize"

    def response_for_packet(packet: dict[str, Any]) -> dict[str, Any]:
        if packet["task"] == "merge_lossy_summaries":
            return {
                "merge_id": packet["merge_id"],
                "summary": "Merged lossy orientation across input summaries.",
                "source_refs": packet["allowed_source_refs"][:2],
                "caveats": ["Merged summaries are still lossy."],
            }
        ref = {
            "doc_id": packet["doc_id"],
            "chunk_id": packet["chunk_id"],
            "byte_range": [packet["byte_range"][0], min(packet["byte_range"][0] + 1, packet["byte_range"][1])],
            "line_range": [packet["line_range"][0], packet["line_range"][0]],
        }
        return {
            "chunk_id": packet["chunk_id"],
            "summary": f"Lossy summary for chunk {packet['chunk_index']}.",
            "source_refs": [ref],
            "source_verified_records": [
                {
                    "text": f"Support record for chunk {packet['chunk_index']}.",
                    "confidence": "medium",
                    "evidence_refs": [ref],
                }
            ],
            "caveats": ["Chunk summary is lossy."],
        }

    with FakeEndpoint(response_for_packet) as endpoint:
        run_streaming(
            "--target-root",
            target,
            "--doc",
            "large.md",
            "--mode",
            "summarize",
            "--role-base-url",
            endpoint.base_url,
            "--chunk-bytes",
            "36",
            "--read-block-bytes",
            "12",
            "--max-summaries",
            "2",
            "--max-summary-depth",
            "4",
            "--output-dir",
            output_dir,
        )

    report = load_one_json(output_dir, "streaming-summarize-*.json")
    summary = report["summarize"]

    assert report["kind"] == "streaming_summarize_report"
    assert report["quality_label"] == "summary_derived"
    assert report["coverage"]["summarized_bytes"] == report["coverage"]["reviewed_bytes"]
    assert summary["lossy"] is True
    assert "Summaries are lossy orientation, not evidence by themselves." in summary["caveats"]
    assert "Merged summaries are still lossy." in summary["caveats"]
    assert summary["summary_aggregate"]["quality_label"] == "summary_derived"
    assert summary["summary_reductions"]
    assert all(item["quality_label"] == "summary_derived" for item in summary["summary_derived"])
    assert all(item["quality_label"] == "source_verified" for item in summary["source_verified_records"])
    assert "source_verified_records" in summary
    assert "summary_derived" in summary


def test_summarize_mode_does_not_treat_unsupported_summary_as_evidence(tmp_path: Path) -> None:
    target = make_large_doc_repo(tmp_path, b"# Unsupported\nsummary without source refs\n")
    output_dir = tmp_path / "unsupported-summary"

    def response_for_packet(packet: dict[str, Any]) -> dict[str, Any]:
        ref = {
            "doc_id": packet["doc_id"],
            "chunk_id": packet["chunk_id"],
            "byte_range": [packet["byte_range"][0], min(packet["byte_range"][0] + 1, packet["byte_range"][1])],
            "line_range": [packet["line_range"][0], packet["line_range"][0]],
        }
        return {
            "chunk_id": packet["chunk_id"],
            "summary": "This summary has no supporting refs and must not become evidence.",
            "source_refs": [],
            "source_verified_records": [
                {
                    "text": "The support record is separate from the summary.",
                    "confidence": "medium",
                    "evidence_refs": [ref],
                }
            ],
            "caveats": [],
        }

    with FakeEndpoint(response_for_packet) as endpoint:
        run_streaming(
            "--target-root",
            target,
            "--doc",
            "large.md",
            "--mode",
            "summarize",
            "--role-base-url",
            endpoint.base_url,
            "--output-dir",
            output_dir,
        )

    report = load_one_json(output_dir, "streaming-summarize-*.json")
    summary = report["summarize"]

    assert report["quality_label"] == "insufficient_evidence"
    assert summary["summary_derived"][0]["quality_label"] == "insufficient_evidence"
    assert summary["source_verified_records"][0]["quality_label"] == "source_verified"
    assert any(warning["reason"] == "evidence_refs_empty" for warning in report["validation_warnings"])


def test_summarize_mode_resume_and_final_merge(tmp_path: Path) -> None:
    data = b"# First\nfirst chunk content\n# Second\nsecond chunk content\n"
    target = make_large_doc_repo(tmp_path, data)
    output_dir = tmp_path / "summarize-resume"

    def response_for_packet(packet: dict[str, Any]) -> dict[str, Any]:
        if packet["task"] == "merge_lossy_summaries":
            return {
                "merge_id": packet["merge_id"],
                "summary": "Final resumed summary.",
                "source_refs": packet["allowed_source_refs"][:1],
                "caveats": ["Final merge is lossy."],
            }
        ref = {
            "doc_id": packet["doc_id"],
            "chunk_id": packet["chunk_id"],
            "byte_range": [packet["byte_range"][0], min(packet["byte_range"][0] + 1, packet["byte_range"][1])],
            "line_range": [packet["line_range"][0], packet["line_range"][0]],
        }
        return {
            "chunk_id": packet["chunk_id"],
            "summary": f"Chunk {packet['chunk_index']} summary.",
            "source_refs": [ref],
            "source_verified_records": [],
            "caveats": [],
        }

    with FakeEndpoint(response_for_packet) as endpoint:
        base_args: list[object] = [
            "--target-root",
            target,
            "--doc",
            "large.md",
            "--mode",
            "summarize",
            "--role-base-url",
            endpoint.base_url,
            "--chunk-bytes",
            "24",
            "--read-block-bytes",
            "8",
        ]

        run_streaming(
            *base_args,
            "--stop-after-chunks",
            "1",
            "--output-dir",
            output_dir,
        )
        state_path = artifact_path(output_dir, "streaming-state-*.json")
        paused_state = json.loads(state_path.read_text(encoding="utf-8"))

        assert paused_state["status"] == "paused"
        assert paused_state["next_start_byte"] > 0

        run_streaming(
            *base_args,
            "--resume",
            state_path,
            "--output-dir",
            output_dir,
        )

    completed_state = json.loads(state_path.read_text(encoding="utf-8"))
    report = load_one_json(output_dir, "streaming-summarize-*.json")

    assert completed_state["status"] == "completed"
    assert report["coverage"]["review_complete"] is True
    assert report["quality_label"] == "summary_derived"
    assert report["summarize"]["summary_aggregate"]["summary"] == "Final resumed summary."


def test_summarize_mode_registry_declares_lossy_summary_controls() -> None:
    definition = MODE_REGISTRY["summarize"]

    assert definition["lossy"] is True
    assert definition["requires_source_refs"] is True
    assert definition["model_assisted"] is True
    assert "max_summaries" in definition["budget_limits"]
    assert "max_summary_depth" in definition["budget_limits"]


def test_model_assisted_mode_registry_entries_declare_budget_and_source_refs() -> None:
    for mode in ("extract_facts", "classify"):
        definition = MODE_REGISTRY[mode]
        assert definition["lossy"] is False
        assert definition["requires_source_refs"] is True
        assert definition["model_assisted"] is True
        assert "byte_range" in definition["source_reference_requirements"]
        assert "max_model_records" in definition["budget_limits"]


def test_in_memory_documenter_rejects_oversized_selected_doc_without_override(tmp_path: Path) -> None:
    target = tmp_path / "tracked"
    target.mkdir()
    (target / "README.md").write_text("# Huge\n\n" + ("x" * 2048), encoding="utf-8")
    run_command(["git", "init"], target)
    run_command(["git", "add", "README.md"], target)
    output_dir = tmp_path / "in-memory"

    rejected = run_orchestrator(
        "--target-root",
        target,
        "--doc",
        "README.md",
        "--mode",
        "full",
        "--dry-run",
        "--max-in-memory-doc-bytes",
        "1024",
        "--output-dir",
        output_dir,
        check=False,
    )

    assert rejected.returncode != 0
    assert "exceeds --max-in-memory-doc-bytes" in rejected.stderr

    run_orchestrator(
        "--target-root",
        target,
        "--doc",
        "README.md",
        "--mode",
        "full",
        "--dry-run",
        "--max-in-memory-doc-bytes",
        "1024",
        "--allow-large-in-memory-docs",
        "--max-chunks",
        "1",
        "--output-dir",
        tmp_path / "override",
    )
