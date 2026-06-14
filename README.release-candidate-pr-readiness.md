# Release-Candidate PR Readiness

Phase 238 creates an auditable release-candidate review packet for the pushed branch.

This gate does not create a new workflow and does not prove chat quality by itself. It packages the current proof chain so a reviewer can open the branch, see what changed, run the right commands, understand known limits, and avoid private chat context.

## What It Checks

- The branch uses the project `codex/` release-candidate prefix.
- The source tree is clean when the packet is generated.
- Required Phase 232-237 handoff and chat-quality docs exist.
- Required validation scripts exist.
- Prior release-handoff phases are marked complete in the canonical roadmap.
- Generated `runtime-state/`, temp directories, protected frozen fixtures, and fixture repositories are not tracked.
- Known limits remain visible: advanced refactor is deferred, real apply is not part of this release path, and raw 1M-token prompting is not claimed.

## Command

```bash
python3 scripts/validate_release_candidate_pr_readiness.py \
  --output-path runtime-state/release-candidate-pr-readiness/phase238/phase238-release-candidate-pr-readiness-report.json \
  --markdown-output-path runtime-state/release-candidate-pr-readiness/phase238/phase238-release-candidate-pr-readiness-packet.md
```

Expected result:

```text
RELEASE CANDIDATE PR READINESS PASS
```

## Output

- JSON report: `runtime-state/release-candidate-pr-readiness/phase238/phase238-release-candidate-pr-readiness-report.json`
- Markdown packet: `runtime-state/release-candidate-pr-readiness/phase238/phase238-release-candidate-pr-readiness-packet.md`

The markdown packet includes a draft PR body. Keep any PR as a draft until a later release decision gate marks the release candidate ready.

Examples: [docs/examples/release-candidate-pr-readiness.md](docs/examples/release-candidate-pr-readiness.md).
