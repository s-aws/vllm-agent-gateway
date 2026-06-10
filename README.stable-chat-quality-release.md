# Stable Chat Quality Release Gate

Phase 130 consolidates the Priority 0 chat-quality proof into one release-readiness command.

This gate does not rerun the expensive live suites. It verifies the current proof artifacts, recomputes artifact hashes, checks the blocking counters, and reports whether the current local model is ready for founder testing.

## Inputs

- governed baseline corpus
- AnythingLLM answer-usefulness report
- holdout prompt-bank report
- Priority 0 gap taxonomy report
- output-format parity report
- founder-feedback loop report
- AnythingLLM UI E2E report
- fresh local-model drift report
- prompt-tightening recommendation report
- skill/tool coverage gap report
- Phase 130 release policy

## Current Result

After Phase 131 closure proof, the current release report is ready for founder testing:

- `status=passed`
- `readiness=ready_for_founder_testing`
- `gate_count=11`
- `blocker_count=0`

## Primary Command

From Bash/WSL:

```bash
python3 scripts/validate_stable_chat_quality_release.py \
  --require-artifacts \
  --output-path runtime-state/stable-chat-quality-release/phase130/phase130-stable-chat-quality-release-report.json
```

Expected current marker:

```text
STABLE CHAT QUALITY RELEASE PASS
```

The command exits nonzero when readiness is blocked. That is the correct behavior for release automation.

## Blocking Rules

The gate blocks release when any upstream Priority 0 report fails or when evidence contains:

- stale or missing source artifacts
- unresolved Priority 0 taxonomy findings
- fresh local-model drift
- missing gateway or AnythingLLM route proof
- missing frozen Coinbase fixture coverage
- protected fixture mutation proof gaps
- output-format or UI case-level marker failures
- accepted founder feedback that is still pending required evaluation and lacks Phase 131 closure proof
- pending or accepted prompt-tightening candidates that lack approval, rerun proof, rejection, or Phase 131 closure proof
- skill/tool coverage gaps that require a new deterministic capability

## Next Step

Use this gate as the stable readiness check before founder smoke testing, founder handoff docs, or release-candidate packaging.
