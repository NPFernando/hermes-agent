"""``hermes memory`` subcommand parser.

Extracted from ``hermes_cli/main.py:main()`` (god-file Phase 2 follow-up).
Handler injected to avoid importing ``main``.
"""

from __future__ import annotations

from typing import Callable


def build_memory_parser(subparsers, *, cmd_memory: Callable) -> None:
    """Attach the ``memory`` subcommand to ``subparsers``."""
    memory_parser = subparsers.add_parser(
        "memory",
        help="Configure external memory provider",
        description=(
            "Set up and manage external memory provider plugins.\n\n"
            "Available providers: honcho, openviking, mem0, hindsight,\n"
            "holographic, retaindb, byterover.\n\n"
            "Only one external provider can be active at a time.\n"
            "Built-in memory (MEMORY.md/USER.md) is always active."
        ),
    )
    memory_sub = memory_parser.add_subparsers(dest="memory_command")
    _setup_parser = memory_sub.add_parser(
        "setup", help="Interactive provider selection and configuration"
    )
    _setup_parser.add_argument(
        "provider",
        nargs="?",
        default=None,
        help="Provider to configure directly (e.g. honcho), skipping the picker",
    )
    memory_sub.add_parser("status", help="Show current memory provider config")
    memory_sub.add_parser("off", help="Disable external provider (built-in only)")

    _decay_parser = memory_sub.add_parser(
        "decay",
        help="Score built-in memory entries and optionally prune low-strength entries",
    )
    _decay_parser.add_argument(
        "--threshold",
        type=float,
        default=0.05,
        help="Strength below which entries are considered forgotten (default: 0.05)",
    )
    _decay_parser.add_argument(
        "--target",
        choices=["all", "memory", "user"],
        default="all",
        help="Which built-in memory store to evaluate",
    )
    _decay_parser.add_argument(
        "--remove",
        action="store_true",
        help="Actually remove forgotten entries; without this, only report them",
    )
    _decay_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full result as JSON for cron/watchdog use",
    )

    _reinforce_parser = memory_sub.add_parser(
        "reinforce",
        help="Reinforce a built-in memory entry after retrieval",
    )
    reinforce_group = _reinforce_parser.add_mutually_exclusive_group(required=True)
    reinforce_group.add_argument("--memory-text", help="Exact memory entry text to reinforce")
    reinforce_group.add_argument("--memory-hash", help="SHA256 hash from memory decay output")
    _reinforce_parser.add_argument(
        "--target",
        choices=["all", "memory", "user"],
        default="all",
        help="Which built-in memory store to search",
    )
    _reinforce_parser.add_argument(
        "--increment-days",
        type=float,
        default=7.0,
        help="Days to add to entry stability on reinforcement (default: 7)",
    )

    _reset_parser = memory_sub.add_parser(
        "reset",
        help="Erase all built-in memory (MEMORY.md and USER.md)",
    )
    _reset_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    _reset_parser.add_argument(
        "--target",
        choices=["all", "memory", "user"],
        default="all",
        help="Which store to reset: 'all' (default), 'memory', or 'user'",
    )
    memory_parser.set_defaults(func=cmd_memory)
