"""Headless smoke tests for the Streamlit UI (no browser, no GitHub mutations)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "ui" / "streamlit_app.py"
PAGES = ["overview", "config_page", "repo_page", "team_page", "ops_page", "dev_page"]


def _app(config_path: Path | None) -> AppTest:
    at = AppTest.from_file(str(ENTRY), default_timeout=60)
    at.session_state["cfg_path"] = str(config_path) if config_path else str(ROOT / "nonexistent.yaml")
    return at


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "gitteam.yaml"
    path.write_text("owner: acme\nmode: org\nteams:\n  - name: core\n    members: [bob]\n", encoding="utf-8")
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


def test_sidebar_shows_config_badge(config_file: Path):
    at = _app(config_file).run()
    assert not at.exception
    assert at.session_state["dry_run"] is True


def test_config_page_validates_editor(config_file: Path):
    at = _app(config_file).run()
    at.switch_page("app_pages/config_page.py").run()
    at.text_area(key="config_editor").set_value("owner: acme\nmode: nope\n")
    at.button[0].click().run()  # 検証
    assert any("is not one of" in e.value for e in at.error)
    assert not at.exception


def test_config_page_generates_file(tmp_path: Path):
    target = tmp_path / "new" / "gitteam.yaml"
    at = _app(target).run()
    at.switch_page("app_pages/config_page.py").run()
    at.text_input[0].set_value("acme")
    at.text_input[1].set_value(str(target))
    at.button[0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert target.exists()


def test_ops_page_branch_builder(config_file: Path):
    at = _app(config_file).run()
    at.switch_page("app_pages/ops_page.py").run()
    at.text_input(key="ops_repo_path").set_value(str(config_file.parent)).run()
    inputs = [w for w in at.text_input if w.label.startswith("説明")]
    inputs[0].set_value("Add Login Page").run()
    assert any("feature/add-login-page" in s.value for s in at.success)
    assert not at.exception
