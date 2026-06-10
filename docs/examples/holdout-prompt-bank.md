# Holdout Prompt Bank Examples

Validate the committed bank and committed prompt/baseline inputs:

```bash
python scripts/validate_holdout_prompt_bank.py
```

Validate against local runtime proof artifacts:

```bash
python scripts/validate_holdout_prompt_bank.py --require-artifacts --output-path runtime-state/holdout-prompt-bank/holdout-prompt-bank-report.json
```

Review failures:

```bash
python -m json.tool runtime-state/holdout-prompt-bank/holdout-prompt-bank-report.json
```

Common failures:

- `holdout_case_ids must exactly match prompt cases marked holdout=true`: update the bank or prompt catalog together.
- `local_eval case ... missing route`: rerun the local eval with gateway and AnythingLLM enabled.
- `comparison case ... pass must be true`: inspect the comparison miss before accepting the repair.
- `score must be >= 85`: the holdout did not meet the stable chat-quality floor.
- `target_changed_files must be {}`: the holdout run mutated protected fixture state.
- `target_coverage.justification is required`: the bank does not explain why a frozen Coinbase fixture is absent from the holdout pair.

The generated report includes `proof_hashes` for prompt cases, blind baselines, local eval, and comparison artifacts so the holdout result is bound to the exact evidence it validated.
