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
| Documentation change plan | Done | `full` mode writes a non-mutating Markdown change plan grouped by target file, evidence class, follow-ups, validation notes, and caveats. |
| Draft output | Done | `--write-draft` writes reversible draft artifact copies and metadata under the configured output directory. |
| Resume and state | Done | `run-state-*.json` tracks queue position, completed chunks, follow-ups, failures, artifacts, and compatibility keys for restartable runs. |
| Controller tests | Done | `tests/regression/test_documenter_orchestrator.py` covers deterministic controller behavior with temp repos and fake endpoints. |
| Tool mediation | Done | `tool_mediator.py` generates schemas, detects structured tool calls, executes local tools, injects results, and validates final responses. |
| Streaming core | Done | `context_presence` proves bounded streaming reads, byte/line offsets, coverage accounting, source labels, and resumable state without vLLM. |
| Reduction/query modes | Planned | Modes are tracked separately after the streaming core; summarization is one lossy mode, not the default. |
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

Status: Done

Convert review findings into a non-mutating documentation change plan.

Deliverables:

- `doc-change-plan-*.md` artifact. Done.
- Group findings by target file. Done.
- Separate safe edits, needs-user-decision items, and insufficient-evidence items. Done.
- Include confidence and source chunk references where available. Done.

Acceptance criteria:

- No target repo files are modified. Done.
- Every proposed change traces back to facts, gaps, or validation warnings in the report. Done.
- The plan can be reviewed without opening the full JSON report. Done.

## Phase 4: Draft Output

Status: Done

Add optional draft generation without mutating target docs in place.

Deliverables:

- `--write-draft` writes proposed files under an ignored draft artifact directory. Done.
- Draft metadata maps each draft file back to source document, change-plan item, and report path. Done.
- No overwrite of target repo files by default. Done.

Acceptance criteria:

- Running draft mode is reversible by deleting the draft artifact directory. Done.
- The controller refuses draft writes outside the configured output directory unless a future explicit unsafe option exists. Done.
- Drafts include enough provenance to review or apply manually. Done.

## Phase 5: Resume And State

Status: Done

Make longer runs restartable.

Deliverables:

- `run-state-*.json` artifact or embedded resumable state. Done.
- `--resume <report-or-state>` option. Done.
- Completed chunks and accepted follow-ups are skipped on resume. Done.
- Failed packet metadata is preserved. Done.

Acceptance criteria:

- Interrupting a run does not require starting from the seed document again. Done.
- Resume refuses incompatible arguments unless explicitly overridden. Done.
- State format is documented and versioned. Done.

## Phase 6: Controller Tests

Status: Done

Add tests before broadening controller behavior further.

Required coverage:

- tracked vs all document scope. Done.
- manifest artifact shape. Done.
- review plan candidate limits. Done.
- follow-up depth/count limits. Done.
- invalid follow-up rejection. Done.
- tool dependency reporting. Done.
- artifact path safety. Done.
- resume compatibility checks when resume exists. Done.

Acceptance criteria:

- Tests use fake endpoints where model behavior is not the subject under test. Done.
- Tests do not require vLLM. Done.
- Model smoke tests remain separate from deterministic controller tests. Done.

## Phase 7: Tool Mediation

Status: Done

Move from controller-only tool authorization toward real mediated tools when needed.

Deliverables:

- Tool schema generation from `runtime/tools.json`. Done.
- Model tool-call detection. Done.
- Local execution loop. Done.
- Tool result injection. Done.
- Final response validation. Done.

Acceptance criteria:

- A model-visible tool name always corresponds to an executable local capability. Done.
- Raw tool-call-shaped text is never treated as completed tool execution. Done.
- Role prompts describe policy, but enforcement lives in controller/client/tool mediator code. Done.

## Phase 8: Streaming Core And Context Presence Mode

Status: Done

Build the reusable streaming foundation for very large documentation sets and oversized single documents. Prove it with one non-lossy query mode before adding additional modes.

Current non-streaming mode is not suitable for 1GB single-document inputs because it reads full files into memory for manifests, chunking, and some reports. It now has an explicit in-memory size guard instead of silently changing behavior.

Streaming is the default target architecture for reading and indexing content. Recursive summarization is not part of this phase.

Deliverables:

