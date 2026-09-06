from __future__ import annotations

import pytest

from gitteam import conventions as conv
from gitteam.config import ConventionsConfig
from gitteam.errors import ConventionError


@pytest.fixture
def rules() -> ConventionsConfig:
    return ConventionsConfig()


# ---- branches


def test_build_branch_name_slugifies(rules):
    assert conv.build_branch_name(rules, "feature", "Add Login  Page!") == "feature/add-login-page"
    assert conv.build_branch_name(rules, "fix", "NPE in parser", issue=42) == "fix/42-npe-in-parser"


def test_build_branch_name_rejects_unknown_type(rules):
    with pytest.raises(ConventionError, match="unknown branch type"):
        conv.build_branch_name(rules, "wip", "x")


def test_build_branch_name_requires_issue_when_configured(rules):
    rules.require_issue_in_branch = True
    with pytest.raises(ConventionError, match="issue number"):
        conv.build_branch_name(rules, "feature", "thing")
    assert conv.build_branch_name(rules, "feature", "thing", issue=7) == "feature/7-thing"


def test_build_branch_name_rejects_non_ascii_only(rules):
    with pytest.raises(ConventionError, match="ASCII"):
        conv.build_branch_name(rules, "feature", "日本語のみ")


@pytest.mark.parametrize(
    "name, valid",
    [
        ("feature/login", True),
        ("fix/12-crash", True),
        ("main", True),  # protected, exempt
        ("develop", True),
        ("Feature/Login", False),
        ("feat/login", False),
        ("feature/", False),
        ("feature/-x", False),
        ("random", False),
    ],
)
def test_validate_branch_name(rules, name, valid):
    assert (conv.validate_branch_name(rules, name) == []) is valid


def test_issue_from_branch():
    assert conv.issue_from_branch("fix/42-thing") == 42
    assert conv.issue_from_branch("fix/thing") is None


# ---- commits


@pytest.mark.parametrize(
    "message, valid",
    [
        ("feat: add login", True),
        ("feat(auth): add login", True),
        ("feat(auth)!: drop v1", True),
        ("fix: handle empty input\n\nDetails here.", True),
        ("Merge branch 'main' into feature/x", True),
        ('Revert "feat: add login"', True),
        ("Add login", False),
        ("feat:add login", False),
        ("wip: stuff", False),
        ("feat: ends with period.", False),
        ("fixup! feat: add login", False),
        ("feat: line one\nline two directly below", False),
        ("feat: " + "x" * 80, False),
        ("", False),
        ("# only comments\n#\n", False),
    ],
)
def test_validate_commit_message(rules, message, valid):
    assert (conv.validate_commit_message(rules, message) == []) is valid, conv.validate_commit_message(rules, message)


def test_commit_scope_rules(rules):
    rules.require_scope = True
    assert conv.validate_commit_message(rules, "feat: x")
    assert not conv.validate_commit_message(rules, "feat(api): x")
    rules.commit_scopes = ["api"]
    assert conv.validate_commit_message(rules, "feat(web): x")


# ---- versions


def test_normalize_version(rules):
    assert conv.normalize_version(rules, "1.2.3") == ("1.2.3", "v1.2.3")
    assert conv.normalize_version(rules, "v1.2.3-rc.1") == ("1.2.3-rc.1", "v1.2.3-rc.1")
    assert conv.is_prerelease("1.2.3-rc.1")
    assert not conv.is_prerelease("1.2.3")
    with pytest.raises(ConventionError):
        conv.normalize_version(rules, "1.2")
    with pytest.raises(ConventionError):
        conv.normalize_version(rules, "v01.2.3")


# ---- PR helpers


def test_pr_title_prefers_single_conventional_commit(rules):
    assert conv.pr_title(rules, "feature/login", ["feat(auth): add login"]) == "feat(auth): add login"


def test_pr_title_from_branch(rules):
    assert conv.pr_title(rules, "feature/42-add-login-page", ["a", "b"]) == "feat: add login page"
    assert conv.pr_title(rules, "hotfix/crash", []) == "fix: crash"
    assert conv.pr_title(rules, "weird", []) == "chore: weird"


def test_pr_label(rules):
    assert conv.pr_label(rules, "fix: x") == "bug"
    assert conv.pr_label(rules, "perf: x") is None
