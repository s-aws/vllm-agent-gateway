# Natural-Language Capability Gap Backlog

Phase 93 makes future natural-language coding-agent work explicit. The source of truth is:

```text
runtime/natural_language_capability_gap_backlog.json
```

This backlog is not a skill list. It is a governed prompt-family backlog that decides whether a common user request is already supported, a small extension, a new workflow, or deferred.

## Entry Contract

Accepted entries use one of these classifications:

- `existing_support`
- `small_extension`
- `new_workflow`

Each accepted entry must include:

- natural-language prompt shape
- rationale
- expected workflow
- expected skills
- expected tools
- expected artifacts
- eval gate
- validation tier
- chat-visible acceptance markers
- mutation policy
- `requires_manual_skill_injection=false`
- `requires_json_envelope=false`

Deferred entries must include:

- clear defer reason
- future phase
- `mutation_policy=blocked`

Broad advanced refactor requests remain deferred until Phase 105 or a later approved advanced scope.

## Current Backlog Summary

The initial Phase 93 backlog contains 30 prompt families:

- existing support: small docs/test drafts, change-surface summaries, task decomposition, configuration runtime-effect explanation
- small extensions: CI-log triage, feature-flag tracing, table read/write lookup, build-error diagnosis, unused-symbol lookup, module onboarding, stack-trace reproduction checklist
- new workflows: patch review, convention discovery, dependency change review, docs-to-code consistency, manifest validation command selection
- deferrals: broad subsystem refactor, fix-all lint and commit, internet-driven dependency upgrade with mutation, open-ended UI inspection and mutation

The accepted Phase 92 missing capability, exact packet generation from an approved investigation, is recorded as `P93-026` and mapped to Phase 96 rather than pulled into Phase 93.

## Validation

Run:

```powershell
python scripts\validate_capability_gap_backlog.py --output-path runtime-state\capability-gap-backlog\phase93-current.json
```

The validator checks:

- schema and entry count
- unique `P93-###` IDs
- required classification diversity
- accepted entries include workflow, skills, tools, artifacts, eval gate, validation tier, and acceptance markers
- deferred entries are blocked and mapped to a future phase
- no entry relies on manual skill injection or JSON-envelope prompting
- broad refactor wording is not accepted as current work

Focused regression:

```powershell
python -m pytest tests\regression\test_capability_gap_backlog.py -q
```

## How To Use This Backlog

Phase 94 should use this backlog to harden runtime skill selection against the accepted prompt families. Do not implement all Phase 93 entries at once. Select the highest-value small extensions first, add deterministic route rules, attach skills/tools/artifacts, then prove the path through regression, Bash gateway validation, AnythingLLM, and both frozen fixtures.
