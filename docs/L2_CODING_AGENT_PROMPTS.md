# L2 Coding Agent Prompt Backlog

L2 prompts are the next product layer after the validated L1 suite. They combine more than one simple operation while preserving deterministic routing, bounded tool use, chat-visible output, and approval gates before mutation.

L2 is not advanced refactoring. Broad refactor requests remain deferred until the advanced acceptance scope is explicitly reapproved.

## Acceptance Standard

Each L2 prompt must have:

- a natural-language prompt that does not require manual skill injection
- deterministic workflow-router selection
- a controller-owned workflow path
- chat-visible default `format_a` output
- JSON artifacts for machine inspection
- mutation policy stated in output
- regression coverage
- Bash workflow-router gateway validation
- AnythingLLM validation
- validation against `/mnt/c/coinbase_testing_repo_frozen_tmp`
- validation against `/mnt/c/coinbase_testing_repo_frozen_tmp.github`

## L2-001: Diagnose Failing Test And Recommend Safe Fix Plan

Prompt:

```text
In <repo>, diagnose why this pytest failure is happening. Do not edit files.
Return root cause, smallest safe fix plan, and verification command.

FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected client_order_id index
E   AssertionError: expected client_order_id index
```

Required behavior:

- route to `code_investigation.plan`
- execute read-only investigation
- return `downstream_test_failure_summary`
- include `Root cause hypothesis:` in chat
- include `Smallest safe fix plan:` in chat
- include an exact `python -m pytest <path>::<test>` command
- include `Source mutation: false`
- leave watched source/test/docs files unchanged

Status: implemented and live validated.

Latest proof from June 4, 2026:

- focused regression returned `3 passed, 102 deselected`
- full regression returned `178 passed, 19 deselected`
- Bash workflow-router gateway passed on `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260604T235632737666Z`
- Bash workflow-router gateway passed on `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260604T235702627998Z`
- AnythingLLM passed on `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260604T235726950225Z`
- AnythingLLM passed on `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260604T235754641271Z`

## L2-002: Investigate Multi-File Behavior

Prompt:

```text
In <repo>, investigate how placed_order_id stealth lookup flows across source files.
Read only. Return the beginning point, participating files, callers/usages,
related tests, risks, and the smallest verification commands.
```

Required behavior:

- route to `code_investigation.plan`
- execute read-only investigation
- return `downstream_multi_file_behavior_investigation`
- include `Beginning point:` in chat
- include `Participating files:` in chat
- include `Callers/usages:` in chat
- include `Related tests:` in chat
- include `Risks:` in chat
- include `Verification:` in chat
- include `Source mutation: false`
- leave watched source/test/docs files unchanged

Status: implemented and live validated.

Latest proof from June 5, 2026:

- focused L2 regression returned `2 passed, 104 deselected`
- full regression returned `179 passed, 19 deselected`
- Bash workflow-router gateway passed on `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260605T000955283060Z`
- Bash workflow-router gateway passed on `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260605T001020196045Z`
- AnythingLLM passed on `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260605T001050565002Z`
- AnythingLLM passed on `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260605T001118990516Z`

## L2-003: Dependency Impact Summary

Prompt:

```text
In <repo>, summarize the dependency impact if placed_order_id stealth lookup behavior changes.
Read only. Return impacted source files, callers/usages, related tests, risk level,
and recommended validation commands.
```

Required behavior:

- route to `code_investigation.plan`
- execute read-only investigation
- return `downstream_dependency_impact_summary`
- include `Impacted files:` in chat
- include `Callers/usages:` in chat
- include `Related tests:` in chat
- include `Risk level:` in chat
- include `Verification:` in chat
- include `Source mutation: false`
- leave watched source/test/docs files unchanged

Status: implemented and live validated.

Latest proof from June 5, 2026:

- focused L2 regression returned `3 passed, 104 deselected`
- full regression returned `180 passed, 19 deselected`
- Bash workflow-router gateway passed on `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260605T002554376202Z`
- Bash workflow-router gateway passed on `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260605T002649367268Z`
- AnythingLLM passed on `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260605T002747790255Z`
- AnythingLLM passed on `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260605T002937663397Z`

## L2-005: Test Selection With Rationale

Prompt:

```text
In <repo>, choose the smallest, medium, and broad validation commands for placed_order_id stealth lookup.
Read only. Explain why each command is relevant, what risk it covers, and what gaps remain.
```

Required behavior:

- route to `code_investigation.plan`
- execute read-only investigation
- return `downstream_test_selection_plan`
- include `Smallest command:` in chat
- include `Medium command:` in chat
- include `Broad command:` in chat
- include `Rationale:` in chat
- include `Covered risks:` in chat
- include `Confidence:` in chat
- include `Gaps:` in chat
- include `Source mutation: false`
- leave watched source/test/docs files unchanged

Status: implemented and live validated.

Latest proof from June 5, 2026:

