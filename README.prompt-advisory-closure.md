# Prompt Advisory Closure

Phase 165 closes the 14 Phase 158 prompt-risk advisories without silently rewriting user prompts or implementing new product behavior.

Use this after Phase 164 founder field round 2 passes.

## What It Proves

- every Phase 158 prompt advisory has exactly one closure decision
- refined prompts are tested as candidates, not applied as hidden prompt rewrites
- holdout prompts still pass after refined prompt validation
- live evidence includes AnythingLLM route surface, workflow-router run ID, full response artifact, score, and fixture mutation proof
- product gaps, if any, are routed to Phase 169 instead of implemented in Phase 165

## Closure Decisions

- `closed_refined_prompt_proven`: original advisory missed the target, refined prompt fixed it, and holdouts passed.
- `documented_guidance`: refined prompt is proven useful, but the current system already passed; keep the safer wording as tester/operator guidance.
- `product_gap_escalation`: refined prompt or holdout proof failed, or the issue requires controller/tool/product work.

## Run

From PowerShell, pass the AnythingLLM key into WSL:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
wsl.exe --cd /mnt/c/agentic_agents -- python3 scripts/validate_prompt_advisory_closure.py --run-live
```

Expected marker:

```text
PHASE165 PROMPT ADVISORY CLOSURE PASS
```

## Output

Default report:

```text
runtime-state/prompt-advisory-closure/phase165/phase165-prompt-advisory-closure-report.json
```

Refined prompt run:

```text
runtime-state/prompt-advisory-closure/phase165/phase165-refined-prompt-run.json
```

Holdout run:

```text
runtime-state/prompt-advisory-closure/phase165/phase165-holdout-run.json
```

The report includes closure records, refined response artifact paths and hashes, holdout evidence, decision counts, validation errors, and the next action.
