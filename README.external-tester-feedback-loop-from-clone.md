# External Tester Feedback Loop From Clone

Phase 243 proves that feedback submitted after release-candidate clone testing becomes traceable work without adding a second feedback database or manual issue tracker.

The gate uses the existing `workflow_feedback.record` workflow. It validates this chain:

`release-candidate clone -> workflow-router target run -> workflow-feedback run -> workflow_feedback_record -> governed_decision -> next required gate`

## What It Proves

- The live run came from a remote release-candidate clone, not the active workspace.
- A positive useful-only tester record becomes `rejected_finding` with an explanation and no repair work.
- A targeted defect record becomes an accepted `repair_followup` and stays open pending rerun proof.
- Feedback records link to target workflow-router run IDs, feedback run IDs, route decisions, prompt hashes, and output artifact hashes.
- Generated reports and feedback artifacts remain under ignored `runtime-state/`.
- Protected frozen fixtures remain unchanged.

## Validation

Static policy/catalog check:

```bash
python3 scripts/validate_external_tester_feedback_loop_from_clone.py --allow-missing-live-artifacts
```

Live feedback run from a release-candidate clone:

```bash
python3 scripts/validate_founder_feedback_loop_live.py \
  --cases-path runtime/external_tester_feedback_loop_from_clone_cases.json \
  --required-decision-kind rejected_finding \
  --required-decision-kind repair_followup \
  --output-path runtime-state/external-tester-feedback-loop-from-clone/phase243/phase243-external-tester-feedback-loop-live.json \
  --timeout-seconds 900
```

Live report gate:

```bash
python3 scripts/validate_external_tester_feedback_loop_from_clone.py
```

Examples: [docs/examples/external-tester-feedback-loop-from-clone.md](docs/examples/external-tester-feedback-loop-from-clone.md)
