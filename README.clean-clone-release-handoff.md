# Clean Clone Release Handoff

Phase 234 proves that the release handoff can be followed from a disposable clean checkout instead of relying on private chat context or files from an active dirty workspace.

The current supported mode is `clean_snapshot`: the validator copies the active release-candidate workspace into a disposable directory, excludes generated/runtime state, records required-file hashes, restarts the managed gateway/controller stack from that snapshot, and runs the handoff proof from inside the snapshot.

`clean_snapshot` is intentionally labeled as weaker than `git_clone`. It proves the current candidate artifact works, not that a public remote clone already contains the candidate. Use `git_clone` only after the release-candidate files have been committed or otherwise packaged as the handoff artifact.

## What It Checks

- required M14 docs, policies, validators, and examples exist in the disposable checkout
- generated `runtime-state/`, `.git`, caches, and temporary directories are excluded
- the snapshot has no symlinks back to the active workspace
- model capability routing uses the clone-safe profile under `runtime/model_capability_profiles/`
- docs index, Phase 232 handoff, release channels, security policy, first-time doctor, and live onboarding proof pass from the snapshot
- the managed gateway/controller stack is restarted from the snapshot before the live AnythingLLM prompt
- AnythingLLM uses `http://127.0.0.1:8500/v1`, API `http://127.0.0.1:3001`, and workspace `my-workspace`
- both frozen Coinbase fixtures remain unchanged

## Command

```bash
python3 scripts/validate_clean_clone_release_handoff.py \
  --prepare-snapshot \
  --run-commands \
  --run-live-minimal \
  --timeout-seconds 240
```

The default snapshot path is under the system temp directory. The report is written to:

- `runtime-state/phase234/phase234-clean-clone-release-handoff-report.json`
- `runtime-state/phase234/phase234-clean-clone-release-handoff-report.md`

When running from a disposable clone while another checkout already owns the local gateway/controller ports, pass the shared state root so the clone can stop the old stack and restart it from the snapshot:

```bash
python3 scripts/validate_clean_clone_release_handoff.py \
  --managed-state-root /mnt/c/private_agentic_agents/runtime-state \
  --prepare-snapshot \
  --run-commands \
  --run-live-minimal \
  --timeout-seconds 240
```

## Release Boundary

A passing `clean_snapshot` report is acceptable for current local release-candidate validation. A final external release handoff should later be repeated in `git_clone` or packaged-archive mode after the candidate files are committed or bundled.
