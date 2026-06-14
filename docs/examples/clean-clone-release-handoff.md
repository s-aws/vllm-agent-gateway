# Clean Clone Release Handoff Examples

Run the current release-candidate proof from a disposable clean snapshot:

```bash
python3 scripts/validate_clean_clone_release_handoff.py \
  --prepare-snapshot \
  --run-commands \
  --run-live-minimal \
  --timeout-seconds 240
```

Use an explicit snapshot path when you want to inspect the disposable checkout:

```bash
python3 scripts/validate_clean_clone_release_handoff.py \
  --snapshot-root /tmp/agentic_agents_phase234_clean_snapshot_review \
  --prepare-snapshot \
  --run-commands \
  --run-live-minimal \
  --timeout-seconds 240
```

When validating from a disposable clone while another checkout already has the managed stack running, use the shared state root so the clone can stop and replace that stack before live proof:

```bash
python3 scripts/validate_clean_clone_release_handoff.py \
  --managed-state-root /mnt/c/private_agentic_agents/runtime-state \
  --prepare-snapshot \
  --run-commands \
  --run-live-minimal \
  --timeout-seconds 240
```

Inspect a static shape report without restarting the stack:

```bash
python3 scripts/validate_clean_clone_release_handoff.py \
  --prepare-snapshot || true
```

That static command is useful while editing docs or policy, but it intentionally exits blocked because Phase 234 requires command execution, managed-stack restart from the snapshot, and live proof from the disposable checkout.

After the release-candidate files are committed or packaged, rerun with `--source-mode git_clone` against a disposable clone or equivalent packaged artifact. Do not call a dirty-worktree snapshot a final remote-clone proof.
