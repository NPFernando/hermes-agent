"""Tests for recently added CLI-only command behavior."""

from types import SimpleNamespace
from unittest.mock import Mock

from cli import HermesCLI


def test_cost_command_uses_existing_usage_and_does_not_fabricate_totals(monkeypatch):
    show_usage = Mock()
    cli_stub = SimpleNamespace(_show_usage=show_usage)
    printed = []
    monkeypatch.setattr("cli._cprint", lambda message, **kwargs: printed.append(str(message)))

    HermesCLI._handle_cost_command(cli_stub, "/cost 30")

    show_usage.assert_called_once_with()
    output = "\n".join(printed)
    assert "Historical cost ranges are not available" in output
    assert "$70 OpenRouter credits remaining" not in output
    assert "$0 spent this session" not in output


def test_project_command_formats_a_detected_project(monkeypatch):
    from hermes_cli import project_detect

    printed = []
    monkeypatch.setattr(project_detect, "detect_project", lambda path: {"name": "demo", "type": "node"})
    monkeypatch.setattr(project_detect, "format_project_summary", lambda project: "demo (node)")
    monkeypatch.setattr("cli._cprint", lambda message, **kwargs: printed.append(str(message)))

    HermesCLI._handle_project_command(SimpleNamespace(), "/project")

    assert "demo (node)" in "\n".join(printed)


def test_search_command_uses_message_search_from_current_session_db(monkeypatch):
    db = SimpleNamespace(
        search_messages=Mock(
            return_value=[
                {
                    "session_id": "12345678-abcd",
                    "role": "user",
                    "source": "cli",
                    "snippet": "found matching text",
                }
            ]
        )
    )
    printed = []
    monkeypatch.setattr("cli._cprint", lambda message, **kwargs: printed.append(str(message)))

    HermesCLI._handle_search_command(SimpleNamespace(_session_db=db), "/search matching text")

    db.search_messages.assert_called_once_with("matching text", limit=5)
    assert "found matching text" in "\n".join(printed)


def test_session_search_includes_full_text_message_matches(monkeypatch):
    db = SimpleNamespace(
        search_sessions=Mock(return_value=[]),
        search_messages=Mock(
            return_value=[
                {
                    "session_id": "abcdef0123456789",
                    "snippet": "the matching message body",
                }
            ]
        ),
    )
    printed = []
    monkeypatch.setattr("cli._cprint", lambda message, **kwargs: printed.append(str(message)))

    HermesCLI._handle_session_command(
        SimpleNamespace(_session_db=db), "/session search matching"
    )

    db.search_messages.assert_called_once_with("matching", limit=10)
    assert "the matching message body" in "\n".join(printed)


def test_git_commands_treat_user_path_as_pathspec_after_option_separator(monkeypatch):
    import subprocess

    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("cli._cprint", lambda message, **kwargs: None)

    HermesCLI._handle_diff_command(SimpleNamespace(), "/diff --output=/tmp/unexpected")
    HermesCLI._handle_blame_command(SimpleNamespace(), "/blame --reverse")
    HermesCLI._handle_git_status_command(SimpleNamespace(), "/git-status --porcelain=v1")

    assert calls[0] == ["git", "diff", "--", "--output=/tmp/unexpected"]
    assert calls[1] == ["git", "blame", "--date=short", "--", "--reverse"]
    assert calls[2] == ["git", "status", "--short", "--", "--porcelain=v1"]


def test_log_command_clamps_nonpositive_limit(monkeypatch):
    import subprocess

    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("cli._cprint", lambda message, **kwargs: None)

    HermesCLI._handle_log_command(SimpleNamespace(), "/log -10")

    assert calls[0][2] == "--max-count=1"


def test_plan_command_creates_unique_private_files_without_overwriting(monkeypatch, tmp_path):
    import os

    home = tmp_path / "home"
    monkeypatch.setattr("cli.os.path.expanduser", lambda value: str(home) if value == "~" else value)
    monkeypatch.setattr("cli.time.strftime", lambda _fmt: "20260913-020000")
    monkeypatch.setattr("cli._cprint", lambda message, **kwargs: None)

    HermesCLI._handle_plan_command(SimpleNamespace(), "/plan first secret goal")
    HermesCLI._handle_plan_command(SimpleNamespace(), "/plan second secret goal")

    plans = sorted((home / ".hermes" / "plans").glob("plan-*.md"))
    assert len(plans) == 2
    contents = {plan.read_text(encoding="utf-8") for plan in plans}
    assert any("first secret goal" in content for content in contents)
    assert any("second secret goal" in content for content in contents)
    if os.name == "posix":
        assert all(plan.stat().st_mode & 0o077 == 0 for plan in plans)


def test_check_command_never_runs_npx_when_local_typescript_is_missing(monkeypatch, tmp_path):
    import subprocess

    project = tmp_path / "project"
    project.mkdir()
    (project / "package.json").write_text("{}", encoding="utf-8")
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    printed = []
    monkeypatch.setattr("cli._cprint", lambda message, **kwargs: printed.append(str(message)))

    HermesCLI._handle_check_command(SimpleNamespace(), f"/check {project}")

    run.assert_not_called()
    assert "local TypeScript is not installed" in "\n".join(printed)


def test_check_command_uses_only_local_typescript(monkeypatch, tmp_path):
    import subprocess

    project = tmp_path / "project"
    tsc = project / "node_modules" / "typescript" / "bin" / "tsc"
    tsc.parent.mkdir(parents=True)
    tsc.write_text("", encoding="utf-8")
    (project / "package.json").write_text("{}", encoding="utf-8")
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("cli._cprint", lambda message, **kwargs: None)

    HermesCLI._handle_check_command(SimpleNamespace(), f"/check {project}")

    assert run.call_args.args[0] == ["node", str(tsc), "--noEmit"]
