"""AnythingLLM Desktop UI E2E validation helpers."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.anythingllm_answer_usefulness import (
    DEFAULT_CONTRACT_PATH,
    contract_entries_by_id,
    validate_response_text,
)
from vllm_agent_gateway.run_inspector import mnt_path_to_windows, resolved_existing_path


DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_REPORT_DIR = Path("runtime-state") / "anythingllm-ui"
DEFAULT_UI_PROMPT_CATALOG_PATH = Path("runtime") / "anythingllm_ui_prompt_cases.json"
DEFAULT_TARGET_ROOTS = (
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
)
DEFAULT_MARKERS = (
    "workflow_router.plan completed",
    "Result:",
    "Skill Selection:",
    "Summary:",
    "run_id:",
    "Artifacts:",
    "Run record:",
)
WATCHED_RELATIVE_PATHS = (
    "README.md",
    "agent.md",
    "configuration.py",
    "dashboard_server.py",
    "main.py",
    "business/lot_config.py",
    "core/orderbook.py",
    "core/stealth_order_manager.py",
    "database/order.py",
    "docs/agents/INVARIANTS.md",
    "tests/test_dashboard_handler.py",
    "tests/test_lot_tracking_integration.py",
    "tests/unit/test_order_id_and_followup_rules.py",
    "tests/unit/test_orderbook_v2.py",
)


class AnythingLLMUiE2EStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class UiPromptTargetRootMode(str, Enum):
    TARGET_ROOT = "target_root"
    NO_TARGET = "no_target"


@dataclass(frozen=True)
class AnythingLLMUiE2EConfig:
    config_root: Path
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS
    output_path: Path | None = None
    ui_dist_root: Path | None = None
    app_asar_path: Path | None = None
    extract_root: Path | None = None
    refresh_extract: bool = False
    npx_command: str | None = None
    browser_channel: str = ""
    timeout_seconds: int = 420
    static_port: int | None = None
    prompt_catalog_path: Path | None = DEFAULT_UI_PROMPT_CATALOG_PATH
    case_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class UiPromptCase:
    case_id: str
    name: str
    prompt_family: str
    required_markers: tuple[str, ...]
    rejected_markers: tuple[str, ...]
    ordered_markers: tuple[str, ...]
    prompt_template: str
    target_root_mode: UiPromptTargetRootMode = UiPromptTargetRootMode.TARGET_ROOT
    target_roots: tuple[str, ...] = ()
    transport_markers: tuple[str, ...] = DEFAULT_MARKERS
    source_baseline_entry_id: str | None = None
    source_prompt_case_id: str | None = None
    expected_workflow: str | None = None
    expected_route_status: str | None = None
    priority_backlog_id: str | None = None

    def prompt(self, target_root: str, tag: str) -> str:
        return self.prompt_template.format(target_root=target_root, tag=tag)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"anythingllm-ui-e2e-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_config_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())


def target_root_mode_from_value(value: object) -> UiPromptTargetRootMode:
    if not isinstance(value, str) or not value.strip():
        return UiPromptTargetRootMode.TARGET_ROOT
    try:
        return UiPromptTargetRootMode(value)
    except ValueError:
        return UiPromptTargetRootMode.TARGET_ROOT


def ui_prompt_case_from_entry(entry: dict[str, Any]) -> UiPromptCase:
    return UiPromptCase(
        case_id=str(entry["case_id"]),
        name=str(entry["name"]),
        prompt_family=str(entry["prompt_family"]),
        required_markers=string_tuple(entry.get("required_markers")),
        rejected_markers=string_tuple(entry.get("rejected_markers")),
        ordered_markers=string_tuple(entry.get("ordered_markers")),
        prompt_template=str(entry["prompt_template"]),
        target_root_mode=target_root_mode_from_value(entry.get("target_root_mode")),
        target_roots=string_tuple(entry.get("target_roots")),
        transport_markers=string_tuple(entry.get("transport_markers")) or DEFAULT_MARKERS,
        source_baseline_entry_id=entry.get("source_baseline_entry_id")
        if isinstance(entry.get("source_baseline_entry_id"), str)
        else None,
        source_prompt_case_id=entry.get("source_prompt_case_id")
        if isinstance(entry.get("source_prompt_case_id"), str)
        else None,
        expected_workflow=entry.get("expected_workflow") if isinstance(entry.get("expected_workflow"), str) else None,
        expected_route_status=entry.get("expected_route_status")
        if isinstance(entry.get("expected_route_status"), str)
        else None,
        priority_backlog_id=entry.get("priority_backlog_id") if isinstance(entry.get("priority_backlog_id"), str) else None,
    )


def case_id_map(path: Path) -> dict[str, dict[str, Any]]:
    payload = read_json_object(path)
    cases = payload.get("cases")
    if not isinstance(cases, list):
        return {}
    return {
        str(item["case_id"]): item
        for item in cases
        if isinstance(item, dict) and isinstance(item.get("case_id"), str) and item["case_id"]
    }


def validate_ui_prompt_catalog(catalog: dict[str, Any], *, config_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    if catalog.get("schema_version") != 1:
        errors.append("catalog.schema_version must be 1")
    if catalog.get("kind") != "anythingllm_ui_prompt_catalog":
        errors.append("catalog.kind must be anythingllm_ui_prompt_catalog")
    if catalog.get("priority_backlog_id") != "P0-BB-011":
        errors.append("catalog.priority_backlog_id must be P0-BB-011")
    cases = catalog.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("catalog.cases must be a non-empty list")
        return errors

    seen: set[str] = set()
    stable_families: set[str] = set()
    stable_family_roots: dict[str, set[str]] = {}
    baseline_entries: dict[str, dict[str, Any]] = {}
    source_cases_by_entry_id: dict[str, dict[str, dict[str, Any]]] = {}
    if config_root is not None:
        baseline_path = config_root / "runtime" / "baseline_corpus.json"
        if not baseline_path.is_file():
            errors.append("runtime/baseline_corpus.json is required for catalog validation")
        else:
            baseline = read_json_object(baseline_path)
            baseline_entries = {
                str(entry["entry_id"]): entry
                for entry in baseline.get("entries", [])
                if isinstance(entry, dict)
                and entry.get("status") == "stable"
                and isinstance(entry.get("entry_id"), str)
            }
    for index, item in enumerate(cases):
        prefix = f"catalog.cases[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            errors.append(f"{prefix}.case_id is required")
        elif case_id in seen:
            errors.append(f"{prefix}.case_id duplicates {case_id}")
        else:
            seen.add(case_id)
        for key in ("name", "prompt_family", "prompt_template"):
            if not isinstance(item.get(key), str) or not str(item.get(key)).strip():
                errors.append(f"{prefix}.{key} is required")
        template = item.get("prompt_template") if isinstance(item.get("prompt_template"), str) else ""
        raw_mode = item.get("target_root_mode", UiPromptTargetRootMode.TARGET_ROOT.value)
        if not isinstance(raw_mode, str) or raw_mode not in {mode.value for mode in UiPromptTargetRootMode}:
            errors.append(f"{prefix}.target_root_mode must be target_root or no_target")
            target_root_mode = UiPromptTargetRootMode.TARGET_ROOT
        else:
            target_root_mode = UiPromptTargetRootMode(raw_mode)
        if "{tag}" not in template:
            errors.append(f"{prefix}.prompt_template must contain {{tag}}")
        lower_template = template.lower()
        if "tracking tag" not in template.lower():
            errors.append(f"{prefix}.prompt_template must include the tracking tag text")
        if not string_tuple(item.get("required_markers")):
            errors.append(f"{prefix}.required_markers is required")
        rejected = item.get("rejected_markers")
        if rejected is not None and not isinstance(rejected, list):
            errors.append(f"{prefix}.rejected_markers must be a list when present")
        ordered = item.get("ordered_markers")
        if ordered is not None and not string_tuple(ordered):
            errors.append(f"{prefix}.ordered_markers must be a non-empty string list when present")
        transport_markers = string_tuple(item.get("transport_markers"))
        if item.get("transport_markers") is not None and not transport_markers:
            errors.append(f"{prefix}.transport_markers must be a non-empty string list when present")
        target_roots = string_tuple(item.get("target_roots"))
        if target_root_mode == UiPromptTargetRootMode.TARGET_ROOT:
            if "{target_root}" not in template:
                errors.append(f"{prefix}.prompt_template must contain {{target_root}}")
            if "read only" not in lower_template and "do not edit files" not in lower_template:
                errors.append(f"{prefix}.prompt_template must declare read-only intent")
            if not target_roots:
                errors.append(f"{prefix}.target_roots is required")
            unsupported_roots = sorted(set(target_roots) - set(DEFAULT_TARGET_ROOTS))
            if unsupported_roots:
                errors.append(
                    f"{prefix}.target_roots contains unsupported Phase 126 root(s): {', '.join(unsupported_roots)}"
                )
        else:
            if "{target_root}" in template:
                errors.append(f"{prefix}.prompt_template must not contain {{target_root}} in no_target mode")
            if target_roots:
                errors.append(f"{prefix}.target_roots must be empty in no_target mode")
            if not transport_markers:
                errors.append(f"{prefix}.transport_markers is required in no_target mode")
            elif "Artifacts:" in transport_markers:
                errors.append(f"{prefix}.transport_markers must not require Artifacts: in no_target mode")
            if not isinstance(item.get("expected_route_status"), str) or not item["expected_route_status"].strip():
                errors.append(f"{prefix}.expected_route_status is required in no_target mode")
            expected_workflow = item.get("expected_workflow")
            if expected_workflow not in {None, "none"}:
                errors.append(f"{prefix}.expected_workflow must be none in no_target mode")
            if isinstance(item.get("source_baseline_entry_id"), str) and item["source_baseline_entry_id"].strip():
                errors.append(f"{prefix}.source_baseline_entry_id is not supported in no_target mode")
        source_entry = item.get("source_baseline_entry_id")
        if (
            target_root_mode == UiPromptTargetRootMode.TARGET_ROOT
            and isinstance(source_entry, str)
            and source_entry.strip()
        ):
            stable_families.add(source_entry)
            stable_family_roots.setdefault(source_entry, set()).update(target_roots)
            if not isinstance(item.get("source_prompt_case_id"), str) or not item["source_prompt_case_id"].strip():
                errors.append(f"{prefix}.source_prompt_case_id is required for stable corpus cases")
            if not isinstance(item.get("expected_workflow"), str) or not item["expected_workflow"].strip():
                errors.append(f"{prefix}.expected_workflow is required for stable corpus cases")
            if item.get("priority_backlog_id") not in {"P0-BB-001", "P0-BB-002", "P0-BB-003", "P0-BB-004"}:
                errors.append(f"{prefix}.priority_backlog_id must reference a stable Priority 0 backlog item")
            if config_root is not None:
                baseline_entry = baseline_entries.get(source_entry)
                if not isinstance(baseline_entry, dict):
                    errors.append(f"{prefix}.source_baseline_entry_id is not a stable baseline corpus entry")
                else:
                    prompt_cases = baseline_entry.get("prompt_cases") if isinstance(baseline_entry.get("prompt_cases"), dict) else {}
                    prompt_cases_path = prompt_cases.get("path")
                    if not isinstance(prompt_cases_path, str) or not prompt_cases_path.strip():
                        errors.append(f"{prefix}.source baseline entry is missing prompt_cases.path")
                    else:
                        source_cases = source_cases_by_entry_id.get(source_entry)
                        if source_cases is None:
                            source_cases = case_id_map(resolve_config_path(config_root, prompt_cases_path))
                            source_cases_by_entry_id[source_entry] = source_cases
                        source_prompt_id = item.get("source_prompt_case_id")
                        source_case = source_cases.get(str(source_prompt_id))
                        if not isinstance(source_case, dict):
                            errors.append(f"{prefix}.source_prompt_case_id is not present in governed prompt cases")
                        else:
                            source_root = source_case.get("target_root")
                            if source_root not in target_roots:
                                errors.append(f"{prefix}.target_roots must include the governed source prompt target_root")
                            source_prompt = source_case.get("prompt")
                            if isinstance(source_prompt, str):
                                normalized = source_prompt.replace(str(source_root), "{target_root}")
                                expected_template = f"{normalized} Tracking tag: {{tag}}"
                                if item.get("prompt_template") != expected_template and item.get("ui_prompt_variant_approved") is not True:
                                    errors.append(
                                        f"{prefix}.prompt_template drift requires ui_prompt_variant_approved=true"
                                    )

    required_stable_families = {
        "phase116_code_quality",
        "phase117_defect_diagnosis",
        "phase118_engineering_judgment",
        "phase119_delivery_mentorship",
    }
    missing_families = sorted(required_stable_families - stable_families)
    if missing_families:
        errors.append("catalog missing stable UI family coverage: " + ", ".join(missing_families))
    for family in required_stable_families:
        roots = stable_family_roots.get(family, set())
        missing_roots = sorted(set(DEFAULT_TARGET_ROOTS) - roots)
        if missing_roots:
            errors.append(f"catalog stable family {family} missing frozen root coverage: {', '.join(missing_roots)}")
    return errors


def load_ui_prompt_cases(
    config_root: Path,
    prompt_catalog_path: Path | None = DEFAULT_UI_PROMPT_CATALOG_PATH,
    *,
    case_ids: tuple[str, ...] = (),
) -> tuple[UiPromptCase, ...]:
    catalog_path = resolve_config_path(config_root, prompt_catalog_path or DEFAULT_UI_PROMPT_CATALOG_PATH)
    catalog = read_json_object(catalog_path)
    errors = validate_ui_prompt_catalog(catalog, config_root=config_root)
    if errors:
        raise RuntimeError("invalid AnythingLLM UI prompt catalog: " + "; ".join(errors))
    all_cases = tuple(ui_prompt_case_from_entry(item) for item in catalog["cases"] if isinstance(item, dict))
    if not case_ids:
        return all_cases
    requested = set(case_ids)
    selected = tuple(case for case in all_cases if case.case_id in requested)
    missing = sorted(requested - {case.case_id for case in selected})
    if missing:
        raise RuntimeError("unknown AnythingLLM UI case id(s): " + ", ".join(missing))
    return selected


UI_PROMPT_CASES = load_ui_prompt_cases(Path(__file__).resolve().parents[1])


def target_roots_for_prompt_cases(cases: tuple[UiPromptCase, ...], fallback_roots: tuple[str, ...]) -> tuple[str, ...]:
    roots: set[str] = set()
    for case in cases:
        if case.target_root_mode == UiPromptTargetRootMode.NO_TARGET:
            roots.update(fallback_roots)
        else:
            roots.update(case.target_roots or fallback_roots)
    return tuple(sorted(roots or set(fallback_roots)))


def execution_target_roots_for_prompt_case(case: UiPromptCase, fallback_roots: tuple[str, ...]) -> tuple[str, ...]:
    if case.target_root_mode == UiPromptTargetRootMode.NO_TARGET:
        return ("",)
    return case.target_roots or fallback_roots


def json_request(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 30,
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                body = {"text": text}
            return response.status, body
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {"text": text}
        return exc.code, body


def host_path(path_value: str) -> Path:
    existing = resolved_existing_path(path_value)
    if existing is not None:
        return existing
    converted = mnt_path_to_windows(path_value)
    if converted is not None:
        return converted
    return Path(path_value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def watched_hashes(target_root: str) -> dict[str, str]:
    root = host_path(target_root)
    hashes: dict[str, str] = {}
    for relative_path in WATCHED_RELATIVE_PATHS:
        path = root / relative_path
        if path.exists():
            hashes[relative_path] = sha256_file(path)
    if not hashes:
        raise RuntimeError(f"{target_root} did not contain watched validation files on host path {root}")
    return hashes


def git_status(target_root: str) -> str | None:
    root = host_path(target_root)
    if not (root / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def fixture_state(target_roots: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {
        target_root: {
            "host_path": str(host_path(target_root)),
            "hashes": watched_hashes(target_root),
            "git_status": git_status(target_root),
        }
        for target_root in sorted(set(target_roots))
    }


def workspace_object_from_body(body: dict[str, Any]) -> dict[str, Any]:
    workspace = body.get("workspace")
    if isinstance(workspace, dict):
        return workspace
    if isinstance(workspace, list):
        for item in workspace:
            if isinstance(item, dict):
                return item
    return {}


def anythingllm_preflight(config: AnythingLLMUiE2EConfig, api_key: str) -> dict[str, Any]:
    api_root = config.anythingllm_api_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}
    ping_status, ping_body = json_request(f"{api_root}/api/ping", timeout_seconds=min(30, config.timeout_seconds))
    workspaces_status, workspaces_body = json_request(
        f"{api_root}/api/v1/workspaces",
        headers=headers,
        timeout_seconds=min(30, config.timeout_seconds),
    )
    workspace_detail_status, workspace_detail_body = json_request(
        f"{api_root}/api/workspace/{config.workspace}",
        headers=headers,
        timeout_seconds=min(30, config.timeout_seconds),
    )
    workspaces = workspaces_body.get("workspaces") if isinstance(workspaces_body, dict) else []
    slugs = [item.get("slug") for item in workspaces if isinstance(item, dict)]
    workspace_detail = workspace_object_from_body(workspace_detail_body if isinstance(workspace_detail_body, dict) else {})
    chat_mode = workspace_detail.get("chatMode") if isinstance(workspace_detail.get("chatMode"), str) else None
    errors: list[str] = []
    if ping_status != 200:
        errors.append("AnythingLLM /api/ping failed")
    if workspaces_status != 200:
        errors.append("AnythingLLM /api/v1/workspaces failed")
    if config.workspace not in slugs:
        errors.append(f"workspace {config.workspace!r} was not found")
    if workspace_detail_status != 200:
        errors.append("AnythingLLM browser workspace detail endpoint failed")
    if chat_mode != "chat":
        errors.append("workspace chatMode must be 'chat'; 'automatic' invokes AnythingLLM agent mode on /stream-chat")
    return {
        "status": AnythingLLMUiE2EStatus.PASSED.value
        if not errors
        else AnythingLLMUiE2EStatus.FAILED.value,
        "ping_status": ping_status,
        "workspace_status": workspaces_status,
        "workspace_detail_status": workspace_detail_status,
        "workspace": config.workspace,
        "workspace_found": config.workspace in slugs,
        "workspace_slugs": slugs,
        "chat_mode": chat_mode,
        "ping": ping_body,
        "errors": errors,
    }


def default_app_asar_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        username = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        candidates: list[Path] = []
        if username:
            candidates.append(Path("C:/Users") / username / "AppData/Local/Programs/AnythingLLM/resources/app.asar")
            candidates.append(Path("/mnt/c/Users") / username / "AppData/Local/Programs/AnythingLLM/resources/app.asar")
        candidates.extend(sorted(Path("/mnt/c/Users").glob("*/AppData/Local/Programs/AnythingLLM/resources/app.asar")))
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0] if candidates else Path("C:/Users") / username / "AppData/Local/Programs/AnythingLLM/resources/app.asar"
    return Path(local_app_data) / "Programs" / "AnythingLLM" / "resources" / "app.asar"


def find_npx_command(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    candidates = ("npx.cmd", "npx") if os.name == "nt" else ("npx",)
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError("npx was not found; install Node.js/npm or pass --npx-command")


def resolve_ui_dist_root(config: AnythingLLMUiE2EConfig) -> Path:
    if config.ui_dist_root is not None:
        dist_root = config.ui_dist_root
        if not (dist_root / "index.html").exists():
            raise RuntimeError(f"ui dist root does not contain index.html: {dist_root}")
        return dist_root

    extract_root = config.extract_root or (config.config_root / DEFAULT_REPORT_DIR / "asar-dist")
    dist_root = extract_root / "dist"
    if not config.refresh_extract and (dist_root / "index.html").exists():
        return dist_root

    app_asar = config.app_asar_path or default_app_asar_path()
    if not app_asar.exists():
        raise RuntimeError(f"AnythingLLM app.asar was not found: {app_asar}")
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if os.name == "nt":
        env["NODE_OPTIONS"] = "--use-system-ca"
    command = [find_npx_command(config.npx_command), "--yes", "asar", "extract", str(app_asar), str(extract_root)]
    result = subprocess.run(command, check=False, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            "failed to extract AnythingLLM app.asar: "
            + json.dumps({"command": command, "stdout": result.stdout[-1000:], "stderr": result.stderr[-1000:]})
        )
    if not (dist_root / "index.html").exists():
        raise RuntimeError(f"extracted AnythingLLM UI did not contain dist/index.html under {extract_root}")
    return dist_root


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_http(url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            status, _body = json_request(url, timeout_seconds=2)
            if status == 200:
                return
        except Exception as exc:  # pragma: no cover - diagnostic detail only
            last_error = exc
        time.sleep(1)
    raise RuntimeError(f"static UI server did not become ready at {url}: {last_error}")


def start_static_server(dist_root: Path, *, port: int) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["NODE_OPTIONS"] = "--use-system-ca"
    command = [
        sys.executable,
        "-m",
        "http.server",
        str(port),
        "--bind",
        "127.0.0.1",
        "--directory",
        str(dist_root),
        "--protocol",
        "HTTP/1.1",
    ]
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def api_base_for_ui(anythingllm_api_base_url: str) -> str:
    return anythingllm_api_base_url.rstrip("/") + "/api"


def build_electron_require_shim(api_base_url: str) -> str:
    api_base = json.dumps(api_base_for_ui(api_base_url))
    return f"""
