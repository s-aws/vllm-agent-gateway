# Documenter E2E Roadmap

This roadmap is the control document for the documenter workflow. Any material documenter workflow change should either complete an item here or update this roadmap first.

The goal is a dependable end-to-end documentation review pipeline:

```text
target repo -> controller manifest -> review plan -> bounded chunk packets -> documenter role -> validated deltas -> aggregate -> summary/change plan -> optional drafts
```

## Guardrails

- The controller owns discovery, sequencing, budgets, tool dependencies, state, and artifact writing.
- The documenter role owns only packet-bound inspection and structured output.
- Do not move repo traversal, manifest creation, chunk selection, retry logic, or write decisions into the role prompt.
- Every controller action that reads files, scans files, runs git, executes tests, or writes artifacts must be represented as a tool dependency or explicit artifact policy.
- Default behavior should be read-only against the target repo.
- New output artifacts must be deterministic enough to compare across runs.
- Long-run features need resume/state before being considered dependable.

## Current State

| Area | Status | Notes |
| --- | --- | --- |
| Role prompt proxy | Done | `documenter/default` role endpoint is available through the prompt proxy and gateway. |
| Token budget gateway | Done | Gateway rejects oversized inputs and clamps output. |
| Tool catalog | Done | `runtime/tools.json` defines controller tool capabilities. |
| Role tool assignment | Done | `documenter/default` has `git_ls_files`, `read_file`, and `scan_files`. |
| External target repo | Done | `--config-root` and `--target-root` are separate. |
| Chunk review | Done | Documents are chunked with configurable line overlap. |
| Structured deltas | Done | Review packets require strict JSON output and controller validation. |
| Summary aggregation | Done | `full` mode writes JSON and Markdown summary artifacts. |
| Follow-up queue | Done | Optional exact-file follow-up expansion has depth/count bounds. |
| Document manifest | Done | `full` mode writes a manifest artifact; default scope is tracked files, with `--document-scope all` for bootstrap scans. |
| Review planning | Done | Review plan artifacts feed bounded `visible_followup_candidates` into packets. |
| Source-aware follow-up review | Done | Follow-up expansion defaults to packet-visible candidates and records skip reason codes. |
| Tool dependency audit | Partial | Reports include `tool_policy.controller_tool_dependencies`; deeper per-artifact provenance is still needed. |

## Phase 1: Manifest-Backed Review Planning

Status: Done

Build a review plan from the document manifest before chunk review.

Deliverables:

- `doc-review-plan-*.json` artifact. Done.
- `visible_followup_candidates` included in each review packet. Done.
- Candidate list bounded by count and token estimate. Done.
- Candidate reasons recorded, such as `seed_doc`, `same_directory`, `runtime_config`, `startup_script`, `role_prompt`, or `linked_from_chunk`. Done.
- Plan summary added to the main report. Done.

Acceptance criteria:

- The documenter no longer has to infer exact follow-up paths only from chunk prose. Done.
- The packet never receives the whole manifest by default. Done.
- Candidate selection is deterministic for the same repo state and arguments. Done.
- Invalid candidate paths cannot enter the packet. Done.
- Tool dependencies used to build the plan are recorded. Done.

## Phase 2: Source-Aware Follow-Up Review

Status: Done

Make follow-up review more consistent by using the review plan as the allowed candidate set.

Deliverables:

- Follow-up files must come from `visible_followup_candidates` unless explicitly allowed by a strict option. Done.
- Skipped follow-ups include reason codes for not visible, not in scope, unsupported suffix, depth limit, count limit, and already seen. Done.
- Follow-up acceptance records include the candidate reason from the plan. Done.

Acceptance criteria:

- A role cannot expand traversal beyond controller-provided candidates by inventing paths. Done.
- The report explains why each accepted follow-up was visible to the model. Done.
- Existing exact tracked follow-up behavior remains available for compatibility only when intentionally enabled. Done.

## Phase 3: Documentation Change Plan

Status: Planned

Convert review findings into a non-mutating documentation change plan.

Deliverables:

- `doc-change-plan-*.md` artifact.
- Group findings by target file.
- Separate safe edits, needs-user-decision items, and insufficient-evidence items.
- Include confidence and source chunk references where available.

Acceptance criteria:

- No target repo files are modified.
- Every proposed change traces back to facts, gaps, or validation warnings in the report.
- The plan can be reviewed without opening the full JSON report.

## Phase 4: Draft Output

Status: Planned

Add optional draft generation without mutating target docs in place.

Deliverables:

- `--write-draft` writes proposed files under an ignored draft artifact directory.
- Draft metadata maps each draft file back to source document, change-plan item, and report path.
- No overwrite of target repo files by default.

Acceptance criteria:

- Running draft mode is reversible by deleting the draft artifact directory.
- The controller refuses draft writes outside the configured output directory unless a future explicit unsafe option exists.
- Drafts include enough provenance to review or apply manually.

## Phase 5: Resume And State

Status: Planned

Make longer runs restartable.

Deliverables:

- `run-state-*.json` artifact or embedded resumable state.
- `--resume <report-or-state>` option.
- Completed chunks and accepted follow-ups are skipped on resume.
- Failed packet metadata is preserved.

Acceptance criteria:

- Interrupting a run does not require starting from the seed document again.
- Resume refuses incompatible arguments unless explicitly overridden.
- State format is documented and versioned.

## Phase 6: Controller Tests

Status: Planned

Add tests before broadening controller behavior further.

Required coverage:

- tracked vs all document scope
- manifest artifact shape
- review plan candidate limits
- follow-up depth/count limits
- invalid follow-up rejection
- tool dependency reporting
- artifact path safety
- resume compatibility checks when resume exists

Acceptance criteria:

- Tests use fake endpoints where model behavior is not the subject under test.
- Tests do not require vLLM.
- Model smoke tests remain separate from deterministic controller tests.

## Phase 7: Tool Mediation

Status: Planned

Move from controller-only tool authorization toward real mediated tools when needed.

Deliverables:

- Tool schema generation from `runtime/tools.json`.
- Model tool-call detection.
- Local execution loop.
- Tool result injection.
- Final response validation.

Acceptance criteria:

- A model-visible tool name always corresponds to an executable local capability.
- Raw tool-call-shaped text is never treated as completed tool execution.
- Role prompts describe policy, but enforcement lives in controller/client/tool mediator code.

## Drift Controls

Use these checks before adding or changing documenter workflow behavior:

1. Does the change belong to controller, gateway, prompt proxy, role prompt, or tool mediator?
2. Is the behavior covered by a roadmap phase above?
3. Does it add a new artifact or change an existing artifact schema?
4. Does it introduce a new tool dependency?
5. Is the target repo still read-only by default?
6. Can the behavior be tested without vLLM?
7. Does the final report explain what happened without relying on hidden process state?

If the answer to item 2 is no, update this roadmap before implementing the behavior.

## Artifact Inventory

Current artifacts:

- `documenter-*.json`: main controller report.
- `documenter-*.md`: final Markdown summary from `full` mode.
- `document-manifest-*.json`: document manifest from `full` mode.
- `doc-review-plan-*.json`: review plan and candidate pool.

Planned artifacts:

- `doc-change-plan-*.md`
- `drafts/<run-id>/...`
- `run-state-*.json`

## Immediate Next Step

Implement Phase 3: documentation change planning. The controller should convert validated review findings into a non-mutating `doc-change-plan-*.md` artifact grouped by target file, risk, missing evidence, and confidence.
