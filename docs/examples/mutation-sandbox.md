# Mutation Sandbox Examples

Run these from Bash after starting the controller with the frozen fixture roots allowlisted.

## Start The Stack

```bash
cd /mnt/c/agentic_agents
./stop-agent-prompt-proxies.sh
CONTROLLER_ALLOWED_TARGET_ROOTS="/mnt/c/agentic_agents:/mnt/c/coinbase_testing_repo_frozen_tmp:/mnt/c/coinbase_testing_repo_frozen_tmp.github" \
CONTROLLER_DEFAULT_ROLE_BASE_URL="http://127.0.0.1:8300/v1" \
./start-agent-prompt-proxies.sh
```

## Validate Disposable Apply Proof

```bash
python3 scripts/validate_controlled_small_change_apply_live.py \
  --timeout-seconds 900 \
  --output-path runtime-state/controlled-small-change-apply/mutation-sandbox-live.json
```

Expected markers:

```text
PHASE54 GATEWAY PASS target=/mnt/c/coinbase_testing_repo_frozen_tmp
PHASE54 GATEWAY PASS target=/mnt/c/coinbase_testing_repo_frozen_tmp.github
PHASE54 ANYTHINGLLM PASS target=/mnt/c/coinbase_testing_repo_frozen_tmp
PHASE54 ANYTHINGLLM PASS target=/mnt/c/coinbase_testing_repo_frozen_tmp.github
PHASE54 CONTROLLED SMALL-CHANGE APPLY LIVE PASS
```

## Inspect Proof Artifacts

Open the workflow-router run artifacts named by the validator report or latest run inspector.

The important files are:

```text
disposable-mutation-sandbox-contract.json
disposable-mutation-diff.json
disposable-rollback-proof.json
disposable-mutation-proof.json
route-decision.json
```

The expected proof shape is:

```json
{
  "kind": "disposable_mutation_proof",
  "source_changed": {},
  "copy_changed": {
    "docs/agents/INVARIANTS.md": {
      "before": "...",
      "after": "..."
    }
  },
  "sandbox_contract": {
    "status": "active",
    "mutation_policy": "disposable_copy_only"
  },
  "structured_diff": {
    "status": "ready",
    "changed_file_count": 1
  },
  "rollback": {
    "status": "restored"
  }
}
```

## Invalid Path Behavior

Packet paths such as `../outside.md` are blocked before `implementation.workflow` runs. The response remains non-mutating and `route-decision.json` includes a blocker with:

```text
invalid_disposable_operation_path
```

