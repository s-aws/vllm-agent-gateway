# External Tester Dry Run Examples

## Live Dry Run

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_external_tester_dry_run.py \
  --live-runtime \
  --include-feedback \
  --output-path runtime-state/external-tester-dry-run/phase147/phase147-external-tester-dry-run.json
```

Expected result:

```text
EXTERNAL TESTER DRY RUN PASS
```

## Static Docs And Pack Check

Use this when localhost services are not running:

```bash
python3 scripts/validate_external_tester_dry_run.py \
  --output-path runtime-state/external-tester-dry-run/phase147/static-docs-and-pack.json
```

This validates the stable channel metadata, release notes, docs clarity, and static onboarding pack. It skips the setup doctor and live AnythingLLM prompt.

## Review

Open the report and start with:

```text
summary.error_count
summary.doc_blocker_count
summary.doc_ambiguity_count
summary.onboarding_live_status
manual_prompt.run_id
feedback_capture.feedback_run_id
errors
```

The live report must include `ONB-001`, a `workflow-router-...` run ID, a `workflow-feedback-...` run ID, and no missing expected markers.
