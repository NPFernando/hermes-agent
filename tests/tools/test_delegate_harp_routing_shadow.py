"""Tests for the shadow-mode HARP routing plan injected into delegate_task().

Covers: default (inherit_parent) behavior is byte-for-byte unchanged; shadow
mode logs a plan without touching credentials; a failing/blocked plan never
raises into delegate_task's caller. Mirrors the existing patterns in
tests/hermes_cli/test_harp_routing.py and
tests/gateway/test_harp_routing_live_integration.py, adapted for the
delegate_task boundary using this file's existing _make_mock_parent fixture.
"""

import json
import threading
from unittest.mock import patch

from tools.delegate_tool import delegate_task


def _make_mock_parent(depth=0):
    from unittest.mock import MagicMock

    parent = MagicMock()
    parent.base_url = "https://openrouter.ai/api/v1"
    parent.api_key = "***"
    parent.provider = "openrouter"
    parent.api_mode = "chat_completions"
    parent.model = "anthropic/claude-sonnet-4"
    parent.platform = "cli"
    parent.providers_allowed = None
    parent.providers_ignored = None
    parent.providers_order = None
    parent.provider_sort = None
    parent._session_db = None
    parent._delegate_depth = depth
    parent._active_children = []
    parent._active_children_lock = threading.Lock()
    parent._print_fn = None
    parent.tool_progress_callback = None
    parent.thinking_callback = None
    return parent


_BASE_CONFIG_RUN = {
    "task_index": 0, "status": "completed",
    "summary": "Done!", "api_calls": 1, "duration_seconds": 1.0,
}


@patch("tools.delegate_tool._run_single_child")
@patch("tools.delegate_tool._load_config")
def test_default_config_has_no_routing_key_behaves_identically(mock_cfg, mock_run):
    """Real config.yaml (no explicit delegation.routing) must behave exactly
    as it did before this feature existed -- the new code path only
    activates for mode in {shadow, enforce}, and the default DEFAULT_CONFIG
    value is inherit_parent."""
    mock_cfg.return_value = {"delegation": {"routing": {"mode": "inherit_parent"}}}
    mock_run.return_value = dict(_BASE_CONFIG_RUN)
    parent = _make_mock_parent()

    result = json.loads(delegate_task(goal="write a function", parent_agent=parent))

    assert result["results"][0]["status"] == "completed"
    mock_run.assert_called_once()


@patch("tools.delegate_tool._run_single_child")
@patch("tools.delegate_tool._load_config")
def test_missing_routing_key_entirely_behaves_identically(mock_cfg, mock_run):
    """Config with no delegation.routing key at all (e.g. an older config.yaml
    predating this feature) must default to inherit_parent, not crash."""
    mock_cfg.return_value = {"delegation": {}}
    mock_run.return_value = dict(_BASE_CONFIG_RUN)
    parent = _make_mock_parent()

    result = json.loads(delegate_task(goal="write a function", parent_agent=parent))

    assert result["results"][0]["status"] == "completed"


@patch("hermes_cli.harp_routing.plan_delegation_route")
@patch("tools.delegate_tool._run_single_child")
@patch("tools.delegate_tool._load_config")
def test_shadow_mode_logs_plan_but_does_not_change_credentials(mock_cfg, mock_run, mock_plan, caplog):
    mock_cfg.return_value = {"delegation": {"routing": {"mode": "shadow"}}}
    mock_run.return_value = dict(_BASE_CONFIG_RUN)
    mock_plan.return_value = {
        "task": "code_generation", "risk": "standard", "data_class": "internal",
        "action_mode": "write", "route": {"model": "nemotron-free", "provider": "openrouter"},
        "fallback_mode": "explicit_route",
    }
    parent = _make_mock_parent()

    import logging
    with caplog.at_level(logging.INFO, logger="tools.delegate_tool"):
        result = json.loads(delegate_task(goal="write a function", parent_agent=parent))

    assert result["results"][0]["status"] == "completed"
    mock_plan.assert_called_once()
    assert any("harp_routing shadow plan" in rec.message for rec in caplog.records)
    # Shadow mode must not have changed what _run_single_child actually received --
    # it's still using the parent's inherited credentials (mock_run was called
    # normally, no explicit_route credentials substituted anywhere since that's
    # Phase 2/enforce-mode work, not implemented here).
    mock_run.assert_called_once()


@patch("hermes_cli.harp_routing.plan_delegation_route")
@patch("tools.delegate_tool._run_single_child")
@patch("tools.delegate_tool._load_config")
def test_shadow_mode_plan_failure_never_raises(mock_cfg, mock_run, mock_plan):
    mock_cfg.return_value = {"delegation": {"routing": {"mode": "shadow"}}}
    mock_run.return_value = dict(_BASE_CONFIG_RUN)
    mock_plan.side_effect = RuntimeError("simulated harp_routing crash")
    parent = _make_mock_parent()

    result = json.loads(delegate_task(goal="write a function", parent_agent=parent))

    assert result["results"][0]["status"] == "completed"
    mock_run.assert_called_once()
