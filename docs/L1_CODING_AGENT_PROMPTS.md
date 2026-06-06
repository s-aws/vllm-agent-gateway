# L1 Coding Agent Prompt Backlog

This is the review list for simple, common coding-agent prompts that should become deterministic skills with tool operation.

The broad refactor prompt is intentionally deferred to advanced stages. L1 prompts should be small enough that a first-time tester can tell whether the agent succeeded without reading a long chain of artifacts.

## Selection Rules

An L1 prompt must:

- match a common coding-agent request
- have one clear user-visible outcome
- use a small, explicit tool set
- produce bounded artifacts
- avoid repository mutation unless the prompt is explicitly in the write-capable group
- have a simple pass/fail acceptance signal

The first L1 skills should be read-only. Write-capable L1 skills can follow after the read-only skills are stable through AnythingLLM.

## Current Status

- `L1-001: Find Where Behavior Starts`: E2E passed through default regression, Bash gateway, localhost model path, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-002: Explain A Function Or File`: E2E passed through default regression, Bash gateway, localhost model path, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-003: Find Related Tests`: E2E passed through default regression, Bash gateway, localhost model path, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-004: Locate Configuration Or Environment Setting`: E2E passed through default regression, Bash gateway, localhost model path, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-005: Summarize Test Failure From Pasted Output`: E2E passed through default regression, Bash gateway, localhost model path, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-006: Check Whether Behavior Already Exists`: E2E passed through default regression, Bash gateway, localhost model path, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-007: Find Callers Or Usages`: E2E passed through default regression, Bash gateway, localhost model path, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-008: Produce A Safe Test Command`: E2E passed through default regression, Bash gateway, localhost model path, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-009: Add Or Update A Small Unit Test`: E2E passed through default regression, Bash gateway, localhost model path, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-010: Make A Small Text Or Documentation Edit`: E2E passed through default regression, Bash gateway, localhost model path, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-011: Fix A Simple Failing Test`: E2E passed through default regression, Bash gateway, localhost model path, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-012: Locate Endpoint Or Route Handler`: E2E passed through full regression, Bash gateway, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-013: Locate Error Or Log Message Source`: E2E passed through full regression, Bash gateway, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-014: Summarize A Module Or File`: E2E passed through full regression, Bash gateway, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-015: Find Data Model Or Schema`: E2E passed through full regression, Bash gateway, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-016: Find Imports Or Dependencies`: E2E passed through full regression, Bash gateway, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-017: Identify Test Coverage Gaps`: E2E passed through full regression, Bash gateway, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-018: Find Documentation For Behavior`: E2E passed through full regression, Bash gateway, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-019: Locate CLI Or Script Entrypoint`: E2E passed through full regression, Bash gateway, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-020: Explain Configuration Runtime Effect`: E2E passed through full regression, Bash gateway, both frozen Coinbase fixtures, and AnythingLLM.
- `L1-021: Find Recent Or Local Changes`: E2E passed through full regression, Bash gateway, both frozen Coinbase fixtures, and AnythingLLM.
- `D1-004: Draft Small Config Default Test`: E2E passed through full regression, Bash gateway, both frozen Coinbase fixtures, and AnythingLLM.
- `D1-005: Draft Small Error Message Assertion Test`: E2E passed through full regression, Bash gateway, both frozen Coinbase fixtures, and AnythingLLM.
- `D1-006: Draft Small Test Assertion Update`: E2E passed through full regression, Bash gateway, both frozen Coinbase fixtures, and AnythingLLM.
- Current status: L1-001 through L1-021 and D1-004 through D1-006 have E2E proof. The broad refactor prompt remains deferred until a separate advanced scope is approved.

## L1 Read-Only Prompts

### L1-001: Find Where Behavior Starts

Prompt shape:

```text
In <repo>, find where <behavior> starts. Read only. Return the entrypoint, evidence files, related tests, and confidence.
```

Example:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find where the placed_order_id stealth lookup begins. Read only. Return the entrypoint, evidence files, related tests, and confidence.
```

Tools:

- `git_grep`
- `read_file`
- `structure_index`

Expected artifacts:

- route decision
- entrypoint evidence
- related files
- related tests
- confidence and unknowns

Acceptance signal:

- identifies at least one plausible entrypoint with source refs
- includes related test files when available
- does not mutate the repo

Recommended first build target: yes.

### L1-002: Explain A Function Or File

Prompt shape:

```text
In <repo>, explain what <file or function> does. Read only. Include key inputs, outputs, side effects, and tests.
```

Tools:

