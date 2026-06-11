# Chat Answer Contract Hardening

Phase 180 proves that supported Priority 0 workflows return useful chat-visible answers before artifact links.

Use this gate when changing controller response rendering, workflow-router summaries, inline artifact answer renderers, or Priority 0 chat-quality policy.

## What It Checks

- default `format_a` output is answer-first, not artifact-first
- JSON output exposes the same primary or inline answer contract
- read-only investigation answers include beginning point, related tests, verification commands, and source mutation status
- schema evidence answers include fields, source refs, and source mutation status
- request-flow answers include flow steps, related tests, verification, and source mutation status
- change-boundary answers include in-scope/out-of-scope files, risks or unknowns, verification, and source mutation status
- generic no-target chat gives a direct answer and mutation status
- format-selected output uses the same rendered answer contract
- mixed-route cases do not let a weaker artifact become the primary answer

Artifacts remain available for deeper review, but they are not the primary answer.

## Run

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_chat_answer_contract_hardening.py
```

Expected marker:

```text
PHASE180 CHAT ANSWER CONTRACT PASS
```

## Outputs

- Policy: `runtime/chat_answer_contract_hardening_policy.json`
- Report: `runtime-state/phase180/phase180-chat-answer-contract-report.json`
- Markdown: `runtime-state/phase180/phase180-chat-answer-contract-report.md`
- Synthetic fixtures: `runtime-state/phase180/chat-answer-contract-fixtures/`

`status=failed` means a supported workflow family can still produce an artifact-only, artifact-first, or incomplete chat answer and must be repaired before advancing.