(() => {{
  const API_BASE = {api_base};
  const listeners = new Map();
  const emit = (channel, payload) => setTimeout(() => {{
    (listeners.get(channel) || []).forEach((handler) => handler({{}}, payload));
  }}, 0);
  const ipcRenderer = {{
    on(channel, handler) {{
      const list = listeners.get(channel) || [];
      list.push(handler);
      listeners.set(channel, list);
      if (channel === "backend-server-online") {{
        emit(channel, {{
          API_BASE,
          APP_VERSION: "phase71-browser-e2e",
          APP_PLATFORM: "browser",
          APP_ARCH: "x64"
        }});
      }}
      return this;
    }},
    once(channel, handler) {{
      const wrap = (...args) => {{
        this.removeListener(channel, wrap);
        handler(...args);
      }};
      return this.on(channel, wrap);
    }},
    off(channel, handler) {{ return this.removeListener(channel, handler); }},
    removeListener(channel, handler) {{
      const list = listeners.get(channel) || [];
      listeners.set(channel, list.filter((item) => item !== handler));
      return this;
    }},
    removeAllListeners(channel) {{
      if (channel) listeners.delete(channel); else listeners.clear();
      return this;
    }},
    send() {{ return undefined; }},
    sendSync(channel) {{
      if (channel === "electron-store-get-data") {{
        return {{ defaultCwd: ".", appVersion: "phase71-browser-e2e" }};
      }}
      return null;
    }},
    invoke() {{ return Promise.resolve(null); }},
    emit(channel, ...args) {{
      (listeners.get(channel) || []).forEach((handler) => handler({{}}, ...args));
      return true;
    }},
    addListener(channel, handler) {{ return this.on(channel, handler); }},
    eventNames() {{ return Array.from(listeners.keys()); }},
    listenerCount(channel) {{ return (listeners.get(channel) || []).length; }},
    listeners(channel) {{ return listeners.get(channel) || []; }},
    getMaxListeners() {{ return 100; }},
    setMaxListeners() {{ return this; }},
    prependListener(channel, handler) {{ return this.on(channel, handler); }},
    prependOnceListener(channel, handler) {{ return this.once(channel, handler); }},
    rawListeners(channel) {{ return listeners.get(channel) || []; }},
    postMessage() {{}},
    sendTo() {{}},
    sendToHost() {{}}
  }};
  const electron = {{
    ipcRenderer,
    webFrame: {{ setZoomFactor() {{}} }},
    shell: {{ openExternal() {{}} }},
    clipboard: {{}},
    contextBridge: {{}},
    crashReporter: {{}},
    nativeImage: {{}},
    app: {{}},
    nativeTheme: {{}},
    screen: {{}},
    session: {{}},
    dialog: {{}}
  }};
  window.require = (name) => name === "electron" ? electron : {{}};
}})();
"""


def build_auth_init_script(api_key: str) -> str:
    token = json.dumps(api_key)
    return f"""
