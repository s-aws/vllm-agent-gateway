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
| Reduction/query modes | Done | Deterministic streaming modes now include `token_count`, `coverage`, and `outline`. |
| Structured model-assisted modes | Done | `extract_facts` and `classify` call a role endpoint chunk-by-chunk and controller-validate evidence refs before accepting source-backed records. |
| Lossy summarization mode | Done | `summarize` recursively reduces chunk summaries with `summary_derived` labels, caveats, and separate source-verified support records. |
| Code structure indexes | Done | Deterministic Python AST, Markdown/reference, and JSON/YAML key-path indexes are available through `scripts/run_code_structure_index.py`. |
| Implementation workflow | Planned | Convert approved plans into bounded implementation packets, verification steps, and reversible draft/application controls. |
| Tool provenance hardening | Nice-to-have | Add artifact/record-level lineage after shipped workflow features exist, unless an earlier phase needs it for correctness. |
| Tool dependency audit | Partial | Reports include `tool_policy.controller_tool_dependencies`; deeper per-artifact provenance is still needed. |

## Test Coverage Map

Implemented phases must have deterministic regression coverage unless the phase is itself a test-suite milestone. Tests should not require vLLM unless a future smoke-test phase explicitly says so.

| Phase | Coverage Status | Primary Tests | Notes |
| --- | --- | --- | --- |
| Phase 1: Manifest-Backed Review Planning | Direct | `test_tracked_and_all_document_scopes_write_manifest_and_tool_dependencies`, `test_review_plan_candidate_limits_are_reflected_in_packets` | Covers manifest shape, tracked/all scopes, tool dependencies, review plan limits, and visible candidates. |
| Phase 2: Source-Aware Follow-Up Review | Direct | `test_followup_depth_count_limits_and_invalid_rejections_are_recorded` | Covers visible-candidate policy, invalid follow-up rejection, depth/count limits, and skip reason codes. |
| Phase 3: Documentation Change Plan | Direct | `test_change_plan_groups_validated_findings_and_does_not_modify_target_docs`, `test_dry_run_change_plan_records_insufficient_evidence_instead_of_safe_edits` | Covers artifact writing, grouping, validation-warning evidence, dry-run caveat, and read-only target behavior. |
| Phase 4: Draft Output | Direct | `test_draft_artifacts_stay_under_output_dir_and_target_files_are_read_only` | Covers output containment, metadata paths, and target read-only behavior. |
| Phase 5: Resume And State | Direct | `test_resume_refuses_incompatible_arguments_and_skips_completed_chunks`, `test_failed_packet_metadata_is_preserved_without_vllm` | Covers compatibility refusal, completed chunk skip, state completion, and failed packet preservation. |
| Phase 6: Controller Tests | Self-covered | Full `tests/regression/` suite | This phase is the creation of deterministic controller tests, not a separate runtime feature. |
| Phase 7: Tool Mediation | Direct | `tests/regression/test_tool_mediator.py` | Covers schema generation, tool execution loop, raw tool-call-shaped text rejection, policy blocks, scan files, and test execution capability. |
| Phase 8: Streaming Core And Context Presence Mode | Direct | `test_context_presence_*`, `test_in_memory_documenter_rejects_oversized_selected_doc_without_override` | Covers bounded reads, source refs, partial coverage, resume offsets, split query boundary, mode registry, and in-memory guard. |
| Phase 9: Deterministic Reduction Modes | Direct | `test_token_count_mode_reports_file_chunk_section_and_query_counts`, `test_coverage_mode_reports_range_accounting_and_partial_budget`, `test_outline_mode_extracts_headings_and_sections_with_source_ranges`, `test_deterministic_modes_resume_from_saved_streaming_state` | Covers mode schemas, budget behavior, source ranges, outline boundary handling, and resume for each deterministic mode. |
| Phase 10: Structured Model-Assisted Modes | Direct | `test_extract_facts_mode_source_validates_model_records`, `test_classify_mode_validates_labels_risks_and_source_refs`, `test_model_assisted_modes_resume_from_saved_streaming_state`, `test_model_assisted_mode_requires_role_base_url`, `test_model_assisted_invalid_result_schema_records_failed_range`, `test_model_assisted_mode_registry_entries_declare_budget_and_source_refs` | Covers fake-endpoint model calls, strict top-level result fields, failed schema state, evidence validation, low-confidence downgrade, disallowed labels, invalid risk severity, required endpoint config, registry metadata, and resume. |
| Phase 11: Lossy Summarization Mode | Direct | `test_summarize_mode_writes_lossy_summary_and_separate_source_records`, `test_summarize_mode_does_not_treat_unsupported_summary_as_evidence`, `test_summarize_mode_resume_and_final_merge`, `test_summarize_mode_registry_declares_lossy_summary_controls` | Covers explicit lossy mode, recursive fake-endpoint merge, `summary_derived` labels, caveats, source-verified support separation, unsupported summary downgrade, resume, and summary budget metadata. |
| Phase 12: Code Structure Indexes | Direct | `tests/regression/test_code_structure_index.py` | Covers Python AST symbols/imports/syntax errors, Markdown link graph/unresolved links, JSON/YAML key paths and parse errors, tracked/all file scopes, and bounded packet-ready slices without vLLM. |
| Phase 13: Implementation Workflow | Not covered | None | Not implemented yet. Tests should prove bounded implementation packets, read-only default behavior, verification capture, and reversible output/application policy. |
| Phase 14: Tool Provenance Hardening | Not covered | None | Nice-to-have after core shipped features. Promote earlier only if artifact-level lineage becomes required for Phase 12 or 13 correctness. |

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

