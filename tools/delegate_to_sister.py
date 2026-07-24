"""
delegate_to_sister — Thinnest possible wrapper that injects a sister's system
prompt into a delegate_task call.  This tool is intentionally kept outside
delegate_tool.py to avoid circular imports and to allow the sister registry
to evolve independently.

When the orchestrator (Astra) needs to route a subtask to a specific sister,
she calls this instead of raw delegate_task so the child agent boots with the
correct identity.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# ── Schema for the tool's own registration ──────────────────────────────────
DELEGATE_TO_SISTER_SCHEMA: Dict[str, Any] = {
    "name": "delegate_to_sister",
    "description": (
        "Delegate a task to a specific sister agent.  Loads the sister's "
        "system prompt from the registry and prepends it to the subagent "
        "context so the child boots with the correct identity.  Use this "
        "when Astra needs Luna for research, Ada for code review, Maya for "
        "builds, etc.  The sister_id is matched against canonical IDs (luna, "
        "ada, maya, nova, helena, larissa, clara, bia, vitoria, daine, novus) "
        "and legacy aliases (fofoqueiro→bia, vini→vitoria, etc.)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "sister_id": {
                "type": "string",
                "description": "Canonical sister ID (e.g., 'luna', 'ada', 'nova') or legacy alias.",
            },
            "goal": {
                "type": "string",
                "description": "The task goal for the sister subagent.",
            },
            "context": {
                "type": "string",
                "description": "Additional background — file paths, error messages, constraints.",
            },
        },
        "required": ["sister_id", "goal"],
    },
}


def delegate_to_sister(
    sister_id: str,
    goal: str,
    context: Optional[str] = None,
    _parent_agent=None,
) -> str:
    """Resolve the sister, inject her prompt, and delegate the task."""
    # Late imports to keep this module importable even when the agent
    # environment is not fully booted (e.g. during tool discovery).
    from hermes_cli.sister_registry import get_sister

    # 1) Resolve the sister identity
    sister = get_sister(sister_id)
    if sister is None:
        from tools.registry import tool_error
        return tool_error(
            f"Sister '{sister_id}' not found. Use `hermes sister list` to see "
            f"available sisters, or `hermes sister match '<task>'` to find "
            f"the best fit.",
            success=False,
        )

    # 2) Build the augmented context: sister identity + user context
    sister_prompt = sister.get("system_prompt", "")
    augmented_context_parts = []
    if sister_prompt:
        augmented_context_parts.append(
            f"[SISTER IDENTITY — You are {sister['name']} ({sister_id}), "
            f"{sister.get('role', 'specialist')}]"
        )
        augmented_context_parts.append(sister_prompt.strip())
    if context:
        augmented_context_parts.append(f"\n[USER CONTEXT]\n{context.strip()}")

    augmented_context = "\n\n".join(augmented_context_parts)

    # 3) Delegate via the existing delegate_task dispatcher
    from tools.delegate_tool import delegate_task
    return delegate_task(
        goal=goal,
        context=augmented_context,
        role="leaf",  # sisters are always leaf workers
        parent_agent=_parent_agent,
    )


def check_requirements() -> bool:
    """Always available — sister registry is a pure-Python module."""
    return True


# ── Registry ────────────────────────────────────────────────────────────────
from tools.registry import registry

registry.register(
    name="delegate_to_sister",
    toolset="delegation",
    schema=DELEGATE_TO_SISTER_SCHEMA,
    handler=lambda args, **kw: delegate_to_sister(
        sister_id=args.get("sister_id", ""),
        goal=args.get("goal", ""),
        context=args.get("context"),
        _parent_agent=kw.get("parent_agent"),
    ),
    check_fn=check_requirements,
    emoji="👯",
)