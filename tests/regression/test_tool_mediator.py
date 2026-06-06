from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from vllm_agent_gateway.tools.mediator import (
    SUPPORTED_TOOL_IDS,
    ToolCall,
    ToolMediationError,
    ToolMediator,
    generate_tool_schemas,
    load_tool_catalog,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_command(args: list[str], cwd: Path) -> None:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if result.returncode != 0:
        pytest.fail(
            f"Command failed: {args}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_target_repo(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    write_text(target / "README.md", "# Sample\n\nInstall with pytest.\n")
    write_text(target / "docs" / "config.md", "# Config\n\nUse runtime/tools.json.\n")
    write_text(target / "runtime" / "tools.json", '{"tools":[]}\n')
    write_text(target / "scratch.tmp", "untracked\n")
    run_command(["git", "init"], target)
    run_command(["git", "add", "README.md", "docs/config.md", "runtime/tools.json"], target)
    return target


def test_tool_schema_generation_only_exposes_executable_catalog_tools(tmp_path: Path) -> None:
    catalog = load_tool_catalog(REPO_ROOT)
    target = make_target_repo(tmp_path)
    mediator = ToolMediator(target, catalog, SUPPORTED_TOOL_IDS)
    schema_names = {schema["function"]["name"] for schema in mediator.tool_schemas}

    assert schema_names == SUPPORTED_TOOL_IDS
    assert all(schema["type"] == "function" for schema in mediator.tool_schemas)
    assert all(schema["function"]["parameters"]["additionalProperties"] is False for schema in mediator.tool_schemas)

    with pytest.raises(ToolMediationError, match="missing from the catalog"):
        generate_tool_schemas(catalog, {"not_in_catalog"})

    unsupported_catalog = {
        "tools": [
            {
                "id": "pretend_tool",
                "description": "No executable mediator exists.",
                "args_schema": {},
            }
        ]
    }
    with pytest.raises(ToolMediationError, match="no executable mediator"):
        generate_tool_schemas(unsupported_catalog, {"pretend_tool"})


def test_tool_loop_executes_tool_call_and_injects_result(tmp_path: Path) -> None:
    catalog = load_tool_catalog(REPO_ROOT)
    target = make_target_repo(tmp_path)
    mediator = ToolMediator(target, catalog, {"git_ls_files"})

    def fake_chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        assert [tool["function"]["name"] for tool in tools] == ["git_ls_files"]
        tool_messages = [message for message in messages if message.get("role") == "tool"]
        if not tool_messages:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "git_ls_files",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        result = json.loads(tool_messages[-1]["content"])
        assert "README.md" in result["files"]
        return {"choices": [{"message": {"role": "assistant", "content": "Listed tracked files."}}]}

    run = mediator.run_tool_loop([{"role": "user", "content": "List files."}], fake_chat)

    assert run["message"]["content"] == "Listed tracked files."
    assert run["tool_results"][0]["name"] == "git_ls_files"
    assert any(message.get("role") == "tool" and message.get("tool_call_id") == "call-1" for message in run["messages"])


def test_raw_tool_call_text_is_rejected_without_execution(tmp_path: Path) -> None:
    catalog = load_tool_catalog(REPO_ROOT)
    target = make_target_repo(tmp_path)
    mediator = ToolMediator(target, catalog, {"git_ls_files"})

    def fake_chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "git_ls_files",
                                            "arguments": {},
                                        }
                                    }
                                ]
                            }
                        ),
                    }
                }
            ]
        }

    with pytest.raises(ToolMediationError, match="Raw tool-call-shaped text"):
        mediator.run_tool_loop([{"role": "user", "content": "List files."}], fake_chat)


def test_tool_policy_blocks_unallowed_and_unsafe_file_access(tmp_path: Path) -> None:
    catalog = load_tool_catalog(REPO_ROOT)
    target = make_target_repo(tmp_path)
    mediator = ToolMediator(target, catalog, {"read_file"})

    with pytest.raises(ToolMediationError, match="not allowed"):
        mediator.execute_tool_call(ToolCall(call_id="1", name="git_ls_files", arguments={}))

    with pytest.raises(ToolMediationError, match="outside repo root"):
        mediator.execute_tool_call(ToolCall(call_id="2", name="read_file", arguments={"path": "../secret.txt"}))

    result = mediator.execute_tool_call(ToolCall(call_id="3", name="read_file", arguments={"path": "README.md"}))
    assert result["ok"] is True
    assert result["path"] == "README.md"
    assert "Install with pytest" in result["content"]


def test_scan_files_and_run_tests_are_executable_local_capabilities(tmp_path: Path) -> None:
    catalog = load_tool_catalog(REPO_ROOT)
    target = make_target_repo(tmp_path)
    mediator = ToolMediator(target, catalog, {"scan_files", "run_tests"})

    scan_result = mediator.execute_tool_call(ToolCall(call_id="1", name="scan_files", arguments={}))
    assert scan_result["ok"] is True
    assert "README.md" in scan_result["files"]
    assert ".git/config" not in scan_result["files"]
    assert "scratch.tmp" in scan_result["files"]

    test_result = mediator.execute_tool_call(
        ToolCall(call_id="2", name="run_tests", arguments={"args": ["--version"]})
    )
    assert test_result["ok"] is True
    assert "pytest" in (test_result["stdout"] + test_result["stderr"]).lower()


def test_codegraph_context_is_executable_curated_relationship_lookup(tmp_path: Path) -> None:
    catalog = load_tool_catalog(REPO_ROOT)
    target = make_target_repo(tmp_path)
    write_text(
        target / "service.py",
        "def place_order(order):\n"
        "    return order\n\n"
        "def wrapper(order):\n"
        "    return place_order(order)\n",
    )
    run_command(["git", "add", "service.py"], target)
    mediator = ToolMediator(target, catalog, {"codegraph_context"})

    result = mediator.execute_tool_call(
        ToolCall(
            call_id="1",
            name="codegraph_context",
            arguments={
                "relationship_queries": [
                    {
                        "kind": "callers",
                        "symbol": "place_order",
                        "max_results": 10,
                    }
                ]
            },
        )
    )

    assert result["ok"] is True
    relationship_results = result["relationship_results"]
    assert relationship_results["adapter"] == "curated_codegraph_context"
    matches = relationship_results["queries"][0]["matches"]
    assert any(match["source_path"] == "service.py" and match["source_symbol"].endswith(".wrapper") for match in matches)