- `read_file`
- `structure_index`
- `git_grep`

Expected artifacts:

- bounded source excerpt
- `code_explanation` artifact
- explanation summary with key inputs, outputs, side effects, and related tests
- source refs
- related tests

Acceptance signal:

- explanation cites source files and line refs
- distinguishes confirmed facts from assumptions
- does not mutate the repo

### L1-003: Find Related Tests

Prompt shape:

```text
In <repo>, find tests related to <behavior or file>. Read only. Return test files, matching terms, and recommended test commands.
```

Tools:

- `git_grep`
- `read_file`

Expected artifacts:

- test discovery result
- test command candidates
- source refs

Acceptance signal:

- returns at least one relevant test file when present
- recommended commands are bounded to discovered test files
- does not invent test paths

### L1-004: Locate Configuration Or Environment Setting

Prompt shape:

```text
In <repo>, find where <setting/env var/config key> is defined or used. Read only. Return files, references, and likely runtime effect.
```

Tools:

- `git_grep`
- `read_file`
- `structure_index` for config/index slices when useful

Expected artifacts:

- exact matches
- `configuration_lookup` artifact with definition/read/usage roles
- defining files
- consuming files
- uncertainty notes

Acceptance signal:

- exact setting name appears in evidence
- distinguishes definition from usage
- does not mutate the repo

### L1-005: Summarize Test Failure From Pasted Output

Prompt shape:

```text
Given this test output, identify the failing test, likely cause, and next read-only inspection step. Do not edit files.
```

Tools:

- no repo tool required when output is sufficient
- `git_grep` and `read_file` if the prompt includes a repo path

Expected artifacts:

- `test_failure_summary` artifact
- failure summary
- suspected cause
- next inspection step
- optional source refs

Acceptance signal:

- identifies the failing test and error message
- proposes a bounded next step, not a broad fix
- does not mutate the repo

### L1-006: Check Whether Behavior Already Exists

Prompt shape:

```text
In <repo>, check whether <behavior> already exists. Read only. Return evidence for yes, no, or unknown.
```

Tools:

- `git_grep`
- `read_file`
- `structure_index`

Expected artifacts:

- evidence for existing behavior
- `behavior_existence` artifact with `exists`, `unknown`, and evidence gaps
- evidence gaps
- likely files to inspect next

Acceptance signal:

- returns `exists`, `not_found`, or `unknown`
- cites evidence
- avoids claiming absence from a shallow search unless budget limits are explicit

### L1-007: Find Callers Or Usages

Prompt shape:

```text
In <repo>, find callers/usages of <function, class, field, or route>. Read only. Group by file and explain each usage briefly.
```

Tools:

- `git_grep`
- `structure_index`
- curated relationship lookup when available

Expected artifacts:

- usage list
- `usage_summary` artifact grouped by file
- grouped files
- source refs
- relationship confidence

Acceptance signal:

- each usage has a source ref
- groups direct usages separately from weak textual matches
- does not mutate the repo

### L1-008: Produce A Safe Test Command

Prompt shape:

```text
In <repo>, recommend the smallest test command for <behavior or file>. Read only. Explain why that command is relevant.
```

Tools:

- `git_grep`
- `read_file`
- optional test discovery helper

Expected artifacts:

- recommended command
- related tests
- reason and source refs

Acceptance signal:

- command targets discovered tests
- command is bounded, not full-suite by default
- no command is recommended without evidence

## L1 Write-Capable Prompts

These should be built only after read-only L1 skills are stable. They require explicit approval, disposable-copy proof, or draft-only packet generation.

### L1-009: Add Or Update A Small Unit Test

Prompt shape:

```text
In <repo>, add a small test for <behavior>. Draft only. Show the proposed test file and verification command before applying.
```

Tools:

- `git_grep`
- `read_file`
- `implementation.workflow` draft path

Expected artifacts:

- test target selection
- `small_unit_test_proposal` artifact
- draft packet
- verification command
- non-mutation proof unless approved apply is in a disposable copy

Acceptance signal:

- proposed test is in an existing relevant test file or a justified new file
- draft does not mutate protected source
- verification command is evidence-backed
- AnythingLLM response lists `small_unit_test_proposal` and `downstream_implementation_workflow_report`

### L1-010: Make A Small Text Or Documentation Edit

Prompt shape:

```text
In <repo>, update <doc/file> with this exact wording. Draft only and verify the old text exists exactly once.
```

Tools:

- `read_file`
- exact `replace_text` validation
- `implementation.workflow` draft path

Expected artifacts:

