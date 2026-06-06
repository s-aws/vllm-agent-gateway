# Model Capability Routing Policy

Phase 78 defines advisory model capability profiles. It does not enable automatic model selection.

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

| Task Type | Advisory Status Rule | Current Phase 78 Boundary |
| --- | --- | --- |
| `read_only_l1` | approved when route stability, output contract, semantic quality, and representative L1 are proven | tested scope only |
| `draft_only_l1` | approved when representative L1 and approval boundary evidence are present | draft packet design only |
| `approval_gated_l1` | conditional when representative L1 and controlled apply proof are present | explicit controller approval remains required |
| `l2_read_only` | approved when representative L2, route stability, and semantic quality are proven | read-only only |
| `apply_prep` | conditional when controlled apply and representative L1 proof are present | disposable-copy or draft packet boundary only |
| `real_apply` | not approved | later approved phase must define this separately |
| `automatic_model_selection` | not approved | no runtime behavior change in Phase 78 |

## Routing Use

Profiles may be used to decide whether a model candidate is ready for manual testing or future routing-policy implementation.

Profiles must not:

- silently change selected workflows
- change which skills are selected
- change tool exposure
- bypass approval
- enable real repository mutation
- promote a model to production automatically

## Current Known Limitation

Existing V1 acceptance reports do not record suite timing. Phase 78 therefore sets `latency=unknown` even when all functional suites pass. A later phase should add timing capture before latency can influence routing.

## Phase 78 Proof Artifacts

The initial Phase 78 profiles are:

```text
runtime-state/model-capability-profiles/phase78-live-current-profile.json
runtime-state/model-capability-profiles/phase78-offline-baseline-profile.json
```

Both are expected to be advisory `warning` profiles because latency is unknown and real apply is not approved.
