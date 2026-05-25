from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from streaming_documenter import MODE_REGISTRY


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


def make_large_doc_repo(tmp_path: Path, data: bytes) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    write_bytes(target / "large.md", data)
    return target


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
