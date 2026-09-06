from __future__ import annotations

import pytest

from gitteam.capabilities import plan_from_api_name, resolve
from gitteam.config import Mode, Plan


@pytest.mark.parametrize(
    "mode, plan, visibility, protection, teams, org_rulesets",
    [
        (Mode.ORG, Plan.FREE, "private", False, True, False),
        (Mode.ORG, Plan.FREE, "public", True, True, False),
        (Mode.ORG, Plan.TEAM, "private", True, True, False),
        (Mode.ORG_ENTERPRISE, Plan.AUTO, "private", True, True, True),
        (Mode.ORG_ENTERPRISE, Plan.FREE, "internal", True, True, True),
        (Mode.PERSONAL, Plan.FREE, "private", False, False, False),
        (Mode.PERSONAL, Plan.PRO, "private", True, False, False),
        (Mode.PERSONAL, Plan.FREE, "public", True, False, False),
    ],
)
def test_matrix(mode, plan, visibility, protection, teams, org_rulesets):
    caps = resolve(mode, plan, visibility)
    assert caps.branch_protection is protection
    assert caps.rulesets is protection
    assert caps.teams is teams
    assert caps.org_rulesets is org_rulesets
    assert caps.required_workflows is org_rulesets
    if not protection:
        assert any("protection" in note for note in caps.notes)


def test_enterprise_mode_forces_plan():
    assert resolve(Mode.ORG_ENTERPRISE, Plan.FREE).plan is Plan.ENTERPRISE


@pytest.mark.parametrize(
    "name, mode, expected",
    [
        ("free", Mode.ORG, Plan.FREE),
        ("team", Mode.ORG, Plan.TEAM),
        ("business", Mode.ORG, Plan.TEAM),
        ("enterprise", Mode.ORG, Plan.ENTERPRISE),
        ("pro", Mode.PERSONAL, Plan.PRO),
        (None, Mode.PERSONAL, Plan.FREE),
        ("silver", Mode.ORG, Plan.TEAM),
        ("free", Mode.ORG_ENTERPRISE, Plan.ENTERPRISE),
    ],
)
def test_plan_mapping(name, mode, expected):
    assert plan_from_api_name(name, mode) is expected
