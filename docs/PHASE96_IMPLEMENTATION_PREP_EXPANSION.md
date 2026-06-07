# Phase 96 Implementation-Prep Workflow Expansion

Phase 96 expands draft-only implementation prep for common natural-language coding-agent requests while preserving `implementation.workflow` as the only implementation executor.

## Implemented

- Added `runtime/implementation_prep_expansion_cases.json` for two governed Phase 96 prompt families:
  - small text/documentation append draft
  - approved read-only investigation to exact packet-operation proposal
- Added `vllm_agent_gateway.acceptance.implementation_prep_expansion` and `scripts/validate_implementation_prep_expansion.py`.
- Added natural approved-investigation packet-prep routing from chat run IDs.
- Added generic packet-seed support for `downstream_investigation_plan` and `downstream_refactor_plan`.
- Added `packet_operation_proposal` inline chat output with target file, operation, verification, evidence source, approval state, and `Source mutation: false`.
- Added deterministic downstream execution-planning profiles for generic packet-objective and approved-investigation packet prep once exact operations are available.
- Added packet-operation diff verification commands to deterministic draft planning.
- Improved packet proposal snippets so explicit Python function objectives prefer the function definition before broader references.
- Added full-tree fixture digests, watched-file hashes, git status, runtime port checks, operation targets, verification commands, and chat excerpts to Phase 96 validation reports.

## Proof Artifacts

- Direct report: `runtime-state/implementation-prep-expansion/phase96-implementation-prep-direct.json`
- Live gateway report: `runtime-state/implementation-prep-expansion/phase96-implementation-prep-gateway.json`
- Live AnythingLLM report: `runtime-state/implementation-prep-expansion/phase96-implementation-prep-anythingllm.json`
- Full Bash regression: `464 passed, 4 skipped, 23 deselected`
- Patch hygiene: `git diff --check` passed
- Docs index: `expected_count=110`, `orphaned_docs=[]`

The live reports include checks for:

- localhost model `8000`
- workflow-router gateway `8500`
- controller `8400`
- AnythingLLM workspace API when enabled
- `/mnt/c/coinbase_testing_repo_frozen_tmp`
- `/mnt/c/coinbase_testing_repo_frozen_tmp.github`
- protected fixture watched hashes, full tree digest, and git status where available
- `source_changed=false`
- downstream `repo_mutated=false`
- downstream verification commands

## Acceptance Coverage

- Draft-only small text append prompts produce `small_text_edit_proposal`, downstream packet preview, downstream verification plan, implementation workflow report, and no source mutation.
- Approved read-only investigation follow-up prompts produce `packet_operation_proposal` from the prior `downstream_investigation_plan`, validate exact `replace_text`, run downstream draft implementation prep, and preserve both frozen fixtures.
- Live gateway and AnythingLLM validation pass the same governed cases on both frozen fixtures.

## Known Limits

- Phase 96 supports draft packet preparation only. It does not apply changes to source repositories.
- The approved-investigation proposal still depends on the local model for exact operation proposal, but the controller bounds the snippets and rejects operations whose `old` text is not found exactly.
- Direct validation uses a generated fixture; frozen fixture proof is provided by live gateway and AnythingLLM validation.
