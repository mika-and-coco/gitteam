from __future__ import annotations

import re
from pathlib import Path

import pytest

from gitteam import config as cfgmod
from gitteam import scaffold


def _gitignore(name: str) -> str | None:
    return "__pycache__/\n*.pyc\n" if name == "Python" else None


def _license(key: str) -> str | None:
    return "MIT License\n\nCopyright (c) [year] [fullname]\n" if key == "mit" else None


def test_materialize_writes_all_components(tmp_path: Path):
    cfg = cfgmod.from_dict(
        {"owner": "acme", "mode": "org", "repo": {"gitignore_templates": ["Python", "Nope"], "license": "mit"}}
    )
    result = scaffold.materialize(tmp_path, cfg, "demo", gitignore_source=_gitignore, license_source=_license)
    written = {p.relative_to(tmp_path).as_posix() for p in result.written}
    expected = {f for files in scaffold.COMPONENTS.values() for f in files}
    assert written == expected
    assert result.executable == [".githooks/commit-msg", ".githooks/pre-push"]

    codeowners = (tmp_path / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert "@acme/core" in codeowners
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "__pycache__/" in gitignore and "Nope" not in gitignore
    license_text = (tmp_path / "LICENSE").read_text(encoding="utf-8")
    assert "[year]" not in license_text and "acme" in license_text

    for path in result.written:
        text = path.read_text(encoding="utf-8")
        assert "$$" not in text, path
        assert not re.search(r"\$(owner|repo|default_branch|branch_pattern|commit_types)\b", text), path
        assert "\r\n" not in text, path


def test_hooks_contain_configured_rules(tmp_path: Path):
    cfg = cfgmod.from_dict({"owner": "acme", "conventions": {"commit_subject_max": 50}})
    scaffold.materialize(tmp_path, cfg, "demo", components=["githooks", "workflows"])
    hook = (tmp_path / ".githooks" / "commit-msg").read_text(encoding="utf-8")
    assert hook.startswith("#!/bin/sh")
    assert "MAX=50" in hook
    assert "feat|fix|docs" in hook
    assert 'MSG_FILE="$1"' in hook
    pre_push = (tmp_path / ".githooks" / "pre-push").read_text(encoding="utf-8")
    assert cfg.conventions.branch_pattern in pre_push
    assert "PROTECTED=' main develop '" in pre_push
    workflow = (tmp_path / ".github" / "workflows" / "conventions.yml").read_text(encoding="utf-8")
    assert "${{ github.head_ref }}" in workflow
    assert "${#TITLE}" in workflow
    assert "$$" not in workflow


def test_existing_files_are_kept_unless_forced(tmp_path: Path):
    cfg = cfgmod.from_dict({"owner": "acme"})
    (tmp_path / "README.md").write_text("mine\n", encoding="utf-8")
    result = scaffold.materialize(tmp_path, cfg, "demo", components=["readme"])
    assert result.written == [] and result.skipped == [tmp_path / "README.md"]
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "mine\n"
    result = scaffold.materialize(tmp_path, cfg, "demo", components=["readme"], force=True)
    assert result.written == [tmp_path / "README.md"]
    assert "# demo" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_dry_run_writes_nothing(tmp_path: Path):
    cfg = cfgmod.from_dict({"owner": "acme"})
    result = scaffold.materialize(tmp_path, cfg, "demo", dry_run=True)
    assert result.written
    assert list(tmp_path.iterdir()) == []


def test_license_skipped_without_source(tmp_path: Path):
    cfg = cfgmod.from_dict({"owner": "acme", "repo": {"license": "mit"}})
    result = scaffold.materialize(tmp_path, cfg, "demo", components=["license"])
    assert result.written == [] and not (tmp_path / "LICENSE").exists()


def test_unknown_component(tmp_path: Path):
    cfg = cfgmod.from_dict({"owner": "acme"})
    with pytest.raises(ValueError, match="unknown scaffold component"):
        scaffold.materialize(tmp_path, cfg, "demo", components=["nope"])
