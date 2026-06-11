from __future__ import annotations

from pathlib import Path

from vllm_agent_gateway.controllers.verification import (
    controller_verification_commands,
    discover_related_tests_from_values,
)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_related_test_discovery_ranks_direct_test_definition_over_incidental_reference(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    write_text(
        target / "tests" / "unit" / "test_direct_lookup.py",
        "def test_placed_order_id_stealth_lookup_uses_manager_index():\n"
        "    assert 'placed_order_id'\n",
    )
    write_text(
        target / "tests" / "unit" / "test_incidental_lookup.py",
        "# placed_order_id appears in a comment but this test does not cover lookup behavior.\n"
        "def test_other_behavior():\n"
        "    assert True\n",
    )

    context = discover_related_tests_from_values(
        target,
        ["Find tests related to placed_order_id stealth lookup."],
        max_files=5,
    )

    assert context is not None
    related = context["related_test_files"]
    assert related[0]["path"] == "tests/unit/test_direct_lookup.py"
    assert related[0]["evidence_kind"] == "direct"
    assert related[0]["confidence"] == "high"
    assert related[0]["evidence_refs"][0]["kind"] == "test_definition"
    assert related[-1]["path"] == "tests/unit/test_incidental_lookup.py"
    assert related[-1]["confidence"] == "low"


def test_related_test_discovery_commands_carry_evidence_and_confidence(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    write_text(
        target / "tests" / "unit" / "test_direct_lookup.py",
        "def test_find_stealth_order_by_placed_order_id():\n"
        "    assert find_stealth_order_by_placed_order_id\n",
    )

    context = discover_related_tests_from_values(
        target,
        ["find_stealth_order_by_placed_order_id"],
        max_files=5,
    )
    commands = controller_verification_commands({"results": [context]})

    assert commands[0]["command"] == ["python", "-m", "pytest", "tests/unit/test_direct_lookup.py"]
    assert commands[0]["confidence"] == "high"
    assert commands[0]["evidence_kind"] == "direct"
    assert commands[0]["source_refs"]
    assert "high confidence" in commands[0]["reason"]


def test_related_test_discovery_returns_none_when_no_bounded_test_evidence_exists(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    write_text(target / "tests" / "unit" / "test_unrelated.py", "def test_unrelated():\n    assert True\n")

    context = discover_related_tests_from_values(
        target,
        ["placed_order_id stealth lookup"],
        max_files=5,
    )

    assert context is None

