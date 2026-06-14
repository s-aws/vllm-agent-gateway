# Chat-Visible Answer Contract Inventory

Phase 200 inventories the answer contract for every currently supported Priority 0 prompt family.

This phase does not enforce new behavior or rerun live prompts. It defines what each supported workflow must return in chat so Phase 201 can add deterministic enforcement without guessing.

## What It Inventories

- Supported prompt families from `runtime/prompt_skill_coverage.json`.
- Stable Priority 0 baseline families from `runtime/baseline_corpus.json`.
- Founder field prompt coverage from `runtime/prompt_catalogs/founder_field_v1.json`.
- Required chat sections for each workflow and prompt family.
- Evidence expectations, safety boundaries, run traceability, and output-format behavior.

## Outputs

- `runtime-state/phase200/phase200-chat-visible-answer-contract-inventory-report.json`
- `runtime-state/phase200/phase200-chat-visible-answer-contract-inventory-report.md`

The report contains `contract_records` for each implemented prompt-family entry, plus baseline and founder-catalog summaries.

## Command

```bash
python3 scripts/validate_chat_visible_answer_contract_inventory.py
```

Expected passing marker:

```text
PHASE200 CHAT VISIBLE ANSWER CONTRACT INVENTORY PASS
```

## Boundary

Phase 200 is an inventory gate. It should not change renderers, routing, prompt catalogs, or live response behavior. Enforcement belongs to Phase 201.
