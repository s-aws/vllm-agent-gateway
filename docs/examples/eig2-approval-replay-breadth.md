# EIG-2 Approval Replay Breadth Examples

Run the Phase 294 validator:

```bash
python3 scripts/validate_eig2_approval_replay_breadth.py
```

Run the focused regression:

```bash
python3 -m pytest tests/regression/test_eig2_approval_replay_breadth.py -q
```

Write a report to a specific path:

```bash
python3 scripts/validate_eig2_approval_replay_breadth.py \
  --output-path runtime-state/eig2-approval-replay-breadth/manual-eig2-approval-report.json
```

Expected success marker:

```text
EIG2 APPROVAL REPLAY BREADTH PASS
```

The report should show:

```json
{
  "status": "passed",
  "summary": {
    "approval_replay_case_count": 9,
    "all_required_scenarios_passed": true,
    "audit_validation_passed": true,
    "scope_change_denied": true,
    "non_dry_run_write_denied": true,
    "phase295_ready": true
  }
}
```

Do not treat this as production approval infrastructure. The gate proves local deterministic approval binding and replay-safe audit artifacts only.
