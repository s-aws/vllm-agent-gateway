---
name: verification-planner
description: Select controller-compatible pytest verification commands, manual checks, and coverage gaps for execution plans or implementation packet candidates. Use after execution-plan-writer or implementation-packet-designer when planned work needs verification strategy without running commands, invoking tools, approving apply mode, marking work complete, or suggesting commands outside the implementation.workflow verification policy.
---

# Verification Planner

Use this skill after `implementation-packet-designer`, or after `execution-plan-writer` when target files and intended behavior are specific enough to plan checks.

This skill supports problem-solving Steps 5 and 7: define verification actions and evaluate expected results. It does not execute the action plan, run tests, edit files, invoke tools, approve apply mode, or mark work complete.

## Inputs

Use only:

- execution plan from `execution-plan-writer`
- packet candidates or packet preview from `implementation-packet-designer`
- affected files, related tests, risks, and unknowns from `impact-map-builder`
- explicit verification strategy already present in the plan
- user or controller constraints

If target files, packet candidates, and related tests are all missing, stop and route back to `execution-plan-writer` or `impact-map-builder`.

## Workflow

1. Refuse to proceed if any prior `stop.required` is true.
2. Identify target files from packet candidates, packet preview, execution-plan steps, or impact map.
3. Identify existing related tests from impact evidence or packet references.
4. Select pytest-style commands only when they are bounded and controller-compatible.
5. Prefer the narrowest test path supported by evidence.
6. Add manual checks for behavior that cannot be verified by known tests yet.
7. Add coverage gaps when no known test covers a target, behavior, operation, or acceptance criterion.
8. Record blocked or rejected commands separately; do not include them in `verification_commands`.
9. Route to `none` when a verification plan exists or when verification is blocked pending more context.

## Controller-Compatible Commands

Use only these command shapes:

- `["python", "-m", "pytest", "<path>"]`
- `["python3", "-m", "pytest", "<path>"]`
- `["pytest", "<path>"]`

Prefer `["python", "-m", "pytest", "<path>"]` for portability.

The path must be repo-relative and bounded, such as:

- `tests/regression/test_controller_service.py`
- `tests/regression/`
- `tests`

Do not suggest shell strings, command chaining, `python -c`, `git`, `npm`, `ruff`, `mypy`, `tox`, `coverage`, broad scripts, or commands that mutate files. Those may be useful later, but they are outside the current implementation workflow verification policy.

## Output

Return exactly one JSON object:

```json
{
  "verification_plan_id": "VERIFY-0001",
  "source_plan_id": "EP-0001 or null",
  "source_packet_set_id": "IMPSET-0001 or null",
  "basis": {
    "target_files": [],
    "packet_ids": [],
    "acceptance_criteria": [],
    "related_tests": [],
    "risks": [],
    "unknowns": []
  },
  "verification_commands": [
    {
      "id": "verification-0001",
      "command": ["python", "-m", "pytest", "tests/regression/"],
      "reason": "why this verifies the change",
      "associated_files": [],
      "timeout_seconds": 120,
      "source_refs": []
    }
  ],
  "manual_checks": [
    {
      "id": "MANUAL-0001",
      "check": "specific check to perform later",
      "reason": "why this cannot be fully covered by known tests",
      "associated_files": [],
      "source_refs": []
    }
  ],
  "coverage_gaps": [
    {
      "id": "GAP-0001",
      "gap": "specific missing verification coverage",
      "affected_files": [],
      "needed_evidence_or_test": "bounded test discovery, new test, manual review, or user decision",
      "blocks_completion": true
    }
  ],
  "rejected_commands": [
    {
      "command": ["string or list"],
      "reason": "not_pytest|unbounded|mutating|shell_string|unsupported_tool|unsafe_scope"
    }
  ],
  "next_step": {
    "suggested_skill": "feedback-capture|implementation-packet-designer|execution-plan-writer|none",
    "reason": "short explanation"
  },
  "stop": {
    "required": false,
    "reason": "string or null",
    "open_questions": []
  }
}
```

Use empty arrays when there is no item. Use `null` for unknown scalar values.

## Command Rules

- Assign command IDs sequentially as `verification-0001`, `verification-0002`, and so on.
- Use one command per bounded test path.
- Keep `timeout_seconds` at `120` unless the input supplies a lower controller-approved timeout.
- Put packet target files in `associated_files`.
- Put evidence references in `source_refs` when known.
- Prefer existing test files over broad test directories.
- Use a test directory only when evidence identifies the directory but not a narrower file.
- If no related tests are known, leave `verification_commands` empty and add a coverage gap.

## Routing

- Route to `feedback-capture` when verification commands, manual checks, or coverage gaps are ready for tester review.
- Route to `implementation-packet-designer` when packet target files or acceptance criteria are missing.
- Route to `execution-plan-writer` when plan scope is too vague for verification planning.
- Route to `none` when verification planning is blocked pending user input or missing context.

## Must Not

- Do not run commands.
- Do not invoke tools.
- Do not edit files.
- Do not approve apply mode.
- Do not mark work complete.
- Do not include shell command strings.
- Do not include non-pytest commands.
- Do not suggest `git diff` or `git status` as verification.
- Do not hide missing test coverage.
- Do not treat a verification plan as proof that the implementation passed.

## Examples

Input context:

