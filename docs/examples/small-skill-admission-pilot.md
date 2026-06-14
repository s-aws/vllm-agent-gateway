# Small Skill Admission Pilot Examples

Phase 230 validates the smallest currently useful skill-library scaling step: admit one fixture/eval coverage candidate without adding a new runtime skill.

## Live Gateway And AnythingLLM Proof

```bash
python3 scripts/validate_multi_repo_fixtures_live.py \
  --case-id python-service-endpoint-route-lookup \
  --case-id python-service-schema-lookup \
  --live-anythingllm \
  --port-health \
  --output-path runtime-state/skill-library-scaling/phase230/phase230-small-skill-admission-pilot-live.json
```

Expected result:

```text
MULTI REPO FIXTURE GATEWAY PASS case=python-service-endpoint-route-lookup ...
MULTI REPO FIXTURE GATEWAY PASS case=python-service-schema-lookup ...
MULTI REPO FIXTURE ANYTHINGLLM PASS case=python-service-endpoint-route-lookup ...
MULTI REPO FIXTURE ANYTHINGLLM PASS case=python-service-schema-lookup ...
MULTI REPO FIXTURE PASS
```

## Admission Gate

```bash
python3 scripts/validate_small_skill_admission_pilot.py
```

Expected result:

```text
PHASE230 SMALL SKILL ADMISSION PILOT PASS
```

## What To Inspect

- `runtime/prompt_skill_coverage.json`: `FX-001` should be `implemented`.
- `runtime/phase230_small_skill_admission_blind_baseline.json`: blind expectations for handler and schema prompts.
- `runtime-state/skill-library-scaling/phase230/phase230-small-skill-admission-pilot-live.json`: gateway and AnythingLLM proof.
- `runtime-state/skill-library-scaling/phase230/phase230-small-skill-admission-pilot-report.json`: final gate result.
