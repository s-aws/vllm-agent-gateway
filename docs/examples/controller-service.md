# Controller Service Examples

Start the stack:

```bash
bash start-agent-prompt-proxies.sh
```

Allow the service to review another repository:

```bash
CONTROLLER_ALLOWED_TARGET_ROOTS=/repo/agentic_agents:/target/repo \
  bash start-agent-prompt-proxies.sh
```

Health check:

```bash
curl http://127.0.0.1:8400/health
```

Run a bounded single-document seed review through the example runner:

```bash
python scripts/run_documenter_service_example.py \
  --target-root /repo/agentic_agents \
  --case seed \
  --seed-doc README.md \
  --max-chunks 1
```

Run all tracked documentation through the controller service:

```bash
python scripts/run_documenter_service_example.py \
  --target-root /repo/agentic_agents \
  --case tracked \
  --max-chunks 1
```

Run a bootstrap all-file documentation review:

```bash
python scripts/run_documenter_service_example.py \
  --target-root /repo/target \
  --case all \
  --max-chunks 1
```

Run through the harness adapter:

```bash
python scripts/run_documenter_service_example.py \
  --target-root /repo/agentic_agents \
  --case harness \
  --max-chunks 1
```

The example runner defaults to `dry_run` so it verifies controller behavior and artifacts without requiring a model call. Add `--live` when the documenter role endpoint and vLLM are running and you want actual model-reviewed chunks. Add `--parallelism 2` or another bounded value to send concurrent chunk review requests.

Run a bounded documenter dry run with curl:

```bash
curl -s http://127.0.0.1:8400/v1/controller/documenter/reviews \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "documenter.review",
    "target_root": "/repo/agentic_agents",
    "seed_doc": "README.md",
    "mode": "full",
    "dry_run": true,
    "budgets": {
      "max_chunks": 1
    }
  }'
```

Run all tracked documentation with curl:

```bash
curl -s http://127.0.0.1:8400/v1/controller/documenter/reviews \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "documenter.review",
    "target_root": "/repo/agentic_agents",
    "mode": "full",
    "document_scope": "tracked",
    "review_scope": "manifest",
    "dry_run": true,
    "budgets": {
      "max_chunks": 1
    }
  }'
```

Run live model review with bounded parallel chunk requests:

```bash
curl -s http://127.0.0.1:8400/v1/controller/documenter/reviews \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "documenter.review",
    "target_root": "/repo/agentic_agents",
    "mode": "full",
    "review_scope": "manifest",
    "budgets": {
      "parallelism": 2
    }
}'
```

Run an execution-planning dry run with explicit packet operations:

```bash
curl -s http://127.0.0.1:8400/v1/controller/execution-planning/plans \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "execution_planning.plan",
    "schema_version": 1,
    "target_root": "/repo/target",
    "user_request": "Prepare implementation packet candidates for an approved documentation clarification. Use draft mode only and do not mutate the repository.",
    "mode": "dry_run",
    "approval": {
      "status": "approved_for_packet_design",
      "scope": "packet_design_only",
      "apply_allowed": false,
      "approval_refs": ["user:approved packet design only"]
    },
    "packet_operations": [
      {
        "kind": "replace_text",
        "path": "docs/agents/INVARIANTS.md",
        "old": "exact existing text",
        "new": "exact proposed text"
      }
    ],
    "budgets": {
      "max_context_requests": 5,
      "max_files": 10,
      "max_records": 50,
      "max_model_calls": 12,
      "max_output_tokens": 4600
    }
  }'
```

Use [execution-planning-harness.md](execution-planning-harness.md) for the concrete frozen Coinbase payload and harness envelopes.

Run a read-only code context lookup:

```bash
curl -s http://127.0.0.1:8400/v1/controller/code-context/lookups \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "code_context.lookup",
    "schema_version": 1,
    "target_root": "/repo/agentic_agents",
    "query": "select_latest_controller_envelope",
    "paths": [
      "vllm_agent_gateway/controller_envelope.py"
    ],
    "max_results": 25,
    "max_files": 5
  }'
```

Use [code-context.md](code-context.md) for harness envelopes and the raw CodeGraphContext rejection example.

Run a read-only code investigation plan:

