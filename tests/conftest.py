from __future__ import annotations

import pytest

from gitteam import config as cfgmod


@pytest.fixture
def org_config() -> cfgmod.Config:
    return cfgmod.from_dict({"owner": "acme", "mode": "org", "plan": "team"})


@pytest.fixture
def personal_config() -> cfgmod.Config:
    return cfgmod.from_dict({"owner": "alice", "mode": "personal"})