- focused L2 regression returned `4 passed, 104 deselected`
- full regression returned `181 passed, 19 deselected`
- Bash workflow-router gateway passed on `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260605T005612353706Z`
- Bash workflow-router gateway passed on `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260605T005700642476Z`
- AnythingLLM passed on `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260605T005753115220Z`
- AnythingLLM passed on `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260605T005844576902Z`
- full L2 suite passed for L2-001, L2-002, L2-003, and L2-005 through Bash gateway and AnythingLLM on both frozen fixtures

## L2-006: Diagnose Runtime Error Or Stack Trace

Prompt:

```text
In <repo>, diagnose this runtime stack trace for request_stealth_orders dashboard behavior.
Read only. Return observed error, likely cause, evidence files, next inspection steps,
risks, gaps, and verification commands.

Traceback (most recent call last):
  File "dashboard_server.py", line 10, in handle_websocket_message
core.exceptions.WebSocketMessageError: Missing 'type' field in message
```

Required behavior:

- route to `code_investigation.plan`
- execute read-only investigation
- return `downstream_runtime_error_diagnosis`
- include `Observed error:` in chat
- include `Likely cause:` in chat
- include `Evidence files:` in chat
- include `Next inspection:` in chat
- include `Verification:` in chat
- include `Source mutation: false`
- leave watched source/test/docs files unchanged

Status: implemented and live validated.

## L2-007: Map Request Or Data Flow

Prompt:

```text
In <repo>, map the request/data flow for request_stealth_orders from dashboard message
to stealth order snapshot. Read only. Return flow steps, participating files,
risks, gaps, and verification commands.
```

Required behavior:

- route to `code_investigation.plan`
- execute read-only investigation
- return `downstream_request_flow_map`
- include `Target flow:` in chat
- include `Flow steps:` in chat
- include `Participating files:` in chat
- include `Verification:` in chat
- include `Source mutation: false`
- leave watched source/test/docs files unchanged

Status: implemented and live validated.

## L2-008: Compare Two Candidate Code Paths

Prompt:

```text
In <repo>, compare the placed_order_id stealth lookup path with the client_order_id
index path. Read only. Return candidate paths, evidence, risks, recommended path
if supported, gaps, and verification commands.
```

Required behavior:

- route to `code_investigation.plan`
- execute read-only investigation
- return `downstream_code_path_comparison`
- include `Comparison target:` in chat
- include `Candidate paths:` in chat
- include `Recommended path:` in chat
- include `Risks:` in chat
- include `Source mutation: false`
- leave watched source/test/docs files unchanged

Status: implemented and live validated.

## L2-009: Identify Minimal Safe Change Surface

Prompt:

```text
In <repo>, identify the minimal safe change surface for changing placed_order_id
stealth lookup behavior. Read only. Return files that would need review, related
tests, risk level, gaps, and verification commands. Stop before implementation.
```

Required behavior:

- route to `code_investigation.plan`
- execute read-only investigation
- return `downstream_change_surface_summary`
- include `Change surface files:` in chat
- include `Risk level:` in chat
- include `Implementation status: not_ready_without_approval` in chat
- include `Verification:` in chat
- include `Source mutation: false`
- leave watched source/test/docs files unchanged

Status: implemented and live validated.

Latest Phase 32 proof from June 5, 2026:

- focused Phase 32 controller regression returned `4 passed`
- skill registry/eval/batch regression returned `41 passed`
- skill eval catalog returned `case_count=34`, `failed_count=0`
- full regression returned `226 passed, 19 deselected`
- Bash workflow-router gateway passed `L2-006` through `L2-009` on both frozen fixtures
- AnythingLLM passed `L2-006` through `L2-009` on both frozen fixtures

## Planned L2 Candidates

These are not approved for implementation until the previous L2 has passing regression and live validation.

1. `L2-004: Approved Draft Implementation Prep`
   - Convert an approved read-only investigation into exact draft packet operations.
   - Expected output: draft proposal, operation targets, safety checks, verification, no source mutation.
   - Status: planned but not the next default scope unless write-adjacent L2 work is explicitly selected.

2. `Skill Library Scaling Foundation`
   - Define the metadata and eval contract needed to scale beyond hand-added L1/L2 prompt routes.
   - Expected output: catalog schema, de-duplication rules, eval fixture shape, and one worked example.
   - Status: completed in roadmap Phase 21.

3. `Skill Library Admission Workflow`
   - Add a controlled path for one future draft skill entry and matching eval case at a time.
   - Expected output: admission validation, rejection cases, docs command, and no runtime route change until regression passes.
   - Status: next roadmap target.

## Explicit Non-Goals

- no broad single-path refactor acceptance yet
- no repository mutation without a separate approval path
- no manual skill injection
- no direct raw CodeGraphContext, MCP, or Cypher access from natural prompts
- no uncontrolled skill-library expansion without catalog validation and eval fixtures
