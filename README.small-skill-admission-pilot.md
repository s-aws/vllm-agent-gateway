# Small Skill Admission Pilot

Phase 230 admits `FX-001`, the Python-service fixture coverage candidate, through the governed skill-library path.

This phase does not create a new runtime skill. It proves that the existing `endpoint-route-locator` and `data-model-schema-locator` skills can route naturally against a non-Coinbase Python service fixture through the workflow-router gateway and AnythingLLM without manual skill injection.

## What It Proves

- `FX-001` is implemented prompt coverage, not theoretical roadmap inventory.
- The endpoint/message-handler prompt routes to `code_investigation.plan` with `endpoint-route-locator`.
- The schema prompt routes to `code_investigation.plan` with `data-model-schema-locator`.
- Gateway and AnythingLLM both return controller-backed artifact proof.
- The protected fixture remains read-only.
- The blind baseline is durable and includes evidence expectations before local-model output is judged.

## Validation

Run the live proof first:

```bash
python3 scripts/validate_multi_repo_fixtures_live.py \
  --case-id python-service-endpoint-route-lookup \
  --case-id python-service-schema-lookup \
  --live-anythingllm \
  --port-health \
  --output-path runtime-state/skill-library-scaling/phase230/phase230-small-skill-admission-pilot-live.json
```

Then run the Phase 230 gate:

```bash
python3 scripts/validate_small_skill_admission_pilot.py
```

Examples: [docs/examples/small-skill-admission-pilot.md](docs/examples/small-skill-admission-pilot.md)
