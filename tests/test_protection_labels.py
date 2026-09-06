from __future__ import annotations

from gitteam import labels as labelmod
from gitteam import protection as prot
from gitteam.config import Label, ProtectionConfig


def test_classic_payload_defaults():
    payload = prot.classic_payload(ProtectionConfig())
    assert payload["enforce_admins"] is True
    assert payload["required_pull_request_reviews"]["required_approving_review_count"] == 1
    assert payload["required_pull_request_reviews"]["require_code_owner_reviews"] is True
    assert payload["required_status_checks"] == {"strict": True, "checks": []}
    assert payload["allow_force_pushes"] is False
    assert payload["required_conversation_resolution"] is True


def test_classic_payload_without_checks_or_reviews():
    cfg = ProtectionConfig(required_approvals=0, require_code_owner_reviews=False, strict_status_checks=False)
    payload = prot.classic_payload(cfg)
    assert payload["required_status_checks"] is None
    assert payload["required_pull_request_reviews"] is None


def test_ruleset_payload_defaults():
    payload = prot.ruleset_payload(ProtectionConfig(), "main")
    assert payload["name"] == "gitteam:main"
    assert payload["conditions"]["ref_name"]["include"] == ["refs/heads/main"]
    types = [rule["type"] for rule in payload["rules"]]
    assert types == ["deletion", "non_fast_forward", "required_linear_history", "pull_request"]
    assert payload["bypass_actors"] == []


def test_ruleset_payload_options():
    cfg = ProtectionConfig(
        require_signed_commits=True,
        status_checks=["test", "lint"],
        enforce_admins=False,
        allow_force_pushes=True,
        allow_deletions=True,
    )
    payload = prot.ruleset_payload(cfg, "release/*")
    types = [rule["type"] for rule in payload["rules"]]
    assert "deletion" not in types and "non_fast_forward" not in types
    assert "required_signatures" in types
    checks = next(r for r in payload["rules"] if r["type"] == "required_status_checks")
    assert checks["parameters"]["required_status_checks"] == [{"context": "test"}, {"context": "lint"}]
    assert payload["bypass_actors"][0]["actor_type"] == "RepositoryRole"
    assert payload["conditions"]["ref_name"]["include"] == ["refs/heads/release/*"]


def test_choose_engine():
    assert prot.choose_engine(ProtectionConfig()) == "ruleset"
    assert prot.choose_engine(ProtectionConfig(engine="classic")) == "classic"


def test_label_plan():
    existing = [
        {"name": "bug", "color": "D73A4A", "description": "Something is not working"},
        {"name": "Enhancement", "color": "000000", "description": ""},
        {"name": "legacy", "color": "ffffff", "description": None},
    ]
    desired = [
        Label("bug", "d73a4a", "Something is not working"),
        Label("enhancement", "a2eeef", "New feature or request"),
        Label("security", "ee0701", "Security related"),
    ]
    actions = {(c.action, c.label.name) for c in labelmod.plan_changes(existing, desired)}
    assert actions == {("keep", "bug"), ("update", "enhancement"), ("create", "security")}
    pruned = {(c.action, c.label.name) for c in labelmod.plan_changes(existing, desired, prune=True)}
    assert ("delete", "legacy") in pruned