```bash
curl -s http://127.0.0.1:8400/v1/controller/code-investigation/plans \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "code_investigation.plan",
    "schema_version": 1,
    "target_root": "/repo/target",
    "user_request": "Investigate whether StealthOrderManager.find_stealth_order_by_placed_order_id has one path before planning a refactor.",
    "behavior": "placed_order_id stealth lookup",
    "entrypoint_hints": [
      {
        "path": "core/stealth_order_manager.py",
        "symbol": "StealthOrderManager.find_stealth_order_by_placed_order_id",
        "reason": "Known owner of placed-order lookup behavior."
      }
    ],
    "queries": [
      "find_stealth_order_by_placed_order_id",
      "placed_order_id"
    ],
    "paths": [
      "core/stealth_order_manager.py",
      "tests/unit/test_order_id_and_followup_rules.py",
      "tests/regression/test_order_id_regression.py"
    ],
    "max_results": 50,
    "max_files": 10
  }'
```

Use [code-investigation.md](code-investigation.md) for harness envelopes and the raw CodeGraphContext rejection example.

Run a single-path refactor investigation:

```bash
curl -s http://127.0.0.1:8400/v1/controller/refactor/single-path \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "refactor.single_path",
    "schema_version": 1,
    "target_root": "/repo/target",
    "user_request": "Investigate whether StealthOrderManager.find_stealth_order_by_placed_order_id has one path before planning a refactor.",
    "behavior": "placed_order_id stealth lookup",
    "entrypoint_hints": [
      {
        "path": "core/stealth_order_manager.py",
        "symbol": "StealthOrderManager.find_stealth_order_by_placed_order_id",
        "reason": "Known owner of placed-order lookup behavior."
      }
    ],
    "queries": [
      "find_stealth_order_by_placed_order_id",
      "placed_order_id"
    ],
    "paths": [
      "core/stealth_order_manager.py",
      "tests/unit/test_order_id_and_followup_rules.py",
      "tests/regression/test_order_id_regression.py"
    ],
    "max_results": 50,
    "max_files": 10
  }'
```

Use [refactor-single-path.md](refactor-single-path.md) for approved dry-run payloads and harness envelopes.

Record founder/tester feedback against a prior workflow run:

```bash
curl -s http://127.0.0.1:8400/v1/controller/workflow-feedback/records \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "workflow_feedback.record",
    "schema_version": 1,
    "target_workflow": "refactor.single_path",
    "target_run_id": "refactor-single-path-20260604T031238337959Z",
    "target_root": "/repo/target",
    "feedback": {
      "useful": ["The beginning point was actionable."],
      "wrong": [],
      "missing": ["Need clearer verification command source."],
      "too_slow": [],
      "too_noisy": [],
      "notes": "Manual controller-service feedback record."
    },
    "tester": {
      "id": "founder",
      "surface": "curl"
    },
    "request_payload": {
      "source": "manual-controller-test"
    },
    "artifact_refs": {}
  }'
```

Use [workflow-feedback.md](workflow-feedback.md) for direct, gateway, and AnythingLLM envelopes.

Run a bootstrap review over all discovered documentation:

```bash
curl -s http://127.0.0.1:8400/v1/controller/documenter/reviews \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "documenter.review",
    "target_root": "/repo/target",
    "mode": "full",
    "document_scope": "all",
    "review_scope": "manifest",
    "budgets": {
      "max_chunks": 1
    }
  }'
```

The response includes a `tool_policy` audit record. For this all-file request, the controller enables `git_ls_files`, `read_file`, and `scan_files`, and records controller actions that tie those tools to result artifacts such as `document_manifest`, `review_plan`, and `json_report`.

Example bounded response fields:

```json
{
  "run_id": "20260526T220000000000Z",
  "workflow": "documenter.review",
  "status": "completed",
  "artifacts": {
    "document_manifest": ".../document-manifest-target-20260526T220000000000Z.json",
    "review_plan": ".../doc-review-plan-target-README.md-20260526T220000000000Z.json",
    "json_report": ".../documenter-target-README.md-20260526T220000000000Z.json",
    "doc_change_plan": ".../doc-change-plan-target-README.md-20260526T220000000000Z.md",
    "run_state": ".../run-state-target-README.md-20260526T220000000000Z.json"
  },
  "summary": null,
  "warnings": [],
  "failures": [],
  "resume_key": {
    "schema_version": 1
  },
  "review_summary": {
    "seed_doc_id": "README.md",
    "document_scope": "tracked",
    "review_scope": "manifest",
    "reviewed_file_count": 2,
    "reviewed_files": ["README.md", "docs/config.md"],
    "chunks_processed": 2,
    "chunks_total": 2,
    "truncated_after_chunks": false,
    "skipped_followup_count": 0
  }
}
```

