from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from vllm_agent_gateway.structure_index.indexer import build_index_slice


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "run_code_structure_index.py"


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


def run_index(*args: object, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT), *[str(arg) for arg in args]]
    return run_command(command, REPO_ROOT, check=check)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_one_json(directory: Path, pattern: str) -> dict[str, Any]:
    paths = sorted(directory.glob(pattern))
    assert len(paths) == 1, f"Expected one {pattern} artifact, found {paths}"
    return json.loads(paths[0].read_text(encoding="utf-8"))


def make_structure_repo(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    write_text(
        target / "pkg" / "mod.py",
        "\n".join(
            [
                '"""Module docs."""',
                "import os",
                "from pathlib import Path as P",
                "",
                "def decorator(fn):",
                "    return fn",
                "",
                "class Service:",
                '    """Service docs."""',
                "    @decorator",
                "    def run(self):",
                "        return os.getcwd()",
                "",
                "async def fetch():",
                "    return P('.')",
                "",
                "raise RuntimeError('would execute if imported')",
                "",
            ]
        ),
    )
    write_text(target / "pkg" / "broken.py", "def broken(:\n    pass\n")
    write_text(
        target / "README.md",
        "\n".join(
            [
                "# Project",
                "",
                "See [Usage](docs/setup.md#usage) and [Missing](docs/missing.md).",
                "Also see [External](https://example.invalid/docs).",
                "The [deferred reference][setup-ref] is valid even before its definition.",
                "",
                "[setup-ref]: docs/setup.md#usage",
                "",
            ]
        ),
    )
    write_text(target / "docs" / "setup.md", "# Setup\n\n## Usage\n\nRun the tool.\n")
    write_text(
        target / "config" / "settings.json",
        '{\n  "runtime": {"port": 8205},\n  "roles": [{"name": "documenter"}]\n}\n',
    )
    write_text(target / "config" / "bad.json", '{"runtime": }\n')
    write_text(target / "config" / "app.yaml", "runtime:\n  port: 8205\n  enabled: true\n")
    write_text(target / "config" / "bad.yaml", "features: [alpha\n")
    write_text(target / "UNTRACKED.py", "def untracked():\n    return True\n")

    run_command(["git", "init"], target)
    run_command(
        [
            "git",
            "add",
            "pkg/mod.py",
            "pkg/broken.py",
            "README.md",
            "docs/setup.md",
            "config/settings.json",
            "config/bad.json",
            "config/app.yaml",
            "config/bad.yaml",
        ],
        target,
    )
    return target


def file_by_path(index: dict[str, Any], path: str) -> dict[str, Any]:
    matches = [item for item in index["files"] if item["path"] == path]
    assert len(matches) == 1
    return matches[0]


def test_code_structure_index_generates_static_python_indexes(tmp_path: Path) -> None:
    target = make_structure_repo(tmp_path)
    output_dir = tmp_path / "reports"

    run_index("--target-root", target, "--output-dir", output_dir)
    index = load_one_json(output_dir, "code-structure-index-*.json")
    module = file_by_path(index, "pkg/mod.py")
    broken = file_by_path(index, "pkg/broken.py")

    assert index["schema_version"] == 1
    assert index["kind"] == "code_structure_index"
    assert index["file_scope"] == "tracked"
    assert index["selection_policy"]["executes_target_code"] is False
    assert [item["tool_id"] for item in index["tool_dependencies"]] == ["git_ls_files", "read_file"]
    assert module["status"] == "indexed"
    assert module["parser"] == "python_ast"
    assert module["sha256"]
    assert {"kind": "import", "line": 2, "module": None, "level": 0, "names": [{"name": "os", "asname": None}]} in module["imports"]
    assert any(item["module"] == "pathlib" and item["names"][0]["asname"] == "P" for item in module["imports"])

    symbols = {item["qualified_name"]: item for item in module["symbols"]}
    assert "pkg.mod" in symbols
    assert "pkg.mod.Service" in symbols
    assert "pkg.mod.Service.run" in symbols
    assert "pkg.mod.fetch" in symbols
    assert symbols["pkg.mod.Service"]["docstring_preview"] == "Service docs."
    assert symbols["pkg.mod.Service.run"]["decorators"] == ["decorator"]
    assert broken["status"] == "parse_error"
    assert broken["parse_errors"][0]["message"]


def test_code_structure_index_records_markdown_graph_and_config_key_paths(tmp_path: Path) -> None:
    target = make_structure_repo(tmp_path)
    output_dir = tmp_path / "reports"

    run_index("--target-root", target, "--output-dir", output_dir)
    index = load_one_json(output_dir, "code-structure-index-*.json")
    readme = file_by_path(index, "README.md")
    setup = file_by_path(index, "docs/setup.md")
    settings = file_by_path(index, "config/settings.json")
    bad_json = file_by_path(index, "config/bad.json")
    app_yaml = file_by_path(index, "config/app.yaml")
    bad_yaml = file_by_path(index, "config/bad.yaml")

    assert readme["parser"] == "markdown_reference_scanner"
    assert setup["inbound_edge_count"] == 2
    assert readme["outbound_edge_count"] == 3
    assert readme["unresolved_link_count"] == 1
    assert any(link["target_path"] == "docs/setup.md" and link["unresolved"] is False for link in readme["links"])
    assert any(link.get("reference_id") == "setup-ref" and link["unresolved"] is False for link in readme["links"])
    assert any(link["target_path"] == "docs/missing.md" and link["unresolved"] is True for link in readme["links"])
    assert index["reference_graph"]["unresolved_edge_count"] == 1

    key_paths = {item["path"]: item for item in settings["key_paths"]}
    assert key_paths["runtime.port"]["scalar_preview"] == "8205"
    assert key_paths["roles[0].name"]["scalar_preview"] == "documenter"
    assert key_paths["runtime"]["line_range"] == [2, 2]
    assert bad_json["status"] == "parse_error"
    assert bad_json["parse_errors"][0]["line"] == 1

    yaml_paths = {item["path"]: item for item in app_yaml["key_paths"]}
    assert yaml_paths["runtime.port"]["scalar_preview"] == "8205"
    assert yaml_paths["runtime.enabled"]["value_type"] == "boolean"
    assert bad_yaml["status"] == "parse_error"
    assert bad_yaml["parse_errors"][0]["message"] == "unbalanced inline collection"


def test_code_structure_index_all_scope_includes_untracked_supported_files(tmp_path: Path) -> None:
    target = make_structure_repo(tmp_path)
    tracked_output = tmp_path / "tracked"
    all_output = tmp_path / "all"

    run_index("--target-root", target, "--output-dir", tracked_output)
    run_index("--target-root", target, "--file-scope", "all", "--output-dir", all_output)

    tracked_index = load_one_json(tracked_output, "code-structure-index-*.json")
    all_index = load_one_json(all_output, "code-structure-index-*.json")

    assert "UNTRACKED.py" not in tracked_index["selected_files"]
    assert "UNTRACKED.py" in all_index["selected_files"]
    assert [item["tool_id"] for item in all_index["tool_dependencies"]] == [
        "git_ls_files",
        "scan_files",
        "read_file",
    ]


def test_code_structure_index_slice_is_bounded_and_packet_ready(tmp_path: Path) -> None:
    target = make_structure_repo(tmp_path)
    output_dir = tmp_path / "reports"

    run_index("--target-root", target, "--output-dir", output_dir)
    index = load_one_json(output_dir, "code-structure-index-*.json")

    index_slice = build_index_slice(
        index,
        paths=["pkg/mod.py"],
        symbol_query="Service",
        max_records=1,
    )

    assert index_slice["kind"] == "code_structure_index_slice"
    assert index_slice["packet_field"] == "structure_index_slice"
    assert index_slice["available_record_count"] >= 2
    assert index_slice["record_count"] == 1
    assert index_slice["truncated"] is True
    assert index_slice["records"][0]["record_type"] == "symbol"
    assert index_slice["records"][0]["path"] == "pkg/mod.py"
    assert {record["record_type"] for record in index_slice["records"]} == {"symbol"}