(() => {{
  localStorage.setItem("anythingllm_authToken", {token} || "x");
  localStorage.setItem("anythingllm_authTimestamp", String(Date.now()));
  localStorage.setItem("anythingllm_user", JSON.stringify({{ id: 1, username: "phase71-e2e" }}));
}})();
"""


def tracking_tag(target_root: str) -> str:
    digest = hashlib.sha1(f"{target_root}-{time.time_ns()}".encode("utf-8")).hexdigest()[:12]
    return f"phase71-ui-e2e-{digest}"


def prompt_for_target(target_root: str, tag: str) -> str:
    return UI_PROMPT_CASES[0].prompt(target_root, tag)


def segment_after_new_tag(text: str, tag: str, minimum_index: int) -> str:
    start_at = max(0, minimum_index - 1000)
    index = text.find(tag, start_at)
    if index < 0:
        return ""
    return text[index + len(tag) :]


def marker_hits(text: str, markers: tuple[str, ...] = DEFAULT_MARKERS) -> dict[str, bool]:
    return {marker: marker in text for marker in markers}


def ui_case_passed(case: dict[str, Any], markers: tuple[str, ...] = DEFAULT_MARKERS) -> bool:
    hits = case.get("marker_hits_after_tag")
    if not isinstance(hits, dict):
        return False
    case_markers = string_tuple(case.get("transport_markers")) or markers
    if not all(bool(hits.get(marker)) for marker in case_markers):
        return False
    semantic_hits = case.get("semantic_marker_hits_after_tag")
    if isinstance(semantic_hits, dict) and not all(bool(value) for value in semantic_hits.values()):
        return False
    rejected_hits = case.get("rejected_marker_hits_after_tag")
    if isinstance(rejected_hits, dict) and any(bool(value) for value in rejected_hits.values()):
        return False
    ordered_errors = case.get("ordered_marker_errors")
    if isinstance(ordered_errors, list) and ordered_errors:
        return False
    usefulness = case.get("answer_usefulness") if isinstance(case.get("answer_usefulness"), dict) else {}
    if usefulness and usefulness.get("usefulness_status") not in {AnythingLLMUiE2EStatus.PASSED.value, "not_applicable"}:
        return False
    screenshots = case.get("screenshots") if isinstance(case.get("screenshots"), dict) else {}
    if screenshots and screenshots.get("status") != AnythingLLMUiE2EStatus.PASSED.value:
        return False
    if case.get("parsed_run_id") in {None, ""}:
        return False
    return bool(case.get("stream_chat_seen"))


def semantic_status_for_segment(segment: str, case: UiPromptCase) -> dict[str, Any]:
    required_hits = marker_hits(segment, case.required_markers)
    rejected_hits = marker_hits(segment, case.rejected_markers)
    missing_required = [marker for marker, present in required_hits.items() if not present]
    rejected_present = [marker for marker, present in rejected_hits.items() if present]
    ordered_marker_errors: list[str] = []
    previous_index = -1
    for marker in case.ordered_markers:
        index = segment.find(marker, previous_index + 1)
        if index < 0:
            ordered_marker_errors.append(f"ordered marker {marker!r} missing after index {previous_index}")
            break
        previous_index = index
    return {
        "semantic_status": AnythingLLMUiE2EStatus.PASSED.value
        if not missing_required and not rejected_present and not ordered_marker_errors
        else AnythingLLMUiE2EStatus.FAILED.value,
        "required_markers": list(case.required_markers),
        "semantic_marker_hits_after_tag": required_hits,
        "missing_required_markers": missing_required,
        "rejected_markers": list(case.rejected_markers),
        "rejected_marker_hits_after_tag": rejected_hits,
        "rejected_markers_present": rejected_present,
        "ordered_markers": list(case.ordered_markers),
        "ordered_marker_errors": ordered_marker_errors,
    }


def run_id_from_segment(segment: str) -> str | None:
    match = re.search(r"\brun_id:\s*([A-Za-z0-9_.:-]+)", segment)
    return match.group(1) if match else None


def usefulness_status_for_segment(
    segment: str,
    case: UiPromptCase,
    answer_usefulness_contract: dict[str, Any],
) -> dict[str, Any]:
    if not case.source_baseline_entry_id:
        return {
            "usefulness_status": "not_applicable",
            "source_baseline_entry_id": None,
            "errors": [],
        }
    entry_contracts = contract_entries_by_id(answer_usefulness_contract)
    entry_contract = entry_contracts.get(case.source_baseline_entry_id)
    if not isinstance(entry_contract, dict):
        return {
            "usefulness_status": AnythingLLMUiE2EStatus.FAILED.value,
            "source_baseline_entry_id": case.source_baseline_entry_id,
            "errors": [f"missing answer-usefulness contract entry {case.source_baseline_entry_id}"],
        }
    errors = validate_response_text(
        segment,
        contract=answer_usefulness_contract,
        entry_contract=entry_contract,
        prefix=f"ui.case[{case.case_id}]",
    )
    return {
        "usefulness_status": AnythingLLMUiE2EStatus.PASSED.value
        if not errors
        else AnythingLLMUiE2EStatus.FAILED.value,
        "source_baseline_entry_id": case.source_baseline_entry_id,
        "errors": errors,
    }


def screenshot_status(*paths: Path) -> dict[str, Any]:
    files = []
    for path in paths:
        files.append(
            {
                "path": str(path.resolve()),
                "exists": path.is_file(),
                "size_bytes": path.stat().st_size if path.is_file() else 0,
            }
        )
    return {
        "status": AnythingLLMUiE2EStatus.PASSED.value
        if all(item["exists"] and item["size_bytes"] > 0 for item in files)
        else AnythingLLMUiE2EStatus.FAILED.value,
        "files": files,
    }


def non_ignored_request_failures(failures: list[dict[str, str]]) -> list[dict[str, str]]:
    ignored_suffixes = ("/api/system/logo?theme=system",)
    return [item for item in failures if not any(item.get("url", "").endswith(suffix) for suffix in ignored_suffixes)]


def ignored_request_failures(failures: list[dict[str, str]]) -> list[dict[str, str]]:
    ignored_suffixes = ("/api/system/logo?theme=system",)
    return [item for item in failures if any(item.get("url", "").endswith(suffix) for suffix in ignored_suffixes)]


def body_text(page: Any) -> str:
    return page.evaluate("document.body ? document.body.innerText : ''") or ""


def is_workspace_stream_chat_url(url: str, workspace: str) -> bool:
    return (
        f"/api/workspace/{workspace}/stream-chat" in url
        or f"/api/workspace/{workspace}/thread/" in url
        and url.endswith("/stream-chat")
    )


def request_failure_text(request: Any) -> str:
    try:
        failure = request.failure
        if callable(failure):
            failure = failure()
        if isinstance(failure, dict):
            return str(failure.get("errorText", ""))
        return str(failure)
    except Exception as exc:  # pragma: no cover - diagnostic detail only
        return f"failure-capture-error:{exc}"


def request_post_data_text(request: Any) -> str:
    try:
        data = request.post_data
        if callable(data):
            data = data()
        return str(data or "")[:4000]
    except Exception as exc:  # pragma: no cover - diagnostic detail only
        return f"post-data-capture-error:{exc}"


def run_browser_case(
    *,
    page: Any,
    workspace: str,
    target_root: str,
    case: UiPromptCase,
    tag: str,
    static_origin: str,
    screenshot_dir: Path,
    timeout_seconds: int,
    answer_usefulness_contract: dict[str, Any],
) -> dict[str, Any]:
    prompt = case.prompt(target_root, tag)
    ui_url = f"{static_origin}/#/workspace/{workspace}"
    page.goto(ui_url, wait_until="load", timeout=60_000)
    page.wait_for_selector("textarea", timeout=60_000)
    initial_text = body_text(page)
    before_screenshot = screenshot_dir / f"{tag}-before.png"
    after_screenshot = screenshot_dir / f"{tag}-after.png"
    page.screenshot(path=str(before_screenshot), full_page=True)

    textarea = page.locator("textarea").first
    textarea.fill(prompt)
    response_start_index = len(page.context._phase71_responses)  # type: ignore[attr-defined]
    textarea.press("Enter")
    time.sleep(2)
    if tag not in body_text(page)[len(initial_text) :]:
        textarea.fill(prompt)
        textarea.press("Control+Enter")
        time.sleep(2)

    deadline = time.time() + timeout_seconds
    snapshots: list[dict[str, Any]] = []
    latest_segment = ""
    latest_hits = marker_hits("", case.transport_markers)
    latest_semantic_status = semantic_status_for_segment("", case)
    latest_usefulness_status = usefulness_status_for_segment("", case, answer_usefulness_contract)
    while time.time() < deadline:
        text = body_text(page)
        latest_segment = segment_after_new_tag(text, tag, len(initial_text))
        latest_hits = marker_hits(latest_segment, case.transport_markers)
        latest_semantic_status = semantic_status_for_segment(latest_segment, case)
        latest_usefulness_status = usefulness_status_for_segment(latest_segment, case, answer_usefulness_contract)
        snapshots.append(
            {
                "elapsed_seconds": int(timeout_seconds - max(0, deadline - time.time())),
                "segment_length": len(latest_segment),
                "marker_hits_after_tag": latest_hits,
                "semantic_marker_hits_after_tag": latest_semantic_status["semantic_marker_hits_after_tag"],
                "missing_required_markers": latest_semantic_status["missing_required_markers"],
                "rejected_markers_present": latest_semantic_status["rejected_markers_present"],
                "ordered_marker_errors": latest_semantic_status["ordered_marker_errors"],
                "usefulness_status": latest_usefulness_status["usefulness_status"],
                "usefulness_error_count": len(latest_usefulness_status["errors"]),
                "segment_tail": latest_segment[-1200:],
            }
        )
        responses = page.context._phase71_responses[response_start_index:]  # type: ignore[attr-defined]
        stream_chat_seen = any(
            is_workspace_stream_chat_url(str(item.get("url", "")), workspace)
            and int(item.get("status", 0)) == 200
            for item in responses
        )
        if (
            all(latest_hits.values())
            and latest_semantic_status["semantic_status"] == AnythingLLMUiE2EStatus.PASSED.value
            and latest_usefulness_status["usefulness_status"]
            in {AnythingLLMUiE2EStatus.PASSED.value, "not_applicable"}
            and stream_chat_seen
        ):
            break
        time.sleep(5)

    page.screenshot(path=str(after_screenshot), full_page=True)
    responses = page.context._phase71_responses[response_start_index:]  # type: ignore[attr-defined]
    stream_chat_seen = any(
        is_workspace_stream_chat_url(str(item.get("url", "")), workspace)
        and int(item.get("status", 0)) == 200
        for item in responses
    )
    screenshots = screenshot_status(before_screenshot, after_screenshot)
    passed = (
        all(latest_hits.values())
        and latest_semantic_status["semantic_status"] == AnythingLLMUiE2EStatus.PASSED.value
        and latest_usefulness_status["usefulness_status"] in {AnythingLLMUiE2EStatus.PASSED.value, "not_applicable"}
        and stream_chat_seen
        and screenshots["status"] == AnythingLLMUiE2EStatus.PASSED.value
        and run_id_from_segment(latest_segment) is not None
    )
    result = {
        "case_id": case.case_id,
        "case_name": case.name,
        "prompt_family": case.prompt_family,
        "target_root_mode": case.target_root_mode.value,
        "source_baseline_entry_id": case.source_baseline_entry_id,
        "source_prompt_case_id": case.source_prompt_case_id,
        "expected_workflow": case.expected_workflow,
        "expected_route_status": case.expected_route_status,
        "priority_backlog_id": case.priority_backlog_id,
        "target_root": target_root if case.target_root_mode == UiPromptTargetRootMode.TARGET_ROOT else None,
        "tracking_tag": tag,
        "prompt": prompt,
        "transport_markers": list(case.transport_markers),
        "status": AnythingLLMUiE2EStatus.PASSED.value if passed else AnythingLLMUiE2EStatus.FAILED.value,
        "parsed_run_id": run_id_from_segment(latest_segment),
        "marker_hits_after_tag": latest_hits,
        **latest_semantic_status,
        "answer_usefulness": latest_usefulness_status,
        "stream_chat_seen": stream_chat_seen,
        "stream_chat_response_count": sum(1 for item in responses if "/stream-chat" in str(item.get("url", ""))),
        "segment_after_tag_tail": latest_segment[-8000:],
        "snapshots_tail": snapshots[-8:],
        "screenshots": screenshots,
        "before_screenshot": str(before_screenshot.resolve()),
        "after_screenshot": str(after_screenshot.resolve()),
    }
    return result


def run_browser_validation(
    *,
    config: AnythingLLMUiE2EConfig,
    dist_root: Path,
    api_key: str,
    port: int,
    screenshot_dir: Path,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError("Python Playwright is not installed; run `pip install playwright`") from exc

    screenshot_dir.mkdir(parents=True, exist_ok=True)
    static_origin = f"http://127.0.0.1:{port}"
    prompt_cases = load_ui_prompt_cases(
        config.config_root,
        config.prompt_catalog_path,
        case_ids=config.case_ids,
    )
    answer_usefulness_contract = read_json_object(resolve_config_path(config.config_root, DEFAULT_CONTRACT_PATH))
    cases: list[dict[str, Any]] = []
    console_messages: list[dict[str, str]] = []
    page_errors: list[str] = []
    request_failures: list[dict[str, str]] = []
    stream_chat_requests: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        launch_options: dict[str, Any] = {"headless": True}
        if config.browser_channel:
            launch_options["channel"] = config.browser_channel
        browser = playwright.chromium.launch(**launch_options)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context._phase71_responses = responses  # type: ignore[attr-defined]
        context.add_init_script(build_electron_require_shim(config.anythingllm_api_base_url))
        context.add_init_script(build_auth_init_script(api_key))
        page = context.new_page()
        page.on(
            "console",
            lambda message: console_messages.append({"type": message.type, "text": message.text[:1000]}),
        )
        page.on("pageerror", lambda exc: page_errors.append(str(exc)[:1200]))
        page.on(
            "requestfailed",
            lambda request: request_failures.append(
                {"url": request.url, "failure": request_failure_text(request)}
            ),
        )
        page.on(
            "request",
            lambda request: stream_chat_requests.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "post_data": request_post_data_text(request),
                }
            )
            if "/stream-chat" in request.url
            else None,
        )
        page.on(
            "response",
            lambda response: responses.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "content_type": response.headers.get("content-type", ""),
                }
            )
            if (str(port) in response.url or "3001" in response.url)
            else None,
        )

        for case in prompt_cases:
            target_roots = execution_target_roots_for_prompt_case(case, config.target_roots)
            for target_root in target_roots:
                tag_seed = f"{case.case_id}-{target_root or case.target_root_mode.value}"
                cases.append(
                    run_browser_case(
                        page=page,
                        workspace=config.workspace,
                        target_root=target_root,
                        case=case,
                        tag=tracking_tag(tag_seed),
                        static_origin=static_origin,
                        screenshot_dir=screenshot_dir,
                        timeout_seconds=config.timeout_seconds,
                        answer_usefulness_contract=answer_usefulness_contract,
                    )
                )
        browser.close()

    ignored_failures = ignored_request_failures(request_failures)
    unexpected_failures = non_ignored_request_failures(request_failures)
    return {
        "status": AnythingLLMUiE2EStatus.PASSED.value
        if all(ui_case_passed(case) for case in cases) and not page_errors and not unexpected_failures
        else AnythingLLMUiE2EStatus.FAILED.value,
        "static_origin": static_origin,
        "ui_dist_root": str(dist_root.resolve()),
        "prompt_case_count": len(prompt_cases),
        "prompt_case_ids": [case.case_id for case in prompt_cases],
        "cases": cases,
        "console_tail": console_messages[-20:],
        "page_errors": page_errors,
        "request_failures": request_failures,
        "ignored_request_failures": ignored_failures,
        "non_ignored_request_failures": unexpected_failures,
        "stream_chat_requests": stream_chat_requests,
        "response_count": len(responses),
        "responses_tail": responses[-30:],
    }


def run_anythingllm_ui_e2e(config: AnythingLLMUiE2EConfig) -> dict[str, Any]:
    output_path = config.output_path or default_report_path(config.config_root)
    prompt_catalog_path = resolve_config_path(
        config.config_root,
        config.prompt_catalog_path or DEFAULT_UI_PROMPT_CATALOG_PATH,
    )
    prompt_cases = load_ui_prompt_cases(
        config.config_root,
        config.prompt_catalog_path,
        case_ids=config.case_ids,
    )
    case_target_roots = target_roots_for_prompt_cases(prompt_cases, config.target_roots)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "anythingllm_ui_e2e_report",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": AnythingLLMUiE2EStatus.FAILED.value,
        "config": {
            "anythingllm_api_base_url": config.anythingllm_api_base_url,
            "workspace": config.workspace,
            "target_roots": list(config.target_roots),
            "case_target_roots": list(case_target_roots),
            "prompt_catalog_path": str(prompt_catalog_path),
            "prompt_catalog_sha256": sha256_file(prompt_catalog_path),
            "case_ids": list(config.case_ids),
            "resolved_case_ids": [case.case_id for case in prompt_cases],
            "browser_channel": config.browser_channel,
            "timeout_seconds": config.timeout_seconds,
        },
        "anythingllm_preflight": {},
        "fixture_state_before": {},
        "fixture_state_after": {},
        "ui": {},
        "errors": [],
    }
    server: subprocess.Popen[str] | None = None
    try:
        api_key = os.environ.get(config.api_key_env)
        if not api_key:
            raise RuntimeError(f"{config.api_key_env} is required for AnythingLLM UI E2E")
        report["fixture_state_before"] = fixture_state(case_target_roots)
        report["anythingllm_preflight"] = anythingllm_preflight(config, api_key)
        if report["anythingllm_preflight"].get("status") != AnythingLLMUiE2EStatus.PASSED.value:
            raise RuntimeError("AnythingLLM preflight failed")

        dist_root = resolve_ui_dist_root(config)
        port = config.static_port or free_port()
        server = start_static_server(dist_root, port=port)
        wait_for_http(f"http://127.0.0.1:{port}/", timeout_seconds=30)

        mimetypes.add_type("application/javascript", ".js")
        screenshot_dir = output_path.parent / output_path.stem
        report["ui"] = run_browser_validation(
            config=config,
            dist_root=dist_root,
            api_key=api_key,
            port=port,
            screenshot_dir=screenshot_dir,
        )
        report["fixture_state_after"] = fixture_state(case_target_roots)
        fixture_unchanged = report["fixture_state_before"] == report["fixture_state_after"]
        report["fixture_unchanged"] = fixture_unchanged
        if not fixture_unchanged:
            report["errors"].append("protected fixture state changed")
        if report["ui"].get("status") != AnythingLLMUiE2EStatus.PASSED.value:
            report["errors"].append("AnythingLLM browser UI validation failed")
        report["status"] = (
            AnythingLLMUiE2EStatus.PASSED.value
            if not report["errors"] and fixture_unchanged
            else AnythingLLMUiE2EStatus.FAILED.value
        )
    except Exception as exc:
        report["errors"].append(str(exc))
        report["status"] = AnythingLLMUiE2EStatus.FAILED.value
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        report["report_path"] = str(output_path.resolve())
        write_json(output_path, report)
    return report
