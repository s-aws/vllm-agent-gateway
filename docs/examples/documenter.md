# Documenter Examples

Dry-run packet generation:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md --dry-run
```

Run the full workflow against the local documenter role endpoint:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md --mode full
```

Bootstrap review with all supported docs, including untracked files:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md \
  --mode full \
  --document-scope all
```

Scan all files but review only the selected seed document:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md \
  --mode full \
  --document-scope all \
  --review-scope seed
```

Review every tracked documentation file:

```bash
python scripts/run_documenter_orchestrator.py --target-root . \
  --mode full \
  --review-scope manifest
```

Quick one-chunk smoke run. `--max-chunks` is applied per reviewed file:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md \
  --mode review \
  --max-chunks 1
```

Adjust chunk sizing:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md \
  --chunk-token-limit 1200 \
  --chunk-overlap-lines 12
```

Review a different project while using this repo for gateway configuration:

```bash
python /path/to/vllm-agent-gateway/scripts/run_documenter_orchestrator.py \
  --config-root /path/to/vllm-agent-gateway \
  --target-root /path/to/project \
  --seed-doc README.md
```

Bounded follow-up expansion:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md \
  --mode full \
  --include-followups \
  --followup-depth 1 \
  --max-followup-files 5
```

Compatibility mode for old exact-path behavior on in-scope files that were not visible in the packet:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md \
  --mode full \
  --include-followups \
  --allow-nonvisible-followups
```

Optional draft artifacts:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md \
  --mode full \
  --write-draft
```

Use a generated change plan as input for a documentation implementation agent:

```text
Based on this documentation change plan:
<path-to-doc-change-plan-*.md>

Update the documentation for <target-repo>.

Follow the "Agent Execution Contract" in the plan. Verify every new claim from
target repository sources, keep the root README as an entry point, update the
relevant feature README/examples/docs index together, report skipped CP items
with reasons, and run the repository-required checks before reporting done.
```

Pause and resume:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md \
  --mode full \
  --dry-run \
  --max-chunks 1 \
  --stop-after-chunks 1

python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md \
  --mode full \
  --dry-run \
  --max-chunks 1 \
  --resume .agentic_reports/run-state-agentic_agents-README.md-<run-id>.json
```

Summarize an existing report:

```bash
python scripts/run_documenter_orchestrator.py \
  --mode summarize \
  --report .agentic_reports/documenter-<target>-<doc>-<run-id>.json
```
