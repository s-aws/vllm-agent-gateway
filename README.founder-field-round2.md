# Founder Field Round 2

Phase 164 runs a bounded founder field-test round through AnythingLLM and the workflow-router gateway, then scores the local response against a blind baseline created before local output is evaluated.

Use this after Phase 163 post-restart readiness passes.

## What It Proves

- selected prompts cover both frozen Coinbase fixtures
- blind baselines are separate from prompt catalog metadata and local-model output
- AnythingLLM routes through the workflow-router gateway
- every prompt keeps a full response artifact, hash, route surface, run ID, and fixture mutation proof
- scoring separates invalid evidence from valid evidence with advisory or blocker chat-quality outcomes

## Inputs

- Policy: `runtime/founder_field_round2_policy.json`
- Governed blind baseline source: `runtime/founder_field_round2_blind_baselines.json`
- Phase 163 readiness report
- Phase 158 transcript feedback intake report
- AnythingLLM workspace and `ANYTHINGLLM_API_KEY`

The blind baseline source contains ideal answer shapes, must-have facts, evidence expectations, safety boundaries, output expectations, and the 100-point rubric. It does not contain local run IDs, model text, status fields, or response hashes.

## Run

From PowerShell, pass the AnythingLLM key into WSL:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
wsl.exe --cd /mnt/c/agentic_agents -- python3 scripts/validate_founder_field_round2.py --run-live
```

Expected evidence-valid marker:

```text
PHASE164 FOUNDER FIELD ROUND 2 PASS
```

The pass marker means the evidence chain is valid. The report's `quality_status` and per-case classifications determine whether Phase 165 advisory closure or Phase 169 proposal routing is required.

## Output

Default report:

```text
runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-report.json
```

Default field run:

```text
runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-run.json
```

Full response artifacts:

```text
runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-run/responses/
```

The report includes:

- policy, baseline, field-run, readiness, and feedback artifact paths and hashes
- case scores and score breakdowns
- blind-baseline comparison data
- route surface and workflow-router run ID
- full response artifact path and hash
- advisory, blocker, and proposal routing flags
- fixture mutation proof

## Failure Meaning

`status=failed` means the evidence chain is invalid, such as a missing response artifact, route-surface proof, baseline provenance issue, fixture mutation, or hidden report edit.

`status=passed` with `quality_status=failed` means the evidence is valid but one or more local-model answers missed the target and must be routed into the next repair/proposal phase.
