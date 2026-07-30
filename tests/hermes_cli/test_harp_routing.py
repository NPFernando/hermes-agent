import subprocess

from hermes_cli import harp_routing


def test_risk_for_chat_type():
    assert harp_routing.risk_for_chat_type("dm") == "standard"
    assert harp_routing.risk_for_chat_type(None) == "standard"
    assert harp_routing.risk_for_chat_type("group") == "low"
    assert harp_routing.risk_for_chat_type("channel") == "low"
    assert harp_routing.risk_for_chat_type("thread") == "low"


def test_classify_task_empty_or_none_falls_back_to_text_summary():
    assert harp_routing.classify_task(None) == "text_summary"
    assert harp_routing.classify_task("") == "text_summary"
    assert harp_routing.classify_task("hey how's it going?") == "text_summary"


def test_classify_task_debugging():
    assert harp_routing.classify_task("I'm getting a traceback when I run this") == "debugging"
    assert harp_routing.classify_task("the script crashed with a stack trace") == "debugging"
    assert harp_routing.classify_task("this doesn't work, can you fix the bug?") == "debugging"


def test_classify_task_code_review():
    assert harp_routing.classify_task("can you do a code review on this PR?") == "code_review"
    assert harp_routing.classify_task("please review my diff") == "code_review"


def test_classify_task_code_generation():
    assert harp_routing.classify_task("write a function that sorts a list") == "code_generation"
    assert harp_routing.classify_task("implement a new caching layer") == "code_generation"
    assert harp_routing.classify_task("can you refactor this module?") == "code_generation"


def test_classify_task_documentation():
    assert harp_routing.classify_task("write docs for this API") == "documentation"
    assert harp_routing.classify_task("add a docstring to this function") == "documentation"


def test_classify_task_structured_output():
    assert harp_routing.classify_task("give me this data as json") == "structured_output"
    assert harp_routing.classify_task("format the output in table format") == "structured_output"


def test_classify_task_security_and_audit():
    assert harp_routing.classify_task("do a security review of this endpoint") == "security_review"
    assert harp_routing.classify_task("check for vulnerabilities in this code") == "security_review"
    assert harp_routing.classify_task("audit our access controls") == "audit"


def test_classify_task_priority_order_overlap():
    # "review this bug" should land on debugging (more actionable), not code_review,
    # per the documented priority order (debugging is checked before code_review).
    assert harp_routing.classify_task("can you review this bug in my code?") == "debugging"


def test_disabled_by_default_returns_none():
    assert harp_routing.select_route({}) is None
    assert harp_routing.select_route(None) is None
    assert harp_routing.select_route({"harp_routing": {"enabled": False}}) is None


def test_missing_selector_script_returns_none(tmp_path):
    config = {"harp_routing": {"enabled": True}}
    missing = tmp_path / "does-not-exist.py"
    assert harp_routing.select_route(config, selector_path=missing) is None


def test_parses_model_and_provider(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="DECISION: free_first\nTASK: text_summary\nMODEL: nemotron-free\nPROVIDER: openrouter\n",
            stderr="",
        )

    monkeypatch.setattr(harp_routing.subprocess, "run", fake_run)
    result = harp_routing.select_route(config, selector_path=selector)
    assert result == {"model": "nemotron-free", "provider": "openrouter"}


def test_nonzero_exit_returns_none(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(harp_routing.subprocess, "run", fake_run)
    assert harp_routing.select_route(config, selector_path=selector) is None


def test_timeout_returns_none(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="harp-select-route.py", timeout=5)

    monkeypatch.setattr(harp_routing.subprocess, "run", fake_run)
    assert harp_routing.select_route(config, selector_path=selector) is None


def test_malformed_output_returns_none(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="not the expected format", stderr="")

    monkeypatch.setattr(harp_routing.subprocess, "run", fake_run)
    assert harp_routing.select_route(config, selector_path=selector) is None


def test_repeated_calls_within_ttl_hit_cache_not_subprocess(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    call_count = {"n": 0}

    def fake_run(*_args, **_kwargs):
        call_count["n"] += 1
        return subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="MODEL: nemotron-free\nPROVIDER: openrouter\n", stderr="",
        )

    monkeypatch.setattr(harp_routing.subprocess, "run", fake_run)
    first = harp_routing.select_route(config, selector_path=selector)
    second = harp_routing.select_route(config, selector_path=selector)
    assert first == second == {"model": "nemotron-free", "provider": "openrouter"}
    assert call_count["n"] == 1, "second call within TTL should hit the cache, not spawn a new subprocess"


def test_cache_expires_after_ttl(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True, "cache_ttl_seconds": 0}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    call_count = {"n": 0}

    def fake_run(*_args, **_kwargs):
        call_count["n"] += 1
        return subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="MODEL: nemotron-free\nPROVIDER: openrouter\n", stderr="",
        )

    monkeypatch.setattr(harp_routing.subprocess, "run", fake_run)
    harp_routing.select_route(config, selector_path=selector)
    harp_routing.select_route(config, selector_path=selector)
    assert call_count["n"] == 2, "cache_ttl_seconds: 0 should disable caching entirely"


