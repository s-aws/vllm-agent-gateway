# Output Format Parity Examples

## Full Live Gate

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_output_format_parity_live.py \
  --output-path runtime-state/output-format-parity/phase124-output-format-parity-live.json \
  --timeout-seconds 900
```

This requires:

- localhost model on `8000`
- controller/gateway/proxy ports running
- AnythingLLM available at `http://127.0.0.1:3001`
- `ANYTHINGLLM_API_KEY` in the Bash environment
- both frozen Coinbase fixtures present

## Narrow To One Case During Repair

Use a single case only while repairing a known formatter issue:

```bash
python3 scripts/validate_output_format_parity_live.py \
  --case-id CQ116-001 \
  --timeout-seconds 900
```

Do not treat a one-case run as Phase 124 completion proof.

## Review The Report

Open:

```text
runtime-state/output-format-parity/phase124-output-format-parity-live.json
```

Review each case in this order:

1. `responses.gateway.status`
2. `responses.anythingllm.status`
3. `responses.gateway.json.parsed.inline_answer_contract`
4. `responses.anythingllm.json.parsed.inline_answer_contract`
5. `mutation_proof.target_changed_files`
6. `mutation_proof.target_git_changed`

The important field is `inline_answer_contract.text`. It should be the same answer body a tester can review in the default chat response, not just a pointer to an artifact file.
