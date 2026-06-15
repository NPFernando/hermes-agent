"""Adaptive decay for built-in Hermes memory files.

This module keeps decay metadata outside MEMORY.md/USER.md so the prompt
snapshot format stays stable. Scores use an Ebbinghaus-style curve:

    strength = exp(-age_days / stability_days)

Recall/reinforcement increases stability; periodic decay can report or prune
entries whose strength falls below a threshold.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from hermes_constants import get_hermes_home
from tools.memory_tool import MemoryStore
from utils import atomic_replace

DEFAULT_STABILITY_DAYS = 30.0
DEFAULT_REINFORCE_DAYS = 7.0
DEFAULT_THRESHOLD = 0.05
SCORES_FILENAME = "memory-scores.json"


@dataclass(frozen=True)
class MemoryEntry:
    target: str
    text: str

    @property
    def key(self) -> str:
        return memory_key(self.target, self.text)


def memory_key(target: str, text: str) -> str:
    """Return a stable id for a memory entry scoped by target store."""
    payload = f"{target}\0{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def scores_path() -> Path:
    return get_hermes_home() / SCORES_FILENAME


def load_scores(path: Optional[Path] = None) -> Dict[str, Any]:
    path = path or scores_path()
    if not path.exists():
        return {"version": 1, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "entries": {}}
    if not isinstance(data, dict):
        return {"version": 1, "entries": {}}
    entries = data.get("entries")
    if not isinstance(entries, dict):
        data["entries"] = {}
    data.setdefault("version", 1)
    return data


def save_scores(data: Dict[str, Any], path: Optional[Path] = None) -> None:
    path = path or scores_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    atomic_replace(tmp, path)


def iter_memory_entries(store: MemoryStore, target: str = "all") -> List[MemoryEntry]:
    if target not in {"all", "memory", "user"}:
        raise ValueError("target must be one of: all, memory, user")
    targets = ["memory", "user"] if target == "all" else [target]
    entries: List[MemoryEntry] = []
    for name in targets:
        for text in store._read_file(store._path_for(name)):
            entries.append(MemoryEntry(name, text))
    return entries


def strength(last_retrieved: float, stability_days: float, now: Optional[float] = None) -> float:
    now = time.time() if now is None else now
    stability_days = max(float(stability_days or DEFAULT_STABILITY_DAYS), 0.001)
    # Unix epoch (0) is a valid timestamp for tests and imported metadata; do
    # not treat it as missing or old entries will be refreshed to full strength.
    retrieved_at = now if last_retrieved is None else float(last_retrieved)
    age_days = max(0.0, (now - retrieved_at) / 86400.0)
    return math.exp(-(age_days / stability_days))


def _record_for(entry: MemoryEntry, now: float, existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    record = dict(existing or {})
    record.setdefault("target", entry.target)
    record.setdefault("hash", entry.key)
    record.setdefault("created_at", now)
    record.setdefault("last_retrieved", now)
    record.setdefault("stability_days", DEFAULT_STABILITY_DAYS)
    record.setdefault("recall_count", 0)
    record["text_preview"] = entry.text[:120]
    record["strength"] = strength(record["last_retrieved"], record["stability_days"], now)
    return record


def evaluate_decay(
    *,
    store: Optional[MemoryStore] = None,
    target: str = "all",
    threshold: float = DEFAULT_THRESHOLD,
    remove: bool = False,
    now: Optional[float] = None,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Score current memory entries and optionally prune low-strength ones.

    New entries are initialized at full strength. Only entries already tracked
    in the score database can decay below the threshold on later runs.
    """
    now = time.time() if now is None else now
    store = store or MemoryStore()
    data = load_scores(path)
    scores: Dict[str, Any] = data.setdefault("entries", {})

    entries = iter_memory_entries(store, target)
    current_by_key = {entry.key: entry for entry in entries}

    forgotten: List[Dict[str, Any]] = []
    kept: List[Dict[str, Any]] = []
    for entry in entries:
        record = _record_for(entry, now, scores.get(entry.key))
        scores[entry.key] = record
        item = {
            "target": entry.target,
            "hash": entry.key,
            "strength": record["strength"],
            "stability_days": record["stability_days"],
            "recall_count": record["recall_count"],
            "text_preview": record["text_preview"],
        }
        if record["strength"] < threshold:
            forgotten.append(item)
        else:
            kept.append(item)

    # Drop metadata for entries no longer present in the memory files.
    for key in list(scores.keys()):
        if key not in current_by_key:
            scores.pop(key, None)

    pruned = 0
    if remove and forgotten:
        forgotten_keys = {item["hash"] for item in forgotten}
        targets = {item["target"] for item in forgotten}
        for name in targets:
            path_for_target = store._path_for(name)
            with store._file_lock(path_for_target):
                current = store._read_file(path_for_target)
                filtered = [text for text in current if memory_key(name, text) not in forgotten_keys]
                pruned += len(current) - len(filtered)
                store._write_file(path_for_target, filtered)
        for key in forgotten_keys:
            scores.pop(key, None)

    data["last_decay_at"] = now
    save_scores(data, path)

    return {
        "success": True,
        "target": target,
        "threshold": threshold,
        "remove": remove,
        "total": len(entries),
        "kept_count": len(kept),
        "forgotten_count": len(forgotten),
        "pruned_count": pruned,
        "forgotten": forgotten,
    }


def reinforce_memory(
    *,
    memory_text: Optional[str] = None,
    memory_hash: Optional[str] = None,
    target: str = "all",
    increment_days: float = DEFAULT_REINFORCE_DAYS,
    now: Optional[float] = None,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Reinforce one current memory entry by exact text or hash."""
    if not memory_text and not memory_hash:
        return {"success": False, "error": "Provide memory_text or memory_hash."}
    now = time.time() if now is None else now
    store = MemoryStore()
    entries = iter_memory_entries(store, target)
    matches = [
        entry for entry in entries
        if (memory_hash and entry.key == memory_hash) or (memory_text and entry.text == memory_text)
    ]
    if not matches:
        return {"success": False, "error": "No current memory entry matched."}
    if len(matches) > 1:
        return {"success": False, "error": "Multiple entries matched; specify memory_hash."}

    entry = matches[0]
    data = load_scores(path)
    scores: Dict[str, Any] = data.setdefault("entries", {})
    record = _record_for(entry, now, scores.get(entry.key))
    record["last_retrieved"] = now
    record["stability_days"] = float(record.get("stability_days", DEFAULT_STABILITY_DAYS)) + float(increment_days)
    record["recall_count"] = int(record.get("recall_count", 0)) + 1
    record["strength"] = 1.0
    scores[entry.key] = record
    data["last_reinforced_at"] = now
    save_scores(data, path)
    return {
        "success": True,
        "target": entry.target,
        "hash": entry.key,
        "stability_days": record["stability_days"],
        "recall_count": record["recall_count"],
        "strength": record["strength"],
    }
