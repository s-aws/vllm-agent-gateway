# V1 Founder Field Test Results

Status: passed on final Phase 56 run, current Phase 57-60 release gate, Phase 64 Batch D expansion, and Phase 65 skill-library release gate integration.

This report documents the Phase 56 field test requested by the founder: create 20-30 natural prompts, baseline them with a contextless subagent, run the same prompts through AnythingLLM, compare misses, tighten the harness, and document the results.

Phase 57 through Phase 60 made this field test part of the V1 release gate, added the prompt matrix, added semantic answer quality checks, and added refined prompt guidance for ambiguity-risk cases. Phase 64 expanded the suite from the original 26 prompts to 34 prompts by adding Batch D skill prompts on both frozen fixtures. Phase 65 added structured skill-library health proof to the same V1 acceptance path.

## Test Setup

- Prompt count: 34 current prompts; the original Phase 56 baseline was 26 prompts
- Baseline evaluator: contextless subagent with no prior project chat context
- Live surface: AnythingLLM workspace API
- AnythingLLM model target: `http://127.0.0.1:8500/v1`
- Local model path: `localhost:8000` through workflow-router gateway
- Controller/gateway ports validated during restart: `8000`, `8300`, `8400`, `8500`, role ports `8101`, `8102`, `8201`, `8202`, `8203`, `8204`, `8205`
- Target fixtures:
  - `/mnt/c/coinbase_testing_repo_frozen_tmp`
  - `/mnt/c/coinbase_testing_repo_frozen_tmp.github`
- Mutation rule: protected fixtures must remain unchanged
- Current V1 release gate: `scripts/validate_v1_acceptance.py` includes the founder field suite and skill-library release gate
- Current offline prompt gate: `scripts/validate_founder_field_prompt_matrix.py`

## Prompt Coverage

- `P01` through `P21`: read-only L1/L2 investigation and context prompts
- `P22`: task decomposition
- `P23` through `P25`: draft-only implementation prep
- `P26`: disposable-copy apply proof
- `P27` through `P34`: Batch D skill prompts for handler branch tracing, table-schema-only lookup, runtime-entrypoint disambiguation, and change-boundary summary on both frozen fixtures

Prompt definitions and live runner:

```text
scripts/run_founder_field_prompt_eval.py
```

## Baseline Summary

The contextless subagent produced expected answer shapes and miss risks for the original 26 prompts. The most important risks were:

- ambiguous "start" wording can miss index creation unless "first source point that creates/populates the lookup key" is clear
- handler prompts can stop at UI sender unless they follow the handler branch to the snapshot function
- schema prompts can return runtime dict fields unless the prompt asks for table schema
- engine entrypoint prompts can confuse dashboard-only server with trading-engine entrypoint
- disposable-copy apply prompts need exact packet JSON and clear copy-only/source-unchanged language

## Initial AnythingLLM Run

Initial report:

```text
runtime-state/founder-field-tests/founder-field-prompts-20260606T001557214431Z.json
runtime-state/founder-field-tests/founder-field-prompts-20260606T001557214431Z.md
```

Initial result: 20 passed, 6 failed.

| Case | Initial difference | Root cause | Change made | Prompt suggestion if still missed |
| --- | --- | --- | --- | --- |
| `P02` | Missing function-explanation markers | `explain find_...` fell through deterministic explanation rule and generic investigation rendered first | Expanded router and investigation explanation predicates | Name the function and file, and request inputs, outputs, side effects, and tests |
| `P04` | Missing yes/evidence markers | `does the repo already have...` missed behavior-existence rule | Expanded behavior-existence predicates | Ask for yes/no/unknown with evidence |
| `P06` | Missing config runtime-effect markers | `what does it affect at runtime` was treated like generic code explanation | Expanded configuration-effect predicates and excluded config-effect prompts from code explanation | Ask for configuration references and runtime effect, plus no secret values |
| `P10` | Missing module-summary markers | `summarize core/file.py` missed module-summary rule | Expanded module-summary predicates for explicit file paths | Name the target module and ask for responsibilities, definitions, tests, and risks |
| `P23` | Stopped at approval instead of draft proposal | natural small-doc edit extractor required an exact anchor | Added append-style draft proposal for named markdown file plus exact "note saying..." text | Use `draft` or `do not mutate files`; show exact proposed change and verification |
| `P26` | Stopped at approval instead of disposable-copy proof | disposable-copy trigger required the literal word `approved` | Accepted exact packet JSON with explicit copy-only/source-unchanged wording | Say `approved disposable copy apply only` if a client uses older wording |

Targeted retest report for those six:

```text
runtime-state/founder-field-tests/founder-field-prompts-20260606T002620057774Z.json
runtime-state/founder-field-tests/founder-field-prompts-20260606T002620057774Z.md
```

Targeted result: 6 passed, 0 failed.

## Follow-Up Full Run

Follow-up full report:

```text
runtime-state/founder-field-tests/founder-field-prompts-20260606T002746710477Z.json
runtime-state/founder-field-tests/founder-field-prompts-20260606T002746710477Z.md
```

Follow-up result: 24 passed, 2 failed.

