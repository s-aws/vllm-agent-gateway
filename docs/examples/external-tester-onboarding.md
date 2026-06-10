# External Tester Onboarding Examples

## Minimum External Tester Dry Run

This is the first external tester command for the current stable path. Run it from Bash/WSL:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_external_tester_dry_run.py \
  --live-runtime \
  --include-feedback \
  --output-path runtime-state/external-tester-dry-run/phase147/phase147-external-tester-dry-run.json
```

Expected result:

```text
EXTERNAL TESTER DRY RUN PASS
```

The gate validates `ONB-001` through AnythingLLM at `http://127.0.0.1:8500/v1`, uses `ANYTHINGLLM_API_KEY`, records linked feedback, and checks protected fixture state.

## Validate The Prompt Pack

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_external_tester_onboarding.py \
  --output-path runtime-state/external-tester-onboarding/static.json
```

Expected result:

```text
EXTERNAL TESTER ONBOARDING PASS
```

## Run The First Live Prompt Through AnythingLLM

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_external_tester_onboarding.py \
  --live-anythingllm \
  --include-feedback \
  --case-id ONB-001 \
  --timeout-seconds 900 \
  --output-path runtime-state/external-tester-onboarding/onb-001-live.json
```

Expected result:

```text
EXTERNAL TESTER ONBOARDING PASS
```

The JSON report records:

- onboarding prompt case ID
- workflow-router run ID
- feedback run ID
- AnythingLLM preflight status
- protected fixture mutation status

## Manual AnythingLLM Prompt

Paste this into a fresh AnythingLLM thread:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what find_stealth_order_by_placed_order_id does in core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests.
```

Expected markers:

```text
workflow_router.plan completed
run_id: workflow-router-
Skill Selection:
Answer:
StealthOrderManager.find_stealth_order_by_placed_order_id
downstream_code_explanation
```

## Manual Feedback Prompt

Replace the run ID with the one returned by the onboarding prompt:

```text
Record feedback for run workflow-router-YYYYMMDDTHHMMSSffffffZ: useful: onboarding response was visible in chat. missing: expected one of the documented answer markers or source references.
```

Expected markers:

```text
workflow_feedback.record
run_id: workflow-feedback-
target_run_id
feedback_record
linked_run_found
```

## Review The Prompt Pack

```bash
python3 - <<'PY'
import json
from pathlib import Path
pack = json.loads(Path("runtime/external_tester_onboarding.json").read_text())
for case in pack["cases"]:
    print(case["case_id"], "-", case["title"])
PY
```

The first-test pack should contain only read-only prompts. Broad refactor, approval continuation, and disposable-copy apply prompts should stay out of external onboarding.
