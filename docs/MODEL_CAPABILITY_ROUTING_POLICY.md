# Model Capability Routing Policy

Phase 78 defined advisory model capability profiles. Phase 100 makes the active profile a fail-closed workflow-router gate. It still does not enable automatic model selection.

## Policy Source

Profiles are generated from `model_portability_report` artifacts:

```text
scripts/generate_model_capability_profile.py
```

Each profile records:

- `route_stability`
- `output_contract_reliability`
- `semantic_answer_quality`
- `latency`
- `timeout_behavior`
- `safe_apply_readiness`
- `task_policy`

Runtime enforcement is configured in:

```text
runtime/model_capability_routing.json
```

## Capability Rules

| Capability | Proven When | Blocking Evidence |
| --- | --- | --- |
| `route_stability` | portability report passed, representative L1 suite passed, and classifier failures are zero | classifier failures or wrong workflow/rule evidence |
| `output_contract_reliability` | portability report passed and output-contract failures are zero | schema, malformed JSON, invalid model-route, or output-contract failures |
| `semantic_answer_quality` | founder field suite passed and model-quality failures are zero | missing semantic markers, forbidden markers, or classified model-quality failures |
| `latency` | source acceptance report contains duration metrics | no timing metrics means `unknown`, not failure |
| `timeout_behavior` | portability report passed and timeout failures are zero | timeout, timed out, or body-byte failures |
| `safe_apply_readiness` | controlled apply suite passed | only disposable-copy and draft packet boundaries are proven |

## Task Policy

| Task Type | Runtime Status Rule | Current Boundary |
| --- | --- | --- |
| `read_only_l1` | route may proceed only when profile `task_policy.read_only_l1.status=approved` | tested scope only |
| `draft_only_l1` | route may proceed only when profile `task_policy.draft_only_l1.status=approved` and the request remains draft-only | draft packet design only |
| `approval_gated_l1` | route may proceed only when profile `task_policy.approval_gated_l1.status=conditional` and explicit controller approval is present | explicit controller approval remains required |
| `l2_read_only` | route may proceed only when profile `task_policy.l2_read_only.status=approved` | read-only only |
| `apply_prep` | route may proceed only when profile `task_policy.apply_prep.status=conditional` and explicit packet/disposable approval is present | disposable-copy or draft packet boundary only |
| `real_apply` | always blocked by current policy | later approved phase must define this separately |
| `automatic_model_selection` | not approved | still disabled; Phase 100 enforces only the active configured profile |

## Routing Use

Profiles are used by `workflow_router.plan` to decide whether the selected deterministic route may proceed to model-involved downstream work.

Profiles must not:

- silently change selected workflows
- change which skills are selected
- change tool exposure
- bypass approval
- enable real repository mutation
- promote a model to production automatically

The gate records `model_capability_routing` in `route-decision.json`. Blocked routes return no downstream execution and an empty `controller_request_preview`.

## Current Known Limitation

Existing V1 acceptance reports do not record suite timing. Phase 78 therefore sets `latency=unknown` even when all functional suites pass. A later phase should add timing capture before latency can influence routing.

## Proof Artifacts

The initial Phase 78 profiles are:

```text
runtime-state/model-capability-profiles/phase78-live-current-profile.json
runtime-state/model-capability-profiles/phase78-offline-baseline-profile.json
```

Both are expected to be `warning` profiles because latency is unknown and real apply is not approved.

Phase 100 enforcement proof is recorded in the roadmap and includes:

- blocked-profile regression for read-only L1
- blocked-profile regression for apply prep
- positive route proof for approved L1/L2 current profile
- live Bash gateway and AnythingLLM validation on both frozen fixtures
