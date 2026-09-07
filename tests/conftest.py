from __future__ import annotations

import pytest

from gitteam import config as cfgmod


@pytest.fixture(autouse=True)
def isolated_config_home(tmp_path_factory, monkeypatch):
    """Keep the trusted-config list (and user config dir) inside a per-test temp dir."""
    home = tmp_path_factory.mktemp("gitteam-home")
    monkeypatch.setenv(cfgmod.ENV_CONFIG_HOME, str(home))
    monkeypatch.delenv(cfgmod.ENV_CONFIG, raising=False)
    return home


@pytest.fixture
def org_config() -> cfgmod.Config:
    return cfgmod.from_dict({"owner": "acme", "mode": "org", "plan": "team"})


@pytest.fixture
def personal_config() -> cfgmod.Config:
    return cfgmod.from_dict({"owner": "alice", "mode": "personal"})
