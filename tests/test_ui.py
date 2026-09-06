"""Headless smoke tests for the Streamlit UI (no browser, no GitHub mutations)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "ui" / "streamlit_app.py"
PAGES = ["start", "overview", "config_page", "repo_page", "team_page", "ops_page", "dev_page", "glossary_page"]

sys.path.insert(0, str(ROOT / "ui"))
import services as svc  # noqa: E402


def _app(config_path: Path | None) -> AppTest:
    at = AppTest.from_file(str(ENTRY), default_timeout=60)
    at.session_state["cfg_path"] = str(config_path) if config_path else str(ROOT / "nonexistent.yaml")
    return at


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "gitteam.yaml"
    path.write_text(
        "# team config\nowner: acme\nmode: org\nteams:\n  - name: core\n    members: [bob]\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("page", PAGES)
def test_pages_render_without_config(page: str):
    at = _app(None).run()
    assert not at.exception
    at.switch_page(f"app_pages/{page}.py").run()
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("page", PAGES)
def test_pages_render_with_config(page: str, config_file: Path):
    at = _app(config_file).run()
    at.switch_page(f"app_pages/{page}.py").run()
    assert not at.exception, [e.value for e in at.exception]


def test_start_wizard_creates_config(tmp_path: Path):
    target = tmp_path / "new" / "gitteam.yaml"
    at = _app(target).run()
    at.text_input(key="start_owner").set_value("acme")
    at.text_input(key="start_output").set_value(str(target))
    at.button[0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert target.exists()
    assert "owner: acme" in target.read_text(encoding="utf-8")


def test_config_yaml_tab_validates(config_file: Path):
    at = _app(config_file).run()
    at.switch_page("app_pages/config_page.py").run()
    at.text_area(key="config_editor").set_value("owner: acme\nmode: nope\n")
    at.button(key="yaml_check").click().run()
    assert any("is not one of" in e.value for e in at.error)
    assert not at.exception


def test_ops_page_branch_builder(config_file: Path):
    at = _app(config_file).run()
    at.switch_page("app_pages/ops_page.py").run()
    at.text_input(key="ops_repo_path").set_value(str(config_file.parent)).run()
    inputs = [w for w in at.text_input if w.label.startswith("作業内容")]
    inputs[0].set_value("Add Login Page").run()
    assert any("feature/add-login-page" in s.value for s in at.success)
    assert not at.exception


def test_repo_single_form_submits_without_widget_key_collision(config_file: Path):
    at = _app(config_file).run()
    at.switch_page("app_pages/repo_page.py").run()
    inputs = [w for w in at.text_input if w.label == "リポジトリ名"]
    inputs[-1].set_value("demo").run()
    submit = [b for b in at.button if b.label == "内容を確認する"][-1]
    submit.click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert "action::repo_single" in at.session_state


def test_team_sync_form_submits_without_widget_key_collision(config_file: Path):
    at = _app(config_file).run()
    at.switch_page("app_pages/team_page.py").run()
    submit = [b for b in at.button if b.label == "内容を確認する"][0]
    submit.click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert "action::team_sync" in at.session_state


# ---------------------------------------------------------------- services (pure helpers)


@pytest.mark.parametrize(
    "line, expected",
    [
        ("gh repo create acme/demo --private", "リポジトリ acme/demo を作成（private）"),
        ("gh api repos/acme/demo -H 'Accept: x' -H 'Y: z' -X PATCH --input -", "リポジトリ acme/demo の設定（マージ方式・機能の有効化）を更新"),
        ("gh api repos/acme/demo/labels -H 'A: b' -X POST --input -", "acme/demo にラベルを作成"),
        ("gh api repos/acme/demo/labels/good%20first%20issue -H 'A: b' -X PATCH --input -", "acme/demo のラベル「good first issue」を更新"),
        ("gh api repos/acme/demo/rulesets -H 'A: b' -X POST --input -", "acme/demo にブランチ保護ルールを作成"),
        ("gh api orgs/acme/teams/core/memberships/bob -H 'A: b' -X PUT --input -", "bob をチーム core に追加（未参加なら招待）"),
        ("gh api orgs/acme/teams/core/repos/acme/demo -H 'A: b' -X PUT --input -", "チーム core にリポジトリ demo の権限を付与"),
        ("gh api repos/acme/demo/collaborators/carol -H 'A: b' -X PUT --input -", "carol を acme/demo のコラボレーターに追加（招待）"),
        ("git push -u origin main", "origin に main をプッシュ"),
        ("git config --global pull.rebase true", "git 設定（global）pull.rebase = true"),
        ("git commit -m 'chore: initial project scaffold'", "コミット: chore: initial project scaffold"),
        ("would write README.md", "ファイルを作成: README.md"),
        ("something unknown", "something unknown"),
    ],
)
def test_describe_command(line: str, expected: str):
    assert svc.describe_command(line) == expected


def test_summarize_counts_operations_and_warnings():
    output = (
        "Repository acme/demo ────\n"
        "[dry-run] gh repo create acme/demo --private\n"
        "i [dry-run] would write README.md\n"
        "  {\"a\": 1}\n"
        "WARN branch protection unavailable\n"
        "OK done\n"
    )
    summary = svc.summarize(svc.RunResult(True, output))
    assert summary.operations == ["リポジトリ acme/demo を作成（private）", "ファイルを作成: README.md"]
    assert summary.warnings == ["branch protection unavailable"]
    assert summary.oks == ["done"]


def test_friendly_error_hints():
    assert "gh auth login" in svc.friendly_error("GitHub API error (HTTP 401): Bad credentials")
    assert "admin:org" in svc.friendly_error("GitHub API error (HTTP 403): Resource not accessible")
    assert svc.friendly_error("totally unknown failure") is None


def test_save_simple_settings_preserves_comments(config_file: Path):
    error = svc.save_simple_settings(
        config_file,
        {
            "owner": "acme2",
            "mode": "org",
            "visibility": "public",
            "teams": [{"name": "core", "permission": "maintain", "members": ["bob", "carol"], "maintainers": [], "repos": ["*"], "description": ""}],
            "collaborators": None,
            "protection": {"required_approvals": 2},
            "conventions": {"tag_prefix": "release-"},
            "dev_repos": ["svc-a"],
        },
    )
    assert error is None
    text = config_file.read_text(encoding="utf-8")
    assert text.startswith("# team config")
    from gitteam import config as cfgmod

    cfg = cfgmod.load(config_file)
    assert cfg.owner == "acme2" and cfg.repo.visibility == "public"
    assert cfg.teams[0].members == ["bob", "carol"] and cfg.teams[0].permission == "maintain"
    assert cfg.protection.required_approvals == 2 and cfg.conventions.tag_prefix == "release-"
    assert cfg.dev.repos == ["svc-a"]


def test_save_simple_settings_rejects_invalid(config_file: Path):
    error = svc.save_simple_settings(config_file, {"owner": "", "mode": "org", "visibility": "private"})
    assert error and "owner" in error
