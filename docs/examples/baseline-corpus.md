# Baseline Corpus Examples

## Validate Current Local Proof

Use this when `runtime-state/` contains the latest local eval and comparison artifacts:

```bash
python scripts/validate_baseline_corpus.py --require-artifacts --output-path runtime-state/baseline-corpus/baseline-corpus-report.json
```

Expected pass summary:

```text
BASELINE CORPUS GOVERNANCE {"entry_count": 4, "error_count": 0, "stable_entry_count": 4}
BASELINE CORPUS GOVERNANCE PASS
```

## Validate A Clean Clone Shape

Use this when local runtime proof artifacts are not present:

```bash
python scripts/validate_baseline_corpus.py
```

This mode still validates committed prompt cases, committed blind baselines, source hashes, source-order policy, local-eval summaries, comparison summaries, repair status, and holdout counts.

## Review A Failure

Open the generated report:

```bash
python -m json.tool runtime-state/baseline-corpus/baseline-corpus-report.json
```

Common failures and intended action:

- `prompt_cases.sha256 is stale`: rerun the prompt-case validator, rerun local eval and comparison, then update the corpus hash after proof is stable.
- `blind_baselines case IDs do not match prompt cases`: collect missing blind baselines before running local-model output.
- `local_eval.routes missing required route`: rerun the eval through both gateway and AnythingLLM.
- `comparison.critical_finding_count must be 0`: repair the smallest harness gap, rerun target and holdouts, then regenerate comparison proof.
- `repair_status cannot be not_required`: record the accepted repair and holdout rerun status.

## Add A New Stable Entry

1. Add or update the prompt cases under `runtime/`.
2. Collect the blind baseline before local output.
3. Run the local eval through gateway and AnythingLLM.
4. Run the comparison script.
5. Add a corpus entry to `runtime/baseline_corpus.json`.
6. Run:

```bash
python scripts/validate_baseline_corpus.py --require-artifacts
python -m pytest tests/regression/test_baseline_corpus.py -q
```

Do not mark a prompt family stable if the corpus validator reports missing local response proof, missing comparison proof, unresolved critical/high findings, stale source hashes, or missing holdout status.
