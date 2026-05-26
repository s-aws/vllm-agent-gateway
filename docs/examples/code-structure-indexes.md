# Code Structure Index Examples

Build an index for tracked supported files:

```bash
python scripts/run_code_structure_index.py --target-root /path/to/project
```

Bootstrap scan all supported files:

```bash
python scripts/run_code_structure_index.py --target-root /path/to/project --file-scope all
```

Skip very large individual files at a smaller limit:

```bash
python scripts/run_code_structure_index.py --target-root /path/to/project \
  --max-file-bytes 1048576
```

Emit a bounded packet-ready slice for a Python symbol:

```bash
python scripts/run_code_structure_index.py --target-root /path/to/project \
  --slice-path pkg/module.py \
  --slice-symbol Service \
  --slice-max-records 25
```

Emit a bounded config key-path slice:

```bash
python scripts/run_code_structure_index.py --target-root /path/to/project \
  --slice-path config/settings.json \
  --slice-key-path runtime \
  --slice-max-records 25
```

Emit a bounded reference slice:

```bash
python scripts/run_code_structure_index.py --target-root /path/to/project \
  --slice-reference-target docs/setup.md \
  --slice-max-records 25
```
