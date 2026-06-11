# Chat Answer Contract Hardening Example

Run the Phase 180 gate:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_chat_answer_contract_hardening.py \
  --output-path runtime-state/phase180/phase180-chat-answer-contract-report.json \
  --markdown-output-path runtime-state/phase180/phase180-chat-answer-contract-report.md
```

Expected output includes:

```text
PHASE180 CHAT ANSWER CONTRACT PASS
```

Inspect the summary:

```bash
jq '.summary' runtime-state/phase180/phase180-chat-answer-contract-report.json
```

Inspect failed cases:

```bash
jq '.cases[] | select(.status != "passed")' runtime-state/phase180/phase180-chat-answer-contract-report.json
```

A passing report means every governed Phase 180 workflow family rendered a standalone chat answer before artifact links in `format_a`, and exposed the matching answer contract in JSON.
