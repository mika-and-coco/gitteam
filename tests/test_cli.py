from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gitteam.cli import app

runner = CliRunner()


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("GITTEAM_CONFIG", raising=False)
    project = tmp_path / "demo"
    project.mkdir()
    _git(project, "init", "-b", "main")
    _git(project, "config", "user.email", "t@example.com")
    _git(project, "config", "user.name", "Tester")
    _git(project, "config", "commit.gpgsign", "false")
    (project / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "chore: initial commit")
    monkeypatch.chdir(project)
    return project


def test_help_and_version():
    assert runner.invoke(app, ["--help"]).exit_code == 0
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0 and "gitteam" in result.stdout


def test_config_init_validate_show(repo: Path):
    result = runner.invoke(app, ["config", "init", "--owner", "acme", "--mode", "org"])
    assert result.exit_code == 0, result.output
    assert (repo / "gitteam.yaml").exists()
    result = runner.invoke(app, ["config", "init", "--owner", "acme", "--mode", "org"])
    assert result.exit_code == 1 and "already exists" in result.output
    assert runner.invoke(app, ["config", "validate"]).exit_code == 0
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0 and "owner: acme" in result.output
    result = runner.invoke(app, ["config", "capabilities", "--visibility", "public"])
    assert result.exit_code == 0 and "yes" in result.output


def test_config_init_personal_has_no_teams(repo: Path):
    result = runner.invoke(app, ["config", "init", "--owner", "alice", "--mode", "personal"])
    assert result.exit_code == 0, result.output
    assert "teams: []" in (repo / "gitteam.yaml").read_text(encoding="utf-8")


def test_branch_check(repo: Path):
    assert runner.invoke(app, ["ops", "branch", "check", "feature/login"]).exit_code == 0
    result = runner.invoke(app, ["ops", "branch", "check", "Feature/Login"])
    assert result.exit_code == 1 and "does not match" in result.output
    # current branch (main) is protected -> ok
    assert runner.invoke(app, ["ops", "branch", "check"]).exit_code == 0


def test_branch_new_and_commit_check(repo: Path):
    result = runner.invoke(app, ["ops", "branch", "new", "feature", "Login Page", "--issue", "12"])
    assert result.exit_code == 0, result.output
    assert _git(repo, "branch", "--show-current") == "feature/12-login-page"
    (repo / "a.txt").write_text("a", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "bad message")
    result = runner.invoke(app, ["ops", "commit", "check", "--range", "main..HEAD"])
    assert result.exit_code == 1 and "bad message" in result.output
    _git(repo, "commit", "--amend", "-m", "feat(login): add login page")
    result = runner.invoke(app, ["ops", "commit", "check", "--range", "main..HEAD"])
    assert result.exit_code == 0, result.output


def test_commit_check_message_and_file(repo: Path):
    assert runner.invoke(app, ["ops", "commit", "check", "-m", "fix: thing"]).exit_code == 0
    assert runner.invoke(app, ["ops", "commit", "check", "-m", "Thing"]).exit_code == 1
    msg = repo / "MSG"
    msg.write_text("docs: update readme\n\n# comment line\n", encoding="utf-8")
    assert runner.invoke(app, ["ops", "commit", "check", "--message-file", str(msg)]).exit_code == 0


def test_hooks_install_shared_and_local(repo: Path):
    result = runner.invoke(app, ["ops", "hooks", "install", "--shared"])
    assert result.exit_code == 0, result.output
    assert (repo / ".githooks" / "commit-msg").exists()
    assert _git(repo, "config", "core.hooksPath") == ".githooks"
    result = runner.invoke(app, ["ops", "hooks", "install", "--local"])
    assert result.exit_code == 0, result.output
    assert (repo / ".git" / "hooks" / "pre-push").exists()


def test_commit_msg_hook_rejects_bad_messages(repo: Path):
    if os.name == "nt" and not Path("C:/Program Files/Git/bin/sh.exe").exists():
        pytest.skip("sh not available")
    runner.invoke(app, ["ops", "hooks", "install", "--shared"])
    (repo / "b.txt").write_text("b", encoding="utf-8")
    _git(repo, "add", ".")
    env = {**os.environ, "PATH": os.environ["PATH"]}
    bad = subprocess.run(["git", "commit", "-m", "not conventional"], cwd=repo, capture_output=True, text=True, env=env)
    assert bad.returncode != 0, bad.stdout + bad.stderr
    good = subprocess.run(["git", "commit", "-m", "test: add b"], cwd=repo, capture_output=True, text=True, env=env)
    assert good.returncode == 0, good.stdout + good.stderr


def test_dev_setup_local_scope_dry_run(repo: Path):
    result = runner.invoke(app, ["--dry-run", "dev", "setup", "--scope", "local", "--name", "T", "--email", "t@x.io", "--skip-gh"])
    assert result.exit_code == 0, result.output
    assert "[dry-run]" in result.output and "user.name" in result.output


def test_dev_setup_local_scope_applies(repo: Path):
    result = runner.invoke(app, ["dev", "setup", "--scope", "local", "--name", "T", "--email", "t@x.io", "--skip-gh"])
    assert result.exit_code == 0, result.output
    assert _git(repo, "config", "--local", "pull.rebase") == "true"
    assert _git(repo, "config", "--local", "alias.st") == "status -sb"


def test_missing_config_message(repo: Path):
    result = runner.invoke(app, ["team", "list"])
    assert result.exit_code == 1 and "gitteam config init" in result.output
