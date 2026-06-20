# EIG-2 Actor Scope Breadth

This feature validates the Phase 293 actor and scope breadth gate for governed connector execution.

It proves that connector invocation uses explicit actor context, operation-level least-privilege scopes, fail-closed authorization, and chat-recoverable missing-scope guidance across the approved local-stub connector breadth fixtures.

## When To Use It

Use this gate when changing connector identity validation, user-scope authorization, connector mediation, connector manifest operation scopes, or EIG-2 roadmap proof.

It does not add real OAuth providers, token refresh, vendor-specific identity propagation, shared privileged service accounts, production connector execution, or raw MCP exposure.

## Inputs

- `runtime/eig2_actor_scope_breadth_policy.json`
- `runtime/eig1_connector_breadth_fixtures.json`
- existing connector identity and mediation modules:
  - `vllm_agent_gateway/connectors/identity.py`
  - `vllm_agent_gateway/connectors/mediator.py`
  - `vllm_agent_gateway/connectors/catalog.py`

## Output

The validator writes an `eig2_actor_scope_breadth_report` JSON artifact under:

```text
runtime-state/eig2-actor-scope-breadth/
```

The report includes scoped manifest validation, actor/scope case outcomes, actor-context negative controls, recovery-guidance checks, and replay-safe audit summaries. It must not retain raw fixture arguments or raw auth subjects.

## Run

```bash
python3 scripts/validate_eig2_actor_scope_breadth.py
python3 -m pytest tests/regression/test_eig2_actor_scope_breadth.py -q
```

On Windows PowerShell:

```powershell
python scripts/validate_eig2_actor_scope_breadth.py
python -m pytest tests/regression/test_eig2_actor_scope_breadth.py -q
```

## Pass Criteria

The gate passes only when:

- work-tracking read succeeds with `work:read` and without `work:write`,
- work-tracking write dry-run succeeds with `work:write` and without `work:read`,
- structured business-record read succeeds with `records:read`,
- unrelated connector scopes do not authorize another connector,
- missing read and write scopes fail closed with `connector_scope_denied`,
- denied scoped operations include recovery guidance naming missing scopes,
- malformed, expired, anonymous, and missing actor contexts fail closed,
- operation-level required scopes are subsets of connector-declared scopes,
- runtime registry and target repository mutation flags remain false,
- raw auth subjects and raw arguments are not retained in report artifacts.

## Next Phase

Phase 294 expands approval replay breadth. It should reuse the same controller-owned connector invocation and operation-scope enforcement path, then add wrong-actor, wrong-session, wrong-request, stale-approval, scope-change, and replay-safe audit negative controls.