- exact operation
- `small_text_edit_proposal` artifact
- packet preview
- `implementation_workflow_report` from the existing draft implementation path
- non-mutation proof for protected source files

Acceptance signal:

- `old` text matches exactly once
- `new` text differs
- draft path completes without mutating the source
- AnythingLLM response lists `small_text_edit_proposal` and `downstream_implementation_workflow_report`

### L1-011: Fix A Simple Failing Test

Prompt shape:

```text
In <repo>, inspect this failing test and propose the smallest fix. Draft only; do not apply until approved.
```

Tools:

- `read_file`
- `git_grep`
- optional `run_tests` on bounded command
- `implementation.workflow` draft path

Expected artifacts:

- `simple_test_fix_proposal` artifact
- exact `replace_text` operation
- packet preview
- `implementation_workflow_report` from the existing draft implementation path
- bounded verification command
- non-mutation proof for protected source files

Acceptance signal:

- fix proposal is tied to failure evidence
- bounded verification command exists
- no unapproved mutation
- AnythingLLM response lists `simple_test_fix_proposal` and `downstream_implementation_workflow_report`

### L1-012: Locate Endpoint Or Route Handler

Prompt shape:

```text
In <repo>, find the handler for <endpoint, route, or message type>. Read only. Return handler files, source refs, and related tests.
```

Expected artifact:

- `endpoint_route_lookup`

Acceptance signal:

- returns the handler file and role with source refs
- uses read-only investigation only
- AnythingLLM response includes the handler evidence without opening artifacts

### L1-013: Locate Error Or Log Message Source

Prompt shape:

```text
In <repo>, locate the source of error or log message "<message>". Read only. Return file, line, and role.
```

Expected artifact:

- `message_source_lookup`

Acceptance signal:

- returns exact or bounded message-source evidence
- classifies the role, such as raised exception or log source
- does not mutate the repo

### L1-014: Summarize A Module Or File

Prompt shape:

```text
In <repo>, summarize module <path>. Read only. Return responsibilities, definitions, related tests, and source refs.
```

Expected artifact:

- `module_summary`

Acceptance signal:

- returns responsibilities and definitions from bounded source evidence
- includes related tests when available
- does not invent module behavior outside the evidence budget

### L1-015: Find Data Model Or Schema

Prompt shape:

```text
In <repo>, find the data model or schema fields for <model/table>. Read only. Return model files, fields, and source refs.
```

Expected artifact:

- `data_model_lookup`

Acceptance signal:

- returns field names, definitions, field-bearing files, and source refs
- prioritizes files that actually contain extracted fields
- does not claim complete schema coverage when bounded extraction is partial

### L1-016: Find Imports Or Dependencies

Prompt shape:

```text
In <repo>, find imports/dependencies for <file>. Read only. Return imports, source refs, and whether files were mutated.
```

Expected artifact:

- `dependency_lookup`

Acceptance signal:

- returns grouped import modules with source refs
- chat output prioritizes project imports over stdlib noise
- does not mutate the repo

### L1-017: Identify Test Coverage Gaps

Prompt shape:

```text
In <repo>, identify test coverage gaps for <behavior>. Read only. Return covered tests, uncovered source files, verification commands, and gaps.
```

Expected artifact:

- `coverage_gap_summary`

Acceptance signal:

- returns related tests and source files from bounded evidence
- reports coverage gaps conservatively instead of claiming full measured coverage
- includes verification commands and `Source mutation: false`

### L1-018: Find Documentation For Behavior

Prompt shape:

```text
In <repo>, find documentation for <behavior>. Read only. Return documentation files, source refs, and gaps.
```

Expected artifact:

- `documentation_lookup`

Acceptance signal:

- returns Markdown/README/agent documentation evidence when found
- separates documentation evidence from source-code evidence
- returns an explicit bounded-evidence gap when docs are not found

### L1-019: Locate CLI Or Script Entrypoint

Prompt shape:

```text
In <repo>, locate the CLI/script entrypoint <path or command target>. Read only. Return entrypoint files, command, and source refs.
```

Expected artifact:

- `cli_entrypoint_lookup`

Acceptance signal:

- returns `main.py`, `def main`, or `__main__` guard evidence when present
- returns conservative runnable commands such as `python main.py`
- does not let unrelated words like `client_order_id` trigger CLI behavior

### L1-020: Explain Configuration Runtime Effect

Prompt shape:

```text
In <repo>, explain the runtime effect of <configuration key or environment variable>. Read only. Return references, effect, and source refs.
```

Expected artifact:

- `configuration_effect_summary`

