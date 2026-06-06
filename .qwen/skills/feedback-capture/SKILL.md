---
name: feedback-capture
description: Convert workflow results, validation output, plan reviews, failed test sessions, or founder/tester critique into structured follow-up records. Use after execution-plan-writer, implementation-packet-designer, verification-planner, controller workflow runs, AnythingLLM harness tests, or live localhost model validation when feedback must be recorded without treating it as approval to implement or rewrite the roadmap.
---

# Feedback Capture

Use this skill after validation, workflow execution, plan review, or tester critique. It supports problem-solving Steps 7 and 8: evaluate results, record consequences, and identify improvement opportunities.

This skill does not run tests, edit files, update roadmaps, approve implementation, retry workflows, or infer success from missing evidence.

## Inputs

Use only:

- workflow, validation, or harness result summaries
- run IDs, model IDs, repository names, tool names, and timestamps supplied in the input
- explicit tester or founder feedback
- artifact references such as output files, logs, command summaries, packet IDs, plan IDs, and verification plan IDs
- prior skill outputs when included in the input

If feedback references an artifact that is not present, record the missing artifact instead of inventing what happened.

## Workflow

1. Identify `workflow_id` from the named workflow, skill chain, harness, or validation run.
2. Identify `run_id` when provided; otherwise use `null`.
3. Separate observable run results from tester opinions.
4. Classify helpful outcomes into `useful`.
5. Classify incorrect behavior, failed checks, policy violations, or bad assumptions into `wrong`.
6. Classify absent evidence, missing tests, missing artifacts, unclear scope, or skipped real-world coverage into `missing`.
7. Classify latency, excessive prompts, broad context reads, noisy output, or repeated restarts into `too_slow_or_noisy`.
8. Create `next_adjustments` as proposed follow-up records only.
9. Preserve approval boundaries: feedback can request an adjustment, but it does not approve writes or scope expansion by itself.

## Output

Return exactly one JSON object:

```json
{
  "workflow_id": "string",
  "run_id": "string or null",
  "useful": [
    {
      "id": "USEFUL-0001",
      "observation": "specific useful result",
      "evidence_refs": []
    }
  ],
  "wrong": [
    {
      "id": "WRONG-0001",
      "observation": "specific incorrect result or failed expectation",
      "severity": "low|medium|high",
      "evidence_refs": []
    }
  ],
  "missing": [
    {
      "id": "MISSING-0001",
      "gap": "specific missing evidence, artifact, test, or decision",
      "blocks_next_step": true,
      "needed_evidence_or_decision": "specific artifact, test, context, or user decision"
    }
  ],
  "too_slow_or_noisy": [
    {
      "id": "NOISE-0001",
      "issue": "specific latency, repetition, verbosity, or noise problem",
      "impact": "why this reduced usability",
      "evidence_refs": []
    }
  ],
  "next_adjustments": [
    {
      "id": "ADJUST-0001",
      "target": "skill|validator|controller|anythingllm|gateway|docs|unknown",
      "action": "specific proposed follow-up",
      "owner": "agent|controller|founder|unknown",
      "requires_approval_before_write": true,
      "source_feedback_refs": []
    }
  ]
}
```

Use empty arrays when there is no item. Use `null` for unknown scalar values.

## Classification Rules

- Put a passed check in `useful` only when there is evidence.
- Put a failed check in `wrong` when expected behavior was explicit and the result contradicted it.
- Put incomplete testing in `missing`, not `useful`.
- Put "took too long", "too much output", "too many prompts", or "not actionable" in `too_slow_or_noisy`.
- Put proposed changes in `next_adjustments`; do not rewrite the plan or roadmap directly.
- Set `requires_approval_before_write` to `true` for any adjustment that would edit files, change scope, alter controller workflows, expose tools, or update automation.

## Routing

- Route back to `request-triage` when feedback is a new task.
- Route to `execution-plan-writer` when feedback requests a revised plan and scope is known.
- Route to `verification-planner` when feedback is only about missing checks.
- Route to `none` when the follow-up record is complete and no next action is approved.

If routing is included, put it inside the most relevant `next_adjustments` item; do not add extra top-level keys.

## Must Not

- Do not treat "this failed, fix it" as approval to edit.
- Do not mark a workflow complete.
- Do not claim live testing happened without supplied evidence.
- Do not rely on conversation memory when artifact references are missing.
- Do not update roadmaps or skill text.
- Do not run commands or invoke tools.
- Do not hide missing real-world repo, gateway, or AnythingLLM validation.

## Examples

Input context:

```json
{
  "workflow_id": "execution-planning-skill-validation",
  "run_id": "local-2026-06-03-001",
  "result_summary": {
    "model": "Qwen3-Coder-30B-A3B-Instruct",
    "smoke_passed": 24,
    "smoke_total": 24,
    "chain_passed": true,
    "packet_preview_workflow_status": "completed",
    "repo_mutated": false
  },
  "tester_feedback": "The localhost validation is useful, but it still does not prove the frozen Coinbase repo, gateway, or AnythingLLM path works."
}
```

Output:

```json
{
  "workflow_id": "execution-planning-skill-validation",
  "run_id": "local-2026-06-03-001",
  "useful": [
    {
      "id": "USEFUL-0001",
      "observation": "Live localhost validation passed 24 of 24 smoke cases and the approval-to-verification dry chain.",
      "evidence_refs": ["result_summary.smoke_passed", "result_summary.chain_passed"]
    },
    {
      "id": "USEFUL-0002",
      "observation": "Packet preview completed in draft mode without mutating the target repository.",
      "evidence_refs": ["result_summary.packet_preview_workflow_status", "result_summary.repo_mutated"]
    }
  ],
  "wrong": [],
  "missing": [
    {
      "id": "MISSING-0001",
      "gap": "No frozen Coinbase repository validation evidence is supplied.",
      "blocks_next_step": true,
      "needed_evidence_or_decision": "Run the validation chain against C:\\coinbase_testing_repo_frozen_tmp and record non-mutation proof."
    },
    {
      "id": "MISSING-0002",
      "gap": "No gateway or AnythingLLM end-to-end validation evidence is supplied.",
      "blocks_next_step": true,
      "needed_evidence_or_decision": "Run or schedule tests that exercise the current gateway and AnythingLLM automation path."
    }
  ],
  "too_slow_or_noisy": [],
  "next_adjustments": [
    {
      "id": "ADJUST-0001",
      "target": "validator",
      "action": "Add a real-repository dry-chain scenario for C:\\coinbase_testing_repo_frozen_tmp.",
      "owner": "agent",
      "requires_approval_before_write": true,
      "source_feedback_refs": ["MISSING-0001"]
    },
    {
      "id": "ADJUST-0002",
      "target": "gateway",
      "action": "Create an approval-gated test plan for current gateway and AnythingLLM automation validation.",
      "owner": "agent",
      "requires_approval_before_write": true,
      "source_feedback_refs": ["MISSING-0002"]
    }
  ]
}
```
