#!/usr/bin/env python3
"""Executable local tool mediation for agent roles.

Prompt text can describe policy, but it cannot execute tools. This module turns
entries from runtime/tools.json into OpenAI-compatible tool schemas, detects
real model tool calls, executes the matching local capability, injects tool
results back into the conversation, and rejects raw tool-call-shaped text as a
final answer.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


SUPPORTED_TOOL_IDS = {
    "git_ls_files",
    "git_grep",
    "read_file",
    "scan_files",
    "structure_index",
    "codegraph_context",
    "run_tests",
}
DEFAULT_IGNORED_SCAN_DIRS = {
    ".agentic_reports",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tmp_pytest",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}


class ToolMediationError(RuntimeError):
    """Raised when tool mediation cannot safely continue."""


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


ChatCompletionCallable = Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]]


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ToolMediationError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ToolMediationError(f"Invalid JSON file: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ToolMediationError(f"JSON file must contain an object: {path}")
    return value


def load_tool_catalog(config_root_or_path: Path) -> dict[str, Any]:
    path = config_root_or_path / "runtime" / "tools.json" if config_root_or_path.is_dir() else config_root_or_path
    return read_json(path)


def catalog_tools_by_id(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_tools = catalog.get("tools")
    if not isinstance(raw_tools, list):
        raise ToolMediationError("Tool catalog must contain a tools list.")
    tools: dict[str, dict[str, Any]] = {}
    for tool in raw_tools:
        if not isinstance(tool, dict) or not isinstance(tool.get("id"), str):
            raise ToolMediationError("Every tool catalog entry must contain a string id.")
        tool_id = tool["id"]
        if tool_id in tools:
            raise ToolMediationError(f"Duplicate tool id in catalog: {tool_id}")
        tools[tool_id] = tool
    return tools


def schema_for_argument(arg_schema: dict[str, Any]) -> dict[str, Any]:
    arg_type = arg_schema.get("type")
    if arg_type == "string":
        return {"type": "string"}
    if arg_type == "array":
        item_type = arg_schema.get("items", "string")
        if item_type == "object":
            return {"type": "array", "items": {"type": "object"}}
        return {"type": "array", "items": {"type": "string"}}
    if arg_type == "boolean":
        return {"type": "boolean"}
    if arg_type == "integer":
        return {"type": "integer"}
    raise ToolMediationError(f"Unsupported tool argument type: {arg_type!r}")


def schema_for_tool(tool: dict[str, Any]) -> dict[str, Any]:
    tool_id = tool["id"]
    if tool_id not in SUPPORTED_TOOL_IDS:
        raise ToolMediationError(f"Tool catalog entry has no executable mediator: {tool_id}")
    raw_args_schema = tool.get("args_schema", {})
    if not isinstance(raw_args_schema, dict):
        raise ToolMediationError(f"Tool {tool_id} args_schema must be an object.")

    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, arg_schema in raw_args_schema.items():
        if not isinstance(name, str) or not isinstance(arg_schema, dict):
            raise ToolMediationError(f"Tool {tool_id} has an invalid argument schema entry.")
        properties[name] = schema_for_argument(arg_schema)
        if arg_schema.get("required") is True:
            required.append(name)

    return {
        "type": "function",
        "function": {
            "name": tool_id,
            "description": str(tool.get("description") or tool_id),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
            "strict": True,
        },
    }


def generate_tool_schemas(catalog: dict[str, Any], allowed_tool_ids: list[str] | set[str]) -> list[dict[str, Any]]:
    tools = catalog_tools_by_id(catalog)
    allowed = set(allowed_tool_ids)
    unknown = sorted(allowed - set(tools))
    if unknown:
        raise ToolMediationError(f"Allowed tool ids are missing from the catalog: {', '.join(unknown)}")
    unsupported = sorted(allowed - SUPPORTED_TOOL_IDS)
    if unsupported:
        raise ToolMediationError(f"Allowed tool ids have no executable mediator: {', '.join(unsupported)}")
    return [schema_for_tool(tool) for tool_id, tool in tools.items() if tool_id in allowed]


def decode_tool_arguments(raw_arguments: Any, tool_name: str) -> dict[str, Any]:
    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError as exc:
            raise ToolMediationError(f"Tool call {tool_name} arguments are not valid JSON.") from exc
    elif isinstance(raw_arguments, dict):
        arguments = raw_arguments
    else:
        raise ToolMediationError(f"Tool call {tool_name} arguments must be a JSON string or object.")
    if not isinstance(arguments, dict):
        raise ToolMediationError(f"Tool call {tool_name} arguments must decode to an object.")
    return arguments


def detect_tool_calls(message: dict[str, Any]) -> list[ToolCall]:
    raw_tool_calls = message.get("tool_calls")
    if raw_tool_calls is None:
        return []
    if not isinstance(raw_tool_calls, list):
        raise ToolMediationError("message.tool_calls must be a list.")

    calls: list[ToolCall] = []
    for index, raw_call in enumerate(raw_tool_calls):
        if not isinstance(raw_call, dict):
            raise ToolMediationError("Every tool call must be an object.")
        if raw_call.get("type") != "function":
            raise ToolMediationError("Only function tool calls are supported.")
        raw_function = raw_call.get("function")
        if not isinstance(raw_function, dict):
            raise ToolMediationError("Tool call function payload must be an object.")
        name = raw_function.get("name")
        if not isinstance(name, str) or not name:
            raise ToolMediationError("Tool call function name must be a non-empty string.")
        call_id = raw_call.get("id")
        if not isinstance(call_id, str) or not call_id:
            call_id = f"tool-call-{index}"
        calls.append(ToolCall(call_id=call_id, name=name, arguments=decode_tool_arguments(raw_function.get("arguments", "{}"), name)))
    return calls


def value_looks_like_raw_tool_call(value: Any) -> bool:
    if isinstance(value, dict):
        if "tool_calls" in value:
            return True
        if "arguments" in value and ("name" in value or "function" in value):
            return True
        return any(value_looks_like_raw_tool_call(item) for item in value.values())
    if isinstance(value, list):
        return any(value_looks_like_raw_tool_call(item) for item in value)
    return False


def content_looks_like_raw_tool_call(content: str) -> bool:
    stripped = content.strip()
    if re.search(r"<\s*/?\s*tool_call\b", stripped, re.IGNORECASE):
        return True
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return bool(re.search(r'"tool_calls"\s*:', stripped) and re.search(r'"arguments"\s*:', stripped))
    return value_looks_like_raw_tool_call(parsed)


def validate_final_response(message: dict[str, Any]) -> str:
    if detect_tool_calls(message):
        raise ToolMediationError("Final response still contains executable tool_calls.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ToolMediationError("Final response content must be a non-empty string.")
    if content_looks_like_raw_tool_call(content):
        raise ToolMediationError("Raw tool-call-shaped text is not a completed tool execution.")
    return content


def message_from_response(response: dict[str, Any]) -> dict[str, Any]:
    try:
        message = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ToolMediationError("Chat completion response must contain choices[0].message.") from exc
    if not isinstance(message, dict):
        raise ToolMediationError("Chat completion message must be an object.")
    return message


def normalize_repo_path(repo_root: Path, value: str) -> str:
    raw_path = Path(value)
    if raw_path.is_absolute():
        raise ToolMediationError(f"Tool path must be relative to the repo root: {value}")
    candidate = (repo_root / raw_path).resolve()
    try:
        relative_path = candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ToolMediationError(f"Tool path is outside repo root: {value}") from exc
    return relative_path.as_posix()


def validate_arguments(tool: dict[str, Any], arguments: dict[str, Any]) -> None:
    tool_id = tool["id"]
    args_schema = tool.get("args_schema", {})
    if not isinstance(args_schema, dict):
        raise ToolMediationError(f"Tool {tool_id} args_schema must be an object.")
    allowed_args = set(args_schema)
    extra_args = sorted(set(arguments) - allowed_args)
    if extra_args:
        raise ToolMediationError(f"Tool {tool_id} received unsupported arguments: {', '.join(extra_args)}")

    for name, arg_schema in args_schema.items():
        if not isinstance(arg_schema, dict):
            raise ToolMediationError(f"Tool {tool_id} has invalid schema for argument {name}.")
        if arg_schema.get("required") is True and name not in arguments:
            raise ToolMediationError(f"Tool {tool_id} is missing required argument: {name}")
        if name not in arguments:
            continue
        value = arguments[name]
        arg_type = arg_schema.get("type")
        if arg_type == "string" and not isinstance(value, str):
            raise ToolMediationError(f"Tool {tool_id} argument {name} must be a string.")
        if arg_type == "array":
            item_type = arg_schema.get("items", "string")
            if not isinstance(value, list):
                raise ToolMediationError(f"Tool {tool_id} argument {name} must be an array.")
            if item_type == "object":
                if not all(isinstance(item, dict) for item in value):
                    raise ToolMediationError(f"Tool {tool_id} argument {name} must be an array of objects.")
            elif not all(isinstance(item, str) for item in value):
                raise ToolMediationError(f"Tool {tool_id} argument {name} must be an array of strings.")
        if arg_type == "boolean" and not isinstance(value, bool):
            raise ToolMediationError(f"Tool {tool_id} argument {name} must be a boolean.")
        if arg_type == "integer" and not isinstance(value, int):
            raise ToolMediationError(f"Tool {tool_id} argument {name} must be an integer.")


class ToolMediator:
    """Generate schemas, execute allowed tools, and inject results."""

    def __init__(self, repo_root: Path, catalog: dict[str, Any], allowed_tool_ids: list[str] | set[str]):
        self.repo_root = Path(repo_root).resolve()
        self.catalog = catalog
        self.tools_by_id = catalog_tools_by_id(catalog)
        self.allowed_tool_ids = set(allowed_tool_ids)
        self.tool_schemas = generate_tool_schemas(catalog, self.allowed_tool_ids)

    def execute_tool_call(self, call: ToolCall) -> dict[str, Any]:
        if call.name not in self.allowed_tool_ids:
            raise ToolMediationError(f"Tool call is not allowed by the active role policy: {call.name}")
        tool = self.tools_by_id.get(call.name)
        if tool is None:
            raise ToolMediationError(f"Tool call is missing from the catalog: {call.name}")
        validate_arguments(tool, call.arguments)

        if call.name == "git_ls_files":
            return self._git_ls_files(call.arguments)
        if call.name == "git_grep":
            return self._git_grep(call.arguments)
        if call.name == "read_file":
            return self._read_file(call.arguments)
        if call.name == "scan_files":
            return self._scan_files(call.arguments)
        if call.name == "structure_index":
            return self._structure_index(call.arguments)
        if call.name == "codegraph_context":
            return self._codegraph_context(call.arguments)
        if call.name == "run_tests":
            return self._run_tests(call.arguments)
        raise ToolMediationError(f"Tool call has no executable mediator: {call.name}")

    def tool_result_message(self, call: ToolCall, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": call.call_id,
            "name": call.name,
            "content": json.dumps(result, ensure_ascii=True, sort_keys=True),
        }

    def run_tool_loop(
        self,
        messages: list[dict[str, Any]],
        create_chat_completion: ChatCompletionCallable,
        max_tool_rounds: int = 4,
    ) -> dict[str, Any]:
        conversation = [dict(message) for message in messages]
        tool_results: list[dict[str, Any]] = []

        for round_index in range(max_tool_rounds + 1):
            response = create_chat_completion(conversation, self.tool_schemas)
            assistant_message = message_from_response(response)
            calls = detect_tool_calls(assistant_message)
            if not calls:
                validate_final_response(assistant_message)
                conversation.append(assistant_message)
                return {
                    "message": assistant_message,
                    "messages": conversation,
                    "tool_results": tool_results,
                }
            if round_index >= max_tool_rounds:
                raise ToolMediationError("Maximum tool rounds exceeded before a final response.")

            conversation.append(assistant_message)
            for call in calls:
                result = self.execute_tool_call(call)
                tool_results.append({"tool_call_id": call.call_id, "name": call.name, "result": result})
                conversation.append(self.tool_result_message(call, result))

        raise ToolMediationError("Tool loop ended without a final response.")

    def _run_command(self, command: list[str], ok_returncodes: set[int] | None = None) -> dict[str, Any]:
        ok_codes = ok_returncodes or {0}
        result = subprocess.run(
            command,
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return {
            "ok": result.returncode in ok_codes,
            "returncode": result.returncode,
            "command": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def _git_ls_files(self, arguments: dict[str, Any]) -> dict[str, Any]:
        command = ["git", "ls-files"]
        pattern = arguments.get("pattern")
        if isinstance(pattern, str) and pattern:
            command.append(pattern)
        result = self._run_command(command)
        result["files"] = [line for line in result["stdout"].splitlines() if line]
        return result

    def _git_grep(self, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._run_command(["git", "grep", "-n", arguments["pattern"]], ok_returncodes={0, 1})
        result["matches"] = [line for line in result["stdout"].splitlines() if line]
        return result

    def _read_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        rel_path = normalize_repo_path(self.repo_root, arguments["path"])
        path = self.repo_root / rel_path
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ToolMediationError(f"Unable to read file {rel_path}: {exc}") from exc
        return {
            "ok": True,
            "path": rel_path,
            "bytes": path.stat().st_size,
            "content": content,
        }

    def _scan_files(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ignored_dirs = set(DEFAULT_IGNORED_SCAN_DIRS)
        ignored_dirs.update(arguments.get("ignored_dirs", []))
        files: list[str] = []
        for current_root, dirnames, filenames in os.walk(self.repo_root):
            dirnames[:] = [
                name
                for name in dirnames
                if name not in ignored_dirs and not name.endswith(".egg-info") and not name.endswith(".dist-info")
            ]
            current_path = Path(current_root)
            for filename in filenames:
                path = current_path / filename
                if path.is_symlink():
                    continue
                try:
                    rel_path = path.resolve().relative_to(self.repo_root)
                except (OSError, ValueError):
                    continue
                files.append(rel_path.as_posix())
        return {"ok": True, "ignored_dirs": sorted(ignored_dirs), "files": sorted(files)}

    def _structure_index(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from vllm_agent_gateway.structure_index.indexer import build_code_structure_index, build_index_slice

        paths = arguments.get("paths", [])
        max_records = arguments.get("max_records", 50)
        index = build_code_structure_index(target_root=self.repo_root, file_scope="tracked")
        index_slice = build_index_slice(
            index,
            paths=paths if paths else None,
            max_records=max_records if isinstance(max_records, int) else 50,
        )
        return {
            "ok": True,
            "summary": index.get("summary", {}),
            "selected_file_count": index.get("selected_file_count"),
            "slice": index_slice,
        }

    def _codegraph_context(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from vllm_agent_gateway.controllers.code_context.codegraph_adapter import (
            CodeGraphContextAdapterError,
            run_relationship_queries,
        )

        try:
            results, warnings = run_relationship_queries(
                self.repo_root,
                arguments["relationship_queries"],
                max_results=arguments.get("max_results", 25),
            )
        except CodeGraphContextAdapterError as exc:
            raise ToolMediationError(str(exc)) from exc
        return {"ok": True, "relationship_results": results, "warnings": warnings}

    def _run_tests(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._run_command([sys.executable, "-m", "pytest", *arguments.get("args", [])])
