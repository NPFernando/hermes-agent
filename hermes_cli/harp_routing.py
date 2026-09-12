"""Universal HARP selector integration for gateway runtime resolution."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from hermes_cli.config import load_config


@dataclass(frozen=True)
class HarpRouteDecision:
    provider: str
    model: str


_MODEL_RE = re.compile(r"^\s*MODEL\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
_PROVIDER_RE = re.compile(r"^\s*PROVIDER\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)


def _selector_candidates(configured: str) -> list[str]:
    candidates: list[str] = []
    if configured.strip():
        candidates.append(configured.strip())
    env_path = (os.getenv("UNIVERSAL_HARP_SELECTOR_SCRIPT", "") or "").strip()
    if env_path:
        candidates.append(env_path)
    candidates.extend(
        [
            "/home/ubuntu/workspace/projects/universal-harp-engine/scripts/harp-select-route.py",
            "/srv/projects/projects/universal-harp-engine/scripts/harp-select-route.py",
        ]
    )
    return candidates


def _resolve_selector_path(configured: str) -> Optional[Path]:
    if configured.strip():
        path = Path(configured.strip()).expanduser()
        return path if path.is_file() else None
    for candidate in _selector_candidates(configured):
        path = Path(candidate).expanduser()
        if path.is_file():
            return path
    return None


def _parse_selector_output(output: str) -> Optional[HarpRouteDecision]:
    provider = ""
    model = ""
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = _PROVIDER_RE.match(line)
        if m:
            provider = m.group("value").strip()
            continue
        m = _MODEL_RE.match(line)
        if m:
            model = m.group("value").strip()
            continue
    if not provider or not model:
        return None
    return HarpRouteDecision(provider=provider, model=model)


def resolve_harp_route_decision() -> Optional[HarpRouteDecision]:
    """Return a route decision when HARP routing is enabled and successful.

    Fail-open behavior: any config issue, missing selector, timeout, non-zero
    exit, or parse failure returns None.
    """
    config = load_config()
    section = config.get("harp_routing")
    if not isinstance(section, dict) or not bool(section.get("enabled")):
        return None

    selector_path = _resolve_selector_path(str(section.get("selector_script") or ""))
    if selector_path is None:
        return None

    task = str(section.get("task") or "code_generation")
    risk = str(section.get("risk") or "standard")
    timeout = int(section.get("timeout_seconds") or 5)
    if timeout < 1:
        timeout = 1

    try:
        result = subprocess.run(
            ["python3", str(selector_path), "--task", task, "--risk", risk],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    output = "\n".join(
        part for part in [result.stdout or "", result.stderr or ""] if part
    )
    return _parse_selector_output(output)
