# EIG Stable Handoff Integration Examples

Run the Phase 304 static handoff gate:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_eig_stable_handoff_integration.py \
  --output-path runtime-state/eig-stable-handoff-integration/phase304-validation.json
```

Expected marker:

```text
EIG STABLE HANDOFF INTEGRATION PASS
```

Inspect the summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/eig-stable-handoff-integration/phase304-validation.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
PY
```

The report should show:

```text
status=passed
missing_doc_count=0
missing_runtime_file_count=0
missing_script_count=0
missing_marker_count=0
phase305_ready=true
```

Use this gate before calling the EIG proof chain ready for a stable tester. It only proves release-facing orientation and required proof references. It does not replace live Phase 296 or Phase 303 closeout validation.
