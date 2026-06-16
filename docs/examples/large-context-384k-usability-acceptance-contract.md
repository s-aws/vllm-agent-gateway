# Large-Context 384k Usability Acceptance Contract Examples

Run the static contract gate:

```bash
python3 scripts/validate_large_context_384k_usability_acceptance_contract.py
```

Inspect the target and next-phase count:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase258/phase258-large-context-384k-usability-acceptance-contract-report.json").read_text())
print(report["summary"]["target_estimated_project_tokens"])
print(report["summary"]["required_followup_phase_count"])
print(report["summary"]["phase258_ready"])
PY
```

Expected target:

```text
384000
```

This gate is static. The live proof comes later through fixture/index readiness, stale-index rejection, gateway validation, AnythingLLM validation, and clean-clone replay.
