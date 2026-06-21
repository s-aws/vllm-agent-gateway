# EIG PR Merge Readiness

Phase 310 validates that PR #1 is ready for a founder merge decision without merging it.

This gate exists because `continue` should not silently merge `codex/eig-stable-handoff` into `main` or promote EIG candidates into the stable corpus. It proves the PR is clean, reviewable, and current while keeping the final merge decision explicit.

## What This Proves

- The working tree is clean.
- PR #1 is open, targets `main`, and uses head branch `codex/eig-stable-handoff`.
- GitHub reports the PR merge state as `CLEAN`.
- Phases 304 through 309 are marked complete.
- Required EIG docs and scripts exist.
- No forbidden runtime/temp/nested-clone paths are tracked.
- The PR body names the Phase 307/308 evidence and non-promotion boundary.
- `merge_allowed`, `main_mutation_allowed`, and `stable_corpus_promotion_allowed` remain `false`.

## Validation

Run:

```bash
python3 scripts/validate_eig_pr_merge_readiness.py
```

Expected marker:

```text
EIG PR MERGE READINESS PASS
```

The report writes to:

```text
runtime-state/eig-pr-merge-readiness/phase310-validation.json
```

This report means the PR is ready for a founder merge decision. It does not authorize the merge.

Examples: [docs/examples/eig-pr-merge-readiness.md](docs/examples/eig-pr-merge-readiness.md).
