"""Regression tests for defects found in code review."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gitteam import config as cfgmod
from gitteam.cli import app
from gitteam.context import AppContext
from gitteam.errors import CommandError, ConfigError
from gitteam.gitcmd import Git
from gitteam.runner import Runner

runner = CliRunner()


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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


# ---- 1) revision ranges with several arguments / invalid ranges


def test_commit_check_accepts_multi_argument_range(repo: Path):
    _git(repo, "switch", "-c", "feature/x")
    (repo / "a.txt").write_text("a", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "bad message")
    # the pre-push hook passes "<sha> --not --remotes=origin" for a brand-new branch
    sha = _git(repo, "rev-parse", "HEAD")
    result = runner.invoke(app, ["ops", "commit", "check", "--range", f"{sha} --not --remotes=origin"])
    assert result.exit_code == 1 and "bad message" in result.output


def test_commit_check_rejects_invalid_range(repo: Path):
    result = runner.invoke(app, ["ops", "commit", "check", "--range", "nope..HEAD"])
    assert result.exit_code == 1 and "invalid revision range" in result.output


def test_git_commits_raises_on_bad_range(repo: Path):
    with pytest.raises(CommandError):
        Git(Runner(), repo).commits("does-not-exist..HEAD")


# ---- 4) config_or_default must not hide broken configs


def test_broken_config_is_an_error_not_a_default(repo: Path):
    (repo / "gitteam.yaml").write_text("owner: acme\nmode: [broken\n", encoding="utf-8")
    cfgmod.trust_path(repo / "gitteam.yaml")
    result = runner.invoke(app, ["ops", "commit", "check", "-m", "feat: x"])
    assert result.exit_code == 1 and "YAML" in result.output


def test_missing_explicit_config_is_an_error(repo: Path):
    result = runner.invoke(app, ["--config", "missing.yaml", "ops", "commit", "check", "-m", "feat: x"])
    assert result.exit_code == 1 and "not found" in result.output


def test_no_config_at_all_uses_defaults(repo: Path):
    ctx = AppContext.create(config_path=None, dry_run=True, verbose=False)
    assert ctx.config_or_default().owner == ""


def test_discover_false_skips_directory_search(repo: Path):
    (repo / "gitteam.yaml").write_text("owner: acme\n", encoding="utf-8")
    cfgmod.trust_path(repo / "gitteam.yaml")
    ctx = AppContext.create(config_path=None, dry_run=True, verbose=False, discover=False)
    assert ctx.config_or_default().owner == ""
    with pytest.raises(ConfigError):
        ctx.load_config()


# ---- 6/7) hooks install


def test_hooks_local_after_shared_unsets_hookspath(repo: Path):
    assert runner.invoke(app, ["ops", "hooks", "install", "--shared"]).exit_code == 0
    assert _git(repo, "config", "--local", "core.hooksPath") == ".githooks"
    # shared hooks are staged with the executable bit recorded
    staged = subprocess.run(["git", "ls-files", "-s", ".githooks"], cwd=repo, capture_output=True, text=True).stdout
    modes = {line.split("\t")[1]: line.split(" ")[0] for line in staged.splitlines()}
    assert modes[".githooks/commit-msg"] == "100755" and modes[".githooks/pre-push"] == "100755"
    assert runner.invoke(app, ["ops", "hooks", "install", "--local"]).exit_code == 0
    proc = subprocess.run(["git", "config", "--local", "core.hooksPath"], cwd=repo, capture_output=True, text=True)
    assert proc.returncode != 0  # unset
    assert (repo / ".git" / "hooks" / "commit-msg").exists()


# ---- 8) remotes


@pytest.mark.parametrize(
    "url, expected",
    [
        ("ssh://git@github.com:22/acme/demo.git", ("acme", "demo")),
        ("ssh://git@github.com/acme/demo", ("acme", "demo")),
        ("git@github.com:acme/demo.git", ("acme", "demo")),
    ],
)
def test_parse_remote_with_port(url, expected):
    assert Git.parse_github_remote(url) == expected


def test_is_repo_on_plain_file(tmp_path: Path):
    file = tmp_path / "x.txt"
    file.write_text("x", encoding="utf-8")
    assert Git.is_repo(file) is False


# ---- repo name validation


def test_repo_init_rejects_bad_names(repo: Path):
    (repo / "gitteam.yaml").write_text("owner: acme\nmode: org\n", encoding="utf-8")
    cfgmod.trust_path(repo / "gitteam.yaml")
    result = runner.invoke(app, ["--dry-run", "repo", "init", "../evil"])
    assert result.exit_code == 1 and "not a valid" in result.output
    result = runner.invoke(app, ["--dry-run", "repo", "init", "bad name"])
    assert result.exit_code == 1 and "not a valid repository name" in result.output
