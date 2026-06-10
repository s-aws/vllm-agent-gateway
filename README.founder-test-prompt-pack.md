# Founder Test Prompt Pack

Phase 137 defines the stable founder test prompt pack used after the four-prompt smoke path passes.

The pack expands read-only coverage without adding draft/apply prompts or advanced refactor scope.

## Pack Tiers

- `smoke`: `P01`, `P02`, `P03`, `P22`
- `expanded_read_only`: `P04`, `P05`, `P06`, `P08`, `P09`, `P10`, `P13`, `P17`, `P19`, `P21`

## Command

From Bash/WSL:

```bash
python3 scripts/validate_founder_test_prompt_pack.py \
  --require-artifacts \
  --output-path runtime-state/founder-test-prompt-pack/phase137/phase137-founder-test-prompt-pack.json
```

Expected marker:

```text
FOUNDER TEST PROMPT PACK PASS
```

## Current Result

The current pack has:

- `case_count=14`
- `smoke_case_count=4`
- `expanded_read_only_case_count=10`
- `workflow_count=3`
- `target_root_count=2`

## Guardrails

The validator rejects:

- unknown or duplicate prompt IDs
- draft-only, disposable-copy, or apply-proof prompt cases
- missing smoke cases
- missing `code_investigation.plan`, `code_context.lookup`, or `task.decompose` coverage
- missing coverage for either frozen Coinbase fixture
