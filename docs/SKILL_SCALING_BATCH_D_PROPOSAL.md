# Skill Scaling Batch D Proposal

Status: accepted from field evidence, registered as draft skills in Phase 62, and promoted in Phase 63 after live proof.

This proposal is the Phase 61 candidate list for the next small deterministic skill batch. Phase 62 turned these candidates into draft registry entries through `skill_batch.register`; Phase 63 validated them through gateway and AnythingLLM before promotion. The structured proposal is [skill-scaling-batch-d.json](skill-scaling-batch-d.json).

## Evidence

- [V1 Founder Field Test Results](V1_FOUNDER_FIELD_TEST_RESULTS.md): remaining prompt suggestions from realistic AnythingLLM use.
- [Founder field prompt catalog](../runtime/prompt_catalogs/founder_field_v1.json): governed prompt, refinement, semantic-marker, and matrix-rule source used by reports and the prompt matrix.
- Prompt matrix reports under `runtime-state/founder-field-tests/`: classifier proof for original and refined prompt variants.

## Candidate Skills

| Candidate | Route key | Workflow | Artifact | Source prompt | Why it belongs in Batch D |
| --- | --- | --- | --- | --- | --- |
| `handler-branch-tracer` | `code.handler_branch_trace` | `code_investigation.plan` | `request_flow_map` | `P08` | Handler prompts can stop too early unless the downstream branch-following procedure is explicit. |
| `table-schema-isolator` | `data.table_schema_only_lookup` | `code_investigation.plan` | `data_model_lookup` | `P11` | Schema prompts need a table-only procedure so runtime fields do not get mixed into the answer. |
| `runtime-entrypoint-disambiguator` | `code.runtime_entrypoint_disambiguation` | `code_investigation.plan` | `cli_entrypoint_lookup` | `P16` | Entrypoint prompts need subsystem disambiguation so UI/service startup files are not returned as the runtime entrypoint. |
| `change-boundary-summarizer` | `planning.change_boundary_summary` | `code_investigation.plan` | `change_surface_summary` | `P21` | Change-surface prompts are clearer when they require both files to touch and files not to touch. |

## Admission Gate

Run the proposal validator before turning this into a real skill batch and after registration to confirm the installed metadata still matches the proposal:

```bash
python scripts/validate_skill_batch_d_proposal.py
```

The validator must pass before any later phase changes Batch D routing, live-suite mappings, or promotion proof.

## Stop Conditions

- Do not add broad single-path refactor orchestration.
- Do not add apply-mode behavior.
- Do not mutate `runtime/skills.json` or `runtime/skill_evals.json` outside the approved lifecycle path.
- Stop if any candidate duplicates an existing route key, eval case id, or deterministic semantic intent.
- Stop if a candidate needs a new workflow or artifact before the roadmap approves that scope.

## Phase 62 Registration And Phase 63 Promotion

Phase 62 registered all four candidates as draft skills through the existing `skill_batch.register` workflow.

- Registration run: `skill-batch-registration-20260606T041116522680Z`
- Phase 63 live report: `runtime-state/skill-batches/phase63-batch-d-live-20260606T043006924969Z.json`
- Promotion run: `skill-eval-promotion-20260606T043425493565Z`
- Skill count: `4`
- Eval case count: `4`
- Current status: validated
