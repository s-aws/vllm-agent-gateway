from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_protected_root(path: Path) -> None:
    watched = path / "core" / "stealth_order_manager.py"
    watched.parent.mkdir(parents=True, exist_ok=True)
    watched.write_text("def sentinel():\n    return 'unchanged'\n", encoding="utf-8")


def test_skill_mutation_command_fails_expected_faults_and_restores_disposable_copies(tmp_path: Path) -> None:
    protected_a = tmp_path / "coinbase_testing_repo_frozen_tmp"
    protected_b = tmp_path / "coinbase_testing_repo_frozen_tmp.github"
    write_protected_root(protected_a)
    write_protected_root(protected_b)
    output_path = tmp_path / "skill-mutations.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/validate_skill_mutations.py",
            "--output-path",
            str(output_path),
            "--protected-root",
            str(protected_a),
            "--protected-root",
            str(protected_b),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["summary"]["mutation_count"] == 9
    assert report["summary"]["failed_count"] == 0
    assert report["summary"]["protected_fixture_mutated"] is False
    assert report["summary"]["all_disposable_roots_restored_or_deleted"] is True
    expected = {
        "duplicate_route_key",
        "missing_skill_body",
        "broken_frontmatter",
        "unknown_workflow",
        "unknown_tool",
        "missing_eval_case",
        "stale_live_proof",
        "deprecated_replacement_breakage",
        "route_namespace_drift",
    }
    observed = {item["observed_failure_code"] for item in report["mutations"]}
    assert observed == expected
    assert all(item["restored_or_deleted"] for item in report["mutations"])
    assert all(not Path(item["disposable_root"]).exists() for item in report["mutations"])
    assert (protected_a / "core" / "stealth_order_manager.py").read_text(encoding="utf-8") == (
        "def sentinel():\n    return 'unchanged'\n"
    )
    assert (protected_b / "core" / "stealth_order_manager.py").read_text(encoding="utf-8") == (
        "def sentinel():\n    return 'unchanged'\n"
    )
