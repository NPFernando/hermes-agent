"""Tests for the HARP heuristic adaptive task classifier."""

from __future__ import annotations

import pytest

from agent.adaptive_task_classifier import TaskClassification, classify_task


def test_secret_auth_requests_classify_high_risk():
    result = classify_task(
        "Rotate the OAuth client secret and update the production auth token."
    )

    assert isinstance(result, TaskClassification)
    assert result.classification == "high_risk"
    assert result.risk == "high"
    assert "high_risk:oauth" in result.matched_signals
    assert "high_risk:secret" in result.matched_signals
    assert "high_risk:token" in result.matched_signals


@pytest.mark.parametrize(
    ("prompt", "expected_signal"),
    [
        ("Rotate the API key for the service.", "high_risk:api_key"),
        ("Update credentials in the config file.", "high_risk:credential"),
        ("Move the private key into the secrets file.", "high_risk:private_key"),
        ("Check whether .env contains an access key.", "high_risk:env_file"),
        ("Open ~/.env and check the value.", "high_risk:env_file"),
        ("Read /tmp/.env for the API configuration.", "high_risk:env_file"),
        ("Open .env, check the setting.", "high_risk:env_file"),
    ],
)
def test_common_secret_synonyms_classify_high_risk(prompt, expected_signal):
    result = classify_task(prompt)

    assert result.classification == "high_risk"
    assert result.risk == "high"
    assert expected_signal in result.matched_signals


@pytest.mark.parametrize(
    "prompt",
    [
        "Summarize this release note in two bullets.",
        "Rewrite this paragraph to be friendlier.",
        "Please explain what this function does.",
        "Format this response as JSON.",
        "Fix the grammar in this sentence.",
        "Short answer: what is HARP?",
    ],
)
def test_summary_rewrite_explain_format_grammar_classify_simple(prompt):
    result = classify_task(prompt)

    assert result.classification == "simple"
    assert result.risk == "low"
    assert result.matched_signals


def test_multi_file_debugging_classifies_complex():
    result = classify_task(
        "Find the root cause of these failing tests across multiple files. "
        "The traceback points at a race condition."
    )

    assert result.classification == "complex"
    assert result.risk == "medium"
    assert "complex:failing_tests" in result.matched_signals
    assert "complex:root_cause" in result.matched_signals
    assert "complex:race_condition" in result.matched_signals


@pytest.mark.parametrize("prompt", ["", "   \n\t", "help", "debug", "fix bug"])
def test_empty_and_ambiguous_prompts_classify_unknown(prompt):
    result = classify_task(prompt)

    assert result.classification == "unknown"
    assert result.risk == "unknown"
    assert result.matched_signals == ()


def test_high_risk_wins_over_complex_and_simple_signals():
    result = classify_task(
        "Summarize the root cause before the database migration deletes production data."
    )

    assert result.classification == "high_risk"
    assert result.risk == "high"
    assert "simple:summarize" in result.matched_signals
    assert "complex:root_cause" in result.matched_signals
    assert "high_risk:database_migration" in result.matched_signals
    assert "high_risk:production" in result.matched_signals


def test_complex_wins_over_simple_signals():
    result = classify_task("Explain the root cause of this traceback from failing tests.")

    assert result.classification == "complex"
    assert result.risk == "medium"
    assert "simple:explain" in result.matched_signals
    assert "complex:traceback" in result.matched_signals


def test_file_modification_or_tools_raise_simple_tasks_to_standard():
    prompt = "Rewrite and format the README file."

    result = classify_task(prompt, has_files=True, needs_tools=True)

    assert result.classification == "standard"
    assert result.risk == "medium"
    assert "tool:file_context" in result.matched_signals
    assert "tool:needs_tools" in result.matched_signals


@pytest.mark.parametrize(
    ("prompt", "expected_signal"),
    [
        ("Read README.md and summarize it.", "tool:file_read"),
        ("Inspect app.py and explain the bug.", "tool:file_read"),
        ("Use a tool to check the file.", "tool:explicit_tool_use"),
        ("Please use the tool.", "tool:explicit_tool_use"),
        ("Please use the search tool.", "tool:explicit_tool_use"),
    ],
)
def test_read_only_file_and_explicit_tool_prompts_are_standard(prompt, expected_signal):
    result = classify_task(prompt)

    assert result.classification == "standard"
    assert result.risk == "medium"
    assert expected_signal in result.matched_signals


@pytest.mark.parametrize(
    ("prompt", "expected_signal"),
    [
        ("Check git status before changing the docs.", "tool:git"),
        ("Update the Docker compose file.", "tool:docker"),
        ("Fix the CI/CD workflow config.", "tool:ci_cd"),
    ],
)
def test_git_docker_ci_cd_prompts_are_at_least_standard(prompt, expected_signal):
    result = classify_task(prompt)

    assert result.classification == "standard"
    assert result.risk == "medium"
    assert expected_signal in result.matched_signals


def test_context_preview_and_toolsets_contribute_signals_without_raw_prompt_logging():
    result = classify_task(
        "Please help with this.",
        context_preview="Traceback from pytest mentions a multi-file failure.",
        toolsets=["git", "docker"],
    )

    assert result.classification == "complex"
    assert "complex:traceback" in result.matched_signals
    assert "tool:git" in result.matched_signals
    assert "tool:docker" in result.matched_signals
    assert "Please help with this" not in repr(result)
    assert "Traceback from pytest" not in repr(result)
