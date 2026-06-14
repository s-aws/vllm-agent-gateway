# Chat-Visible Answer Contract Enforcement

Phase 201 turns the Phase 200 inventory into a deterministic enforcement gate.

The gate proves that every supported Priority 0 prompt-family contract has passing default `format_a` and `json` fixtures rendered through the existing controller chat formatter, and that bad response shapes fail closed before they can be treated as useful chat answers.

## What It Enforces

- Answer-first chat content for supported workflows.
- Evidence markers instead of unsupported claims.
- Safety boundaries, including source mutation status.
- Run traceability through workflow-router run IDs and selected workflow metadata.
- Default `format_a` and requested `json` output formats.
- Contract-specific details from the Phase 200 inventory, including selected workflow, prompt family, required sections, evidence expectations, and safety boundaries.
- Fail-closed handling for artifact-only answers, vague marker-only answers, missing evidence, missing safety boundaries, unsupported mutation claims, and missing output-format metadata.

## Inputs

- `runtime/chat_visible_answer_contract_enforcement_policy.json`
- `runtime-state/phase200/phase200-chat-visible-answer-contract-inventory-report.json`

The Phase 200 report must already be passing and must contain the current `contract_records`.

## Outputs

- `runtime-state/phase201/phase201-chat-visible-answer-contract-enforcement-report.json`
- `runtime-state/phase201/phase201-chat-visible-answer-contract-enforcement-report.md`

## Command

```bash
python3 scripts/validate_chat_visible_answer_contract_enforcement.py
```

Expected passing marker:

```text
PHASE201 CHAT VISIBLE ANSWER CONTRACT ENFORCEMENT PASS
```

## Boundary

Phase 201 is an acceptance gate. It does not add a second response renderer and does not replace the controller chat output path; positive fixtures call the same controller formatter used by chat completions. Phase 202 is responsible for refreshing live gateway and AnythingLLM proof against this contract.
