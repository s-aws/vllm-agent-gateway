from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.implementation_prep_expansion import (
    DEFAULT_CASES_PATH,
    ImplementationPrepExpansionConfig,
    read_json_object,
    validate_catalog,
    validate_implementation_prep_expansion,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_implementation_prep_expansion_catalog_passes_contract() -> None:
    catalog = read_json_object(REPO_ROOT / DEFAULT_CASES_PATH)
    checks = validate_catalog(catalog, cases_path=REPO_ROOT / DEFAULT_CASES_PATH)
    assert checks[0]["status"] == "passed"


def test_implementation_prep_expansion_catalog_rejects_missing_mutation_policy() -> None:
    catalog = read_json_object(REPO_ROOT / DEFAULT_CASES_PATH)
    mutated = copy.deepcopy(catalog)
    del mutated["cases"][0]["mutation_policy"]
    checks = validate_catalog(mutated, cases_path=REPO_ROOT / DEFAULT_CASES_PATH)
    assert checks[0]["status"] == "failed"
    assert any("mutation_policy" in error for error in checks[0]["details"]["errors"])


def test_implementation_prep_expansion_direct_cases_pass(tmp_path: Path) -> None:
    report = validate_implementation_prep_expansion(
        ImplementationPrepExpansionConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "phase96-direct.json",
            include_direct=True,
            include_gateway=False,
            include_anythingllm=False,
        )
    )
    assert report["status"] == "passed"
    assert report["summary"]["case_count"] == 2
    assert report["summary"]["failed_check_ids"] == []
