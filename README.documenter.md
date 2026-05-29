# Documenter

The documenter workflow is a controller-owned review pipeline:

```text
target repo -> manifest -> review plan -> bounded chunk packets -> documenter role -> validated deltas -> aggregate -> summary/change plan -> optional drafts
```

The documenter role receives one bounded packet and returns structured JSON. It does not own repo traversal, manifest creation, chunk selection, retry logic, state, or write decisions.

## Capabilities

- Reviews a seed documentation file in bounded chunks.
- Uses line overlap for local continuity without making the role stateful.
- Writes a document manifest in `full` mode.
- Writes a review plan with bounded `visible_followup_candidates`.
- Can review either the selected seed doc or the full discovered manifest.
- Optionally expands exact follow-up files within depth/count/scope limits.
- Writes non-mutating Markdown change plans.
- Optionally writes draft artifact copies under the configured output directory.
- Writes resumable `run-state-*.json` state.

## Modes

```text
review      write chunk-review JSON only
summarize   summarize an existing JSON report with --report
full        review chunks and write manifest, review plan, change plan, and final summary artifacts
```

`--document-scope` controls discovery. `--review-scope` controls what enters the review queue:

```text
auto      seed doc by default; full + document-scope all reviews the full manifest
seed      only the selected document
manifest  every discovered documentation file
```

Use `--seed-doc` to name the selected seed document. The older `--doc` alias is still accepted for compatibility.

## Model Output Contract

Each chunk packet tells the model to return one JSON object and includes `output_limits` for maximum array sizes and string length. The controller validates the JSON, trims oversized valid fields into the bounded contract, and fails the packet when the model returns malformed or truncated JSON. The final Markdown summary also uses a compact, counted summary packet instead of sending the full report aggregate back through the model. Detailed evidence remains in the JSON report and change-plan artifacts. The default `--max-output-tokens` is `2000`; increase it only when the model is consistently cut off after the output has already been constrained.

## Artifacts

- `documenter-*.json`: main controller report.
- `documenter-*.md`: final Markdown summary from `full` mode.
- `document-manifest-*.json`: document manifest from `full` mode.
- `doc-review-plan-*.json`: review plan and candidate pool.
- `doc-change-plan-*.md`: non-mutating documentation change plan.
- `drafts/<run-id>/...`: optional draft artifact directory from `--write-draft`.
- `run-state-*.json`: resumable controller state.

Reports are written under `.agentic_reports/` by default. The target project is read-only unless the caller intentionally points `--output-dir` into it.

## Safety Model

- Default document discovery uses tracked files.
- `--document-scope all` is explicit and skips common generated directories such as virtual environments, `.agentic_reports`, and `test_runtime`.
- `--review-scope seed` can force a one-document review even when discovery uses all files.
- Follow-up expansion is fail-closed by default and limited to packet-visible candidates.
- The normal path has an in-memory file size guard. Use the streaming workflow for oversized files.
- Drafts are artifact copies, not applied edits.

## References

- Roadmap and artifact inventory: [docs/DOCUMENTER_E2E_ROADMAP.md](docs/DOCUMENTER_E2E_ROADMAP.md)
- Run state schema: [docs/DOCUMENTER_RUN_STATE.md](docs/DOCUMENTER_RUN_STATE.md)
- Examples: [docs/examples/documenter.md](docs/examples/documenter.md)
