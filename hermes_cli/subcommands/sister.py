"""
``hermes sister`` subcommand parser.

Commands:
  hermes sister list              — List all registered sisters
  hermes sister show <id>         — Show detailed sister profile
  hermes sister match <query>     — Find best sister for a task
"""
from __future__ import annotations

from typing import Callable, Optional


def _cmd_sister_list(args) -> int:  # noqa: ANN001
    """List all sisters in a table."""
    from hermes_cli.sister_registry import list_sisters

    sisters = list_sisters(include_disabled=getattr(args, "all", False))

    if not sisters:
        print("No sisters registered.")
        print("Run 'hermes sister init' to scaffold the sister system, or")
        print("add profiles to ~/.hermes/profiles/<id>/config.yaml with sister_id set.")
        return 0

    # Table header
    print(f"{'Emoji':<6} {'ID':<12} {'Name':<12} {'Role'}")
    print(f"{'─'*5:<6} {'─'*11:<12} {'─'*11:<12} {'─'*40}")

    for s in sisters:
        emoji = s.get("emoji", "🤖")
        sid = s["id"]
        name = s.get("name", sid.title())
        role = s.get("role", "unknown")
        # Truncate long roles
        if len(role) > 40:
            role = role[:37] + "..."
        print(f"{emoji:<6} {sid:<12} {name:<12} {role}")

    print(f"\n{len(sisters)} sister(s) registered.")
    return 0


def _cmd_sister_show(args) -> int:  # noqa: ANN001
    """Show detailed information for a specific sister."""
    from hermes_cli.sister_registry import get_sister

    sister_id = getattr(args, "sister_id", "")
    sister = get_sister(sister_id)

    if not sister:
        print(f"Sister '{sister_id}' not found.")
        print("Available sisters:")
        from hermes_cli.sister_registry import list_sisters
        for s in list_sisters():
            print(f"  {s['emoji']} {s['id']}")
        return 1

    # Rich profile output
    print(f"\n  {sister['emoji']}  {sister['name']}  ({sister['id']})")
    print(f"  {'─' * 50}")
    print(f"  Role:        {sister.get('role', 'unknown')}")
    print(f"  Enabled:     {sister.get('enabled', True)}")
    print(f"  Source:      {sister.get('source', 'unknown')}")
    print(f"  Description: {sister.get('description', 'N/A')}")

    prompt = sister.get("system_prompt", "")
    if prompt:
        # Show first 500 chars of system prompt
        preview = prompt[:500].strip()
        if len(prompt) > 500:
            preview += "\n  ... (truncated)"
        print(f"\n  System Prompt ({len(prompt)} chars):")
        for line in preview.splitlines():
            print(f"  │ {line}")

    return 0


def _cmd_sister_match(args) -> int:  # noqa: ANN001
    """Find the best sister for a given task query."""
    from hermes_cli.sister_registry import match_sister

    query = getattr(args, "query", "")
    if not query:
        print("Please provide a task description to match.")
        print("Example: hermes sister match 'debug a Python memory leak'")
        return 1

    top_n = getattr(args, "top", 3)
    matches = match_sister(query, top_n=top_n)

    if not matches:
        print(f"No sister matched for: \"{query}\"")
        print("Try a more specific query with keywords about the task domain.")
        return 0

    print(f"\n  Best match(es) for: \"{query}\"\n")
    print(f"  {'Rank':<6} {'Emoji':<6} {'Sister':<12} {'Role':<25} {'Score':<8} {'Keywords'}")
    print(f"  {'─'*4:<6} {'─'*5:<6} {'─'*11:<12} {'─'*24:<25} {'─'*7:<8} {'─'*30}")

    for rank, m in enumerate(matches, 1):
        keywords = ", ".join(m.get("matched_keywords", []))
        if len(keywords) > 30:
            keywords = keywords[:27] + "..."
        print(f"  #{rank:<5} {m['emoji']:<6} {m['id']:<12} {m['role'][:25]:<25} {m.get('match_score', 0):<8} {keywords}")

    return 0


def build_sister_parser(subparsers, *, cmd_sister: Optional[Callable] = None) -> None:
    """Attach the ``sister`` subcommand (and its sub-actions) to ``subparsers``."""
    sister_parser = subparsers.add_parser(
        "sister",
        help="Sister agent management",
        description="List, inspect, and match sister AI agents for delegation",
    )
    sister_subparsers = sister_parser.add_subparsers(dest="sister_command")

    # sister list
    sister_list = sister_subparsers.add_parser("list", help="List all registered sisters")
    sister_list.add_argument("--all", action="store_true", help="Include disabled sisters")
    sister_list.set_defaults(func=_cmd_sister_list)

    # sister show <id>
    sister_show = sister_subparsers.add_parser("show", help="Show detailed sister profile")
    sister_show.add_argument("sister_id", help="Sister ID (e.g., luna, ada, nova)")
    sister_show.set_defaults(func=_cmd_sister_show)

    # sister match <query>
    sister_match = sister_subparsers.add_parser(
        "match", help="Find best sister for a task"
    )
    sister_match.add_argument("query", help="Task description to match against sister domains")
    sister_match.add_argument(
        "--top", type=int, default=3,
        help="Number of top matches to show (default: 3)",
    )
    sister_match.set_defaults(func=_cmd_sister_match)

    # Fallback: if no subcommand given, show help
    sister_parser.set_defaults(func=lambda args: (sister_parser.print_help(), 0)[1])