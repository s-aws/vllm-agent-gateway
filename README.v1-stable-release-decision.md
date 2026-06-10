# V1 Stable Release Decision

Phase 156 is the final governed decision gate for the current V1 founder-testing release.

It does not rerun every live workflow. It reads the accumulated proof chain and decides whether the current local harness can be released for founder testing within the documented scope.

## What It Reads

Policy:

```text
runtime/v1_stable_release_decision_policy.json
```

Required evidence:

```text
runtime-state/v1-product-readiness-review/phase155/phase155-v1-product-readiness-review-report.json
runtime-state/stable-chat-quality-release/phase130/phase130-stable-chat-quality-release-report.json
runtime-state/release-notes/phase146/phase146-release-notes-report.json
runtime-state/stable-release-reset-rehearsal/phase153/phase153-live-report.json
runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report.json
runtime/release_proofs/v1-1-release-candidate-stable-proof.json
```

Required release docs:

```text
README.getting-started.md
README.release-notes.md
README.productized-setup.md
README.stable-handoff.md
README.stable-release-reset-rehearsal.md
README.v1-product-readiness-review.md
README.v1-stable-release-decision.md
```

## What It Produces

JSON:

```text
runtime-state/v1-stable-release-decision/phase156/phase156-v1-stable-release-decision-report.json
```

Markdown:

```text
runtime-state/v1-stable-release-decision/phase156/phase156-v1-stable-release-decision-report.md
```

The report includes:

- final decision: `release_for_founder_testing` or `blocked`
- linked evidence with source hashes
- release scope
- release limitations
- rollback path
- next roadmap batch status
- release blockers, if any

## Released Scope

The governed release scope is:

- local founder testing
- AnythingLLM through the workflow-router path at `http://127.0.0.1:8500/v1`
- the current localhost model
- the two frozen Coinbase fixtures
- `format_a` and `json` output
- read-only L1/L2 and narrow draft workflows

## Limitations

This gate must keep these limitations visible:

- not a production deployment
- not advanced broad refactor orchestration
- not every repository, language, or coding task
- not direct mutation of protected frozen fixtures
- not unsupported output-format parity
- not automatic model selection

## Rollback Path

Use the stable handoff and stable reset rehearsal path:

1. Stop the gateway/proxies.
2. Start them again with `start-agent-prompt-proxies.sh`.
3. Rerun the first-time doctor and Phase 153 stable reset/start/recovery rehearsal.
4. Preserve `runtime-state/` as local-only evidence.

## Run

Run from Bash/WSL:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_v1_stable_release_decision.py \
  --output-path runtime-state/v1-stable-release-decision/phase156/phase156-v1-stable-release-decision-report.json \
  --markdown-output-path runtime-state/v1-stable-release-decision/phase156/phase156-v1-stable-release-decision-report.md
```

Expected marker:

```text
V1 STABLE RELEASE DECISION PASS
```

Examples: [docs/examples/v1-stable-release-decision.md](docs/examples/v1-stable-release-decision.md).
