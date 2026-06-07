# Advanced Refactor Readiness Examples

These examples generate or inspect the Phase 105 readiness gate. They do not promote broad refactor orchestration to stable.

## Generate The Canonical Gate Report

```bash
cd /mnt/c/agentic_agents
python3 scripts/report_advanced_refactor_readiness.py
```

Expected output:

```text
ADVANCED REFACTOR READINESS REPORT ...
ADVANCED REFACTOR READINESS SUMMARY {"readiness_status": "pilot_ready", ...}
ADVANCED REFACTOR READINESS PASS
```

The report is written to:

```text
runtime-state/advanced-refactor-readiness/phase105-readiness.json
```

## Generate With Explicit Evidence Paths

Use explicit paths when validating a fresh run instead of relying on the default Phase 96 through Phase 104 artifacts:

```bash
python3 scripts/report_advanced_refactor_readiness.py \
  --implementation-prep-report runtime-state/implementation-prep-expansion/phase96-implementation-prep-direct.json \
  --implementation-prep-report runtime-state/implementation-prep-expansion/phase96-implementation-prep-gateway.json \
  --implementation-prep-report runtime-state/implementation-prep-expansion/phase96-implementation-prep-anythingllm.json \
  --approval-continuation-report runtime-state/approval-continuation-robustness/phase97-approval-direct.json \
  --approval-continuation-report runtime-state/approval-continuation-robustness/phase97-approval-gateway.json \
  --approval-continuation-report runtime-state/approval-continuation-robustness/phase97-approval-anythingllm.json \
  --disposable-apply-report runtime-state/disposable-apply-expansion/phase98-direct.json \
  --disposable-apply-report runtime-state/disposable-apply-expansion/phase98-gateway.json \
  --disposable-apply-report runtime-state/disposable-apply-expansion/phase98-anythingllm.json \
  --multi-repo-report runtime-state/multi-repo-fixtures/phase101-gateway-anythingllm.json \
  --task-decomposition-report runtime-state/task-decomposition/phase102-live.json \
  --eval-repair-loop-report runtime-state/eval-repair-loop/phase104-live-failed-founder-repair.json \
  --model-policy-path runtime/model_capability_routing.json
```

## Inspect A Blocked Report

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/advanced-refactor-readiness/phase105-readiness.json").read_text())
for item in report["prerequisites"]:
    if item["status"] != "passed":
        print(item["id"], item["errors"])
PY
```

## Natural Prompt Behavior

When the canonical report is missing or blocked, natural advanced-refactor requests remain blocked by the workflow router:

```text
advanced_refactor_readiness_not_met
```

When the canonical report is `pilot_ready`, the router may run read-only `refactor.single_path` investigation and request packet-design approval. That is still not stable broad-refactor promotion and does not enable source apply.

## Live Gateway And AnythingLLM Validation

Start the stack with both frozen fixtures allowlisted:

```bash
CONTROLLER_ALLOWED_TARGET_ROOTS="/mnt/c/agentic_agents:/mnt/c/coinbase_testing_repo_frozen_tmp:/mnt/c/coinbase_testing_repo_frozen_tmp.github" \
  ./start-agent-prompt-proxies.sh
```

Then run:

```bash
python3 scripts/validate_advanced_refactor_readiness_live.py
```

Expected markers:

```text
PHASE105 LIVE NATURAL REPORT ...
PHASE105 LIVE NATURAL SUMMARY {"status": "passed", ...}
PHASE105 LIVE NATURAL PASS
```

The report confirms the natural prompt path through the workflow-router gateway and AnythingLLM on both frozen fixtures without source mutation.