class _FakeCursor:
    """Minimal fake matching the subset of the sqlite3/harp_pg cursor
    interface these functions use: execute(sql, params).fetchone()."""

    def __init__(self, rows_by_query):
        # rows_by_query: dict mapping a substring of the SQL to a fixed
        # fetchone() return value (a tuple, or None).
        self._rows_by_query = rows_by_query

    def execute(self, sql, params=()):
        for substring, row in self._rows_by_query.items():
            if substring in sql:
                self._next_row = row
                return self
        self._next_row = None
        return self

    def fetchone(self):
        return self._next_row


class _FakeConn:
    def __init__(self, rows_by_query):
        self._cursor = _FakeCursor(rows_by_query)

    def cursor(self):
        return self._cursor

    def close(self):
        pass


def test_is_free_route():
    assert harp_routing.is_free_route({"model": "nvidia/x:free", "provider": "openrouter"}) is True
    assert harp_routing.is_free_route({"model": "gpt-4o", "provider": "openai-codex"}) is False
    assert harp_routing.is_free_route({"model": "x:free", "provider": "anthropic"}) is False  # wrong provider
    assert harp_routing.is_free_route(None) is False
    assert harp_routing.is_free_route({}) is False


def test_within_paid_budget_under_cap(monkeypatch):
    # Conn whose cursor always returns usage_now=1.0, and both historical
    # lookups return None (no earlier snapshot -> burn treated as 0), well
    # under the default $2/$30 caps.
    def fake_execute(self, sql, params=()):
        if "captured_at <=" in sql:
            self._next_row = None  # no historical snapshot -> burn = 0
        elif "usage_usd IS NOT NULL ORDER BY captured_at DESC LIMIT 1" in sql:
            self._next_row = (1.0,)
        else:
            self._next_row = None
        return self

    monkeypatch.setattr(_FakeCursor, "execute", fake_execute)
    monkeypatch.setattr(harp_routing, "_harp_pg_connect", lambda: _FakeConn({}))
    assert harp_routing.within_paid_budget({}) is True


def test_within_paid_budget_over_daily_cap(monkeypatch):
    def fake_execute(self, sql, params=()):
        if "captured_at <=" in sql:
            self._next_row = (1.0,)  # usage 24h ago was $1.0
        elif "usage_usd IS NOT NULL ORDER BY captured_at DESC LIMIT 1" in sql:
            self._next_row = (10.0,)  # usage now is $10.0 -> burn_24h = $9.0 > $2 cap
        else:
            self._next_row = None
        return self

    monkeypatch.setattr(_FakeCursor, "execute", fake_execute)
    monkeypatch.setattr(harp_routing, "_harp_pg_connect", lambda: _FakeConn({}))
    assert harp_routing.within_paid_budget({}) is False


def test_within_paid_budget_no_connection_fails_closed(monkeypatch):
    monkeypatch.setattr(harp_routing, "_harp_pg_connect", lambda: None)
    assert harp_routing.within_paid_budget({}) is False


def test_within_paid_budget_no_usage_data_fails_closed(monkeypatch):
    def fake_execute(self, sql, params=()):
        self._next_row = None
        return self

    monkeypatch.setattr(_FakeCursor, "execute", fake_execute)
    monkeypatch.setattr(harp_routing, "_harp_pg_connect", lambda: _FakeConn({}))
    assert harp_routing.within_paid_budget({}) is False


def test_within_paid_budget_uses_custom_config_caps(monkeypatch):
    def fake_execute(self, sql, params=()):
        if "captured_at <=" in sql:
            self._next_row = (1.0,)
        elif "usage_usd IS NOT NULL ORDER BY captured_at DESC LIMIT 1" in sql:
            self._next_row = (2.5,)  # burn_24h = $1.5
        else:
            self._next_row = None
        return self

    monkeypatch.setattr(_FakeCursor, "execute", fake_execute)
    monkeypatch.setattr(harp_routing, "_harp_pg_connect", lambda: _FakeConn({}))
    # $1.5 burn is under the default $2 cap...
    assert harp_routing.within_paid_budget({}) is True
    # ...but over a stricter configured $1 cap.
    config = {"delegation": {"routing": {"paid_budget_daily_usd": 1.0, "paid_budget_monthly_usd": 30.0}}}
    assert harp_routing.within_paid_budget(config) is False


