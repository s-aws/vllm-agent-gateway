# Natural Output Format Preference Examples

## Full Live Gate

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_natural_output_format_preference_live.py \
  --output-path runtime-state/natural-output-format-preference/phase144-natural-output-format-preference-live.json \
  --timeout-seconds 900
```

This requires:

- localhost model on `8000`
- controller/gateway/proxy ports running
- AnythingLLM available at `http://127.0.0.1:3001`
- `ANYTHINGLLM_API_KEY` in the Bash environment
- both frozen Coinbase fixtures present

## Narrow To One Case During Repair

```bash
python3 scripts/validate_natural_output_format_preference_live.py \
  --case-id NOFP-CQ116-001 \
  --timeout-seconds 900
```

Do not treat a one-case run as Phase 144 completion proof.

## Review The Report

Open:

```text
runtime-state/natural-output-format-preference/phase144-natural-output-format-preference-live.json
```

Review each case in this order:

1. `responses.gateway.preferences.default_format_a`
2. `responses.gateway.preferences.natural_format_a`
3. `responses.gateway.preferences.natural_json.request`
4. `responses.gateway.preferences.natural_json.parsed.inline_answer_contract`
5. `responses.gateway.preferences.unsupported_explicit_output_format.error.code`
6. `responses.gateway.preferences.unsupported_response_format.error.code`
7. `responses.anythingllm.preferences.default_format_a`
8. `responses.anythingllm.preferences.natural_format_a`
9. `responses.anythingllm.preferences.natural_json.parsed.inline_answer_contract`
10. `mutation_proof.target_changed_files`
11. `mutation_proof.target_git_changed`

The `natural_json.request.explicit_output_format_fields` list must be empty. If it is not empty, the test did not prove natural-language selection.
Unsupported format holdouts must return `unsupported_output_format`; otherwise the selector is silently accepting or ignoring an unsupported user request.
