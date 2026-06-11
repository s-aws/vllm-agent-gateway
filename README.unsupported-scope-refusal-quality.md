# Unsupported Scope Refusal Quality

Phase 190 validates that unsupported, unsafe, oversized, or under-specified prompts fail usefully in chat.

The goal is not just refusing. The chat answer must help the user recover without pretending that work started.

## What It Checks

- blocked prompts include a chat-visible `Recovery:` section
- the answer names the blocking reason
- the answer lists exact missing information
- the answer gives one bounded next step
- the answer offers safe alternatives
- the answer states evidence expectations when debugging or changing code
- the answer states mutation policy
- blocked prompts do not silently start repository workflows
- supported holdout prompts still route and answer normally
- both frozen Coinbase fixtures remain unchanged

## Contract

Policy:

```text
runtime/unsupported_scope_refusal_quality_policy.json
```

Validator:

```text
scripts/validate_unsupported_scope_refusal_quality.py
```

Report kind:

```text
unsupported_scope_refusal_quality_report
```

The policy records the blind contextless baseline used before local output evaluation.

## Run

From PowerShell, pass the AnythingLLM key into WSL:

```powershell
$key=$env:ANYTHINGLLM_API_KEY
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$key" python3 scripts/validate_unsupported_scope_refusal_quality.py --run-live --timeout-seconds 180
```

Expected marker:

```text
PHASE190 UNSUPPORTED SCOPE REFUSAL QUALITY PASS
```

## Output

Default report:

```text
runtime-state/unsupported-scope-refusal-quality/phase190/
```

`runtime-state` is local-only and should not be committed.

## Failure Meaning

`status=failed` means AnythingLLM or the gateway can still return a blocked prompt response that is vague, unsafe, artifact-only, silently rerouted, or not immediately actionable for the user.
