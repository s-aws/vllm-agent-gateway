# Execution Planning Harness Catalog

This catalog contains explicit `execution_planning.plan` request envelopes for controller and AnythingLLM testing.

Status: implemented for the controller direct endpoint, controller harness adapter, explicit-envelope gateway route, and AnythingLLM routed path through `http://127.0.0.1:8300/v1`. Direct gateway and AnythingLLM dry-run validation passed against both frozen fixtures, including repeated testing in a workspace with older controller-envelope history.

The purpose is to make founder/tester validation concrete. Every request below is explicit. None of these workflows should be triggered by ordinary natural-language chat.

## Prerequisites

Start the controller/gateway stack with the project repo and both frozen validation repos allowlisted:

```bash
cd /mnt/c/agentic_agents
./stop-agent-prompt-proxies.sh
export CONTROLLER_ALLOWED_TARGET_ROOTS="/mnt/c/agentic_agents:/mnt/c/coinbase_testing_repo_frozen_tmp:/mnt/c/coinbase_testing_repo_frozen_tmp.github"
export GATEWAY_BIND_HOST=0.0.0.0
export CONTROLLER_BIND_HOST=0.0.0.0
./start-agent-prompt-proxies.sh
```

The controller endpoint is:

```text
POST http://127.0.0.1:8400/v1/controller/execution-planning/plans
```

The current harness adapter endpoint is:

```text
POST http://127.0.0.1:8400/v1/controller/harness/chat/completions
```

The AnythingLLM-compatible gateway endpoint is:

```text
POST http://127.0.0.1:8300/v1/chat/completions
```

AnythingLLM workspace configuration should use:

```text
http://127.0.0.1:8300/v1
```

Do not configure the workspace base URL as `8400`; that is the controller service, not the OpenAI-compatible gateway.

Windows-hosted clients should use the WSL/network URL for controller requests until direct Windows clients to Bash-hosted `127.0.0.1:8400` consistently receive response bodies.

## Catalog 1: Frozen Coinbase Documentation Packet Dry Run

Use this as the first implementation acceptance case. It mirrors the full AnythingLLM skill validation that already passed, but moves orchestration into the controller. The copied tree at `/mnt/c/coinbase_testing_repo_frozen_tmp` may not contain `.git`, so the controller must use bounded non-Git fallback lookup when Git metadata is unavailable.

Direct controller payload:

```json
{
  "workflow": "execution_planning.plan",
  "schema_version": 1,
  "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
  "user_request": "Prepare implementation packet candidates for an approved frozen-repo documentation clarification that client_order_id owns internal lookup paths, including StealthOrderManager placed-order index keys. Use draft mode only and do not mutate the frozen repository.",
  "mode": "dry_run",
  "approval": {
    "status": "approved_for_packet_design",
    "scope": "packet_design_only",
    "apply_allowed": false,
    "approval_refs": [
      "founder:approved packet design only for frozen documentation dry run"
    ]
  },
  "context": {
    "entrypoint_hints": [
      {
        "path": "docs/agents/INVARIANTS.md",
        "symbol": null,
        "reason": "Existing validation target for client_order_id invariant clarification."
      }
    ],
    "allowed_context_tools": [
      "structure_index",
      "git_grep",
      "read_file",
      "manual"
    ]
  },
  "packet_operations": [
    {
      "kind": "replace_text",
      "path": "docs/agents/INVARIANTS.md",
      "old": "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.",
      "new": "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys."
    }
  ],
  "budgets": {
    "max_context_requests": 5,
    "max_files": 10,
    "max_records": 50,
    "max_model_calls": 12,
    "max_output_tokens": 4600,
    "timeout_seconds": 600
  },
  "feedback": {
    "tester_feedback": "Confirm that the controller-owned workflow produces the same bounded result as the standalone AnythingLLM validator and preserves frozen repo hashes."
  }
}
```

Expected artifacts:

