# Onboarding And Release Handoff Refresh

Phase 232 refreshes the first-time tester path after the current large-context, founder-feedback, skill-scaling, and runtime-recovery work.

This is a documentation and handoff gate. It does not add new runtime behavior.

Required decision: `handoff_ready`.

## What It Proves

- The root README stays short and points to the ordered documentation index.
- First-time testers can find the current AnythingLLM target: `http://127.0.0.1:8500/v1`.
- The current handoff path documents setup doctor, runtime recovery, small-repo prompt proof, large-context prompt proof, and feedback capture.
- Known limits are clear: advanced broad refactor orchestration is not released, raw 1M-token prompts are not promised, and protected frozen fixtures must not be mutated.
- Stale current-phase markers are rejected before release handoff is marked ready.

## Validation

```bash
python3 scripts/validate_onboarding_release_handoff_refresh.py
```

Expected marker:

```text
PHASE232 ONBOARDING RELEASE HANDOFF REFRESH PASS
```

## Output

Default report:

```text
runtime-state/phase232/phase232-onboarding-release-handoff-refresh-report.json
```

Markdown summary:

```text
runtime-state/phase232/phase232-onboarding-release-handoff-refresh-report.md
```

Examples: [docs/examples/onboarding-release-handoff-refresh.md](docs/examples/onboarding-release-handoff-refresh.md)
