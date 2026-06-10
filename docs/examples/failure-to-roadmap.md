# Failure-To-Roadmap Examples

## Run Current Gate

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_failure_to_roadmap.py \
  --require-artifacts \
  --output-path runtime-state/failure-to-roadmap/phase148/phase148-failure-to-roadmap-report.json
```

Expected result:

```text
FAILURE TO ROADMAP PASS
```

## Review

Start with:

```text
summary.finding_count
summary.proposal_count
summary.release_blocker_count
proposals[]
errors[]
```

Current expected state is no findings and no proposals because Phase 145 through Phase 147 proof artifacts pass.

If a future source report fails, inspect:

```text
proposals[].approval_status
proposals[].release_blocker
proposals[].recommended_roadmap_position
proposals[].acceptance_proof
```

Do not add a generated proposal to the roadmap until the founder approves the scope.

## Run Phase 169 Proposal Pass

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_failure_to_roadmap.py \
  --require-artifacts \
  --policy-path runtime/failure_to_roadmap_phase169_policy.json \
  --output-path runtime-state/failure-to-roadmap/phase169/phase169-failure-to-roadmap-report.json
```

Expected Phase 169 result:

```text
FAILURE TO ROADMAP PASS
```

Expected Phase 169 summary:

```json
{
  "finding_count": 6,
  "proposal_count": 6,
  "unapproved_proposal_count": 6,
  "release_blocker_count": 0
}
```

The six proposals should trace to Phase 165 product-gap cases `P08`, `P21`, `P29`, `P30`, `P33`, and `P34`. They remain `unapproved` and `not_started` until the founder approves a future phase.