Acceptance signal:

- distinguishes environment reads, runtime consumers, and client/auth configuration inputs
- does not expose runtime secret values
- preserves older `configuration_lookup` behavior for "defined or used" prompts

### L1-021: Find Recent Or Local Changes

Prompt shape:

```text
In <repo>, find recent or local changes. Read only. Return git status, recent commits, changed files, and unsupported gaps.
```

Expected artifact:

- `local_change_summary`

Acceptance signal:

- uses only non-mutating git status/log/diff-summary commands
- returns recent commits and local status for git repositories
- returns `limited_non_git` with `git_history_unavailable` for non-git repositories instead of hallucinating history

## D1 Draft-Only Prompt Expansions

These are write-adjacent prompt families that must stay draft-only. They route through `execution_planning.plan` and the existing `implementation.workflow` draft path. They must not mutate protected fixture source files.

### D1-004: Draft Small Config Default Test

Prompt shape:

```text
In <repo>, draft a small unit test in <test_file> proving config default <symbol> in <source_file> defaults to <value>. Draft only. Show the proposed test file, safety checks, and verification command before applying. Do not mutate files.
```

Expected artifact:

- `small_unit_test_proposal` with subkind `config_default_test`

Acceptance signal:

- exact config symbol and expected value are bounded from source evidence
- proposal uses `append_text` against the requested test file
- chat output includes `Draft proposal:` and `Source mutation: false`

### D1-005: Draft Small Error Message Assertion Test

Prompt shape:

```text
In <repo>, draft a small unit test in <test_file> asserting exact error message "<message>" from <source_file>. Draft only. Show the proposed test file, safety checks, and verification command before applying. Do not mutate files.
```

Expected artifact:

- `small_unit_test_proposal` with subkind `message_assertion_test`

Acceptance signal:

- exact message source is found before proposal generation
- proposed test includes the exact message text
- chat output includes `Draft proposal:` and `Source mutation: false`

### D1-006: Draft Small Test Assertion Update

Prompt shape:

```text
In <repo>, draft an update to <test_file> changing assertion '<old_assertion>' to '<new_assertion>'. Draft only. Show exact operation, safety checks, and verification command before applying. Do not mutate files.
```

Expected artifact:

- `small_unit_test_proposal` with subkind `test_assertion_update`

Acceptance signal:

- old assertion is found exactly once
- proposal uses `replace_text` and does not imply production-code edits
- chat output includes `Draft proposal:` and `Source mutation: false`

## Deferred Advanced Prompt

The broad refactor prompt is not an L1 prompt:

```text
In <repo>, refactor the placed_order_id stealth lookup so there is only one code path. Start from the logic beginning point, investigate first, create an implementation plan, wait for approval before implementation prep, and provide verification commands.
```

Reason for deferral:

- combines multiple skills
- requires investigation, planning, approval, packet design, verification, and feedback
- hard for a first-time tester to evaluate
- too broad for validating one skill at a time

It should return only after L1 read-only skills and L1 draft-only write skills are stable.

## Validated Build Order

1. `L1-001: Find Where Behavior Starts`
2. `L1-003: Find Related Tests`
3. `L1-008: Produce A Safe Test Command`
4. `L1-002: Explain A Function Or File`
5. `L1-006: Check Whether Behavior Already Exists`
6. `L1-007: Find Callers Or Usages`
7. `L1-004: Locate Configuration Or Environment Setting`
8. `L1-005: Summarize Test Failure From Pasted Output`
9. `L1-010: Make A Small Text Or Documentation Edit`
10. `L1-009: Add Or Update A Small Unit Test`
11. `L1-011: Fix A Simple Failing Test`
12. `L1-012: Locate Endpoint Or Route Handler`
13. `L1-013: Locate Error Or Log Message Source`
14. `L1-014: Summarize A Module Or File`
15. `L1-015: Find Data Model Or Schema`
16. `L1-016: Find Imports Or Dependencies`
17. `L1-017: Identify Test Coverage Gaps`
18. `L1-018: Find Documentation For Behavior`
19. `L1-019: Locate CLI Or Script Entrypoint`
20. `L1-020: Explain Configuration Runtime Effect`
21. `L1-021: Find Recent Or Local Changes`

## Review Questions

- Which L1 prompts should remain in the first-time tester path, and which should move to optional checks?
- Should the next approved scope continue with Phase 32 L2 diagnostic expansion or pause for founder testing of the 21 L1 prompts?
- Should L1 write-capable prompts stay draft-only permanently, or should disposable-copy apply become an L2 capability?
