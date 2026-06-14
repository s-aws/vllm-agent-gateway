# V1 Release-Candidate Decision Gate Examples

Run from the active release-candidate branch:

```bash
python3 scripts/validate_v1_release_candidate_decision_gate.py \
  --health-timeout-seconds 10
```

Expected decisions:

- `ship`: all required proof and live health checks pass.
- `hold`: runtime health is down or incomplete, but proof artifacts are otherwise valid.
- `repair_required`: missing phase completion, missing machine proof, stale docs, or invalid policy.

When the decision is `hold`, restore the local model and gateway/proxy stack first, then rerun the gate. Do not ship from a `hold` result.
