"""SQLite state store for HARP adaptive routing.

This module is intentionally standalone and is not wired into runtime routing yet.
It stores only local routing metadata such as quota-window attempts, cooldowns,
and aggregate-safe prompt hashes. Raw prompt text and provider credentials must
never be persisted here.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
import sqlite3
from typing import Any

from hermes_constants import get_hermes_home


DEFAULT_DB_RELATIVE_PATH = Path("adaptive-routing") / "state.db"
_PROMPT_HASH_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS route_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    classification TEXT,
    reasoning_effort TEXT,
    outcome TEXT NOT NULL,
    error_class TEXT,
    prompt_hash TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    duration_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_route_attempts_provider_model_created_at
ON route_attempts(provider, model, created_at);

CREATE INDEX IF NOT EXISTS idx_route_attempts_created_at
ON route_attempts(created_at);

CREATE TABLE IF NOT EXISTS route_cooldowns (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    cooldown_until TEXT NOT NULL,
    reason TEXT NOT NULL,
    last_error_class TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (provider, model)
);

CREATE INDEX IF NOT EXISTS idx_route_cooldowns_until
ON route_cooldowns(cooldown_until);
"""


def _to_utc_datetime(value: datetime | str | None = None) -> datetime:
    """Normalize a datetime-ish value to a timezone-aware UTC datetime."""
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    else:
        raise TypeError(f"expected datetime, ISO string, or None; got {type(value)!r}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_utc_iso(value: datetime | str | None = None) -> str:
    return _to_utc_datetime(value).isoformat(timespec="microseconds")


def _prompt_hash(prompt: str | None, prompt_hash: str | None) -> str | None:
    if prompt_hash is not None:
        value = prompt_hash.strip()
        if not _PROMPT_HASH_RE.fullmatch(value):
            raise ValueError("prompt_hash must be a 64-character SHA-256 hex digest")
        return value.lower()
    if prompt is None:
        return None
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _apply_wal_if_safe(conn: sqlite3.Connection) -> str | None:
    """Enable WAL mode when SQLite and the filesystem allow it.

    SQLite can reject WAL on network or FUSE-like filesystems. Adaptive routing
    state should remain usable there, so WAL activation failures are tolerated
    and SQLite keeps its default journal mode.
    """
    try:
        row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    return str(row[0]).strip().lower()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


class AdaptiveRoutingState:
    """Small SQLite-backed store for adaptive routing attempts and cooldowns."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = (
            Path(db_path) if db_path is not None else get_hermes_home() / DEFAULT_DB_RELATIVE_PATH
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with closing(self._connect()) as conn:
            if _apply_wal_if_safe(conn) == "wal":
                conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA_SQL)
            conn.commit()

    def record_attempt(
        self,
        source: str,
        provider: str,
        model: str,
        outcome: str,
        classification: str | None = None,
        reasoning_effort: str | None = None,
        error_class: str | None = None,
        prompt: str | None = None,
        prompt_hash: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        duration_ms: int | None = None,
        created_at: datetime | str | None = None,
    ) -> int:
        """Record one routing attempt and return its row id.

        ``prompt`` is accepted only so callers can request a hash. It is never
        written to SQLite; only ``prompt_hash`` (explicit or SHA-256 derived) is
        stored.
        """
        created_at_iso = _to_utc_iso(created_at)
        safe_prompt_hash = _prompt_hash(prompt, prompt_hash)
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO route_attempts (
                    created_at,
                    source,
                    provider,
                    model,
                    classification,
                    reasoning_effort,
                    outcome,
                    error_class,
                    prompt_hash,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at_iso,
                    source,
                    provider,
                    model,
                    classification,
                    reasoning_effort,
                    outcome,
                    error_class,
                    safe_prompt_hash,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    duration_ms,
                ),
            )
            conn.commit()
            if cursor.lastrowid is None:
                raise sqlite3.DatabaseError("route_attempt insert did not return a row id")
            return cursor.lastrowid

    def set_cooldown(
        self,
        provider: str,
        model: str,
        cooldown_until: datetime | str,
        reason: str,
        last_error_class: str | None = None,
        updated_at: datetime | str | None = None,
    ) -> None:
        cooldown_until_iso = _to_utc_iso(cooldown_until)
        updated_at_iso = _to_utc_iso(updated_at)
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO route_cooldowns (
                    provider,
                    model,
                    cooldown_until,
                    reason,
                    last_error_class,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, model) DO UPDATE SET
                    cooldown_until = excluded.cooldown_until,
                    reason = excluded.reason,
                    last_error_class = excluded.last_error_class,
                    updated_at = excluded.updated_at
                """,
                (
                    provider,
                    model,
                    cooldown_until_iso,
                    reason,
                    last_error_class,
                    updated_at_iso,
                ),
            )
            conn.commit()

    def get_active_cooldown(
        self,
        provider: str,
        model: str,
        now: datetime | str | None = None,
    ) -> dict[str, Any] | None:
        now_iso = _to_utc_iso(now)
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT provider, model, cooldown_until, reason, last_error_class, updated_at
                FROM route_cooldowns
                WHERE provider = ? AND model = ? AND cooldown_until > ?
                """,
                (provider, model, now_iso),
            ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)

    def is_model_available(
        self,
        provider: str,
        model: str,
        now: datetime | str | None = None,
    ) -> bool:
        return self.get_active_cooldown(provider, model, now=now) is None

    def count_attempts(
        self,
        provider: str,
        model: str,
        since: datetime | str,
        outcome: str | None = None,
    ) -> int:
        since_iso = _to_utc_iso(since)
        sql = """
            SELECT COUNT(*)
            FROM route_attempts
            WHERE provider = ? AND model = ? AND created_at >= ?
        """
        params: list[Any] = [provider, model, since_iso]
        if outcome is not None:
            sql += " AND outcome = ?"
            params.append(outcome)

        with closing(self._connect()) as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row[0]) if row is not None else 0

    def get_recent_attempt_counts(
        self,
        provider: str,
        model: str,
        now: datetime | str | None = None,
    ) -> dict[str, int]:
        now_dt = _to_utc_datetime(now)
        return {
            "rpm": self.count_attempts(provider, model, since=now_dt - timedelta(minutes=1)),
            "rpd": self.count_attempts(provider, model, since=now_dt - timedelta(days=1)),
        }

    def cleanup_old_attempts(self, older_than: datetime | str) -> int:
        """Delete route attempts older than ``older_than`` and return rows removed."""
        older_than_iso = _to_utc_iso(older_than)
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                "DELETE FROM route_attempts WHERE created_at < ?",
                (older_than_iso,),
            )
            conn.commit()
            return max(cursor.rowcount, 0)


__all__ = ["AdaptiveRoutingState", "DEFAULT_DB_RELATIVE_PATH"]
