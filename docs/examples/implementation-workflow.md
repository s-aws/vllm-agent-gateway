# Implementation Workflow Examples

Create draft artifacts from a documenter report by approving all safe items:

```bash
python scripts/run_implementation_workflow.py --target-root /path/to/project \
  --from-report .agentic_reports/documenter-<run>.json \
  --approve-all-safe
```

Approve one change-plan item:

```bash
python scripts/run_implementation_workflow.py --target-root /path/to/project \
  --from-report .agentic_reports/documenter-<run>.json \
  --approve-change-plan-item CP-0001
```

Explicit packet file:

```json
{
  "schema_version": 1,
  "packets": [
    {
      "id": "IMP-0001",
      "target_files": ["README.md"],
      "operation": {
        "kind": "replace_text",
        "path": "README.md",
        "old": "old text",
        "new": "new text"
      },
      "acceptance_criteria": ["README is updated."]
    }
  ]
}
```

Run explicit packets in draft mode with pytest verification:

```bash
python scripts/run_implementation_workflow.py --target-root /path/to/project \
  --packet-file implementation-packets.json \
  --verification-pytest tests
```

Apply explicitly:

```bash
python scripts/run_implementation_workflow.py --target-root /path/to/project \
  --mode apply \
  --packet-file implementation-packets.json \
  --verification-pytest tests
```

Inspect patch and rollback proof in `implementation-report-*.json`:

```json
{
  "changed_artifacts": [
    {
      "patch_preview": ".agentic_reports/implementation-drafts/<run-id>/patches/IMP-0001-README.md.diff",
      "before_sha256": "...",
      "after_sha256": "...",
      "rollback_operation": {
        "kind": "replace_text",
        "path": "README.md",
        "old": "new text",
        "new": "old text"
      }
    }
  ]
}
```

Pause after one packet:

```bash
python scripts/run_implementation_workflow.py --target-root /path/to/project \
  --packet-file implementation-packets.json \
  --stop-after-packets 1
```

Resume:

```bash
python scripts/run_implementation_workflow.py --target-root /path/to/project \
  --output-dir .agentic_reports \
  --resume .agentic_reports/implementation-state-<target>-<run-id>.json
```

Disable structure slices if a packet must stay smaller:

```bash
python scripts/run_implementation_workflow.py --target-root /path/to/project \
  --packet-file implementation-packets.json \
  --no-structure-index
```
