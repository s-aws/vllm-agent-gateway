# Implementation-Prep Expansion

Implementation-prep expansion is the workflow-router capability for turning tightly scoped, draft-only natural-language requests into exact packet proposals without mutating the target repository.

It does not add a second apply path. The router creates or validates exact packet operations, then `execution_planning.plan` runs the existing `implementation.workflow` in draft mode.

## When To Use It

Use this when a tester asks through AnythingLLM or the workflow-router gateway for one of these draft-only requests:

- small documentation or text edit, such as appending a note to `README.md`
- approved read-only investigation follow-up that asks for exact implementation packet operations

The prompt must be draft-only. If the request asks to apply, mutate, commit, or change files without the approved disposable-copy path, the router must block.

## Output Contract

Successful runs return a chat-visible `Draft proposal:` section with:

- proposal artifact kind
- target file
- operation summary
- verification command
- safety checks
- approval requirement before apply
- `Source mutation: false`

Controller artifacts include:

- `route-decision.json`
- `approval-state.json`
- `small-text-edit-proposal.json` or `packet-operation-proposal.json`
- downstream `packet-preview.json`
- downstream `verification-plan.json`
- downstream `implementation-workflow-report.json`
- downstream `run-state.json`

## Validation

The governed case catalog is:

```text
runtime/implementation_prep_expansion_cases.json
```

Run direct validation:

```bash
python3 scripts/validate_implementation_prep_expansion.py \
  --output-path runtime-state/implementation-prep-expansion/phase96-implementation-prep-direct.json
```

Run live gateway validation from Bash:

```bash
python3 scripts/validate_implementation_prep_expansion.py \
  --skip-direct \
  --live-gateway \
  --output-path runtime-state/implementation-prep-expansion/phase96-implementation-prep-gateway.json
```

Run AnythingLLM validation after the API key is visible to Bash:

```bash
python3 scripts/validate_implementation_prep_expansion.py \
  --skip-direct \
  --live-anythingllm \
  --output-path runtime-state/implementation-prep-expansion/phase96-implementation-prep-anythingllm.json
```

The live validators cover localhost model `8000`, workflow-router gateway `8500`, controller `8400`, AnythingLLM, `/mnt/c/coinbase_testing_repo_frozen_tmp`, and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.

## Safety Constraints

- Packet generation is draft-only.
- Direct source apply remains blocked.
- Protected frozen fixture hashes and git status must remain unchanged.
- Model-proposed `replace_text` operations must match exact source text before downstream draft planning.
- Existing `implementation.workflow` remains the only implementation executor.
