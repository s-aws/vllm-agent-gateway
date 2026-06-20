# EIG-2 Approval Replay Breadth

This feature validates the Phase 294 approval replay breadth gate for governed connector execution.

It proves write-class connector approvals are bound to the exact actor, session, request, connector, operation, and granted-scope state. It also proves stale or replayed approvals fail closed while still producing replay-safe local audit artifacts.

## When To Use It

Use this gate when changing connector write approvals, approval validation, connector invocation audit behavior, operation-level scope enforcement, or EIG-2 roadmap proof.

It does not add real OAuth providers, real approval stores, signatures, external audit sinks, SIEM integrations, production connector execution, or raw MCP exposure.

## Inputs

- `runtime/eig2_approval_replay_breadth_policy.json`
- `runtime/eig2_actor_scope_breadth_policy.json`
- `runtime/eig1_connector_breadth_fixtures.json`
- existing connector invocation and audit modules:
  - `vllm_agent_gateway/controllers/connector_catalog/invoke.py`
  - `vllm_agent_gateway/connectors/mediator.py`
  - `vllm_agent_gateway/acceptance/connector_user_scope_audit.py`

## Output

The validator writes an `eig2_approval_replay_breadth_report` JSON artifact under:

```text
runtime-state/eig2-approval-replay-breadth/
```

The report includes approval replay outcomes, expected denial codes, audit validation status, compact audit summaries, and safety markers. It must not retain raw fixture arguments or raw auth subjects.

## Run

```bash
python3 scripts/validate_eig2_approval_replay_breadth.py
python3 -m pytest tests/regression/test_eig2_approval_replay_breadth.py -q
```

On Windows PowerShell:

```powershell
python scripts/validate_eig2_approval_replay_breadth.py
python -m pytest tests/regression/test_eig2_approval_replay_breadth.py -q
```

## Pass Criteria

The gate passes only when:

- a correctly approved write dry-run succeeds,
- wrong actor, session, request, connector, and operation approvals fail closed,
- approval records missing granted-scope state fail closed,
- actor granted-scope changes after approval fail closed,
- non-dry-run write execution fails closed,
- every allowed and denied attempt has a connector invocation audit artifact,
- connector audit validation passes for every attempt,
- raw auth subjects and raw arguments are not retained,
- runtime registry and target repository mutation flags remain false.

## Next Phase

Phase 295 exposes selected breadth fixture behavior through natural language. It should use blind-baseline-first evaluation through the workflow-router gateway and AnythingLLM only for fixtures intentionally exposed to chat.
