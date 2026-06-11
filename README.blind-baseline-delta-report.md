# Blind-Baseline Delta Report

Phase 178 turns the blind-baseline-first process into an auditable delta report for repaired Priority 0 prompt families.

Use this after a live founder-field run has already produced local answers through AnythingLLM and the workflow-router gateway. The report does not rerun prompts; it validates and summarizes the existing evidence chain.

## What It Proves

- the blind baseline was collected before local output was reviewed
- repaired target prompts and holdout prompts have local answer artifacts
- each prompt has a score, score breakdown, gap classification, and next action
- routing, evidence, correctness, completeness, format, and user-visible usefulness are evaluated separately
- blocking misses become roadmap proposal candidates instead of implicit scope drift

## Inputs

- Policy: `runtime/blind_baseline_delta_report_policy.json`
- Live field report: `runtime-state/phase177/phase177-founder-field-round2-live-field-report-after-p21-metadata.json`
- Blind-baseline comparison report: `runtime-state/phase177/phase177-founder-field-round2-report-after-p21-metadata.json`
- Blind baseline package: `runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-blind-baselines.json`

The current policy covers repaired prompt families from Phases 171 through 176:

- handler branch evidence
- minimal change surface boundary
- persisted schema evidence for git and non-git fixtures
- change-boundary verification for git and non-git fixtures

## Run

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_blind_baseline_delta_report.py \
  --output-path runtime-state/phase178/phase178-blind-baseline-delta-report.json \
  --markdown-output-path runtime-state/phase178/phase178-blind-baseline-delta-report.md
```

Expected marker:

```text
PHASE178 BLIND BASELINE DELTA REPORT PASS
```

## Output

Default report:

```text
runtime-state/phase178/phase178-blind-baseline-delta-report.json
```

Default markdown:

```text
runtime-state/phase178/phase178-blind-baseline-delta-report.md
```

The report includes:

- source report paths and hashes
- target and holdout prompt deltas
- local answer artifact paths and hashes
- blind-baseline ideal answer shape and must-have facts
- per-dimension pass/advisory/fail status
- gap classes
- backlog candidates for blocking misses

## Failure Meaning

`status=failed` means the delta evidence is not safe to trust. Common causes are stale hashes, missing local answer artifacts, fixture mutation, missing blind-baseline details, late blind-baseline timestamps, routing misses, or scores below the configured floor.

`status=passed` with advisory gap classes means the prompts remain usable, but future governance should keep the advisory wording or evidence-detail risk visible.
