# Contextless Agent Audit Pack

Phase 185 packages the blind-baseline-first chat-quality process into a reusable audit pack.

This is not a replacement for live localhost, workflow-router, or AnythingLLM proof. It defines the contextless-agent prompts, ordering rules, recursion limits, sample report shape, and validation gate that future phases should use before comparing local model output.

## What It Proves

- a fresh blind agent must define the ideal answer before local output is inspected
- baseline and local runs must use the same prompt hash
- audit records must show context isolation: `fork_context=false`, no session history, and no local output seen by the blind agent
- local proof must still include localhost `8000`, workflow-router gateway, AnythingLLM, both frozen Coinbase fixtures, and mutation proof
- repairs are bounded by explicit recursion limits and stop conditions
- sample reports are valid examples for current Priority 0 prompt families

## Governed Files

```text
runtime/contextless_agent_audit_pack_policy.json
runtime/contextless_agent_audit_pack_sample_reports.json
vllm_agent_gateway/acceptance/contextless_agent_audit_pack.py
scripts/validate_contextless_agent_audit_pack.py
```

## Run

```bash
python3 scripts/validate_contextless_agent_audit_pack.py
```

Expected final marker:

```text
CONTEXTLESS AGENT AUDIT PACK PASS
```

The default report is written to:

```text
runtime-state/contextless-agent-audit-pack/phase185/phase185-contextless-agent-audit-pack-report.json
```

## Process

1. Record the natural-language prompt, target root, prompt family, expected user-visible outcome, and safety boundary.
2. Ask a fresh contextless blind agent for the ideal answer shape, must-have facts, evidence expectations, safety boundaries, output expectations, and scoring rubric.
3. Run the same prompt through the local stack, including localhost `8000`, the workflow-router gateway, and AnythingLLM.
4. Score the local answer against the blind baseline.
5. Accept or reject findings using deterministic evidence.
6. Rerun the target prompt and holdouts after accepted repairs.
7. Close with validation refs, mutation proof, residual risks, and next action.

## Examples

See [docs/examples/contextless-agent-audit-pack.md](docs/examples/contextless-agent-audit-pack.md).
