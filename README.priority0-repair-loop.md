# Priority 0 Repair Loop

Phase 159 closes the repair-loop decision after Phase 158 transcript quality intake.

It does not invent repairs. It reads the Phase 158 findings and decides whether any item requires target-plus-holdout repair proof. If Phase 158 contains only monitoring findings, Phase 159 produces a governed `no_repair_required` report.

## What It Reads

Policy:

```text
runtime/priority0_repair_loop_policy.json
```

Required Phase 158 evidence:

```text
runtime-state/transcript-quality-feedback-intake/phase158/phase158-transcript-quality-feedback-intake-report.json
```

Optional repair records, used only when Phase 158 contains `phase159_eligible=true` findings:

```text
runtime-state/priority0-repair-loop/phase159/repair-records.json
```

## What It Produces

JSON:

```text
runtime-state/priority0-repair-loop/phase159/phase159-priority0-repair-loop-report.json
```

Markdown:

```text
runtime-state/priority0-repair-loop/phase159/phase159-priority0-repair-loop-report.md
```

The report includes:

- repair mode
- monitoring-only findings
- repair items, when required
- closed repair count
- open repair count
- missing repair-record count
- validation errors
- next phase marker

## Repair Modes

- `no_repair_required`: Phase 158 has no Phase 159-eligible findings.
- `repairs_closed`: every eligible finding has target and holdout proof.
- `blocked_with_next_action`: at least one eligible finding remains open with a concrete blocker and next action. The report status is `blocked`, and the CLI exits non-zero.

Closed repair records must prove:

- rerun gate is `phase159_target_plus_holdout`
- live surfaces include `gateway` and `anythingllm`
- target result passed
- holdout result passed
- mutation status is `unchanged`
- target and holdout report paths are present
- target and holdout report paths exist and contain readable JSON proof reports

Target proof reports must use:

```text
kind=priority0_repair_target_proof
status=passed
result_status=passed
```

Holdout proof reports must use:

```text
kind=priority0_repair_holdout_proof
status=passed
result_status=passed
```

## Run

Run from Bash/WSL:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_priority0_repair_loop.py \
  --output-path runtime-state/priority0-repair-loop/phase159/phase159-priority0-repair-loop-report.json \
  --markdown-output-path runtime-state/priority0-repair-loop/phase159/phase159-priority0-repair-loop-report.md
```

Expected marker:

```text
PHASE159 PRIORITY0 REPAIR LOOP PASS
```

Examples: [docs/examples/priority0-repair-loop.md](docs/examples/priority0-repair-loop.md).