```json
{
  "execution_plan": {
    "plan_id": "EP-0001",
    "verification_strategy": [
      {
        "type": "pytest",
        "description": "Run controller service regression tests.",
        "associated_files": ["vllm_agent_gateway/controller_service/server.py"]
      }
    ]
  },
  "packet_design": {
    "packet_set_id": "IMPSET-0001",
    "packet_candidates": [
      {
        "id": "IMP-0001",
        "target_files": ["vllm_agent_gateway/controller_service/server.py"],
        "acceptance_criteria": ["Run lookup behavior is preserved."]
      }
    ]
  },
  "impact_map": {
    "related_tests": [
      {
        "path": "tests/regression/test_controller_service.py",
        "test_name": "test_controller_service_runs_documenter_review_and_persists_status",
        "coverage_for": ["vllm_agent_gateway/controller_service/server.py"],
        "status": "existing",
        "evidence_refs": ["tests/regression/test_controller_service.py:237"]
      }
    ]
  }
}
```

Output:

```json
{
  "verification_plan_id": "VERIFY-0001",
  "source_plan_id": "EP-0001",
  "source_packet_set_id": "IMPSET-0001",
  "basis": {
    "target_files": ["vllm_agent_gateway/controller_service/server.py"],
    "packet_ids": ["IMP-0001"],
    "acceptance_criteria": ["Run lookup behavior is preserved."],
    "related_tests": ["tests/regression/test_controller_service.py"],
    "risks": [],
    "unknowns": []
  },
  "verification_commands": [
    {
      "id": "verification-0001",
      "command": ["python", "-m", "pytest", "tests/regression/test_controller_service.py"],
      "reason": "This regression test file covers controller service run lookup and persistence behavior related to the target file.",
      "associated_files": ["vllm_agent_gateway/controller_service/server.py", "tests/regression/test_controller_service.py"],
      "timeout_seconds": 120,
      "source_refs": ["tests/regression/test_controller_service.py:237"]
    }
  ],
  "manual_checks": [],
  "coverage_gaps": [],
  "rejected_commands": [],
  "next_step": {
    "suggested_skill": "feedback-capture",
    "reason": "The verification plan is ready for tester review before execution."
  },
  "stop": {
    "required": false,
    "reason": null,
    "open_questions": []
  }
}
```

Input context:

```json
{
  "packet_design": {
    "packet_set_id": "IMPSET-0001",
    "packet_candidates": [
      {
        "id": "IMP-0001",
        "target_files": ["README.md"],
        "acceptance_criteria": ["README install sentence is updated."]
      }
    ]
  },
  "impact_map": {
    "related_tests": []
  }
}
```

Output:

```json
{
  "verification_plan_id": "VERIFY-0001",
  "source_plan_id": null,
  "source_packet_set_id": "IMPSET-0001",
  "basis": {
    "target_files": ["README.md"],
    "packet_ids": ["IMP-0001"],
    "acceptance_criteria": ["README install sentence is updated."],
    "related_tests": [],
    "risks": [],
    "unknowns": []
  },
  "verification_commands": [],
  "manual_checks": [
    {
      "id": "MANUAL-0001",
      "check": "Review README.md draft output and confirm the install sentence matches the approved replacement.",
      "reason": "No existing pytest target is identified for this documentation-only packet.",
      "associated_files": ["README.md"],
      "source_refs": []
    }
  ],
  "coverage_gaps": [
    {
      "id": "GAP-0001",
      "gap": "No existing pytest coverage is identified for the README text replacement.",
      "affected_files": ["README.md"],
      "needed_evidence_or_test": "Manual review or bounded test discovery for documentation checks.",
      "blocks_completion": false
    }
  ],
  "rejected_commands": [],
  "next_step": {
    "suggested_skill": "feedback-capture",
    "reason": "Manual verification and coverage gaps are ready for tester review."
  },
  "stop": {
    "required": false,
    "reason": null,
    "open_questions": []
  }
}
```

Input context:

```json
{
  "packet_design": {
    "packet_set_id": "IMPSET-0001",
    "packet_candidates": [
      {
        "id": "IMP-0001",
        "target_files": ["README.md"],
        "acceptance_criteria": ["README is updated."]
      }
    ]
  },
  "requested_verification_commands": [
    "git diff",
    ["python", "-c", "print('ok')"],
    ["npm", "test"]
  ]
}
```

Output:

```json
{
  "verification_plan_id": "VERIFY-0001",
  "source_plan_id": null,
  "source_packet_set_id": "IMPSET-0001",
  "basis": {
    "target_files": ["README.md"],
    "packet_ids": ["IMP-0001"],
    "acceptance_criteria": ["README is updated."],
    "related_tests": [],
    "risks": [],
    "unknowns": []
  },
  "verification_commands": [],
  "manual_checks": [],
  "coverage_gaps": [
    {
      "id": "GAP-0001",
      "gap": "No controller-compatible pytest verification target is identified.",
      "affected_files": ["README.md"],
      "needed_evidence_or_test": "Provide an existing pytest path or use manual review.",
      "blocks_completion": true
    }
  ],
  "rejected_commands": [
    {
      "command": ["git diff"],
      "reason": "shell_string"
    },
    {
      "command": ["python", "-c", "print('ok')"],
      "reason": "not_pytest"
    },
    {
      "command": ["npm", "test"],
      "reason": "unsupported_tool"
    }
  ],
  "next_step": {
    "suggested_skill": "none",
    "reason": "Verification planning is blocked until a controller-compatible pytest target or manual review decision is available."
  },
  "stop": {
    "required": true,
    "reason": "Requested verification commands are outside controller policy and no pytest target is known.",
    "open_questions": ["Which existing pytest path should verify this packet, or should this be manual review only?"]
  }
}
```
