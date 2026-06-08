"""Tests for the adaptive routing SQLite state store."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3

from agent.adaptive_routing_state import AdaptiveRoutingState


_FIXED_NOW = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)


def _state(tmp_path: Path) -> AdaptiveRoutingState:
    return AdaptiveRoutingState(tmp_path / "adaptive-routing-state.db")


def test_database_initializes_under_temp_hermes_home(tmp_path, monkeypatch):
    hermes_home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    state = AdaptiveRoutingState()

    assert state.db_path == hermes_home / "adaptive-routing" / "state.db"
    assert state.db_path.exists()
    assert state.db_path.parent.exists()
    with sqlite3.connect(state.db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"route_attempts", "route_cooldowns"}.issubset(tables)


def test_request_attempt_increments_rpm_rpd_counters(tmp_path):
    state = _state(tmp_path)
    provider = "openrouter"
    model = "free-model"

    state.record_attempt(
        source="delegation",
        provider=provider,
        model=model,
        outcome="success",
        created_at=_FIXED_NOW - timedelta(seconds=30),
    )
    state.record_attempt(
        source="delegation",
        provider=provider,
        model=model,
        outcome="success",
        created_at=_FIXED_NOW - timedelta(hours=2),
    )
    state.record_attempt(
        source="delegation",
        provider="other-provider",
        model=model,
        outcome="success",
        created_at=_FIXED_NOW - timedelta(seconds=10),
    )

    assert state.get_recent_attempt_counts(provider, model, now=_FIXED_NOW) == {
        "rpm": 1,
        "rpd": 2,
    }
    assert state.count_attempts(
        provider,
        model,
        since=_FIXED_NOW - timedelta(minutes=1),
    ) == 1


def test_cooldown_suppresses_model_until_expiry(tmp_path):
    state = _state(tmp_path)
    cooldown_until = _FIXED_NOW + timedelta(minutes=5)

    state.set_cooldown(
        provider="openrouter",
        model="free-model",
        cooldown_until=cooldown_until,
        reason="rate_limit",
        last_error_class="rate_limit",
        updated_at=_FIXED_NOW,
    )

    cooldown = state.get_active_cooldown(
        "openrouter",
        "free-model",
        now=_FIXED_NOW,
    )
    assert cooldown is not None
    assert cooldown["reason"] == "rate_limit"
    assert cooldown["last_error_class"] == "rate_limit"
    assert state.is_model_available("openrouter", "free-model", now=_FIXED_NOW) is False
    assert state.is_model_available("openrouter", "other-model", now=_FIXED_NOW) is True


def test_expired_cooldown_is_ignored(tmp_path):
    state = _state(tmp_path)

    state.set_cooldown(
        provider="openrouter",
        model="free-model",
        cooldown_until=_FIXED_NOW - timedelta(seconds=1),
        reason="rate_limit",
        updated_at=_FIXED_NOW - timedelta(minutes=10),
    )

    assert state.get_active_cooldown("openrouter", "free-model", now=_FIXED_NOW) is None
    assert state.is_model_available("openrouter", "free-model", now=_FIXED_NOW) is True


def test_record_attempt_hashes_prompt_without_storing_raw_text(tmp_path):
    state = _state(tmp_path)
    raw_prompt = "please do not persist this raw prompt text"

    state.record_attempt(
        source="delegation",
        provider="openrouter",
        model="free-model",
        outcome="success",
        prompt=raw_prompt,
        created_at=_FIXED_NOW,
    )

    expected_hash = hashlib.sha256(raw_prompt.encode("utf-8")).hexdigest()
    with sqlite3.connect(state.db_path) as conn:
        row = conn.execute(
            "SELECT prompt_hash, source, provider, model, outcome FROM route_attempts"
        ).fetchone()
    assert row[0] == expected_hash
    assert raw_prompt not in "\n".join(str(value) for value in row if value is not None)

    raw_prompt_bytes = raw_prompt.encode("utf-8")
    for path in [
        state.db_path,
        state.db_path.with_name(state.db_path.name + "-wal"),
        state.db_path.with_name(state.db_path.name + "-shm"),
    ]:
        if path.exists():
            assert raw_prompt_bytes not in path.read_bytes()


def test_record_attempt_rejects_invalid_explicit_prompt_hash(tmp_path):
    state = _state(tmp_path)
    raw_prompt_disguised_as_hash = "this is raw prompt text, not a sha256 hex digest"

    try:
        state.record_attempt(
            source="delegation",
            provider="openrouter",
            model="free-model",
            outcome="success",
            prompt_hash=raw_prompt_disguised_as_hash,
            created_at=_FIXED_NOW,
        )
    except ValueError as exc:
        assert "prompt_hash" in str(exc)
    else:
        raise AssertionError("invalid prompt_hash should be rejected")

    with sqlite3.connect(state.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM route_attempts").fetchone()[0] == 0


def test_record_attempt_accepts_valid_explicit_prompt_hash(tmp_path):
    state = _state(tmp_path)
    explicit_hash = hashlib.sha256(b"already hashed elsewhere").hexdigest()

    state.record_attempt(
        source="delegation",
        provider="openrouter",
        model="free-model",
        outcome="success",
        prompt_hash=explicit_hash.upper(),
        created_at=_FIXED_NOW,
    )

    with sqlite3.connect(state.db_path) as conn:
        row = conn.execute("SELECT prompt_hash FROM route_attempts").fetchone()
    assert row[0] == explicit_hash


def test_cleanup_old_attempts_removes_only_old_attempts(tmp_path):
    state = _state(tmp_path)
    provider = "openrouter"
    model = "free-model"

    state.record_attempt(
        source="delegation",
        provider=provider,
        model=model,
        outcome="success",
        created_at=_FIXED_NOW - timedelta(days=2),
    )
    state.record_attempt(
        source="delegation",
        provider=provider,
        model=model,
        outcome="success",
        created_at=_FIXED_NOW - timedelta(hours=1),
    )

    deleted = state.cleanup_old_attempts(_FIXED_NOW - timedelta(days=1))

    assert deleted == 1
    assert state.count_attempts(provider, model, since=_FIXED_NOW - timedelta(days=3)) == 1