| Case | Initial difference | Root cause | Change made |
| --- | --- | --- | --- |
| `P07` | Pasted-failure markers missing | generic module-summary rule stole `summarize this pytest failure` because failure text contained a test path | Excluded test-failure prompts from module-summary detection |
| `P17` | Test-selection tier markers missing | `why each command matters` missed test-selection rationale terms, then broader explanation artifact rendered first | Expanded test-selection rationale terms and excluded test-selection prompts from code explanation |

Targeted retest report:

```text
runtime-state/founder-field-tests/founder-field-prompts-20260606T003520753944Z.json
runtime-state/founder-field-tests/founder-field-prompts-20260606T003520753944Z.md
```

Targeted result: 2 passed, 0 failed.

## Final AnythingLLM Run

Final report:

```text
runtime-state/founder-field-tests/founder-field-prompts-20260606T005029609430Z.json
runtime-state/founder-field-tests/founder-field-prompts-20260606T005029609430Z.md
```

Final result: 26 passed, 0 failed.

V1 acceptance after the final-code field run:

```text
runtime-state/v1-acceptance/v1-acceptance-20260606T005600322822Z.json
```

V1 acceptance result: passed with `suite_count=5`, `json_output_count=2`, `feedback_count=2`, and `error_count=0`.

## Current Release Gate Update

Phase 57 made the founder field suite a required V1 acceptance suite.

Latest V1 acceptance report:

```text
runtime-state/v1-acceptance/v1-acceptance-20260606T021841646193Z.json
```

Latest V1 acceptance result: passed with `suite_count=6`, `json_output_count=2`, `feedback_count=2`, and `error_count=0`.

The six V1 suites were:

- `representative_l1`
- `representative_l2`
- `task_decomposition`
- `controlled_apply`
- `inline_format_a`
- `founder_field_prompts`

Embedded founder field report:

```text
runtime-state/founder-field-tests/founder-field-prompts-20260606T022428180540Z.json
runtime-state/founder-field-tests/founder-field-prompts-20260606T022428180540Z.md
```

Embedded founder field result: 26 passed, 0 failed.

Current prompt matrix report:

```text
runtime-state/founder-field-tests/prompt-matrix-20260606T021705662427Z.json
runtime-state/founder-field-tests/prompt-matrix-20260606T021705662427Z.md
```

Prompt matrix result after Phase 64 expansion: 50 passed, 0 failed.

Semantic answer quality result:

- all 34 field prompts passed the output-contract gate
- all 34 field prompts passed the semantic-quality gate
- no field prompt reported forbidden mutation markers
- refined prompts are now recorded for `P01`, `P08`, `P11`, `P16`, `P17`, `P21`, `P23`, `P26`, and Batch D cases `P27` through `P34`

## Phase 64 Batch D Expansion

Phase 64 added eight natural prompts to prove the promoted Batch D skills from AnythingLLM without manual skill injection. Each Batch D behavior is tested against both frozen fixtures.

Offline prompt matrix:

```text
runtime-state/founder-field-tests/phase64-prompt-matrix-initial.json
runtime-state/founder-field-tests/phase64-prompt-matrix-initial.md
```

Matrix result: 50 passed, 0 failed.

Batch D focused AnythingLLM run:

```text
runtime-state/founder-field-tests/phase64-batch-d-field-prompts.json
runtime-state/founder-field-tests/phase64-batch-d-field-prompts.md
```

Batch D focused result: 8 passed, 0 failed.

Expanded full AnythingLLM run:

```text
runtime-state/founder-field-tests/phase64-expanded-founder-field-prompts.json
runtime-state/founder-field-tests/phase64-expanded-founder-field-prompts.md
```

Expanded result: 34 passed, 0 failed.

V1 acceptance with the expanded suite:

```text
runtime-state/v1-acceptance/phase64-v1-acceptance.json
```

V1 acceptance result: passed with `suite_count=6`, `json_output_count=2`, `feedback_count=2`, and `error_count=0`.

## Current Skill-Library Release Gate Integration

Phase 65 added the skill-library release gate to V1 acceptance as suite `skill_library_release_gate`.

Latest V1 acceptance report:

```text
runtime-state/v1-acceptance/phase65-v1-acceptance.json
```

Latest V1 acceptance result: passed with `suite_count=7`, `json_output_count=2`, `feedback_count=2`, and `error_count=0`.

Structured V1 report sections now include:

- `founder_field_summary`: `prompt_count=34`, `passed=34`, `failed=0`
- `skill_library_health.catalog_summary`: `skill_count=50`, `eval_case_count=49`, `route_key_count=50`, `workflow_count=21`
- `skill_library_health.prompt_catalog_summary`: `field_prompt_count=34`, `prompt_matrix_case_count=50`, `prompt_matrix_failed=0`
- `skill_library_health.batch_d_live_report`: `runtime-state/skill-batches/phase63-batch-d-live-20260606T061926847189Z.json`

Embedded founder field report from the V1 acceptance run:

```text
runtime-state/founder-field-tests/founder-field-prompts-20260606T050450683364Z.json
runtime-state/founder-field-tests/founder-field-prompts-20260606T050450683364Z.md
```

