# Contextless Handoff Dry Run

Phase 233 proves the refreshed handoff can be followed without private chat context.

This phase does not add a new runtime. It validates the proof package produced by existing gates.

## What It Proves

- Phase 232 handoff docs are fresh and marked `handoff_ready`.
- External tester dry run passes live through AnythingLLM using `http://127.0.0.1:8500/v1`.
- Feedback capture writes a `workflow_feedback.record` artifact linked to the workflow-router run.
- The Python-service small-repo prompt passes through gateway and AnythingLLM.
- The large-context `P221-LC-001` prompt passes through gateway and AnythingLLM.
- A contextless blind audit defines the expected handoff proof before local results are judged.

## Required Live Commands

```bash
python3 scripts/validate_onboarding_release_handoff_refresh.py
python3 scripts/validate_release_channels.py \
  --output-path runtime-state/release-channels/phase233.json
python3 scripts/validate_security_policy.py \
  --output-path runtime-state/security-policy/phase233.json
python3 scripts/run_first_time_user_doctor.py \
  --output-path runtime-state/phase233/phase233-first-time-user-doctor.json
python3 scripts/validate_runtime_recovery_reliability_rebaseline.py \
  --restart-managed-stack \
  --restart-vllm-container vllm-qwen3 \
  --timeout-seconds 900

python3 scripts/validate_external_tester_dry_run.py \
  --live-runtime \
  --include-feedback \
  --output-path runtime-state/phase233/phase233-external-tester-dry-run.json

python3 scripts/validate_external_tester_onboarding.py \
  --output-path runtime-state/external-tester-onboarding/phase233-static.json

python3 scripts/validate_external_tester_onboarding.py \
  --live-anythingllm \
  --include-feedback \
  --case-id ONB-001 \
  --output-path runtime-state/external-tester-onboarding/phase233-live-onb-001.json

python3 scripts/validate_multi_repo_fixtures_live.py \
  --case-id python-service-code-explanation \
  --case-id python-service-endpoint-route-lookup \
  --case-id python-service-schema-lookup \
  --live-anythingllm \
  --port-health \
  --output-path runtime-state/skill-library-scaling/phase233/phase233-small-skill-admission-pilot-live.json

python3 scripts/validate_small_skill_admission_pilot.py \
  --live-report-path runtime-state/skill-library-scaling/phase233/phase233-small-skill-admission-pilot-live.json \
  --output-path runtime-state/skill-library-scaling/phase233/phase233-small-skill-admission-pilot-report.json \
  --markdown-output-path runtime-state/skill-library-scaling/phase233/phase233-small-skill-admission-pilot-report.md

python3 scripts/validate_large_context_usability_live_closeout.py \
  --live \
  --allow-partial \
  --case-id P221-LC-001 \
  --output-path runtime-state/phase233/phase233-large-context-live-report.json \
  --markdown-output-path runtime-state/phase233/phase233-large-context-live-report.md \
  --timeout-seconds 900
```

## Final Gate

```bash
python3 scripts/validate_contextless_handoff_dry_run.py
```

Expected marker:

```text
PHASE233 CONTEXTLESS HANDOFF DRY RUN PASS
```

Examples: [docs/examples/contextless-handoff-dry-run.md](docs/examples/contextless-handoff-dry-run.md)
