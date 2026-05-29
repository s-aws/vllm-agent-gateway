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

Run live model reviews with bounded parallel chunk requests:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md \
  --mode full \
  --review-scope manifest \
  --parallelism 2
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
Resolve the Executable Work Packages in <path-to-doc-change-plan-*.md> for <target-repo>.
```

The plan carries the implementation contract, target files, source `CP-*` item ids, required actions, and acceptance criteria. A longer prompt should not be necessary unless the work package is blocked and needs a user decision.

For repository-wide setup/configuration/runtime/tested-environment gaps, the generated work package should target entry-point docs such as `README.md` and `docs/README.md`. Do not spread those generic gaps across feature reference files.

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
