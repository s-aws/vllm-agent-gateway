# Security Policy Examples

## Run The Release-Candidate Security Gate

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_security_policy.py \
  --output-path runtime-state/security-policy/release-candidate.json
```

Expected result:

```text
SECURITY POLICY PASS
```

## Development-Only Run Without Secret Scan

Use this only when the local secret is unavailable:

```bash
python scripts/validate_security_policy.py \
  --skip-secret-value-scan \
  --output-path runtime-state/security-policy/dev-no-secret-scan.json
```

Expected result:

```text
SECURITY POLICY PASS
```

The report will mark `secret.value_scan` as `skipped`.

## Review A Failure

```bash
python - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/security-policy/release-candidate.json").read_text())
print(report["summary"]["failed_check_ids"])
for check in report["checks"]:
    if check["status"] == "failed":
        print(check["id"])
        print(check["next_action"])
PY
```

Do not print or paste secret values while debugging. The report intentionally records only secret variable names and file paths.
