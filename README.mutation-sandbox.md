# Mutation Sandbox

The mutation sandbox is the controller-owned proof layer for `workflow_router.plan` disposable-copy apply.

It does not add a second apply path. Approved disposable-copy requests still execute through:

```text
workflow_router.plan -> implementation.workflow
```

The sandbox wraps that path with deterministic guardrails and artifacts so testers can verify that source repositories were not modified.

## When To Use It

Use this proof when a workflow asks to apply exact approved packet operations only to a disposable copy.

Do not use it for normal read-only L1/L2 prompts, draft-only packet proposals, or unapproved mutation. Those flows should continue to report `Source mutation: false` or request approval.

## Guardrails

- `approval.status` must be `approved_for_disposable_apply`.
- `approval.apply_allowed` must be `true`.
- `approval.apply_scope` must be `disposable_copy_only`.
- `packet_operations` must be exact JSON objects.
- every packet path must be repo-relative and stay inside the source root and disposable copy root.
- the disposable copy root must stay under the workflow run directory.
- `implementation.workflow` remains the only executor for packet application.
- rollback must restore the disposable copy to its original target-file hashes.

## Artifacts

Successful disposable-copy apply writes:

- `disposable-mutation-sandbox-contract.json`: allowed roots, allowed packet paths, approval scope, and guardrails.
- `disposable-mutation-diff.json`: structured per-file before/after hash and unified diff excerpt for the disposable copy.
- `disposable-rollback-proof.json`: rollback status, expected hashes, after-rollback hashes, blockers, and backup artifacts.
- `disposable-mutation-proof.json`: combined source hash proof, copy hash proof, sandbox contract, structured diff, and rollback proof.

The workflow-router response exposes these files as:

- `disposable_mutation_sandbox_contract`
- `disposable_mutation_diff`
- `disposable_rollback_proof`
- `disposable_mutation_proof`

## Failure Behavior

Invalid packet paths are blocked before the apply executor runs and are recorded in `route-decision.json`.

Rollback failures fail closed with `disposable_copy_rollback_failed` after writing mutation proof artifacts. Source files must remain unchanged.

## Validation

Focused regression:

```bash
python -m pytest tests/regression/test_controlled_small_change_apply.py tests/regression/test_implementation_workflow.py -q
```

Live Bash validation through localhost ports, gateway, both frozen Coinbase fixtures, and AnythingLLM:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_controlled_small_change_apply_live.py --timeout-seconds 900
```

