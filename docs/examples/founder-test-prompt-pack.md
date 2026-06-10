# Founder Test Prompt Pack Examples

## Validate The Pack

```bash
python3 scripts/validate_founder_test_prompt_pack.py \
  --require-artifacts \
  --output-path runtime-state/founder-test-prompt-pack/phase137/phase137-founder-test-prompt-pack.json
```

Expected output:

```text
FOUNDER TEST PROMPT PACK {"case_count": 14, "expanded_read_only_case_count": 10, "smoke_case_count": 4, "target_root_count": 2, "tier_count": 2, "workflow_count": 3}
FOUNDER TEST PROMPT PACK PASS
```

## Inspect Selected Cases

```bash
python3 -c 'import json; from pathlib import Path; report=json.loads(Path("runtime-state/founder-test-prompt-pack/phase137/phase137-founder-test-prompt-pack.json").read_text()); print(json.dumps(report["tiers"], indent=2, sort_keys=True))'
```
