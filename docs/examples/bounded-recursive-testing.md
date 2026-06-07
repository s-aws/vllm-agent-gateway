# Bounded Recursive Testing Examples

## Policy Validation

Validate the current policy and write a timestamped report under `runtime-state/recursive-blind-testing/`:

```bash
python scripts/validate_recursive_blind_testing.py
```

The command passes when `runtime/recursive_blind_testing_policy.json` defines bounded rounds, no-context evaluators, deterministic adjudication, the required finding categories, and the 100-point rubric.

## Report Validation

Validate a recursive report created by a test run:

```bash
python scripts/validate_recursive_blind_testing.py \
  --report runtime-state/recursive-blind-testing/phase92-feedback-triage/recursive-report.json
```

The report must contain no unresolved critical or high findings. If `status` is `passed`, `convergence.status` must be `converged`, the total score must meet the policy minimum, and every category score must meet the policy floor.

## Minimal Report Shape

```json
{
  "schema_version": 1,
  "kind": "recursive_blind_testing_report",
  "status": "passed",
  "policy_id": "bounded-recursive-blind-testing-v1",
  "scenario_id": "stable_handoff_usability",
  "rounds": [
    {
      "round_id": "round-1",
      "evaluator_context": {
        "fork_context": false,
        "agent_id": "blind-agent-1",
        "input_summary": "Stable handoff README plus selected validation artifacts"
      },
      "input_refs": [
        "README.stable-handoff.md",
        "runtime-state/stable-handoff/phase91-bash-stable-smoke.json"
      ],
      "blind_findings": [],
      "accepted_findings": [],
      "rejected_findings": []
    }
  ],
  "score_summary": {
    "total_score": 90,
    "category_scores": {
      "route_workflow_skill_tool_correctness": 90,
      "evidence_grounding_and_artifact_quality": 90,
      "semantic_correctness": 90,
      "output_contract_and_chat_visible_markers": 90,
      "verification_command_relevance": 90,
      "safety_approval_and_mutation_boundary": 90,
      "diagnosability": 90
    }
  },
  "convergence": {
    "status": "converged",
    "summary": "No accepted current-phase findings remain and validation proof is linked.",
    "evidence_refs": [
      "python scripts/validate_recursive_blind_testing.py",
      "python -m pytest tests/regression/test_recursive_blind_testing.py -q"
    ]
  }
}
```

## Phase 92 Use

For founder and external tester feedback triage:

1. Collect stable handoff feedback, workflow feedback artifacts, and selected live run evidence.
2. Ask a fresh no-context evaluator to review the visible user output and docs.
3. Classify every proposed finding using the policy categories.
4. Accept only findings supported by artifacts.
5. Implement current-phase tightening only; add future-scope findings to the roadmap.
6. Rerun the validator and focused regression.