- `request-triage.json`
- `scope-and-assumptions.json`
- `entrypoint-finder.json`
- `context-plan.json`
- `context-results.json`
- `impact-map.json`
- `execution-plan.json`
- `implementation-packet-candidates.json`
- `packet-preview.json`
- `verification-plan.json`
- `implementation-workflow-report.json`
- `feedback-record.json`
- `run-state.json`

Expected compact summary:

- `status: "completed"`
- `mode: "dry_run"`
- selected entrypoint path is `docs/agents/INVARIANTS.md`
- packet preview count is `1`
- verification commands include the unit and regression order ID tests
- `repo_mutated: false`
- `non_mutation.changed_files` is empty

Tester feedback to provide:

- whether artifact names and locations are easy to inspect
- whether the compact response has enough information for AnythingLLM
- whether the packet preview is specific enough for approval or rejection
- whether the run was too slow or noisy

## Catalog 1A: Git-Enabled Frozen Coinbase Dry Run

Use this to validate the same request against the Git-enabled frozen fixture:

```text
/mnt/c/coinbase_testing_repo_frozen_tmp.github
```

Use the Catalog 1 payload and change only `target_root` to:

```json
"/mnt/c/coinbase_testing_repo_frozen_tmp.github"
```

Expected differences:

- `git_grep` should use the target repository as its Git top-level.
- `structure_index` should be able to use tracked-file scope.
- non-mutation proof must still show no changed files.

## Catalog 1B: Mutation Test On Disposable Fixture Copies

Use this to prove that approved packet application still goes through the existing `implementation.workflow` apply path and does not mutate either frozen source fixture.

```powershell
pytest tests\regression\test_implementation_workflow.py::test_frozen_coinbase_fixture_packet_mutation_on_disposable_copy -v
```

Expected result:

- both parameterized fixture cases pass when the external fixtures are present
- the disposable target copy contains the packet mutation
- the source fixture text remains unchanged
- the changed artifact records before and after hashes

Bash live matrix equivalent:

```bash
cd /mnt/c/agentic_agents
PYTHONUNBUFFERED=1 python3 scripts/validate_live_execution_planning_matrix.py --mode dry_run --timeout-seconds 900
```

This performs disposable-copy mutation probes directly against `/mnt/c/coinbase_testing_repo_frozen_tmp` and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.

## Catalog 2: Read-Only Controller Run Status Investigation

Use this to validate `investigation_only` mode before packet creation.

Direct controller payload:

```json
{
  "workflow": "execution_planning.plan",
  "schema_version": 1,
  "target_root": "/mnt/c/agentic_agents",
  "user_request": "Create a read-only execution plan for investigating whether controller-service run lookup and run status persistence have one code path per behavior before any refactor.",
  "mode": "investigation_only",
  "context": {
    "entrypoint_hints": [
      {
        "path": "vllm_agent_gateway/controller_service/server.py",
        "symbol": "load_run_record",
        "reason": "Existing validation identified this as a controller run lookup anchor."
      }
    ],
    "allowed_context_tools": [
      "structure_index",
      "git_grep",
      "read_file",
      "manual"
    ]
  },
  "budgets": {
    "max_context_requests": 5,
    "max_files": 10,
    "max_records": 50,
    "max_model_calls": 8,
    "max_output_tokens": 4600
  }
}
```

Expected artifacts:

- `request-triage.json`
- `scope-and-assumptions.json`
- `entrypoint-finder.json`
- `context-plan.json`
- `context-results.json`
- `impact-map.json`
- `execution-plan.json`
- `feedback-record.json`
- `run-state.json`

Expected compact summary:

- `status: "completed"` or `status: "paused"` if context is insufficient
- `mode: "investigation_only"`
- no `implementation-packet-candidates.json`
- no `packet-preview.json`
- no `implementation-workflow-report.json`
- no target repository mutation check is needed unless files were selected for hash proof

Tester feedback to provide:

- whether the selected entrypoint matches the actual logic beginning point
- whether affected files and tests are evidence-backed
- whether the workflow stopped instead of inventing missing context

