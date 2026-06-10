# V1 Product Readiness Review

Phase 155 decides whether the current V1 local-model harness is ready for founder testing against the original product goal: semi-well-defined natural-language prompts should produce useful chat-visible answers through the current local model, skills, tools, gateway, and AnythingLLM path.

This is a review gate. It does not rerun every expensive live suite and does not expand supported scope.

## What It Reads

Policy:

```text
runtime/v1_product_readiness_review_policy.json
```

Required evidence:

```text
runtime-state/stable-chat-quality-release/phase130/phase130-stable-chat-quality-release-report.json
runtime-state/release-notes/phase146/phase146-release-notes-report.json
runtime-state/stable-release-reset-rehearsal/phase153/phase153-live-report.json
runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report.json
runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report-current-model-compatibility.json
```

## What It Produces

JSON:

```text
runtime-state/v1-product-readiness-review/phase155/phase155-v1-product-readiness-review-report.json
```

Markdown:

```text
runtime-state/v1-product-readiness-review/phase155/phase155-v1-product-readiness-review-report.md
```

The report includes:

- go/no-go recommendation
- supported workflows
- unsupported workflows
- release blockers
- monitored risks
- source artifact hashes
- summary of model identity, prompt-family coverage, output-format coverage, and reset/recovery evidence

## Recommendation Meanings

- `go_for_founder_testing`: current evidence supports V1 founder testing within the documented scope.
- `no_go`: at least one required artifact, status, readiness marker, model-swap decision, documentation marker, or policy boundary failed.

## Run

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_v1_product_readiness_review.py \
  --output-path runtime-state/v1-product-readiness-review/phase155/phase155-v1-product-readiness-review-report.json \
  --markdown-output-path runtime-state/v1-product-readiness-review/phase155/phase155-v1-product-readiness-review-report.md
```

Expected marker:

```text
V1 PRODUCT READINESS REVIEW PASS
```

Examples: [docs/examples/v1-product-readiness-review.md](docs/examples/v1-product-readiness-review.md).
