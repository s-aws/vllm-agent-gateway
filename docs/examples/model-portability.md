# Model Portability Examples

These examples run or classify the Phase 72 model portability gate.

## Live Candidate Run

Run from Bash after the stack is pointed at the candidate model and AnythingLLM targets `http://127.0.0.1:8500/v1`:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_model_portability.py \
  --candidate-id smaller-local-candidate \
  --candidate-description "Smaller local model candidate behind localhost:8000" \
  --candidate-model-base-url http://127.0.0.1:8000/v1 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900 \
  --command-timeout-seconds 3600
```

Expected pass markers:

```text
MODEL PORTABILITY REPORT ...
MODEL PORTABILITY SUMMARY ...
MODEL PORTABILITY PASS
```

## Existing Acceptance Report

Classify an existing V1 acceptance report without another live run:

```bash
python3 scripts/validate_model_portability.py \
  --candidate-id already-tested-candidate \
  --skip-live-acceptance \
  --skip-model-probe \
  --acceptance-report-path runtime-state/v1-acceptance/phase71-v1-acceptance.json
```

This writes a new model portability report while preserving the original acceptance report.

## Generate Capability Profile

After a portability report exists, generate the Phase 78 advisory profile:

```bash
python scripts/generate_model_capability_profile.py \
  --portability-report-path runtime-state/model-portability/phase72-live-current.json \
  --output-path runtime-state/model-capability-profiles/phase78-live-current-profile.json \
  --markdown-output-path runtime-state/model-capability-profiles/phase78-live-current-profile.md
```

Review the profile before using a model candidate for broader testing. Phase 78 profiles do not enable automatic model selection.

## Expected JSON Fields

```text
kind=model_portability_report
candidate.candidate_id=...
candidate_model_probe.model_ids=[...]
acceptance_report.status=passed|failed
classification_summary.harness=...
classification_summary.classifier=...
classification_summary.prompt=...
classification_summary.model_quality=...
classified_failures=[...]
```

## Failure Review

When the gate fails, start with `classified_failures[0]`:

```text
source=...
classification=harness|classifier|prompt|model_quality|unknown
matched_terms=[...]
recommended_next_action=...
```

Do not change router rules for `harness` failures. Fix runtime setup first.
