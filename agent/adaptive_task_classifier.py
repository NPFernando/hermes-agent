"""Heuristic task classifier for HARP adaptive routing.

This module is deliberately standalone and side-effect free. It performs a small
set of conservative string/regex checks so future routing code can classify a
prompt without making an additional model call.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Pattern, Sequence


@dataclass(frozen=True, slots=True)
class TaskClassification:
    """Result returned by :func:`classify_task`.

    The raw prompt and context are intentionally not stored on this dataclass so
    accidental repr/log output remains generic.
    """

    classification: str
    risk: str
    matched_signals: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class _SignalRule:
    signal: str
    pattern: Pattern[str]


def _rule(signal: str, pattern: str) -> _SignalRule:
    return _SignalRule(signal=signal, pattern=re.compile(pattern, re.IGNORECASE))


_HIGH_RISK_RULES: tuple[_SignalRule, ...] = (
    _rule("high_risk:token", r"\btokens?\b"),
    _rule("high_risk:secret", r"\bsecrets?\b"),
    _rule("high_risk:credential", r"\bcredentials?\b"),
    _rule("high_risk:api_key", r"\bapi[-_\s]+keys?\b"),
    _rule("high_risk:access_key", r"\baccess[-_\s]+keys?\b"),
    _rule("high_risk:private_key", r"\bprivate[-_\s]+keys?\b"),
    _rule("high_risk:env_file", r'(?:^|[\s`\'"/\\~])\.env(?:[\s`\'".,/\\]|$)|\benv\s+files?\b'),
    _rule("high_risk:password", r"\b(?:passwords?|passwd)\b"),
    _rule("high_risk:auth", r"\bauth(?:entication|orization)?\b"),
    _rule("high_risk:oauth", r"\boauth\b"),
    _rule("high_risk:ssh_key", r"\bssh[-_\s]+keys?\b"),
    _rule("high_risk:production", r"\bproduction\b"),
    _rule("high_risk:client", r"\bclients?\b"),
    _rule("high_risk:firewall", r"\bfirewalls?\b"),
    _rule("high_risk:dns", r"\bdns\b"),
    _rule("high_risk:ssl", r"\bssl\b"),
    _rule("high_risk:database_migration", r"\b(?:database|db)\s+migrations?\b"),
    _rule("high_risk:destructive", r"\b(?:destructive|destroy)\b"),
    _rule("high_risk:delete", r"\bdelet(?:e|es|ed|ing)\b"),
    _rule("high_risk:reset_hard", r"\breset\s+(?:--)?hard\b|\bgit\s+reset\s+--hard\b"),
)

_COMPLEX_RULES: tuple[_SignalRule, ...] = (
    _rule("complex:traceback", r"\btraceback\b"),
    _rule(
        "complex:failing_tests",
        r"\bfailing\s+tests?\b|\bfailed\s+tests?\b|\btests?\s+fail(?:ed|ing|ure|ures|s)?\b",
    ),
    _rule("complex:multi_file", r"\bmulti(?:ple)?[-_\s]+files?\b"),
    _rule("complex:architecture", r"\barchitect(?:ure|ural)?\b"),
    _rule("complex:race_condition", r"\brace\s+conditions?\b"),
    _rule("complex:pr_review", r"\bpr\s+review\b|\bpull\s+request\s+review\b"),
    _rule("complex:root_cause", r"\broot\s+cause\b"),
)

_SIMPLE_RULES: tuple[_SignalRule, ...] = (
    _rule("simple:summarize", r"\bsummari(?:ze|se|zed|sed|zing|sing)\b|\bsummary\b"),
    _rule("simple:rewrite", r"\brewrite\b|\brewritten\b|\breword\b|\bparaphrase\b"),
    _rule("simple:explain", r"\bexplain(?:s|ed|ing)?\b"),
    _rule("simple:format", r"\bformat(?:s|ted|ting)?\b"),
    _rule("simple:grammar", r"\bgrammar\b|\bgrammatical\b"),
    _rule("simple:short_answer", r"\bshort\s+answer\b|\bbrief\s+answer\b|\bconcise\s+answer\b"),
)

_TOOL_RULES: tuple[_SignalRule, ...] = (
    _rule(
        "tool:file_read",
        r"\b(?:read|inspect|check|open|view|review|look\s+at)\b"
        r"[^\n]*\b(?:[\w.-]+\.(?:md|py|js|ts|tsx|jsx|json|ya?ml|toml|ini|cfg|txt|sh|ps1)|readme|files?|docs?|config|code)\b",
    ),
    _rule("tool:explicit_tool_use", r"\buse\b[^\n.]{0,40}\btools?\b|\bwith\s+(?:a\s+)?tools?\b"),
    _rule(
        "tool:file_modification",
        r"\b(?:modify|modifying|modification|edit|editing|update|updating|change|changing|write|writing|create|creating|patch|patching|fix|fixing|rewrite|format)\b"
        r"[^\n]*\b(?:files?|docs?|readme|config|code|workflow)\b"
        r"|\bfiles?\s+modification\b",
    ),
    _rule("tool:git", r"\bgit\b"),
    _rule("tool:docker", r"\bdocker\b|\bdockerfile\b"),
    _rule(
        "tool:ci_cd",
        r"\bci\s*/\s*cd\b|\bcicd\b|\bci\b|\bcd\b|\bgithub\s+actions\b|\bworkflow\b|\bpipeline\b",
    ),
)

_RISK_BY_CLASSIFICATION = {
    "trivial": "low",
    "simple": "low",
    "standard": "medium",
    "complex": "medium",
    "high_risk": "high",
    "unknown": "unknown",
}

_REASON_BY_CLASSIFICATION = {
    "simple": "Simple heuristic signal matched.",
    "standard": "Tool or file heuristic signal matched.",
    "complex": "Complex heuristic signal matched.",
    "high_risk": "High-risk heuristic signal matched.",
    "unknown": "No recognized heuristic signals.",
}


def _matched_signals(rules: Iterable[_SignalRule], text: str) -> tuple[str, ...]:
    return tuple(rule.signal for rule in rules if rule.pattern.search(text))


def _clean_toolsets(toolsets: Sequence[str] | None) -> tuple[str, ...]:
    if not toolsets:
        return ()
    return tuple(str(toolset).strip() for toolset in toolsets if str(toolset).strip())


def _append_unique(signals: list[str], signal: str) -> None:
    if signal not in signals:
        signals.append(signal)


def _tool_signals(
    text: str,
    *,
    toolsets: Sequence[str] | None,
    has_files: bool,
    needs_tools: bool,
) -> tuple[str, ...]:
    signals: list[str] = []
    if has_files:
        signals.append("tool:file_context")
    if needs_tools:
        signals.append("tool:needs_tools")

    cleaned_toolsets = _clean_toolsets(toolsets)
    tool_text = " ".join(cleaned_toolsets)
    searchable = f"{text}\n{tool_text}" if tool_text else text
    for signal in _matched_signals(_TOOL_RULES, searchable):
        _append_unique(signals, signal)
    return tuple(signals)


def _classification_result(classification: str, matched_signals: tuple[str, ...]) -> TaskClassification:
    return TaskClassification(
        classification=classification,
        risk=_RISK_BY_CLASSIFICATION[classification],
        matched_signals=matched_signals,
        reason=_REASON_BY_CLASSIFICATION[classification],
    )


def classify_task(
    prompt: str,
    context_preview: str = "",
    *,
    toolsets: list[str] | None = None,
    has_files: bool = False,
    needs_tools: bool = False,
) -> TaskClassification:
    """Classify a task using deterministic heuristic signals.

    Conservative precedence is enforced as:
    ``high_risk`` > ``complex`` > ``standard`` > ``simple`` > ``unknown``.
    Empty prompts are always ``unknown`` even when optional context is present.
    """
    prompt_text = "" if prompt is None else str(prompt)
    if not prompt_text.strip():
        return _classification_result("unknown", ())

    context_text = "" if context_preview is None else str(context_preview)
    searchable = f"{prompt_text}\n{context_text}" if context_text else prompt_text

    high_risk_signals = _matched_signals(_HIGH_RISK_RULES, searchable)
    complex_signals = _matched_signals(_COMPLEX_RULES, searchable)
    simple_signals = _matched_signals(_SIMPLE_RULES, searchable)
    tool_matches = _tool_signals(
        searchable,
        toolsets=toolsets,
        has_files=has_files,
        needs_tools=needs_tools,
    )
    matched_signals = high_risk_signals + complex_signals + simple_signals + tool_matches

    if high_risk_signals:
        return _classification_result("high_risk", matched_signals)
    if complex_signals:
        return _classification_result("complex", matched_signals)
    if tool_matches:
        return _classification_result("standard", matched_signals)
    if simple_signals:
        return _classification_result("simple", matched_signals)
    return _classification_result("unknown", ())


__all__ = ["TaskClassification", "classify_task"]
