"""Fail-closed scaffolded regression gates for the Phase 194 draft skill."""

import pytest


SKILL_ID = "phase194-readme-locator"
NATURAL_PROMPT = "In <repo>, find where the skill authoring pipeline docs explain promotion boundaries. Read only."
EXPECTED_WORKFLOW = "code_investigation.plan"
EXPECTED_ARTIFACT = "documentation_lookup"
COVERAGE_ID = "PHASE194-README-LOCATOR"


def test_phase194_readme_locator_routing():
    pytest.fail("routing gate is not installed yet")


def test_phase194_readme_locator_artifact_contract():
    pytest.fail("artifact_contract gate is not installed yet")


def test_phase194_readme_locator_natural_language_chat_output():
    pytest.fail("natural_language_chat_output gate is not installed yet")


def test_phase194_readme_locator_prompt_coverage():
    pytest.fail("prompt_coverage gate is not installed yet")


def test_phase194_readme_locator_blind_baseline_first():
    pytest.fail("blind_baseline_first gate is not installed yet")


def test_phase194_readme_locator_holdout_prompt():
    pytest.fail("holdout_prompt gate is not installed yet")


def test_phase194_readme_locator_live_gateway():
    pytest.fail("live_gateway gate is not installed yet")


def test_phase194_readme_locator_anythingllm_when_applicable():
    pytest.fail("anythingllm_when_applicable gate is not installed yet")


def test_phase194_readme_locator_fixture_parity():
    pytest.fail("fixture_parity gate is not installed yet")
