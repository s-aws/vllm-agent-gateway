# V1 Product Readiness Reassessment

Phase 196 reassesses whether the current local-model chat-quality product is ready for broader V1 founder beta.

Use this after Phase 195 passes strict proof-artifact and fixture-state validation.

## What It Checks

- Phase 191 prompt-family drift detection passed.
- Phase 192 chat-answer scoring passed with zero failed scored cases.
- Phase 193 skill-registry readiness passed with zero semantic conflicts.
- Phase 194 skill-authoring pipeline stayed draft-only and did not promote without proof.
- Phase 195 founder trial pack passed with proof-artifact mode and live fixture-state validation enabled.
- Required docs are present.
- Release scope and limitations are explicit.

The reassessment does not release advanced broad refactor orchestration, mutation-capable founder prompts, production deployment, automatic model selection, or unbounded skill-library scale.

## Run

First build the live proof. If the API key is only present in Windows, bridge it into WSL for the command:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" \
  python3 scripts/validate_v1_product_readiness_reassessment_live.py --timeout-seconds 900
```

Then generate the reassessment:

```bash
python3 scripts/validate_v1_product_readiness_reassessment.py
```

Expected marker:

```text
PHASE196 V1 PRODUCT READINESS REASSESSMENT PASS
```

Outputs:

- `runtime-state/phase196/phase196-v1-product-readiness-live-proof.json`
- `runtime-state/phase196/phase196-v1-product-readiness-reassessment-report.json`
- `runtime-state/phase196/phase196-v1-product-readiness-reassessment-report.md`

## Decision Values

- `release_for_broader_founder_beta`
- `priority0_repair_cycle_required`
- `scope_reduction_required`
- `roadmap_expansion_required`
- `blocked_stale_or_invalid_evidence`

The release can pass with advisories, but not with blockers. Current governed advisories include Phase 192 prompt-quality monitoring, Phase 194 draft-only skill admission, and advanced-refactor deferral.

## Next Candidates

The report proposes the next unapproved phase candidates instead of silently expanding scope:

- Phase 197: Founder Trial Execution Round
- Phase 198: Founder Feedback Intake And Repair Proposal
- Phase 199: V1 Beta Release Closeout

Examples: [docs/examples/v1-product-readiness-reassessment.md](docs/examples/v1-product-readiness-reassessment.md).
