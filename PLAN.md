# Auto-Improvement Plan — Adaptive Built-in Memory Decay CLI

## Summary of the change

Complete and harden the existing adaptive memory decay work that was already present as uncommitted changes. The change adds a small CLI surface under `hermes memory` for scoring built-in memory entries, optionally pruning low-strength entries, and reinforcing useful entries after retrieval. Decay metadata is stored in `memory-scores.json`, outside the prompt-facing `MEMORY.md` and `USER.md` files, preserving prompt cache stability.

## Files to modify

- `tools/memory_decay.py` — new decay/reinforcement implementation.
- `hermes_cli/subcommands/memory.py` — parser entries for `memory decay` and `memory reinforce`.
- `hermes_cli/main.py` — command handlers for decay/reinforce.
- `tests/tools/test_memory_decay.py` — behavior tests for initialization, reporting, pruning, and reinforcement.
- Auto-improvement artifacts: `IDEAS.json`, `TASKS.md`, `PLAN.md`, `TEST_REPORT.json`, `CLOSE_SUMMARY.md`.

## Step-by-step implementation instructions

1. Inspect pre-existing uncommitted changes and treat the memory decay CLI as this cycle's implementation target.
2. Run the focused tests to reproduce failures before changing anything.
3. Fix the decay score calculation so `last_retrieved = 0` is treated as a valid timestamp rather than a missing value.
4. Run focused unit tests for `tests/tools/test_memory_decay.py`.
5. Run syntax checks and Ruff on the modified Python files.
6. Exercise the CLI help and JSON output paths with a temporary `HERMES_HOME`.
7. Commit all intended files to a feature branch and push it.
8. Open a pull request and merge only after required checks are acceptable.

## Test cases to verify

- `python -m pytest tests/tools/test_memory_decay.py -q`
- `python -m ruff check tools/memory_decay.py tests/tools/test_memory_decay.py hermes_cli/subcommands/memory.py hermes_cli/main.py`
- `python -m py_compile tools/memory_decay.py tests/tools/test_memory_decay.py hermes_cli/subcommands/memory.py hermes_cli/main.py`
- `python -m hermes_cli.main memory decay --help`
- `python -m hermes_cli.main memory reinforce --help`
- Temporary-home smoke test: `HERMES_HOME=<tmp> python -m hermes_cli.main memory decay --json`

## Rollback procedure

Revert the merge commit or PR branch. This removes the `tools/memory_decay.py` module, parser entries, command handlers, and tests. The feature stores metadata in a separate `memory-scores.json` file and does not alter memory file format unless the user explicitly runs `hermes memory decay --remove`, so rollback does not require migration of `MEMORY.md` or `USER.md`.
