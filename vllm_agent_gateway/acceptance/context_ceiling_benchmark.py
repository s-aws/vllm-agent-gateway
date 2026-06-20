"""Raw local-model context ceiling benchmark for M7."""

from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.baseline_corpus import (
    object_list,
    read_json_object,
    resolve_path,
    sha256_file,
    string_list,
    write_json,
)


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "context_ceiling_benchmark_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "context-ceiling-benchmark"
REQUIRED_CONTEXT_CLASS_IDS = ["ctx-32k", "ctx-64k", "ctx-128k", "ctx-256k"]
REQUIRED_BOUNDARIES = {
    "measures_raw_prompt_classes_only",
    "does_not_claim_raw_500k_prompt_support",
    "does_not_change_supported_500k_project_usability_path",
    "does_not_mutate_runtime_baseline_corpus",
    "does_not_promote_eig_candidates",
}


class ContextCeilingBenchmarkStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class ContextCeilingBenchmarkConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    run_live: bool = True
    model_base_url: str | None = None
    timeout_seconds: int | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"context-ceiling-benchmark-{utc_timestamp()}.json"


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"policy.schema_version must be {SCHEMA_VERSION}")
    if policy.get("kind") != "context_ceiling_benchmark_policy":
        errors.append("policy.kind must be context_ceiling_benchmark_policy")
    if policy.get("phase") != 318:
        errors.append("policy.phase must be 318")
    if policy.get("priority_backlog_id") != "P0-M7-318":
        errors.append("policy.priority_backlog_id must be P0-M7-318")
    if set(string_list(policy.get("required_claim_boundaries"))) != REQUIRED_BOUNDARIES:
        errors.append("policy.required_claim_boundaries must match M7 benchmark boundaries")
    model = policy.get("model") if isinstance(policy.get("model"), dict) else {}
    if not isinstance(model.get("base_url"), str) or not model["base_url"].startswith("http://"):
        errors.append("model.base_url must be a local http URL")
    if not isinstance(model.get("expected_model"), str) or not model["expected_model"].strip():
        errors.append("model.expected_model is required")
    benchmark = policy.get("benchmark_policy") if isinstance(policy.get("benchmark_policy"), dict) else {}
    if benchmark.get("tokenizer_required") is not True:
        errors.append("benchmark_policy.tokenizer_required must be true")
    if benchmark.get("hardware_memory_snapshot_required") is not True:
        errors.append("benchmark_policy.hardware_memory_snapshot_required must be true")
    if benchmark.get("raw_500k_prompt_support_claim_allowed") is not False:
        errors.append("benchmark_policy.raw_500k_prompt_support_claim_allowed must be false")
    if not isinstance(benchmark.get("answer_minimum_score"), int) or benchmark["answer_minimum_score"] < 1:
        errors.append("benchmark_policy.answer_minimum_score must be a positive integer")
    if not isinstance(benchmark.get("max_model_len_required"), int) or benchmark["max_model_len_required"] < 262144:
        errors.append("benchmark_policy.max_model_len_required must be at least 262144")
    if not isinstance(benchmark.get("chat_overhead_token_allowance"), int) or benchmark["chat_overhead_token_allowance"] < 256:
        errors.append("benchmark_policy.chat_overhead_token_allowance must be at least 256")

    context_classes = object_list(policy.get("context_classes"))
    if [str(item.get("id")) for item in context_classes] != REQUIRED_CONTEXT_CLASS_IDS:
        errors.append("context_classes must be ordered ctx-32k, ctx-64k, ctx-128k, ctx-256k")
    expected_targets = {
        "ctx-32k": 32768,
        "ctx-64k": 65536,
        "ctx-128k": 131072,
        "ctx-256k": 262144,
    }
    for item in context_classes:
        class_id = str(item.get("id"))
        if item.get("target_context_tokens") != expected_targets.get(class_id):
            errors.append(f"{class_id}.target_context_tokens must be {expected_targets.get(class_id)}")
        for key in ("minimum_prompt_tokens", "max_output_tokens", "timeout_seconds"):
            if not isinstance(item.get(key), int) or item[key] < 1:
                errors.append(f"{class_id}.{key} must be a positive integer")
        if isinstance(item.get("minimum_prompt_tokens"), int) and isinstance(item.get("target_context_tokens"), int):
            if item["minimum_prompt_tokens"] >= item["target_context_tokens"]:
                errors.append(f"{class_id}.minimum_prompt_tokens must be below target_context_tokens")
    expected = policy.get("expected_answer") if isinstance(policy.get("expected_answer"), dict) else {}
    if len(string_list(expected.get("must_include_fragments"))) < 6:
        errors.append("expected_answer.must_include_fragments must contain at least six fragments")
    if not string_list(expected.get("forbidden_controlling_fragments")):
        errors.append("expected_answer.forbidden_controlling_fragments is required")
    return errors