## Catalog 3: Harness Adapter Top-Level Envelope

Use this when a harness supports extra JSON fields.

```json
{
  "model": "agentic-controller",
  "agentic_controller_request": {
    "workflow": "execution_planning.plan",
    "schema_version": 1,
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "user_request": "Prepare implementation packet candidates for an approved frozen-repo documentation clarification that client_order_id owns internal lookup paths, including StealthOrderManager placed-order index keys. Use draft mode only and do not mutate the frozen repository.",
    "mode": "dry_run",
    "approval": {
      "status": "approved_for_packet_design",
      "scope": "packet_design_only",
      "apply_allowed": false,
      "approval_refs": [
        "founder:approved packet design only for frozen documentation dry run"
      ]
    },
    "context": {
      "entrypoint_hints": [
        {
          "path": "docs/agents/INVARIANTS.md",
          "symbol": null,
          "reason": "Existing validation target for client_order_id invariant clarification."
        }
      ],
      "allowed_context_tools": [
        "structure_index",
        "git_grep",
        "read_file",
        "manual"
      ]
    },
    "packet_operations": [
      {
        "kind": "replace_text",
        "path": "docs/agents/INVARIANTS.md",
        "old": "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.",
        "new": "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys."
      }
    ],
    "budgets": {
      "max_context_requests": 5,
      "max_files": 10,
      "max_records": 50,
      "max_model_calls": 12,
      "max_output_tokens": 4600
    }
  }
}
```

Expected response:

- OpenAI-style `choices[0].message.content`
- structured `agentic_controller_response`
- bounded artifact paths only, not full artifact bodies

## Catalog 4: Harness Adapter Message-Content Envelope

Use this when a harness can only send normal OpenAI-style chat messages.

```json
{
  "model": "agentic-controller",
  "messages": [
    {
      "role": "user",
      "content": "{\"agentic_controller_request\":{\"workflow\":\"execution_planning.plan\",\"schema_version\":1,\"target_root\":\"/mnt/c/coinbase_testing_repo_frozen_tmp\",\"user_request\":\"Prepare implementation packet candidates for an approved frozen-repo documentation clarification that client_order_id owns internal lookup paths, including StealthOrderManager placed-order index keys. Use draft mode only and do not mutate the frozen repository.\",\"mode\":\"dry_run\",\"approval\":{\"status\":\"approved_for_packet_design\",\"scope\":\"packet_design_only\",\"apply_allowed\":false,\"approval_refs\":[\"founder:approved packet design only for frozen documentation dry run\"]},\"context\":{\"entrypoint_hints\":[{\"path\":\"docs/agents/INVARIANTS.md\",\"symbol\":null,\"reason\":\"Existing validation target for client_order_id invariant clarification.\"}],\"allowed_context_tools\":[\"structure_index\",\"git_grep\",\"read_file\",\"manual\"]},\"packet_operations\":[{\"kind\":\"replace_text\",\"path\":\"docs/agents/INVARIANTS.md\",\"old\":\"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\\n  local rows.\",\"new\":\"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\\n  local rows, and stealth manager placed-order index keys.\"}],\"budgets\":{\"max_context_requests\":5,\"max_files\":10,\"max_records\":50,\"max_model_calls\":12,\"max_output_tokens\":4600}}}"
    }
  ]
}
```

Expected response:

- same bounded response as the top-level envelope
- no reliance on prior workspace chat history; older message envelopes are ignored in favor of the latest message-content envelope

## Catalog 5: AnythingLLM Pasteable Prompt

Use this in an AnythingLLM chat box when the workspace is configured to use the gateway base URL:

```text
http://127.0.0.1:8300/v1
```

The gateway also accepts clients configured as `http://127.0.0.1:8300` when they call `/chat/completions`.

The gateway should route this explicit envelope to the controller harness.

