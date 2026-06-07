# Runtime-State Examples

## Validate Repository Hygiene

```bash
cd /mnt/c/agentic_agents
python3 scripts/check_runtime_state_hygiene.py \
  --output-path runtime-state/runtime-state-hygiene/current.json
```

Expected result:

```text
RUNTIME STATE HYGIENE PASS
```

## Confirm No Runtime Reports Are Tracked

```bash
git ls-files runtime-state
```

Expected result: no output.

If files are listed, remove them from the index without deleting local reports:

```bash
git rm --cached -r runtime-state
```

Review the staged change before committing.

## Confirm Runtime Reports Are Ignored

```bash
git check-ignore -v runtime-state/hygiene-sample.json
```

Expected result includes `.gitignore` and `runtime-state/`.

## Validate Stable Proof Metadata

```bash
python3 scripts/validate_release_channels.py \
  --channel stable \
  --release-candidate-report runtime/release_proofs/v1-1-release-candidate-stable-proof.json \
  --output-path runtime-state/release-channels/stable-readiness.json
```

Expected result:

```text
RELEASE CHANNEL PASS
```

The generated report remains local. The compact proof metadata stays committed under `runtime/release_proofs/`.
