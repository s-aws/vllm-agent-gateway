# Regression Examples

Full phase-closeout gate:

```bash
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python scripts/run_regression.py --workers 4
```

Focused iteration on one file:

```bash
python3 -m pytest tests/regression/test_gateway_server.py -v
```

Dry-run the split lanes:

```bash
. .venv/bin/activate
python scripts/run_regression.py --dry-run
```

Debug only the process-parallel lane:

```bash
. .venv/bin/activate
python scripts/run_regression.py --parallel-only --workers 2 -- --maxfail=1
```

Debug only tests that are unsafe for process parallelism:

```bash
. .venv/bin/activate
python scripts/run_regression.py --serial-only
```

Run a clean-clone static replay while excluding tests that require ignored local proof artifacts:

```bash
. .venv/bin/activate
python -m pytest tests/regression/test_fresh_local_model_drift.py -m "not requires_baseline_artifacts"
```