Embedded founder field result: 34 passed, 0 failed.

Batch D run IDs from the expanded full run:

| Case | Expected skill | Expected artifact | Run ID |
| --- | --- | --- | --- |
| `P27` | `handler-branch-tracer` | `downstream_request_flow_map` | `workflow-router-20260606T045607589815Z` |
| `P28` | `handler-branch-tracer` | `downstream_request_flow_map` | `workflow-router-20260606T045623208844Z` |
| `P29` | `table-schema-isolator` | `downstream_data_model_lookup` | `workflow-router-20260606T045641614405Z` |
| `P30` | `table-schema-isolator` | `downstream_data_model_lookup` | `workflow-router-20260606T045658071998Z` |
| `P31` | `runtime-entrypoint-disambiguator` | `downstream_cli_entrypoint_lookup` | `workflow-router-20260606T045713567892Z` |
| `P32` | `runtime-entrypoint-disambiguator` | `downstream_cli_entrypoint_lookup` | `workflow-router-20260606T045729363861Z` |
| `P33` | `change-boundary-summarizer` | `downstream_change_surface_summary` | `workflow-router-20260606T045747487695Z` |
| `P34` | `change-boundary-summarizer` | `downstream_change_surface_summary` | `workflow-router-20260606T045801350851Z` |

Final run IDs:

| Case | Run ID |
| --- | --- |
| `P01` | `workflow-router-20260606T005031499736Z` |
| `P02` | `workflow-router-20260606T005040534201Z` |
| `P03` | `workflow-router-20260606T005049658378Z` |
| `P04` | `workflow-router-20260606T005102271013Z` |
| `P05` | `workflow-router-20260606T005110727490Z` |
| `P06` | `workflow-router-20260606T005126141531Z` |
| `P07` | `workflow-router-20260606T005140449864Z` |
| `P08` | `workflow-router-20260606T005152471040Z` |
| `P09` | `workflow-router-20260606T005206694276Z` |
| `P10` | `workflow-router-20260606T005217423981Z` |
| `P11` | `workflow-router-20260606T005228637508Z` |
| `P12` | `workflow-router-20260606T005244135385Z` |
| `P13` | `workflow-router-20260606T005300416290Z` |
| `P14` | `workflow-router-20260606T005317634426Z` |
| `P15` | `workflow-router-20260606T005328558923Z` |
| `P16` | `workflow-router-20260606T005339530589Z` |
| `P17` | `workflow-router-20260606T005353585151Z` |
| `P18` | `workflow-router-20260606T005404667286Z` |
| `P19` | `workflow-router-20260606T005421041679Z` |
| `P20` | `workflow-router-20260606T005431772005Z` |
| `P21` | `workflow-router-20260606T005442153691Z` |
| `P22` | `workflow-router-20260606T005457678654Z` |
| `P23` | `workflow-router-20260606T005501625245Z` |
| `P24` | `workflow-router-20260606T005504463494Z` |
| `P25` | `workflow-router-20260606T005510416790Z` |
| `P26` | `workflow-router-20260606T005515208642Z` |

## Implemented Tightening

- Added `scripts/run_founder_field_prompt_eval.py`.
- Added `README.founder-field-tests.md`.
- Added docs-index references.
- Added deterministic detection for broader natural phrasing:
  - `explain find_...`
  - `does the repo already have...`
  - `what does it affect at runtime`
  - `summarize core/file.py`
  - `why each command matters`
- Prevented generic code-explanation/module-summary artifacts from stealing test-selection and pasted-failure prompts.
- Added append-style small documentation draft proposals for named markdown files with exact unquoted "note saying..." text.
- Allowed exact packet JSON disposable-copy apply when wording explicitly limits apply to the disposable copy and asks to prove source repo unchanged.
- Added focused regression coverage for the field prompt catalog, append-style small doc drafts, and copy-only disposable apply wording.
- Added the founder field suite to the V1 acceptance release gate.
- Added `scripts/validate_founder_field_prompt_matrix.py` for offline classifier priority and refined-prompt checks.
- Added separate output-contract and semantic-quality status fields to founder field reports.
- Added forbidden mutation marker checks for read-only and draft-only prompts.
- Added `PROMPT_REFINEMENTS` for ambiguity-risk prompts.
- Added the Phase 61 Batch D proposal based on field evidence without mutating the skill registry.

## Remaining Prompt Suggestions

No prompt failed the final marker-level or current semantic-quality gate. The contextless baseline recommendations below are now represented as refined prompt guidance and prompt-matrix variants:

- `P01`: define "start" as first source point that creates or populates the lookup key.
- `P08`: ask to follow the handler branch through the snapshot function.
- `P11`: ask for only the `stealth_orders` table schema, not related runtime fields.
- `P16`: specify trading-engine entrypoint, not dashboard-only server.
- `P17`: specify whether commands should be Bash or Windows PowerShell.
- `P21`: ask for files to touch and files explicitly not to touch.
- `P23`: ask for unified diff only when you want a tighter review surface.
- `P26`: name the disposable destination when you want copy-path proof in addition to source hash proof.
