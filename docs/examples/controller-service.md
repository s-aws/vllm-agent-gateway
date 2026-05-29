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