Status: Done

Add reduction/query modes that can be implemented and tested without model calls.

Modes:

- `token_count`: estimate or count tokens by file, section, chunk, or query match. Done.
- `coverage`: report reviewed, skipped, summarized, and failed ranges. Done.
- `outline`: heading/section/index extraction without full review. Done.

Deliverables:

- Mode-specific schemas and report sections. Done.
- Mode-specific budget controls. Done.
- Mode-specific regression tests using large synthetic files. Done.
- Aggregation rules that do not rely on hidden state. Done.

Acceptance criteria:

- Each deterministic mode can run without vLLM. Done.
- Each deterministic mode reports source ranges and coverage. Done.
- Each deterministic mode can resume from saved streaming state. Done.

## Phase 10: Structured Model-Assisted Modes

Status: Done

Add source-backed model-assisted modes after the streaming core and deterministic modes are stable.

Modes:

- `extract_facts`: structured facts, gaps, and evidence refs. Done.
- `classify`: classify chunks by relevance, type, or risk. Done.

Deliverables:

- Strict packet schemas per mode. Done.
- Strict result schemas per mode. Done.
- Controller validation for evidence refs and quality labels. Done.
- Fake-endpoint regression tests that do not require vLLM. Done.

Acceptance criteria:

- A model-assisted claim cannot be accepted without a valid source range. Done.
- Low-confidence or unsupported model output is labeled `insufficient_evidence`. Done.
- The controller, not the role prompt, enforces schema and evidence policy. Done.

## Phase 11: Lossy Summarization Mode

Status: Done

Add summarization only after source-backed and deterministic modes exist. Summarization is useful, but it is lossy compression and is not evidence by itself.

Mode:

- `summarize`: lossy prose summary with source refs and caveats. Done.

Deliverables:

- Recursive reduction pipeline for summary mode: chunk -> structured records -> merge records -> summary aggregate. Done.
- `summary_derived` quality labels. Done.
- Report caveats that explicitly state summaries are lossy and are not evidence by themselves. Done.
- Budget controls for max summaries, max summary depth, and max elapsed run budget. Done.

Acceptance criteria:

- Summary-derived claims cannot satisfy criteria unless backed by source-verified records. Done.
- The controller never silently switches to summarization. Done.
- The report separates source-verified findings from summary-derived orientation. Done.

## Phase 12: Code Structure Indexes

Status: Done

For code repositories, prefer deterministic structure indexes when structure is available instead of naive recursive reading or lossy summarization.

Initial target:

- Python AST/symbol index.
- Markdown/reference link graph.
- JSON/YAML key path index.

Deliverables:

- `code-structure-index-*.json` artifact with schema version, target root, selected files, parser versions, and per-file index status. Done.
- Python index records for modules, classes, functions, imports, decorators, docstrings, line ranges, and syntax errors. Done.
- Markdown link/reference graph records for headings, anchors, relative links, unresolved links, and inbound/outbound edges. Done.
- JSON/YAML key-path records for config files, including dotted paths, scalar previews, line ranges where available, and parse errors. Done.
- Controller selection policy that decides when to prefer a structure index over raw chunk review. Done.
- Packet fields that expose only the relevant index slice to a role, not the full index by default. Done.
- Tool dependency records for parsers/scanners used to build each index artifact. Done.
- Regression tests using small temp repos with valid files, syntax errors, unresolved links, and malformed config. Done.

Acceptance criteria:

- Index generation is deterministic for the same repo state and arguments. Done.
- Parser failures are represented as indexed errors, not silent skips. Done.
- Every indexed symbol/reference/key path has a file path and line range when the parser can provide it. Done.
- Role packets can request bounded slices by symbol, file, reference edge, or key path. Done.
- Indexes remain read-only and do not execute target code. Done.
- The controller can fall back to existing document/chunk paths when no suitable structural index exists. Done.

