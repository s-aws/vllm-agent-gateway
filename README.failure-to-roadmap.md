# Failure-To-Roadmap Proposal Gate

Phase 148 converts failed gates or founder misses into proposed roadmap phases without mutating the roadmap automatically.

Phase 169 reuses the same proposal-only gate for the current Priority 0 batch. It reads Phase 163 through Phase 168 proof artifacts and extracts Phase 165 `product_gap_escalation` closure records into unapproved candidate phases.

It is a proposal gate, not an implementation gate. A generated proposal remains `unapproved` unless the founder explicitly approves it.

## What It Reads

Phase 148 source reports:

```text
runtime-state/external-tester-dry-run/phase147/phase147-external-tester-dry-run.json
runtime-state/release-notes/phase146/phase146-release-notes-report.json
runtime-state/founder-feedback-triage-dashboard/phase145/phase145-founder-feedback-triage-dashboard.json
```

Phase 169 source reports:

```text
runtime-state/post-restart-runtime-readiness/phase163/phase163-post-restart-runtime-readiness-report.json
runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-report.json
runtime-state/prompt-advisory-closure/phase165/phase165-prompt-advisory-closure-report.json
runtime-state/generic-chat-vague-prompt-contract/phase166/phase166-generic-chat-vague-prompt-contract-report.json
runtime-state/anythingllm-ui/phase167/phase167-ui-replay-mixed.json
runtime-state/anythingllm-ui/phase168/phase168-answer-first-ui-replay-mixed.json
runtime-state/post-restart-runtime-readiness/phase168/phase168-post-restart-runtime-readiness-report.json
```

Policies:

```text
runtime/failure_to_roadmap_policy.json
runtime/failure_to_roadmap_phase169_policy.json
```

## What It Produces

Reports:

```text
runtime-state/failure-to-roadmap/phase148/phase148-failure-to-roadmap-report.json
runtime-state/failure-to-roadmap/phase169/phase169-failure-to-roadmap-report.json
```

If a source report fails, or a governed extractor finds product-gap escalation records, the gate creates a proposal with:

- source report ID and path
- failure category and severity
- evidence summary
- candidate phase title
- goal
- implementation tasks
- acceptance proof
- dependencies
- recommended roadmap position
- approval status

## Run

Phase 148:

```bash
python3 scripts/validate_failure_to_roadmap.py \
  --require-artifacts \
  --output-path runtime-state/failure-to-roadmap/phase148/phase148-failure-to-roadmap-report.json
```

Phase 169:

```bash
python3 scripts/validate_failure_to_roadmap.py \
  --require-artifacts \
  --policy-path runtime/failure_to_roadmap_phase169_policy.json \
  --output-path runtime-state/failure-to-roadmap/phase169/phase169-failure-to-roadmap-report.json
```

Expected current marker:

```text
FAILURE TO ROADMAP PASS
```

Expected Phase 148 summary:

```json
{
  "finding_count": 0,
  "proposal_count": 0,
  "release_blocker_count": 0
}
```

Expected Phase 169 summary:

```json
{
  "finding_count": 6,
  "proposal_count": 6,
  "unapproved_proposal_count": 6,
  "approved_proposal_count": 0,
  "release_blocker_count": 0
}
```

## Boundaries

- Does not edit `docs/ACTIONABLE_WORKFLOW_ROADMAP.md`.
- Does not approve proposed phases.
- Does not start implementation.
- Does not mutate source files or frozen fixtures.
- Critical and high findings are release blockers until explicitly handled.

Examples: [docs/examples/failure-to-roadmap.md](docs/examples/failure-to-roadmap.md).
