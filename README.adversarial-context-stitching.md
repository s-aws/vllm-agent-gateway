# Adversarial Context Stitching

Phase 278 adds a deterministic large-context fixture for cross-chunk synthesis, precedence handling, boundary loss, and hallucinated reconciliation.

The fixture is intentionally small enough to run often, but hostile enough to catch the failures that make large-context chat unusable: superseded launch facts, EU legal blockers, production API precedence, cost math, split boundary values, and document-order sentinels.

## What It Validates

- The generated Meridian Gate corpus contains filler blocks large enough to force chunking in normal retrieval configurations.
- The emergency kill-switch value is split across SECTION 05 and SECTION 06 and must be reconstructed as `ORCHID-17`.
- The expected answer preserves all eight required outcomes.
- A captured answer fails hard if it allows EU rollout, uses November 15 as the controlling launch date, allows Payments API v2 in production, miscalculates cost or CFO approval, loses `ORCHID-17`, or changes sentinel order.
- The fixture emits standard, zero-overlap, and randomized retrieval-order manifests for future release validation.

## Run It

Generate the fixture and validate the built-in expected answer:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_adversarial_context_stitching.py
```

Score a captured gateway or model answer:

```bash
python3 scripts/validate_adversarial_context_stitching.py \
  --answer-file runtime-state/phase278/fixture/live-gateway-answer.txt
```

Run the generated standard prompt through the workflow-router gateway and score the response:

```bash
python3 scripts/validate_adversarial_context_stitching.py --live-gateway
```

The live gateway command is intentionally fail-closed. If the gateway routes the prompt to an unrelated workflow or asks for a repository target instead of answering the supplied corpus, the report fails and records the captured answer. That is a product gap, not a passing synthesis result.

Expected marker:

```text
PHASE278 ADVERSARIAL CONTEXT STITCHING PASS
```

## Artifacts

- `runtime-state/phase278/fixture/standard/prompt.txt`
- `runtime-state/phase278/fixture/zero_overlap/chunk-manifest.json`
- `runtime-state/phase278/fixture/randomized_retrieval_order/chunk-manifest.json`
- `runtime-state/phase278/fixture/expected-answer.txt`
- `runtime-state/phase278/phase278-adversarial-context-stitching-report.json`

## Boundary

This is a validation fixture and answer scorer. It does not introduce a new retrieval implementation, a new chat endpoint, or a raw 500k prompt-serving claim. The live path is optional so the fixture can remain part of continuous validation even when the local model stack is not running.

Current live gap: the first Phase 278 live gateway run returned `missing_target_root_for_coding_request` instead of answering the supplied corpus. The fixture therefore proves the gap is now measurable; a follow-up route/contract phase is required before live corpus-QA synthesis can be treated as release-ready.

Examples: [docs/examples/adversarial-context-stitching.md](docs/examples/adversarial-context-stitching.md).