def test_top_scoring_model_for_task_returns_best_scorer(monkeypatch):
    def fake_execute(self, sql, params=()):
        assert params == ("code_review",)
        self._next_row = ("some/best-model:free",)
        return self

    monkeypatch.setattr(_FakeCursor, "execute", fake_execute)
    monkeypatch.setattr(harp_routing, "_harp_pg_connect", lambda: _FakeConn({}))
    assert harp_routing.top_scoring_model_for_task("code_review") == {
        "model": "some/best-model:free", "provider": "openrouter",
    }


def test_top_scoring_model_for_task_maps_security_review_to_audit(monkeypatch):
    seen_params = []

    def fake_execute(self, sql, params=()):
        seen_params.append(params)
        self._next_row = ("audit-model", )
        return self

    monkeypatch.setattr(_FakeCursor, "execute", fake_execute)
    monkeypatch.setattr(harp_routing, "_harp_pg_connect", lambda: _FakeConn({}))
    harp_routing.top_scoring_model_for_task("security_review")
    assert seen_params == [("audit",)]


def test_top_scoring_model_for_task_none_when_no_rows(monkeypatch):
    def fake_execute(self, sql, params=()):
        self._next_row = None
        return self

    monkeypatch.setattr(_FakeCursor, "execute", fake_execute)
    monkeypatch.setattr(harp_routing, "_harp_pg_connect", lambda: _FakeConn({}))
    assert harp_routing.top_scoring_model_for_task("nonexistent_task") is None


def test_top_scoring_model_for_task_no_connection_returns_none(monkeypatch):
    monkeypatch.setattr(harp_routing, "_harp_pg_connect", lambda: None)
    assert harp_routing.top_scoring_model_for_task("code_review") is None


def test_status_summary_disabled():
    assert harp_routing.status_summary({}) == {"enabled": False, "decision": None, "age_seconds": None}


def test_status_summary_enabled_no_cache_yet(tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")
    result = harp_routing.status_summary(config, selector_path=selector)
    assert result == {"enabled": True, "decision": None, "age_seconds": None}


def test_status_summary_reflects_cached_decision(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="MODEL: nemotron-free\nPROVIDER: openrouter\n", stderr="",
        )

    monkeypatch.setattr(harp_routing.subprocess, "run", fake_run)
    harp_routing.select_route(config, selector_path=selector)  # populate cache

    status = harp_routing.status_summary(config, selector_path=selector)
    assert status["enabled"] is True
    assert status["decision"] == {"model": "nemotron-free", "provider": "openrouter"}
    assert status["age_seconds"] is not None and status["age_seconds"] >= 0


def test_failure_is_also_cached(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    call_count = {"n": 0}

    def fake_run(*_args, **_kwargs):
        call_count["n"] += 1
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(harp_routing.subprocess, "run", fake_run)
    assert harp_routing.select_route(config, selector_path=selector) is None
    assert harp_routing.select_route(config, selector_path=selector) is None
    assert call_count["n"] == 1, "a failure should also be cached, not retried on every message"


def test_plan_delegation_route_disabled_returns_inherit_parent():
    plan = harp_routing.plan_delegation_route({}, goal_text="write a function to sort a list")
    assert plan["route"] is None
    assert plan["fallback_mode"] == "inherit_parent"
    assert plan["task"] == "code_generation"  # classification still happens even when disabled


def test_plan_delegation_route_classifies_and_carries_policy_context(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="MODEL: nemotron-free\nPROVIDER: openrouter\n", stderr="",
        )

    monkeypatch.setattr(harp_routing.subprocess, "run", fake_run)
    plan = harp_routing.plan_delegation_route(
        config, goal_text="I'm getting a traceback, please fix this bug",
        data_class="confidential", action_mode="review", risk="high_risk",
        selector_path=selector,
    )
    assert plan["task"] == "debugging"
    assert plan["risk"] == "high_risk"
    assert plan["data_class"] == "confidential"
    assert plan["action_mode"] == "review"
    assert plan["route"] == {"model": "nemotron-free", "provider": "openrouter"}
    assert plan["fallback_mode"] == "explicit_route"


def test_plan_delegation_route_never_raises_on_selector_failure(monkeypatch, tmp_path):
    config = {"harp_routing": {"enabled": True}}
    selector = tmp_path / "harp-select-route.py"
    selector.write_text("#!/usr/bin/env python3\n")

    def exploding_run(*_args, **_kwargs):
        raise RuntimeError("simulated selector crash")

    monkeypatch.setattr(harp_routing.subprocess, "run", exploding_run)
    plan = harp_routing.plan_delegation_route(config, goal_text="hello", selector_path=selector)
    assert plan["fallback_mode"] == "inherit_parent"
    assert plan["route"] is None