def http_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout_seconds: int = 30,
) -> tuple[int, dict[str, Any] | str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - local benchmark URL from policy.
            body = response.read().decode("utf-8", errors="replace")
            try:
                return response.status, json.loads(body)
            except json.JSONDecodeError:
                return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def fetch_metrics_excerpt(base_url: str, *, timeout_seconds: int = 5, max_bytes: int = 262144) -> str:
    url = base_url.rstrip("/") + "/metrics"
    try:
        result = subprocess.run(
            ["curl", "-sS", "-m", str(timeout_seconds), url],
            capture_output=True,
            timeout=timeout_seconds + 2,
            check=False,
        )
        return result.stdout[:max_bytes].decode("utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""


def metric_values(metrics_text: str) -> dict[str, float]:
    selected: dict[str, float] = {}
    wanted = (
        "vllm:num_requests_running",
        "vllm:num_requests_waiting",
        "vllm:gpu_cache_usage_perc",
        "vllm:kv_cache_usage_perc",
        "process_resident_memory_bytes",
    )
    for raw_line in metrics_text.splitlines():
        if raw_line.startswith("#") or not raw_line.strip():
            continue
        for name in wanted:
            if raw_line.startswith(name):
                parts = raw_line.rsplit(" ", 1)
                try:
                    selected[name] = float(parts[-1])
                except ValueError:
                    pass
    return selected


def hardware_memory_snapshot() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used,memory.free",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    gpus = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            continue
        name, total, used, free = parts
        try:
            gpus.append(
                {
                    "name": name,
                    "memory_total_mib": int(total),
                    "memory_used_mib": int(used),
                    "memory_free_mib": int(free),
                }
            )
        except ValueError:
            continue
    return {
        "available": result.returncode == 0 and bool(gpus),
        "returncode": result.returncode,
        "gpus": gpus,
        "stderr": result.stderr.strip(),
    }


def tokenize(base_url: str, model: str, prompt: str, *, timeout_seconds: int = 120) -> dict[str, Any]:
    status, payload = http_json(
        base_url.rstrip("/") + "/tokenize",
        payload={"model": model, "prompt": prompt},
        timeout_seconds=timeout_seconds,
    )
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"tokenize failed with status {status}: {payload}")
    return payload


def prompt_template(case_id: str, filler: str) -> str:
    return f"""CONTEXT CEILING BENCHMARK {case_id}

Use only this supplied corpus. Return a concise answer with:
1. controlling decision id
2. emergency code
3. sentinel items in document order
4. obsolete decision id

SECTION 01 - EARLY FACTS
The project codename is Ceiling Meridian.
The obsolete decision id is SILVER-11.
The current controlling decision id is BRIDGE-42 and it supersedes SILVER-11.
Sentinel item: ALPHA-32.
The emergency code begins with LANTERN-

{filler}

SECTION 02 - LATE FACTS
Sentinel item: BRAVO-64.
Sentinel item: CHARLIE-128.
Sentinel item: DELTA-256.
The emergency code ends with 29.
Treat the emergency code as the single contiguous value LANTERN-29.
SILVER-11 is obsolete and must not control the final answer.
BRIDGE-42 is the controlling decision id.

QUESTION
Based only on the supplied corpus, answer the four requested fields.
"""


def build_prompt_for_context_class(
    *,
    base_url: str,
    model: str,
    case: dict[str, Any],
    chat_overhead: int,
) -> tuple[str, int, int]:
    filler_unit = (
        "neutral benchmark filler for context ceiling measurement. "
        "This line contains no controlling facts and should be ignored by synthesis. "
    )
    unit_tokens = int(tokenize(base_url, model, filler_unit)["count"])
    target_context_tokens = int(case["target_context_tokens"])
    max_output_tokens = int(case["max_output_tokens"])
    budget = target_context_tokens - max_output_tokens - chat_overhead
    minimum = int(case["minimum_prompt_tokens"])
    if budget <= minimum:
        raise RuntimeError(f"{case['id']} has no construction room below context budget")
    repeats = max(1, budget // max(1, unit_tokens))
    last_prompt = ""
    last_count = 0
    for _ in range(8):
        prompt = prompt_template(str(case["id"]), filler_unit * repeats)
        count = int(tokenize(base_url, model, prompt)["count"])
        last_prompt = prompt
        last_count = count
        if minimum <= count <= budget:
            return prompt, count, budget
        if count < minimum:
            deficit = minimum - count
            repeats += max(1, deficit // max(1, unit_tokens))
        else:
            excess = count - budget
            repeats -= max(1, excess // max(1, unit_tokens) + 1)
            repeats = max(1, repeats)
    if not (minimum <= last_count <= budget):
        raise RuntimeError(f"{case['id']} prompt token count {last_count} outside required range {minimum}-{budget}")
    return last_prompt, last_count, budget


def chat_completion(
    *,
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    timeout_seconds: int,
) -> tuple[int, dict[str, Any] | str, float]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "top_p": 1,
        "max_tokens": max_tokens,
    }
    started = time.monotonic()
    try:
        status, body = http_json(
            base_url.rstrip("/") + "/v1/chat/completions",
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
        return status, body, time.monotonic() - started
    except TimeoutError as exc:
        return 0, f"TimeoutError: {exc}", time.monotonic() - started
    except (OSError, urllib.error.URLError) as exc:
        return 0, f"{type(exc).__name__}: {exc}", time.monotonic() - started


def response_text(payload: dict[str, Any] | str) -> str:
    if not isinstance(payload, dict):
        return str(payload)
    choices = payload.get("choices") if isinstance(payload.get("choices"), list) else []
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
    content = message.get("content")
    return content if isinstance(content, str) else ""


def score_answer(text: str, expected: dict[str, Any]) -> dict[str, Any]:
    missing = [fragment for fragment in string_list(expected.get("must_include_fragments")) if fragment not in text]
    forbidden = [
        fragment
        for fragment in string_list(expected.get("forbidden_controlling_fragments"))
        if fragment.lower() in text.lower()
    ]
    score = max(0, 100 - (15 * len(missing)) - (30 * len(forbidden)))
    return {
        "score": score,
        "passed": score >= 85 and not forbidden,
        "missing_fragments": missing,
        "forbidden_fragments": forbidden,
    }


def failure_class(status: int, body: dict[str, Any] | str, score: dict[str, Any]) -> str:
    if status == 200 and score.get("passed") is True:
        return "passed"
    text = json.dumps(body) if isinstance(body, dict) else str(body)
    lower = text.lower()
    if status == 0 and "timeout" in lower:
        return "timeout"
    if "maximum context" in lower or "context length" in lower or "too long" in lower:
        return "context_length_rejected"
    if status and status >= 400:
        return "http_error"
    if status == 200:
        return "answer_quality_below_threshold"
    return "runtime_error"


def run_context_case(
    *,
    policy: dict[str, Any],
    base_url: str,
    model: str,
    case: dict[str, Any],
    timeout_override: int | None,
) -> dict[str, Any]:
    benchmark = policy.get("benchmark_policy") if isinstance(policy.get("benchmark_policy"), dict) else {}
    prompt, prompt_tokens, input_budget = build_prompt_for_context_class(
        base_url=base_url,
        model=model,
        case=case,
        chat_overhead=int(benchmark.get("chat_overhead_token_allowance", 1024)),
    )
    status, body, latency = chat_completion(
        base_url=base_url,
        model=model,
        prompt=prompt,
        max_tokens=int(case["max_output_tokens"]),
        timeout_seconds=timeout_override or int(case["timeout_seconds"]),
    )
    text = response_text(body)
    score = score_answer(text, policy.get("expected_answer") if isinstance(policy.get("expected_answer"), dict) else {})
    result_class = failure_class(status, body, score)
    return {
        "case_id": case.get("id"),
        "label": case.get("label"),
        "target_context_tokens": case.get("target_context_tokens"),
        "input_budget_tokens": input_budget,
        "prompt_tokens": prompt_tokens,
        "max_output_tokens": case.get("max_output_tokens"),
        "http_status": status,
        "latency_seconds": round(latency, 3),
        "answer_score": score["score"],
        "answer_passed": score["passed"],
        "failure_class": result_class,
        "passed": result_class == "passed",
        "missing_fragments": score["missing_fragments"],
        "forbidden_fragments": score["forbidden_fragments"],
        "text_sample": text[:1000],
        "error_sample": "" if status == 200 else (json.dumps(body) if isinstance(body, dict) else str(body))[:1000],
    }


def model_info(base_url: str, expected_model: str, *, timeout_seconds: int = 30) -> dict[str, Any]:
    status, payload = http_json(base_url.rstrip("/") + "/v1/models", timeout_seconds=timeout_seconds)
    models = []
    max_model_len = None
    if isinstance(payload, dict):
        for item in object_list(payload.get("data")):
            model_id = item.get("id")
            if isinstance(model_id, str):
                models.append(model_id)
            if model_id == expected_model and isinstance(item.get("max_model_len"), int):
                max_model_len = item["max_model_len"]
    return {
        "status": status,
        "models": models,
        "expected_model_present": expected_model in models,
        "max_model_len": max_model_len,
    }


def run_context_ceiling_benchmark(config: ContextCeilingBenchmarkConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = resolve_path(config_root, config.output_path or default_report_path(config_root))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    errors = validate_policy(policy)
    model_policy = policy.get("model") if isinstance(policy.get("model"), dict) else {}
    benchmark = policy.get("benchmark_policy") if isinstance(policy.get("benchmark_policy"), dict) else {}
    base_url = config.model_base_url or str(model_policy.get("base_url") or "http://127.0.0.1:8000")
    expected_model = str(model_policy.get("expected_model") or "")
    baseline_hash_before = sha256_file(config_root / "runtime" / "baseline_corpus.json")
    info = model_info(base_url, expected_model) if config.run_live and not errors else {}
    metrics_before = metric_values(fetch_metrics_excerpt(base_url)) if config.run_live else {}
    hardware_before = hardware_memory_snapshot() if config.run_live else {}
    if config.run_live:
        if info.get("expected_model_present") is not True:
            errors.append("expected model must be present before live benchmark")
        if not isinstance(info.get("max_model_len"), int) or info["max_model_len"] < int(benchmark.get("max_model_len_required", 262144)):
            errors.append("model max_model_len must satisfy benchmark requirement")
    results: list[dict[str, Any]] = []
    if config.run_live and not errors:
        for case in object_list(policy.get("context_classes")):
            print(f"CONTEXT CEILING BENCHMARK START {case.get('id')}", flush=True)
            try:
                result = run_context_case(
                    policy=policy,
                    base_url=base_url,
                    model=expected_model,
                    case=case,
                    timeout_override=config.timeout_seconds,
                )
                results.append(result)
                print(
                    "CONTEXT CEILING BENCHMARK RESULT "
                    + json.dumps(
                        {
                            "case_id": result.get("case_id"),
                            "prompt_tokens": result.get("prompt_tokens"),
                            "latency_seconds": result.get("latency_seconds"),
                            "answer_score": result.get("answer_score"),
                            "failure_class": result.get("failure_class"),
                            "passed": result.get("passed"),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 - benchmark should report failure class.
                results.append(
                    {
                        "case_id": case.get("id"),
                        "label": case.get("label"),
                        "target_context_tokens": case.get("target_context_tokens"),
                        "passed": False,
                        "failure_class": "benchmark_exception",
                        "error_sample": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(
                    "CONTEXT CEILING BENCHMARK RESULT "
                    + json.dumps({"case_id": case.get("id"), "failure_class": "benchmark_exception", "passed": False}),
                    flush=True,
                )
    failed = [result for result in results if result.get("passed") is not True]
    context_classes = object_list(policy.get("context_classes"))
    for result in failed:
        if result.get("failure_class") == "benchmark_exception":
            errors.append(f"{result.get('case_id')} benchmark exception: {result.get('error_sample')}")
    if config.run_live and len(results) != len(context_classes):
        errors.append("live benchmark must produce one classified result per context class")
    baseline_hash_after = sha256_file(config_root / "runtime" / "baseline_corpus.json")
    stable_corpus_mutated = baseline_hash_before != baseline_hash_after
    if stable_corpus_mutated:
        errors.append("runtime/baseline_corpus.json changed during context ceiling benchmark")
    metrics_after = metric_values(fetch_metrics_excerpt(base_url)) if config.run_live else {}
    hardware_after = hardware_memory_snapshot() if config.run_live else {}
    status = ContextCeilingBenchmarkStatus.PASSED.value if not errors else ContextCeilingBenchmarkStatus.FAILED.value
    latencies = [float(result.get("latency_seconds")) for result in results if isinstance(result.get("latency_seconds"), (int, float))]
    scores = [int(result.get("answer_score")) for result in results if isinstance(result.get("answer_score"), int)]
    live_benchmark_complete = (
        config.run_live
        and status == ContextCeilingBenchmarkStatus.PASSED.value
        and len(results) == len(context_classes)
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "context_ceiling_benchmark_report",
        "phase": 318,
        "priority_backlog_id": "P0-M7-318",
        "status": status,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "model_base_url": base_url,
        "model_info": info,
        "telemetry": {
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "hardware_memory_before": hardware_before,
            "hardware_memory_after": hardware_after,
        },
        "summary": {
            "status": status,
            "run_live": config.run_live,
            "context_class_count": len(context_classes),
            "result_count": len(results),
            "passed_result_count": len(results) - len(failed),
            "failed_result_count": len(failed),
            "failure_classes": sorted({str(result.get("failure_class")) for result in results if result.get("failure_class")}),
            "max_prompt_tokens": max([int(result.get("prompt_tokens")) for result in results if isinstance(result.get("prompt_tokens"), int)], default=0),
            "max_latency_seconds": max(latencies, default=0),
            "minimum_answer_score": min(scores, default=None),
            "stable_corpus_mutated": stable_corpus_mutated,
            "raw_500k_prompt_support_proven": False,
            "governed_500k_project_usability_unchanged": True,
            "validation_error_count": len(errors),
            "phase319_ready": live_benchmark_complete,
        },
        "results": results,
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
