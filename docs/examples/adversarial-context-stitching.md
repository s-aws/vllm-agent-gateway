# Adversarial Context Stitching Examples

Generate the continuous-validation fixture:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_adversarial_context_stitching.py
```

The command writes:

```text
runtime-state/phase278/fixture/standard/prompt.txt
runtime-state/phase278/fixture/zero_overlap/chunk-manifest.json
runtime-state/phase278/fixture/randomized_retrieval_order/chunk-manifest.json
runtime-state/phase278/fixture/expected-answer.txt
runtime-state/phase278/phase278-adversarial-context-stitching-report.json
```

Feed the generated standard, zero-overlap, and randomized-retrieval-order prompts through the workflow-router gateway and score each answer:

```bash
python3 scripts/validate_adversarial_context_stitching.py \
  --live-gateway \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --model-base-url http://127.0.0.1:8000/v1
```

This command should pass each mode through the supplied-corpus QA route. A `missing_target_root_for_coding_request` response is a valid failure signal: it means routing blocked the test before the corpus answer contract could run.

The successful live route writes answer artifacts in the workflow-router run directory:

```text
supplied-corpus-qa-answer.txt
supplied-corpus-qa-extraction.json
```

Score an answer captured from another surface, including AnythingLLM, without rerunning the model:

```bash
python3 scripts/validate_adversarial_context_stitching.py \
  --answer-file /path/to/captured-answer.txt
```

Use the zero-overlap and randomized retrieval-order manifests when validating retrieval implementations:

```bash
python3 scripts/validate_adversarial_context_stitching.py
cat runtime-state/phase278/fixture/zero_overlap/chunk-manifest.json
cat runtime-state/phase278/fixture/randomized_retrieval_order/chunk-manifest.json
```

The answer must preserve these outcomes:

- Production launch date is December 3, 2026.
- United States and Canada may proceed; EU may not.
- EU rollout is blocked because the DPA has not been signed.
- Payments API v3 is mandatory for production; v2 is sandbox-only or obsolete for production.
- Contract cost is `$224,400`; CFO approval is not required because it is below `$240,000`.
- Emergency kill-switch code is `ORCHID-17`.
- Sentinel sequence is `ALPHA-19`, `BRAVO-27`, `CHARLIE-08`, `DELTA-66`.
- Obsolete facts are explicitly identified instead of controlling the final answer.
