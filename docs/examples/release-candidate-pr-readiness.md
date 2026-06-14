# Release-Candidate PR Readiness Examples

Run this after the release-candidate branch has the current Phase 232-237 source, docs, policies, tests, and proof commands committed.

```bash
python3 scripts/validate_release_candidate_pr_readiness.py \
  --output-path runtime-state/release-candidate-pr-readiness/phase238/phase238-release-candidate-pr-readiness-report.json \
  --markdown-output-path runtime-state/release-candidate-pr-readiness/phase238/phase238-release-candidate-pr-readiness-packet.md
```

Review the packet:

```bash
sed -n '1,220p' runtime-state/release-candidate-pr-readiness/phase238/phase238-release-candidate-pr-readiness-packet.md
```

Check the machine-readable decision:

```bash
python3 -m json.tool runtime-state/release-candidate-pr-readiness/phase238/phase238-release-candidate-pr-readiness-report.json | less
```

The gate should fail if:

- the working tree is dirty,
- a required handoff doc is missing,
- generated `runtime-state/` files are tracked,
- a protected fixture repository is tracked as part of the release branch,
- Phase 232-237 are not complete in the canonical roadmap,
- known non-goals are missing from the durable docs.