```text
{"agentic_controller_request":{"workflow":"execution_planning.plan","schema_version":1,"target_root":"/mnt/c/coinbase_testing_repo_frozen_tmp","user_request":"Prepare implementation packet candidates for an approved frozen-repo documentation clarification that client_order_id owns internal lookup paths, including StealthOrderManager placed-order index keys. Use draft mode only and do not mutate the frozen repository.","mode":"dry_run","approval":{"status":"approved_for_packet_design","scope":"packet_design_only","apply_allowed":false,"approval_refs":["founder:approved packet design only for frozen documentation dry run"]},"context":{"entrypoint_hints":[{"path":"docs/agents/INVARIANTS.md","symbol":null,"reason":"Existing validation target for client_order_id invariant clarification."}],"allowed_context_tools":["structure_index","git_grep","read_file","manual"]},"packet_operations":[{"kind":"replace_text","path":"docs/agents/INVARIANTS.md","old":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.","new":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys."}],"budgets":{"max_context_requests":5,"max_files":10,"max_records":50,"max_model_calls":12,"max_output_tokens":4600}}}
```

Expected tester review:

- response includes `agentic_controller_response`
- response names artifact paths
- response says the target repo was not mutated
- response does not include full JSON artifacts inline
- a normal model-generated plan without `agentic_controller_response` is a failed controller-routing test, even if the text looks useful

Latest live proof:

- Direct gateway dry run, copied fixture: `execution-planning-20260603T222254799100Z`
- Direct gateway dry run, Git-enabled fixture: `execution-planning-20260603T222506207778Z`
- AnythingLLM dry run, copied fixture: `execution-planning-20260603T222615829911Z`
- AnythingLLM dry run, Git-enabled fixture: `execution-planning-20260603T222818822509Z`
- Live matrix mutation probes: copied fixture passed with initialized Git on the disposable copy; Git-enabled fixture passed with existing Git metadata on the disposable copy.

## Catalog 6: Rejected Apply Request

This must fail before model calls.

```json
{
  "workflow": "execution_planning.plan",
  "schema_version": 1,
  "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
  "user_request": "Apply the documentation clarification immediately.",
  "mode": "dry_run",
  "approval": {
    "status": "approved_for_packet_design",
    "scope": "packet_design_only",
    "apply_allowed": true,
    "approval_refs": [
      "user:apply now"
    ]
  }
}
```

Expected error:

```json
{
  "error": {
    "code": "apply_mode_not_supported"
  }
}
```

## Catalog 7: Rejected Raw CodeGraphContext Request

This must fail before model-visible tool use.

```json
{
  "workflow": "execution_planning.plan",
  "schema_version": 1,
  "target_root": "/mnt/c/agentic_agents",
  "user_request": "Use raw CodeGraphContext Cypher to scan all callers and rewrite the plan.",
  "mode": "investigation_only",
  "context": {
    "allowed_context_tools": [
      "raw_mcp_cypher",
      "codegraph_index_package"
    ]
  }
}
```

Expected error:

```json
{
  "error": {
    "code": "raw_codegraph_not_allowed"
  }
}
```

## Catalog 8: Rejected Natural-Language Harness Chat

This must keep failing after `execution_planning.plan` is implemented.

```json
{
  "model": "agentic-controller",
  "messages": [
    {
      "role": "user",
      "content": "Investigate the frozen repo and prepare packets."
    }
  ]
}
```

Expected error:

```json
{
  "error": {
    "code": "missing_controller_envelope"
  }
}
```

## Validation Checklist

For the first implemented workflow run, record:

- controller URL used
- request payload catalog ID
- run ID
- artifact directory
- selected entrypoint
- packet count
- verification commands
- frozen selected-file hashes before and after
- mutation test result for disposable copies of both frozen fixtures
- AnythingLLM workspace slug if tested through AnythingLLM
- AnythingLLM controller markers: `agentic_controller_response`, run ID, artifact paths, and non-mutation proof
- feedback record summary

The test is not complete until the frozen repository remains unchanged and the response can be understood without reading this conversation.
