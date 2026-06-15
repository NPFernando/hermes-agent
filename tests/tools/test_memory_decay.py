"""Tests for adaptive built-in memory decay."""

from __future__ import annotations

import json

from tools.memory_decay import evaluate_decay, memory_key, reinforce_memory
from tools.memory_tool import ENTRY_DELIMITER


def _write_memories(hermes_home, *, memory_entries=(), user_entries=()):
    memories = hermes_home / "memories"
    memories.mkdir(parents=True, exist_ok=True)
    if memory_entries:
        (memories / "MEMORY.md").write_text(
            ENTRY_DELIMITER.join(memory_entries), encoding="utf-8"
        )
    if user_entries:
        (memories / "USER.md").write_text(
            ENTRY_DELIMITER.join(user_entries), encoding="utf-8"
        )
    return memories


def test_decay_initializes_scores_without_pruning(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    _write_memories(hermes_home, memory_entries=["stable fact"], user_entries=["user preference"])

    result = evaluate_decay(now=1_700_000_000, threshold=0.05)

    assert result["success"] is True
    assert result["total"] == 2
    assert result["forgotten_count"] == 0
    scores = json.loads((hermes_home / "memory-scores.json").read_text(encoding="utf-8"))
    assert memory_key("memory", "stable fact") in scores["entries"]
    assert memory_key("user", "user preference") in scores["entries"]


def test_decay_reports_forgotten_entry_from_existing_score(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    _write_memories(hermes_home, memory_entries=["stale fact"])
    key = memory_key("memory", "stale fact")
    (hermes_home / "memory-scores.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entries": {
                    key: {
                        "target": "memory",
                        "hash": key,
                        "created_at": 0,
                        "last_retrieved": 0,
                        "stability_days": 1,
                        "recall_count": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_decay(now=10 * 86400, threshold=0.05, remove=False)

    assert result["forgotten_count"] == 1
    assert result["pruned_count"] == 0
    assert (hermes_home / "memories" / "MEMORY.md").read_text(encoding="utf-8") == "stale fact"


def test_decay_remove_prunes_forgotten_entry(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    _write_memories(hermes_home, memory_entries=["stale fact", "fresh fact"])
    stale_key = memory_key("memory", "stale fact")
    fresh_key = memory_key("memory", "fresh fact")
    (hermes_home / "memory-scores.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entries": {
                    stale_key: {
                        "target": "memory",
                        "hash": stale_key,
                        "created_at": 0,
                        "last_retrieved": 0,
                        "stability_days": 1,
                        "recall_count": 0,
                    },
                    fresh_key: {
                        "target": "memory",
                        "hash": fresh_key,
                        "created_at": 10 * 86400,
                        "last_retrieved": 10 * 86400,
                        "stability_days": 30,
                        "recall_count": 0,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_decay(now=10 * 86400, threshold=0.05, remove=True)

    assert result["forgotten_count"] == 1
    assert result["pruned_count"] == 1
    assert (hermes_home / "memories" / "MEMORY.md").read_text(encoding="utf-8") == "fresh fact"


def test_reinforce_exact_memory_text_increases_stability(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    _write_memories(hermes_home, memory_entries=["useful fact"])

    result = reinforce_memory(memory_text="useful fact", now=1_700_000_000, increment_days=3)

    assert result["success"] is True
    assert result["recall_count"] == 1
    assert result["stability_days"] == 33.0
    assert result["strength"] == 1.0
