# Model Capability Profiles

Model capability profiles turn model-portability reports into advisory routing evidence.

They do not change controller routing, prompts, skills, tool policy, or model selection. Phase 78 profiles answer one narrower question: what has the current candidate model actually proven through the existing V1 acceptance path?

## When To Use It

Use this after a model-portability run when you need a durable profile for:

- route stability
- output contract reliability
- semantic answer quality
- latency evidence
- timeout behavior
- safe apply readiness
- task-level routing policy

Use `README.model-portability.md` first when the model has not been tested yet.

## Artifact Names

Profile JSON and Markdown reports are written under:

```text
runtime-state/model-capability-profiles/
```

The JSON artifact uses:

```text
kind=model_capability_profile
schema_version=1
```

## Generate A Profile

```bash
python scripts/generate_model_capability_profile.py \
  --portability-report-path runtime-state/model-portability/phase72-live-current.json \
  --output-path runtime-state/model-capability-profiles/phase78-live-current-profile.json \
  --markdown-output-path runtime-state/model-capability-profiles/phase78-live-current-profile.md
```

Expected marker:

```text
MODEL CAPABILITY PROFILE GENERATED
```

## Statuses

Capability statuses:

- `proven`: the source reports prove the capability for the tested scope.
- `partially_proven`: the source reports prove part of the behavior, but not enough for broad routing approval.
- `not_proven`: the source reports contain misses that block the capability.
- `unknown`: the source reports do not contain enough measurement.
- `not_approved`: the capability is intentionally outside current policy.

Task policy statuses:

- `approved`: advisory profile supports the task type for the tested scope.
- `conditional`: task type is only acceptable with explicit controller approval boundaries.
- `not_approved`: do not route this task type based on this profile.

## Current Phase 78 Boundary

Profiles are advisory only.

Automatic model selection is not enabled. Real repository apply is not approved by any Phase 78 profile. Latency remains `unknown` unless the source acceptance report records duration metrics.

## Routing Policy

See [docs/MODEL_CAPABILITY_ROUTING_POLICY.md](docs/MODEL_CAPABILITY_ROUTING_POLICY.md) for the policy table that maps profile evidence to allowed read-only L1, draft-only L1, approval-gated L1, L2, and apply-prep use.