## Phase 13: Implementation Workflow

Status: Planned

Add a controlled path from validated plans to bounded implementation work. This should not make the documenter an implementer; it should hand off approved, source-backed work packets to an implementation controller or role.

Scope:

- Documentation edits generated from approved change-plan items.
- Code/config edits generated from explicit implementation packets.
- Verification commands tied to the changed files and declared by controller policy.
- Reversible drafts by default, with direct target mutation only behind an explicit apply option.

Deliverables:

- `implementation-plan-*.json` artifact derived from approved change-plan items or explicit user-approved work packets.
- `implementation-state-*.json` artifact with queued packets, completed packets, failed packets, changed artifacts, verification results, and resume keys.
- Bounded implementation packets with exact target files, allowed operations, relevant source refs, acceptance criteria, and max context budget.
- Default draft mode that writes proposed changes under the configured output directory without mutating the target repo.
- Explicit apply mode that refuses untracked or out-of-scope writes unless a future unsafe option is added deliberately.
- Verification capture for command, working directory, timeout, exit code, stdout/stderr hashes or bounded excerpts, and associated changed files.
- Rollback/review metadata that maps every draft or applied change back to packet ID, source refs, and verification result.
- Regression tests with temp repos proving draft containment, packet bounds, resume behavior, verification capture, and refusal of out-of-scope writes.

Acceptance criteria:

- The default implementation workflow is read-only against the target repo.
- No packet can edit files outside its explicit target set.
- No implementation result can be marked complete without a recorded verification decision.
- Failed verification is preserved in state and final artifacts.
- Resume skips completed packets and refuses incompatible arguments by default.
- Direct apply, when added, must be explicit, auditable, and reversible through generated metadata or VCS state.

## Phase 14: Tool Provenance Hardening

Status: Nice-to-have

Add deeper audit lineage after the main shipped workflow exists. Run-level tool dependency reporting is already useful; this phase adds artifact-level and record-level provenance so claims, packets, drafts, applied changes, and verification results can be traced back to exact controller actions.

This should not block Phase 12 or Phase 13 unless an implementation detail needs stronger lineage for correctness, replay, or user trust. If that happens, pull forward only the minimal provenance needed by that earlier phase.

Deliverables:

- Artifact-level provenance for manifests, review plans, structure indexes, implementation plans, drafts, and reports.
- Record-level provenance for findings, summaries, index entries, implementation packets, verification results, and change-plan items.
- Tool invocation records with tool ID, normalized command/action, working directory, allowed scope, timestamp, exit status, bounded output metadata, and output hashes.
- Source material fingerprints such as file path, file size, file hash, byte range, line range, and repository commit or working-tree marker when available.
- Parent/child lineage linking packets to tool outputs, tool outputs to artifacts, artifacts to final reports, and implementation packets to verification records.
- Redaction/bounding policy so provenance can be useful without storing full sensitive command output by default.
- Optional replay/check mode that detects when source inputs or tool outputs no longer match recorded hashes.

Acceptance criteria:

- A user can answer which controller action produced a specific artifact record without relying on model narration.
- Provenance records are deterministic aside from timestamp/run IDs.
- Sensitive or large outputs are represented by hashes and bounded excerpts unless explicitly configured otherwise.
- Missing provenance is reported as an audit gap rather than silently ignored.
- Provenance does not grant new tool permissions and does not change target repo files by itself.

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
- `streaming-token-count-*.json`: deterministic token estimate report with file, chunk, section, and optional query-match ranges.
- `streaming-coverage-*.json`: deterministic coverage report with reviewed, skipped, summarized, and failed ranges.
- `streaming-outline-*.json`: deterministic heading and section outline report.
- `streaming-extract-facts-*.json`: model-assisted facts and gaps with source-validated evidence refs and validation warnings.
- `streaming-classify-*.json`: model-assisted classifications, risks, class counts, source-validated evidence refs, and validation warnings.
- `streaming-summarize-*.json`: lossy summary aggregate, chunk summaries, recursive merge rounds, caveats, and separate source-verified support records.
- `code-structure-index-*.json`: deterministic Python AST, Markdown/reference, and JSON/YAML key-path index for a target repo.
- `code-structure-slice-*.json`: optional bounded `structure_index_slice` records intended for future role packets.

## Immediate Next Step

Implement Phase 13 implementation workflow. Use Phase 12 structure indexes to give implementation packets precise symbol/reference/key-path context instead of broad file chunks.

Keep Phase 14 as a nice-to-have audit hardening phase unless Phase 12 or Phase 13 exposes a concrete need for artifact-level provenance earlier.
