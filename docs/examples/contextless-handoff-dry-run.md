# Contextless Handoff Dry Run Examples

Run from Bash/WSL after vLLM, the gateway/proxies, controller, and AnythingLLM are running.

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
```

## Generate Source Reports

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

## Validate The Handoff Package

```bash
python3 scripts/validate_contextless_handoff_dry_run.py
```

Expected marker:

```text
PHASE233 CONTEXTLESS HANDOFF DRY RUN PASS
```

## Inspect The Report

```bash
python3 - <<'PY'
import json
from pathlib import Path

path = Path("runtime-state/phase233/phase233-contextless-handoff-dry-run-report.json")
report = json.loads(path.read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
print("missing:", report["missing_required_surfaces"])
for artifact in report["source_artifacts"]:
    print(f"{artifact['name']}: {artifact['status']} {artifact['path']}")
PY
```
