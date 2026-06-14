# Evidence Quality Live Rerun Examples

Use these commands from Bash/WSL because the policy references `/mnt/c/...` fixture roots.

## Offline Preflight

```bash
python3 scripts/validate_evidence_quality_live_rerun.py
```

This validates the policy, Phase 206 report, Phase 207 report, required target roots, and live-run shape without calling the local model or AnythingLLM.

The offline preflight writes to:

```text
runtime-state/phase208/phase208-evidence-quality-live-rerun-preflight-report.json
runtime-state/phase208/phase208-evidence-quality-live-rerun-preflight-report.md
```

## Live Closeout

Start the local model manually, then restart the gateway/proxies if code changed:

```bash
./stop-agent-prompt-proxies.sh
./start-agent-prompt-proxies.sh
```

Run the full live gate:

```bash
python3 scripts/validate_evidence_quality_live_rerun.py --live
```

The full gate runs four Phase 206 audit prompts plus four Phase 208 holdout prompts across two fixture roots and two surfaces, for 32 live responses.

The live closeout writes to:

```text
runtime-state/phase208/phase208-evidence-quality-live-rerun-report.json
runtime-state/phase208/phase208-evidence-quality-live-rerun-report.md
```

## Focused Smoke

Use a single case and one fixture root while iterating on a repair:

```bash
python3 scripts/validate_evidence_quality_live_rerun.py --live --allow-partial \
  --case-id P206-EV-001 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

Use gateway only when isolating AnythingLLM configuration drift:

```bash
python3 scripts/validate_evidence_quality_live_rerun.py --live --allow-partial \
  --skip-anythingllm \
  --case-id P206-EV-001 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

Use a holdout id to test overfit protection:

```bash
python3 scripts/validate_evidence_quality_live_rerun.py --live --allow-partial \
  --skip-anythingllm \
  --case-id P208-HO-001 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

## Report Review

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase208/phase208-evidence-quality-live-rerun-report.json").read_text())
print(report["status"], report["summary"])
for item in report.get("responses", []):
    if item.get("status") != "passed":
        print(
            item["surface"],
            item.get("live_case_id"),
            "baseline",
            item["audit_case_id"],
            item["target_root"],
            item.get("baseline_comparison", {}).get("score"),
            item["errors"],
        )
PY
```