- Hard max file size for current in-memory document mode, with an explicit future override or large-content mode flag. Done.
- Streaming manifest/index that records size, line or byte ranges, sampled headings, and document type without reading full content into memory. Done.
- Streaming chunk iterator that emits bounded packets by byte and/or line offsets. Done.
- Minimal reduction mode registry where each mode declares input type, chunking strategy, output schema, lossy/lossless status, source-reference requirements, aggregation rules, and budget limits. Done.
- `context_presence` mode as the first implemented mode: locate whether and where a concept appears, with file/chunk/line or byte refs. Done.
- Coverage accounting for reviewed, skipped, summarized, and failed byte/line/chunk ranges. Done.
- Quality labels on every aggregate claim: `source_verified` or `insufficient_evidence`. Done.
- Resume state that can continue from byte/line offsets instead of restarting a large file. Done.
- Regression tests that prove the streaming path does not read a large file fully into memory. Done.

Acceptance criteria:

- A very large file is never read fully into memory by the controller's large-content path. Done.
- A final recommendation cannot be labeled source-verified unless it cites source chunk ranges. Done.
- `context_presence` results cite exact source ranges or return `insufficient_evidence`. Done.
- The report shows coverage totals and skipped ranges clearly enough to judge review completeness. Done.
- The user can bound work by max bytes, max chunks, or max elapsed run budget. Done.
- Existing normal-document mode remains simple and does not silently switch to lossy summarization. Done.

## Phase 9: Deterministic Reduction Modes

Status: Planned

Add reduction/query modes that can be implemented and tested without model calls.

Modes:

- `token_count`: estimate or count tokens by file, section, chunk, or query match.
- `coverage`: report reviewed, skipped, summarized, and failed ranges.
- `outline`: heading/section/index extraction without full review.

Deliverables:

- Mode-specific schemas and report sections.
- Mode-specific budget controls.
- Mode-specific regression tests using large synthetic files.
- Aggregation rules that do not rely on hidden state.

Acceptance criteria:

- Each deterministic mode can run without vLLM.
- Each deterministic mode reports source ranges and coverage.
- Each deterministic mode can resume from saved streaming state.

## Phase 10: Structured Model-Assisted Modes

Status: Planned

Add source-backed model-assisted modes after the streaming core and deterministic modes are stable.

Modes:

- `extract_facts`: structured facts, gaps, and evidence refs.
- `classify`: classify chunks by relevance, type, or risk.

Deliverables:

- Strict packet schemas per mode.
- Strict result schemas per mode.
- Controller validation for evidence refs and quality labels.
- Fake-endpoint regression tests that do not require vLLM.

Acceptance criteria:

- A model-assisted claim cannot be accepted without a valid source range.
- Low-confidence or unsupported model output is labeled `insufficient_evidence`.
- The controller, not the role prompt, enforces schema and evidence policy.

## Phase 11: Lossy Summarization Mode

Status: Planned

Add summarization only after source-backed and deterministic modes exist. Summarization is useful, but it is lossy compression and is not evidence by itself.

Mode:

- `summarize`: lossy prose summary with source refs and caveats.

Deliverables:

- Recursive reduction pipeline for summary mode: chunk -> structured records -> merge records -> summary aggregate.
- `summary_derived` quality labels.
- Report caveats that explicitly state summaries are lossy and are not evidence by themselves.
- Budget controls for max summaries, max summary depth, and max elapsed run budget.

Acceptance criteria:

- Summary-derived claims cannot satisfy criteria unless backed by source-verified records.
- The controller never silently switches to summarization.
- The report separates source-verified findings from summary-derived orientation.

## Future: Code Structure Indexes

Status: Planned

For code repositories, prefer AST or symbol indexes when structure is available instead of naive recursive reading.

Candidate extensions:

- Python AST/symbol index.
- Markdown/reference link graph.
- JSON/YAML key path index.
- Language-specific adapters added only when tests and use cases justify them.

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
- `doc-change-plan-*.md`: non-mutating documentation change plan from `full` mode.
- `drafts/<run-id>/...`: optional draft artifact directory from `--write-draft`.
- `run-state-*.json`: resumable controller state with schema version 1.
- `streaming-manifest-*.json`: streaming manifest for large-document modes.
- `streaming-state-*.json`: resumable streaming state with byte/line offsets.
- `streaming-context-presence-*.json`: deterministic context presence report with source ranges and coverage.

## Immediate Next Step

Implement Phase 9 deterministic reduction modes. Keep `token_count`, `coverage`, and `outline` as explicit modes so recursive summarization does not drift into the streaming foundation.
