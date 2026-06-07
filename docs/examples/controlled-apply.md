# Controlled Small-Change Apply Examples

These examples prove small approved edits can be previewed, applied to a disposable copy, and rejected from protected frozen source roots.

## Direct Dry-Run Patch Preview

```bash
curl -fsS http://127.0.0.1:8400/v1/controller/implementation-runs \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "implementation.workflow",
    "schema_version": 1,
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    "mode": "dry_run",
    "approval": {
      "status": "approved_for_small_change_dry_run",
      "scope": "patch_preview_only",
      "apply_allowed": false,
      "approval_refs": ["example dry run"]
    },
    "packet_operations": [
      {
        "kind": "replace_text",
        "path": "docs/agents/INVARIANTS.md",
        "old": "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.",
        "new": "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys."
      }
    ],
    "no_structure_index": true
  }'
```

Expected:

- HTTP 200
- `summary.mode` is `draft`
- `summary.target_repository_changed` is `false`
- `summary.patch_preview_count` is `1`
- source files remain unchanged

## Protected Real Apply Refusal

```bash
curl -i http://127.0.0.1:8400/v1/controller/implementation-runs \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "implementation.workflow",
    "schema_version": 1,
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    "mode": "apply",
    "approval": {
      "status": "approved_for_real_apply",
      "apply_allowed": true,
      "apply_scope": "target_root",
      "explicit_real_apply": true,
      "approval_refs": ["example real apply boundary"]
    },
    "packet_operations": [
      {
        "kind": "replace_text",
        "path": "docs/agents/INVARIANTS.md",
        "old": "exact old text",
        "new": "exact new text"
      }
    ],
    "no_structure_index": true
  }'
```

Expected:

- HTTP 403
- `error.code` is `protected_frozen_real_apply_denied`
- source files remain unchanged

## Natural Disposable-Copy Apply Through Gateway

Send to `http://127.0.0.1:8500/v1/chat/completions`:

```json
{
  "model": "agentic-workflow-router",
  "messages": [
    {
      "role": "user",
      "content": "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, approved disposable copy apply only. Apply these exact packet_operations to a disposable copy and do not mutate the source repo: {\"packet_operations\":[{\"kind\":\"replace_text\",\"path\":\"docs/agents/INVARIANTS.md\",\"old\":\"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\\n  local rows.\",\"new\":\"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\\n  local rows, and stealth manager placed-order index keys.\"}]}"
    }
  ]
}
```

Expected chat markers:

- `workflow_router.plan completed`
- `downstream_workflow: implementation.workflow`
- `source_changed: False`
- `source_tree_changed: False`
- `disposable_copy_changed: True`
- `mutation_diff_file_count: 1`
- `Disposable Apply:`
- `Changed files: 1`

Expected artifact proof in `route-decision.json`:

- `disposable_apply.mutation_proof.source_changed` is `{}`
- `disposable_apply.mutation_proof.source_tree_changed` is `false`
- `disposable_apply.mutation_proof.copy_changed` contains `docs/agents/INVARIANTS.md`
- `disposable_apply.mutation_proof.copy_tree_restored` is `true`
- `disposable_apply.mutation_proof.rollback.status` is `restored`

## Multi-Operation Disposable-Copy Apply

Phase 98 allows approved exact packet operations for existing files when every operation stays inside the disposable-copy boundary.

```json
{
  "model": "agentic-workflow-router",
  "messages": [
    {
      "role": "user",
      "content": "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, approved disposable copy apply only. Apply these exact packet_operations to a disposable copy and do not mutate the source repo: {\"packet_operations\":[{\"kind\":\"replace_text\",\"path\":\"docs/agents/INVARIANTS.md\",\"old\":\"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\\n  local rows.\",\"new\":\"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\\n  local rows, and stealth manager placed-order index keys.\"},{\"kind\":\"append_text\",\"path\":\"README.md\",\"content\":\"\\n<!-- disposable copy proof marker -->\\n\"}]}"
    }
  ]
}
```

Expected:

- `mutation_diff_file_count: 2`
- `mutation_diff_paths` contains `README.md` and `docs/agents/INVARIANTS.md`
- `Disposable Apply:` lists both changed files with operation kinds
- source tree digest remains unchanged
- disposable copy tree digest is restored after rollback

## Create-File Apply Refusal

`create_file` is still draft-only. An approved disposable-copy apply request that includes `create_file` is blocked before downstream apply setup.

Expected:

- `route_status` is `blocked`
- a `route-decision.json` blocker has `reason=unsupported_disposable_operation_kind`
- no `disposable-mutation-proof.json` is written
- source files remain unchanged

## AnythingLLM Test

Use a fresh AnythingLLM thread while the LLM provider points at:

```text
http://127.0.0.1:8500/v1
```

Paste the same natural disposable-copy apply message from the gateway example.

Expected result:

- chat-visible proof markers appear immediately
- the `run_id` maps to a workflow-router artifact directory
- the frozen source fixture remains unchanged

## Live Validator

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_controlled_small_change_apply_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

Phase 98 expansion validator:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_disposable_apply_expansion.py \
  --port-health \
  --live-gateway \
  --live-anythingllm \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --output-path runtime-state/disposable-apply-expansion/manual-live.json \
  --timeout-seconds 900
```