The response is intentionally compact. Full details stay in the artifact paths.

Denied tool policy example:

```bash
curl -s http://127.0.0.1:8400/v1/controller/documenter/reviews \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "documenter.review",
    "target_root": "/repo/agentic_agents",
    "seed_doc": "README.md",
    "mode": "full",
    "model_visible_tool_ids": ["read_file"],
    "dry_run": true
  }'
```

`documenter.review` does not currently expose model-visible tools, so this returns `tool_policy_denied` before workflow artifacts are created.

Look up a completed run:

```bash
curl http://127.0.0.1:8400/v1/controller/runs/<run-id>
```

Start a long-running review asynchronously:

```bash
curl -i -s http://127.0.0.1:8400/v1/controller/documenter/reviews \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "documenter.review",
    "target_root": "/repo/agentic_agents",
    "seed_doc": "README.md",
    "mode": "full",
    "async": true,
    "budgets": {
      "max_chunks": 10
    }
  }'
```

The async response uses `202 Accepted` and includes a controller `run_id`. Poll the bounded run record:

```bash
curl -s http://127.0.0.1:8400/v1/controller/runs/<run-id>
```

Request cooperative cancellation:

```bash
curl -s -X POST http://127.0.0.1:8400/v1/controller/runs/<run-id>/cancel \
  -H 'Content-Type: application/json' \
  -d '{}'
```

The run moves to `cancel_requested` first. The workflow checks the stop signal between packets, then records `canceled`.

Pause after one packet for resume testing:

```bash
curl -s http://127.0.0.1:8400/v1/controller/documenter/reviews \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "documenter.review",
    "target_root": "/repo/agentic_agents",
    "seed_doc": "README.md",
    "mode": "full",
    "dry_run": true,
    "chunk_token_limit": 128,
    "budgets": {
      "stop_after_chunks": 1
    }
  }'
```

Resume with the `artifacts.run_state` path returned by the paused response:

```bash
curl -s http://127.0.0.1:8400/v1/controller/documenter/reviews \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "documenter.review",
    "target_root": "/repo/agentic_agents",
    "seed_doc": "README.md",
    "mode": "full",
    "dry_run": true,
    "chunk_token_limit": 128,
    "resume": "<run-state-path>"
  }'
```

Remove old completed, failed, or canceled controller run records:

```bash
curl -s -X POST http://127.0.0.1:8400/v1/controller/runs/cleanup \
  -H 'Content-Type: application/json' \
  -d '{
    "max_age_seconds": 86400,
    "statuses": ["completed", "failed", "canceled"]
  }'
```

Cleanup only removes controller run records and cooperative stop signal files. Workflow artifacts stay on disk.

Run through the harness adapter with an OpenAI-style chat request:

```bash
curl -s http://127.0.0.1:8400/v1/controller/harness/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "agentic-controller",
    "messages": [
      {
        "role": "user",
        "content": "{\"agentic_controller_request\":{\"workflow\":\"documenter.review\",\"target_root\":\"/repo/agentic_agents\",\"seed_doc\":\"README.md\",\"mode\":\"full\",\"dry_run\":true,\"budgets\":{\"max_chunks\":1}}}"
      }
    ]
  }'
```

Use a top-level envelope when the harness supports extra request fields:

```bash
curl -s http://127.0.0.1:8400/v1/controller/harness/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "agentic-controller",
    "agentic_controller_request": {
      "workflow": "documenter.review",
      "target_root": "/repo/agentic_agents",
      "seed_doc": "README.md",
      "mode": "full",
      "dry_run": true,
      "budgets": {
        "max_chunks": 1
      }
    }
  }'
```

Rejected implicit chat request:

```bash
curl -s http://127.0.0.1:8400/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Review all docs"}]}'
```

The controller service returns `404` for that route. Use role prompt proxy ports for chat and controller routes for workflows.

Rejected harness request without an explicit envelope:

```bash
curl -s http://127.0.0.1:8400/v1/controller/harness/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"agentic-controller","messages":[{"role":"user","content":"Review all docs"}]}'
```
