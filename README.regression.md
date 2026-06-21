# Regression Process

The full regression gate uses `scripts/run_regression.py`.

The runner splits the suite into two lanes:

- `parallel_safe_regression`: runs `tests/regression` with `pytest-xdist`, `--dist loadfile`, and marker expression `not advanced_workflow and not serial`.
- `serial_regression`: runs tests marked `serial` without xdist using marker expression `not advanced_workflow and serial`.

Use direct pytest commands for focused iteration. Use the split runner for phase closeout, release-candidate work, shared controller/router/formatter changes, and any change whose blast radius is not bounded.

## Commands

Install the dev test dependency if the environment does not already have xdist. On WSL/Ubuntu, use a project-local venv because the system Python may be externally managed:

```bash
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Run the full split regression:

```bash
. .venv/bin/activate
python scripts/run_regression.py --workers 4
```

Preview the lanes without running tests:

```bash
python scripts/run_regression.py --dry-run
```

Run only the xdist lane:

```bash
python scripts/run_regression.py --parallel-only --workers 4
```

Run only the serial lane:

```bash
python scripts/run_regression.py --serial-only
```

Pass extra pytest arguments after `--`:

```bash
python scripts/run_regression.py --workers 4 -- --maxfail=1
```

## Serial Marker Policy

Mark a regression test or module with `pytest.mark.serial` when it touches shared repo state, fixed runtime-state paths, fixed external resources, process-global state, or timing-sensitive reset/recovery behavior.

Examples:

```python
import pytest

pytestmark = pytest.mark.serial
```

Keep isolated unit-style regression tests out of the serial lane. Tests that use `tmp_path`, random ports, mocked external clients, or file-local resources are expected to stay xdist-safe.

## Baseline Artifact Marker Policy

Mark a regression test with `pytest.mark.requires_baseline_artifacts` when it validates accepted proof artifacts stored under ignored `runtime-state/` paths. These tests are valid in the active maintainer workspace after the required proof has been generated, but they are not clean-clone static replay tests because those local artifacts are intentionally not tracked.

Clean-clone static replay commands should exclude that marker:

```bash
python -m pytest tests/regression/test_fresh_local_model_drift.py -m "not requires_baseline_artifacts"
```
