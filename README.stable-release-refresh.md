# Stable Release Refresh

Phase 170 refreshes the current founder-testing release proof after the Phase 163-169 chat-quality batch.

It does not add new product behavior. It reruns the stable proof floor, verifies the post-Phase-169 evidence chain, and confirms the release is still `ready_for_founder_testing` and `release_for_founder_testing`.

## What It Reruns

The refresh command reruns:

- stable chat-quality release gate
- stable release reset/recovery rehearsal
- model-swap smoke probe
- V1 product readiness review
- V1 stable release decision

It then validates the refreshed outputs plus:

- Phase 157 founder field round 1
- Phase 158 transcript quality feedback intake
- Phase 159 Priority 0 repair-loop closure
- Phase 163 post-restart runtime readiness
- Phase 164 founder field round 2
- Phase 165 prompt-advisory closure
- Phase 166 generic chat and vague prompt contract
- Phase 167 AnythingLLM UI replay
- Phase 168 answer-first UI replay and post-restart readiness
- Phase 169 failure-to-roadmap proposals and release-notes validation

Phase 160 remains historical proof for the earlier field-test chain. Use Phase 170 as the current stable refresh floor.

## What It Produces

JSON:

```text
runtime-state/stable-release-refresh/phase170/phase170-stable-release-refresh-report.json
```

Markdown:

```text
runtime-state/stable-release-refresh/phase170/phase170-stable-release-refresh-report.md
```

The report includes:

- refresh command results
- governed output paths and hashes for each refresh command
- source report hashes
- current model identity
- Phase 159 repair mode
- Phase 169 proposal and release-blocker counts
- readiness
- release decision
- validation errors

## Pass Rules

Phase 170 fails closed if:

- any refresh command fails
- any refresh command does not record the governed output path hashes
- stable chat-quality readiness is not `ready_for_founder_testing`
- stable release decision is not `release_for_founder_testing`
- current model identity changes
- a full drift gate is required
- both frozen Coinbase fixtures are not covered where required
- Phase 159 is blocked
- generic/vague chat proof, UI replay, post-restart readiness, or Phase 169 proposal safety regresses
- release limitations are weakened

Timeouts or uncaught refresh-command exceptions are captured as failed command results in the report so an older passing report is not the only artifact left behind.

## Run

Run from Bash/WSL:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_stable_release_refresh.py \
  --policy-path runtime/stable_release_refresh_phase170_policy.json \
  --run-refresh \
  --execute-reset-start \
  --execute-recovery \
  --output-path runtime-state/stable-release-refresh/phase170/phase170-stable-release-refresh-report.json \
  --markdown-output-path runtime-state/stable-release-refresh/phase170/phase170-stable-release-refresh-report.md
```

Expected marker:

```text
PHASE170 STABLE RELEASE REFRESH PASS
```

Examples: [docs/examples/stable-release-refresh.md](docs/examples/stable-release-refresh.md).
