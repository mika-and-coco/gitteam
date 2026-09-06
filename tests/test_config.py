from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gitteam import config as cfgmod
from gitteam.commands.config_cmd import render_example
from gitteam.errors import ConfigError


def test_minimal_config_gets_defaults():
    cfg = cfgmod.from_dict({"owner": "acme"})
    assert cfg.mode is cfgmod.Mode.ORG
    assert cfg.repo.default_branch == "main"
    assert cfg.labels  # built-in defaults
    assert cfg.scaffold.codeowners == {"*": ["@{owner}/core"]}


def test_personal_codeowners_default():
    cfg = cfgmod.from_dict({"owner": "alice", "mode": "personal"})
    assert cfg.scaffold.codeowners == {"*": ["@alice".replace("alice", "{owner}")]}


def test_unknown_key_rejected():
    with pytest.raises(ConfigError, match="unknown key"):
        cfgmod.from_dict({"owner": "acme", "repo": {"visibilty": "private"}})


def test_invalid_enum_rejected():
    with pytest.raises(ConfigError, match="is not one of"):
        cfgmod.from_dict({"owner": "acme", "mode": "enterprise"})


def test_missing_owner_rejected():
    with pytest.raises(ConfigError, match="missing required key"):
        cfgmod.from_dict({"mode": "org"})


def test_teams_in_personal_mode_rejected():
    with pytest.raises(ConfigError, match="teams"):
        cfgmod.from_dict({"owner": "alice", "mode": "personal", "teams": [{"name": "core"}]})


def test_internal_visibility_requires_enterprise():
    with pytest.raises(ConfigError, match="internal"):
        cfgmod.from_dict({"owner": "acme", "mode": "org", "repo": {"visibility": "internal"}})
    cfg = cfgmod.from_dict({"owner": "acme", "mode": "org-enterprise", "repo": {"visibility": "internal"}})
    assert cfg.effective_plan is cfgmod.Plan.ENTERPRISE


def test_bad_label_color_rejected():
    with pytest.raises(ConfigError, match="color"):
        cfgmod.from_dict({"owner": "acme", "labels": [{"name": "x", "color": "#ff0000"}]})


@pytest.mark.parametrize("mode", list(cfgmod.Mode))
def test_example_template_is_valid_for_every_mode(mode: cfgmod.Mode):
    content = render_example("acme", mode)
    data = yaml.safe_load(content)
    cfg = cfgmod.from_dict(data)
    assert cfg.owner == "acme"
    assert cfg.mode is mode
    assert cfg.conventions.branch_pattern.endswith("$")
    if mode.is_org:
        assert cfg.teams and cfg.teams[0].name == "core"
    else:
        assert cfg.teams == []


def test_load_and_roundtrip(tmp_path: Path):
    path = tmp_path / "gitteam.yaml"
    path.write_text("owner: acme\nmode: org\nteams:\n  - name: core\n    members: [bob]\n", encoding="utf-8")
    cfg = cfgmod.load(path)
    assert cfg.source_path == path
    dumped = cfgmod.to_dict(cfg)
    assert dumped["mode"] == "org"
    assert dumped["teams"][0]["members"] == ["bob"]
    assert "source_path" not in dumped


def test_find_config_walks_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "gitteam.yaml").write_text("owner: acme\n", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    monkeypatch.delenv(cfgmod.ENV_CONFIG, raising=False)
    assert cfgmod.find_config() == tmp_path / "gitteam.yaml"
