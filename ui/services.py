"""Bridge between the Streamlit UI and the gitteam command layer.

Every command prints through ``gitteam.ui``; here that output is redirected into a
plain-text buffer so pages can show it with ``st.code``.
"""

from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import streamlit as st
import yaml
from rich.console import Console

from gitteam import config as cfgmod
from gitteam import ui as rich_ui
from gitteam.context import AppContext
from gitteam.errors import GitTeamError
from gitteam.gitcmd import Git
from gitteam.runner import Runner

OUTPUT_WIDTH = 110


@dataclass
class RunResult:
    ok: bool
    output: str
    error: str | None = None
    value: Any = None


# --------------------------------------------------------------------------- state


def init_state() -> None:
    """Initialise app-wide session state (called from the entry point on every run)."""
    st.session_state.setdefault("dry_run", True)
    st.session_state.setdefault("verbose", False)
    # A page may request a new config path; apply it before the sidebar widget renders.
    pending = st.session_state.pop("pending_cfg_path", None)
    if pending:
        st.session_state.cfg_path = pending
    if "cfg_path" not in st.session_state:
        found = cfgmod.find_config()
        st.session_state.cfg_path = str(found) if found else str(Path.cwd() / cfgmod.CONFIG_FILENAME)


def config_path() -> Path:
    return Path(st.session_state.get("cfg_path") or cfgmod.CONFIG_FILENAME).expanduser()


def make_context(dry_run: bool | None = None) -> AppContext:
    effective = st.session_state.get("dry_run", True) if dry_run is None else dry_run
    path = config_path()
    return AppContext.create(
        config_path=path if path.is_file() else None,
        dry_run=effective,
        verbose=st.session_state.get("verbose", False),
    )


def load_config() -> tuple[cfgmod.Config | None, str | None]:
    """Return ``(config, error)`` for the configured path without raising."""
    path = config_path()
    if not path.is_file():
        return None, f"設定ファイルが見つかりません: {path}"
    try:
        return cfgmod.load(path), None
    except GitTeamError as exc:
        return None, str(exc)


def validate_yaml_text(text: str) -> tuple[cfgmod.Config | None, str | None]:
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        return None, f"YAML の構文エラー: {exc}"
    try:
        return cfgmod.from_dict(data), None
    except GitTeamError as exc:
        return None, str(exc)


def effective_yaml(cfg: cfgmod.Config) -> str:
    return yaml.safe_dump(cfgmod.to_dict(cfg), sort_keys=False, allow_unicode=True)


# --------------------------------------------------------------------------- execution


def run_captured(fn: Callable[..., Any], *args: Any, cwd: Path | None = None, **kwargs: Any) -> RunResult:
    """Run a command function, capturing rich output as plain text."""
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=False,
        color_system=None,
        width=OUTPUT_WIDTH,
        emoji=False,
        highlight=False,
        soft_wrap=False,
    )
    with rich_ui.redirected(console):
        try:
            with contextlib.chdir(cwd) if cwd else contextlib.nullcontext():
                value = fn(*args, **kwargs)
            return RunResult(True, buffer.getvalue(), value=value)
        except GitTeamError as exc:
            return RunResult(False, buffer.getvalue(), error=str(exc))
        except Exception as exc:  # noqa: BLE001 - surface unexpected errors in the UI
            return RunResult(False, buffer.getvalue(), error=f"{type(exc).__name__}: {exc}")


def render_result(result: RunResult | None, *, empty_hint: str = "まだ実行していません。") -> None:
    if result is None:
        st.caption(empty_hint)
        return
    if result.error:
        st.error(result.error, icon=":material/error:")
    elif result.ok:
        st.success("完了", icon=":material/check_circle:")
    if result.output.strip():
        st.code(result.output.rstrip(), language=None, height=min(600, 60 + 20 * result.output.count("\n")))


def dry_run_notice() -> bool:
    """Show a hint when the global dry-run switch is on. Returns the switch value."""
    dry = bool(st.session_state.get("dry_run", True))
    if dry:
        st.caption(":material/visibility: サイドバーの dry-run が ON のため、実行しても変更は加えられません。")
    return dry


# --------------------------------------------------------------------------- environment


@st.cache_data(ttl="5m", show_spinner=False)
def gh_login() -> str | None:
    if not shutil.which("gh"):
        return None
    proc = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, encoding="utf-8")
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def tool_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for tool in ("git", "gh"):
        if not shutil.which(tool):
            versions[tool] = None
            continue
        proc = subprocess.run([tool, "--version"], capture_output=True, text=True, encoding="utf-8")
        versions[tool] = proc.stdout.strip().splitlines()[0] if proc.returncode == 0 and proc.stdout else None
    return versions


def local_repo_info(path: Path) -> dict[str, str | None]:
    """Branch / remote information for a local clone (None values when not a repo)."""
    runner = Runner()
    if not path.is_dir() or not Git.is_repo(path, runner):
        return {"is_repo": None, "branch": None, "remote": None, "toplevel": None}
    git = Git(runner, path)
    return {
        "is_repo": "yes",
        "branch": git.current_branch() or "(detached)",
        "remote": git.remote_url(),
        "toplevel": str(git.toplevel()),
    }
