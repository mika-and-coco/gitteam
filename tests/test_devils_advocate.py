"""Regression tests from the devil's-advocate review (2026-09-10)."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest
from rich.console import Console

from gitteam import config as cfgmod
from gitteam import ui as rich_ui
from gitteam.commands import config_cmd
from gitteam.commands import repo as repo_cmd
from gitteam.context import AppContext
from gitteam.errors import ConfigError, GitTeamError
from gitteam.gh import Gh
from gitteam.runner import Runner


class HybridRunner(Runner):
    """Real git, canned gh. ``responses`` maps an endpoint (or gh sub-command) to (code, stdout, stderr)."""

    def __init__(self, responses: dict[str, tuple[int, str, str]], dry_run: bool = False):
        super().__init__(dry_run=dry_run)
        self.responses = responses
        self.gh_calls: list[list[str]] = []

    def run(self, cmd, *, input=None, check=True, mutating=True, cwd=None):  # type: ignore[override]
        if cmd[0] != "gh":
            return super().run(cmd, input=input, check=check, mutating=mutating, cwd=cwd)
        self.gh_calls.append(list(cmd))
        if self.dry_run and mutating:
            return subprocess.CompletedProcess(list(cmd), 0, "", "")
        key = cmd[2] if cmd[1] == "api" else " ".join(cmd[1:3])
        default = (0, "{}", "") if mutating else (1, json.dumps({"message": "Not Found"}), "gh: Not Found (HTTP 404)")
        code, out, err = self.responses.get(key, default)
        return subprocess.CompletedProcess(list(cmd), code, out, err)


def _capture():
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None, width=200, soft_wrap=True)
    return buffer, console


# --------------------------------------------------------------------------- A: dry-run of a brand-new repository


def test_repo_init_dry_run_for_new_repo_does_not_touch_missing_directory(tmp_path: Path, monkeypatch, org_config):
    monkeypatch.chdir(tmp_path)
    runner = HybridRunner({"orgs/acme": (0, json.dumps({"plan": {"name": "team"}}), "")}, dry_run=True)
    ctx = AppContext(runner=runner, gh=Gh(runner), discover=False, _config=org_config)
    buffer, console = _capture()
    with rich_ui.redirected(console):
        repo_cmd.init_repo(ctx, repo_cmd.InitOptions(name="newrepo"))
    out = buffer.getvalue()
    assert "would clone acme/newrepo" in out
    assert "git push -u origin main" in out
    assert not (tmp_path / "newrepo").exists()


def test_runner_reports_missing_cwd_clearly(tmp_path: Path):
    with pytest.raises(GitTeamError, match="does not exist"):
        Runner().run(["git", "status"], mutating=False, cwd=tmp_path / "nope")


# --------------------------------------------------------------------------- B: dry-run marker must survive rich markup


def test_config_trust_dry_run_prints_marker(tmp_path: Path):
    path = tmp_path / "gitteam.yaml"
    path.write_text("owner: acme\nmode: org\n", encoding="utf-8")
    runner = Runner(dry_run=True)
    ctx = AppContext(runner=runner, gh=Gh(runner))
    buffer, console = _capture()
    with rich_ui.redirected(console):
        config_cmd.trust(ctx, path)
        config_cmd.untrust(ctx, path)
    assert buffer.getvalue().count("[dry-run]") == 2


# --------------------------------------------------------------------------- C/F/G/H/I: configuration validation gaps


@pytest.mark.parametrize(
    "data, fragment",
    [
        ({"scaffold": {"include": ["readme", "bogus"]}}, "scaffold.include"),
        ({"teams": [{"name": "core", "members": ["evil/../x"]}]}, "teams.core.members"),
        ({"teams": [{"name": "core", "maintainers": ["a b"]}]}, "teams.core.maintainers"),
        ({"teams": [{"name": "core", "repos": ["../x"]}]}, "teams.core.repos"),
        ({"collaborators": [{"user": "a?b"}]}, "collaborators"),
        ({"collaborators": [{"user": "bob", "repos": ["x/y"]}]}, "collaborators.bob.repos"),
        ({"repo": {"topics": ["Bad Topic!"]}}, "repo.topics"),
        ({"repo": {"license": "../x"}}, "repo.license"),
        ({"labels": [{"name": "bug", "color": "aaaaaa"}, {"name": "Bug", "color": "bbbbbb"}]}, "labels"),
        ({"protection": {"engine": "classic", "branches": ["release/*"]}}, "protection.branches"),
    ],
)
def test_validation_rejects(data, fragment):
    with pytest.raises(ConfigError, match=fragment):
        cfgmod.from_dict({"owner": "acme", **data})


def test_validation_accepts_wildcard_repos_and_normal_values():
    cfg = cfgmod.from_dict(
        {
            "owner": "acme",
            "teams": [{"name": "core", "members": ["alice", "bob-1"], "repos": ["*"]}],
            "collaborators": [{"user": "carol", "repos": ["*", "demo.app"]}],
            "repo": {"topics": ["python", "cli-tool"], "license": "apache-2.0"},
        }
    )
    assert cfg.repo.topics == ["python", "cli-tool"]


def test_resolve_target_and_invite_reject_bad_names(org_config):
    runner = HybridRunner({})
    ctx = AppContext(runner=runner, gh=Gh(runner), discover=False, _config=org_config)
    from gitteam.commands import team as team_cmd

    with pytest.raises(GitTeamError, match="login"):
        team_cmd.invite(ctx, "bad/user", None, "member", None, "push")
    with pytest.raises(GitTeamError, match="repository name"):
        team_cmd.invite(ctx, "alice", None, "member", "../x", "push")
    with pytest.raises(GitTeamError, match="not one of"):
        team_cmd.invite(ctx, "alice", None, "owner", None, "push")
    with pytest.raises(GitTeamError, match="not one of"):
        team_cmd.invite(ctx, "alice", None, "member", "demo", "root")


# --------------------------------------------------------------------------- D: invisible plan in personal mode


def test_personal_plan_not_visible_warns(personal_config):
    runner = HybridRunner({"user": (0, json.dumps({"login": "alice"}), "")})
    ctx = AppContext(runner=runner, gh=Gh(runner), discover=False, _config=personal_config)
    buffer, console = _capture()
    with rich_ui.redirected(console):
        plan = ctx.resolve_plan()
    assert plan is cfgmod.Plan.FREE
    assert "WARN" in buffer.getvalue() and "plan" in buffer.getvalue()


# --------------------------------------------------------------------------- E: organisation rulesets must not be updated through the repo endpoint


def test_apply_protection_ignores_org_level_rulesets(org_config):
    rulesets = [
        {"id": 1, "name": "gitteam:main", "source_type": "Organization"},
        {"id": 2, "name": "gitteam:main", "source_type": "Repository"},
    ]
    runner = HybridRunner({"repos/acme/demo/rulesets?per_page=100": (0, json.dumps([rulesets]), "")})
    ctx = AppContext(runner=runner, gh=Gh(runner), discover=False, _config=org_config)
    buffer, console = _capture()
    with rich_ui.redirected(console):
        repo_cmd.apply_protection(ctx, repo_cmd.RepoTarget("acme", "demo"), "private")
    updates = [c for c in runner.gh_calls if c[2].startswith("repos/acme/demo/rulesets/")]
    assert [c[2] for c in updates] == ["repos/acme/demo/rulesets/2"]


# --------------------------------------------------------------------------- turn 2: release tag, PR order, markup, UI summary


def test_latest_version_tag_ignores_unrelated_tags_and_sorts_numerically():
    from gitteam import conventions as conv

    rules = cfgmod.ConventionsConfig()
    tags = ["version-old", "v1.9.0", "v1.10.0", "v1.10.0-rc.1", "vnext"]
    assert conv.latest_version_tag(rules, tags) == "v1.10.0"
    assert conv.latest_version_tag(rules, ["v2.0.0-beta.1", "v2.0.0-beta.2", "v1.10.0"]) == "v2.0.0-beta.2"
    assert conv.latest_version_tag(rules, ["version-old"]) is None
    assert conv.latest_version_tag(cfgmod.ConventionsConfig(tag_prefix=""), ["1.2.3", "v9.9.9"]) == "1.2.3"


def _init_repo(path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)

    path.mkdir()
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "Tester")
    git("config", "commit.gpgsign", "false")
    (path / "README.md").write_text("# demo\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-q", "-m", "chore: initial commit")


def test_pr_create_validates_before_pushing(tmp_path: Path, monkeypatch, org_config):
    from gitteam.commands import ops as ops_cmd
    from gitteam.errors import ConventionError

    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True, capture_output=True)
    work = tmp_path / "work"
    _init_repo(work)

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=work, check=True, capture_output=True, text=True).stdout.strip()

    git("remote", "add", "origin", str(remote))
    git("push", "-q", "-u", "origin", "main")
    git("switch", "-q", "-c", "feature/bad-commit")
    git("commit", "-q", "--allow-empty", "-m", "this is not conventional")
    monkeypatch.chdir(work)
    runner = HybridRunner({})
    ctx = AppContext(runner=runner, gh=Gh(runner), discover=False, _config=org_config)
    buffer, console = _capture()
    with rich_ui.redirected(console), pytest.raises(ConventionError, match="Conventional Commits"):
        ops_cmd.pr_create(ctx, title=None, base=None, draft=False, reviewers=[], labels=[], no_verify=False)
    remote_branches = subprocess.run(
        ["git", "branch", "--list", "feature/bad-commit"], cwd=remote, check=True, capture_output=True, text=True
    ).stdout
    assert remote_branches.strip() == "", "the branch must not be pushed when validation fails"
    assert not runner.gh_calls


def test_console_output_keeps_bracketed_text(tmp_path: Path, monkeypatch):
    """Regexes, label names and commit subjects contain '[...]' which rich would eat as markup."""
    from gitteam.commands import ops as ops_cmd

    work = tmp_path / "work"
    _init_repo(work)
    monkeypatch.chdir(work)
    runner = Runner(dry_run=True)
    ctx = AppContext(runner=runner, gh=Gh(runner), discover=False)
    buffer, console = _capture()
    with rich_ui.redirected(console):
        assert ops_cmd.branch_check(ctx, "nope") is False
        assert ops_cmd.commit_check(ctx, None, None, "feat: handle [edge] case") is True
        rich_ui.warn("label [priority: high] changed")
        rich_ui.table("t", ["a"], [("[x]",)])
        rich_ui.info(f"{rich_ui.DRY_RUN} would write x")
        runner.run(["git", "commit", "-m", "fix: [ci] skip"])
    out = buffer.getvalue()
    assert "[a-z0-9][a-z0-9._-]*$" in out
    assert "[priority: high]" in out and "[x]" in out
    assert "[dry-run] would write x" in out
    assert "[dry-run] git commit -m 'fix: [ci] skip'" in out


def test_describe_command_keeps_full_pr_title():
    pytest.importorskip("streamlit")
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ui"))
    import services as svc

    line = "gh pr create --base main --title 'feat: add login page' --body-file x.md --label enhancement"
    assert svc.describe_command(line) == "プルリクエストを作成: feat: add login page"
    assert svc.describe_command("gh pr create --base main --title single --body-file x.md") == "プルリクエストを作成: single"


# --------------------------------------------------------------------------- turn 3: commit -v, team sync failures, config values


def test_commit_message_ignores_diff_after_scissors_line():
    from gitteam import conventions as conv

    rules = cfgmod.ConventionsConfig()
    verbose = (
        "feat: add login\n"
        "# Please enter the commit message for your changes.\n"
        "# ------------------------ >8 ------------------------\n"
        "# Do not modify or remove the line above.\n"
        "diff --git a/x b/x\n+new\n"
    )
    assert conv.validate_commit_message(rules, verbose) == []
    assert conv.validate_commit_message(rules, "# only comments\n# ------------------------ >8 ------------------------\ndiff\n") == [
        "commit message is empty"
    ]


def test_pr_title_from_long_branch_respects_max_length():
    from gitteam import conventions as conv

    rules = cfgmod.ConventionsConfig(commit_subject_max=40)
    title = conv.pr_title(rules, "feature/" + "-".join(["word"] * 30), ["a", "b"])
    assert title.startswith("feat: word") and len(title) <= 40
    assert conv.validate_commit_message(rules, title) == []


@pytest.mark.parametrize(
    "data, fragment",
    [
        ({"repo": {"squash_merge_commit_title": "TITLE"}}, "squash_merge_commit_title"),
        ({"repo": {"squash_merge_commit_message": "BODY"}}, "squash_merge_commit_message"),
        ({"repo": {"allow_squash_merge": False, "allow_merge_commit": False, "allow_rebase_merge": False}}, "at least one"),
    ],
)
def test_validation_rejects_bad_merge_settings(data, fragment):
    with pytest.raises(ConfigError, match=fragment):
        cfgmod.from_dict({"owner": "acme", **data})


def test_team_sync_continues_after_a_failed_item_and_reports(org_config):
    from gitteam.commands import team as team_cmd

    org_config.teams = [cfgmod.TeamConfig(name="core", members=["alice", "ghost", "bob"], repos=["demo"])]
    teams = [{"name": "core", "slug": "core"}]
    runner = HybridRunner(
        {
            "orgs/acme/teams?per_page=100": (0, json.dumps([teams]), ""),
            "orgs/acme/teams/core/members?per_page=100": (0, json.dumps([[{"login": "alice"}]]), ""),
            "orgs/acme/teams/core/memberships/ghost": (1, json.dumps({"message": "Not Found"}), "gh: Not Found (HTTP 404)"),
        }
    )
    ctx = AppContext(runner=runner, gh=Gh(runner), discover=False, _config=org_config)
    buffer, console = _capture()
    with rich_ui.redirected(console), pytest.raises(GitTeamError, match="1 failed item"):
        team_cmd.sync(ctx, None, False)
    out = buffer.getvalue()
    endpoints = [c[2] for c in runner.gh_calls]
    assert "orgs/acme/teams/core/memberships/bob" in endpoints, "later members must still be processed"
    assert "orgs/acme/teams/core/repos/acme/demo" in endpoints
    assert "failed: Not Found" in out and "ensured" in out


# --------------------------------------------------------------------------- turn 4: dry-run side effects, UI path quoting


def test_dev_onboard_dry_run_creates_nothing(tmp_path: Path, monkeypatch, org_config):
    from gitteam.commands import dev as dev_cmd

    monkeypatch.chdir(tmp_path)
    org_config.dev.repos = ["demo"]
    runner = HybridRunner({}, dry_run=True)
    ctx = AppContext(runner=runner, gh=Gh(runner), discover=False, _config=org_config)
    target = tmp_path / "work"
    buffer, console = _capture()
    with rich_ui.redirected(console):
        dev_cmd.onboard(ctx, directory=target, name=None, email=None, skip_gh=True)
    assert not target.exists()
    assert "would clone acme/demo" in buffer.getvalue()


def test_describe_command_strips_quotes_from_paths():
    pytest.importorskip("streamlit")
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ui"))
    import services as svc

    assert svc.describe_command(r"gh repo clone acme/demo 'C:\projects\my demo'") == r"acme/demo を C:\projects\my demo にクローン"
    assert svc.describe_command("gh repo clone acme/demo") == "acme/demo をローカルにクローン"
    assert svc.describe_command(r"git clone https://x/y.git 'C:\p\y'") == r"C:\p\y にクローン"


def test_pr_title_from_branch_with_one_huge_word_still_has_a_description():
    from gitteam import conventions as conv

    rules = cfgmod.ConventionsConfig(commit_subject_max=30)
    title = conv.pr_title(rules, "feature/" + "x" * 60, ["a", "b"])
    assert len(title) <= 30 and conv.validate_commit_message(rules, title) == []


# --------------------------------------------------------------------------- untrusted config: read-only checks keep working


def test_hook_checks_use_untrusted_conventions_with_a_hint(tmp_path: Path, monkeypatch):
    """A fresh clone shipping gitteam.yaml must not block every commit for people who installed gitteam."""
    from gitteam.commands import ops as ops_cmd
    from gitteam.errors import UntrustedConfigError

    work = tmp_path / "clone"
    _init_repo(work)
    (work / "gitteam.yaml").write_text(
        "owner: acme\nmode: org\nconventions:\n  commit_types: [feat, story]\n  branch_types: [story]\n"
        "  branch_pattern: '^story/[a-z0-9-]+$'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(work)
    runner = Runner()
    ctx = AppContext(runner=runner, gh=Gh(runner))
    buffer, console = _capture()
    with rich_ui.redirected(console):
        assert ops_cmd.commit_check(ctx, None, None, "story: use the team's own type") is True
        assert ops_cmd.branch_check(ctx, "story/abc") is True
        assert ops_cmd.branch_check(ctx, "feature/abc") is False  # the untrusted file's rules apply, not the defaults
    out = buffer.getvalue()
    assert out.count("WARN") >= 1 and "config trust" in out
    # side effects still require trust
    with pytest.raises(UntrustedConfigError):
        ops_cmd.hooks_install(AppContext(runner=Runner(dry_run=True), gh=Gh(runner)), shared=True)
    # once trusted, no more hint
    cfgmod.trust_path(work / "gitteam.yaml")
    buffer, console = _capture()
    with rich_ui.redirected(console):
        assert ops_cmd.commit_check(AppContext(runner=runner, gh=Gh(runner)), None, None, "feat: ok") is True
    assert "untrusted" not in buffer.getvalue()


# --------------------------------------------------------------------------- branch_types drives the default branch_pattern


def test_branch_pattern_follows_custom_branch_types():
    from gitteam import conventions as conv

    cfg = cfgmod.from_dict({"owner": "acme", "conventions": {"branch_types": ["feature", "fix", "chore", "docs"]}})
    rules = cfg.conventions
    assert rules.branch_pattern == "^(feature|fix|chore|docs)/[a-z0-9][a-z0-9._-]*$"
    assert conv.validate_branch_name(rules, "feature/12-login") == []
    assert conv.validate_branch_name(rules, "release/1-x"), "types removed from branch_types must be rejected by hooks/CI too"
    # an explicit pattern always wins, and the default set keeps the built-in pattern
    explicit = cfgmod.from_dict({"owner": "acme", "conventions": {"branch_types": ["x"], "branch_pattern": "^x/.*$"}})
    assert explicit.conventions.branch_pattern == "^x/.*$"
    assert cfgmod.from_dict({"owner": "acme"}).conventions.branch_pattern == cfgmod.DEFAULT_BRANCH_PATTERN
    # generated patterns stay within the safe alphabet embedded in hooks/workflows
    assert cfgmod.from_dict({"owner": "acme", "conventions": {"branch_types": ["rel.1"]}}).conventions.branch_pattern
