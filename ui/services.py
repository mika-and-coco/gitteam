"""Bridge between the Streamlit UI and the gitteam command layer.

* Commands print through ``gitteam.ui``; here that output is captured as plain text.
* Every mutating action follows one flow: ``stage_action`` runs it in dry-run mode
  and stores the plan, ``render_action`` shows the plan in plain language and offers
  a single "execute" button that re-runs the very same call for real.
"""

from __future__ import annotations

import contextlib
import io
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

import streamlit as st
import yaml
from rich.console import Console
from ruamel.yaml import YAML

from gitteam import config as cfgmod
from gitteam import ui as rich_ui
from gitteam.context import AppContext
from gitteam.errors import GitTeamError
from gitteam.gitcmd import Git
from gitteam.runner import Runner

OUTPUT_WIDTH = 120


@dataclass
class RunResult:
    ok: bool
    output: str
    error: str | None = None
    value: Any = None


@dataclass
class ActionState:
    fn: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    cwd: Path | None
    plan: RunResult
    result: RunResult | None = None


@dataclass
class Summary:
    operations: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    hint: str | None = None


# --------------------------------------------------------------------------- state


def init_state() -> None:
    """Initialise app-wide session state (called from the entry point on every run)."""
    st.session_state.setdefault("verbose", False)
    pending = st.session_state.pop("pending_cfg_path", None)
    if pending:
        st.session_state.cfg_path = str(Path(pending).expanduser().resolve())
    if "cfg_path" not in st.session_state:
        found = cfgmod.find_config()
        default = Path.cwd() / cfgmod.CONFIG_FILENAME
        if found and check_config_path(found) is None:
            st.session_state.cfg_path = str(found.resolve())
        else:
            st.session_state.cfg_path = str(default.resolve())
    # The YAML editor keeps its text per widget key; drop it whenever the target file changes.
    if st.session_state.get("_editor_path") != st.session_state.cfg_path:
        st.session_state.pop("config_editor", None)
        st.session_state["_editor_path"] = st.session_state.cfg_path


def reset_config_editor() -> None:
    """Forget the YAML editor text so it is reloaded from disk on the next run."""
    st.session_state.pop("config_editor", None)


def config_path() -> Path:
    raw = st.session_state.get("cfg_path") or cfgmod.CONFIG_FILENAME
    return Path(raw).expanduser().resolve()


def make_context(dry_run: bool) -> AppContext:
    path = config_path()
    usable = path.is_file() and check_config_path(path) is None and cfgmod.is_trusted(path)
    # An unusable (missing / disallowed / untrusted) path must not fall back to directory discovery;
    # commands then see "no config" consistently with what the page shows.
    return AppContext.create(
        config_path=path if usable else None,
        discover=usable,
        dry_run=dry_run,
        verbose=st.session_state.get("verbose", False),
    )


def allowed_config_dirs() -> list[Path]:
    """Directories a config file may live in when chosen from the UI."""
    return [Path.cwd().resolve(), *[d.resolve() for d in cfgmod.user_config_dirs()]]


def _within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def check_config_path(path: Path) -> str | None:
    """Reject paths that are not YAML files inside an allowed directory (prevents arbitrary file access)."""
    if path.suffix.lower() not in (".yaml", ".yml"):
        return "設定ファイルには .yaml / .yml ファイルのみ指定できます。"
    resolved = path.expanduser().resolve()
    if not any(_within(resolved, directory) for directory in allowed_config_dirs()):
        places = "、".join(str(d) for d in allowed_config_dirs())
        return f"この場所の設定ファイルは使えません。使用できる場所: {places}"
    return None


def trust_status(path: Path) -> str:
    """'trusted' | 'untrusted' (found in the working tree, not yet trusted) | 'missing'."""
    if not path.is_file():
        return "missing"
    return "trusted" if cfgmod.is_trusted(path) else "untrusted"


def trust_current_config() -> None:
    path = config_path()
    if check_config_path(path) is None and path.is_file():
        cfgmod.trust_path(path)


def load_config() -> tuple[cfgmod.Config | None, str | None]:
    """Return ``(config, error)`` for the configured path without raising."""
    path = config_path()
    problem = check_config_path(path)
    if problem:
        return None, problem
    if not path.is_file():
        return None, f"設定ファイルがまだありません: {path}"
    if not cfgmod.is_trusted(path):
        return None, (
            f"このフォルダーで見つかった設定ファイル（{path}）はまだ信頼されていません。"
            "内容を確認したうえで、サイドバーの「この設定ファイルを信頼する」を押してください。"
        )
    try:
        return cfgmod.load(path), None
    except GitTeamError as exc:
        return None, str(exc)


def readable_config_text(path: Path) -> tuple[str | None, str | None]:
    """Return the raw text only if the file looks like a gitteam config (never arbitrary files)."""
    problem = check_config_path(path)
    if problem:
        return None, problem
    text = path.read_text(encoding="utf-8", errors="replace")
    is_named_config = path.name.lower().endswith(cfgmod.CONFIG_FILENAME)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        if is_named_config:
            return text, f"YAML の書き方に誤りがあります（修正して保存してください）: {exc}"
        return None, f"YAML の書き方に誤りがあります: {exc}"
    if not isinstance(data, dict) or not ({"owner", "mode"} & set(data)):
        if is_named_config:
            return text, "owner / mode が見つかりません。設定として読めるように修正してください。"
        return None, "gitteam の設定ファイル（owner / mode を含む YAML）ではないため表示しません。"
    return text, None


def validate_yaml_text(text: str) -> tuple[cfgmod.Config | None, str | None]:
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        return None, f"YAML の書き方に誤りがあります: {exc}"
    try:
        return cfgmod.from_dict(data), None
    except GitTeamError as exc:
        return None, str(exc)


def effective_yaml(cfg: cfgmod.Config) -> str:
    return yaml.safe_dump(cfgmod.to_dict(cfg), sort_keys=False, allow_unicode=True)


# --------------------------------------------------------------------------- simple (form) editing


def _yaml_rt() -> YAML:
    rt = YAML()
    rt.preserve_quotes = True
    rt.width = 4096
    return rt


def save_simple_settings(path: Path, values: dict[str, Any]) -> str | None:
    """Update selected keys of gitteam.yaml while preserving comments. Returns an error or None.

    ``values`` keys: owner, mode, visibility, teams, collaborators, protection (dict),
    conventions (dict), dev_repos (list).
    """
    rt = _yaml_rt()
    doc = rt.load(path.read_text(encoding="utf-8")) or {}
    doc["owner"] = values["owner"]
    doc["mode"] = values["mode"]
    doc.setdefault("repo", {})["visibility"] = values["visibility"]
    if values.get("teams") is not None:
        doc["teams"] = values["teams"]
    if values.get("collaborators") is not None:
        doc["collaborators"] = values["collaborators"]
    if values["mode"] == "personal":
        doc["teams"] = []
    protection = doc.setdefault("protection", {})
    for key, value in values.get("protection", {}).items():
        protection[key] = value
    conventions = doc.setdefault("conventions", {})
    for key, value in values.get("conventions", {}).items():
        conventions[key] = value
    if values.get("dev_repos") is not None:
        doc.setdefault("dev", {})["repos"] = values["dev_repos"]
    buffer = io.StringIO()
    rt.dump(doc, buffer)
    text = buffer.getvalue()
    _, error = validate_yaml_text(text)
    if error:
        return error
    path.write_text(text, encoding="utf-8", newline="\n")
    return None


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
        soft_wrap=True,
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


def _state_key(key: str) -> str:
    # Namespaced so action keys never collide with widget/form keys in session state.
    return f"action::{key}"


def stage_action(key: str, fn: Callable[..., Any], *args: Any, cwd: Path | None = None, **kwargs: Any) -> None:
    """Run ``fn(ctx, *args, **kwargs)`` in dry-run mode and remember it for execution."""
    plan = run_captured(fn, make_context(dry_run=True), *args, cwd=cwd, **kwargs)
    st.session_state[_state_key(key)] = ActionState(fn, args, kwargs, cwd, plan)


def run_direct(key: str, fn: Callable[..., Any], *args: Any, cwd: Path | None = None, **kwargs: Any) -> None:
    """Run a read-only command immediately and remember the result."""
    st.session_state[_state_key(key)] = run_captured(fn, make_context(dry_run=True), *args, cwd=cwd, **kwargs)


def clear(key: str) -> None:
    st.session_state.pop(_state_key(key), None)


# --------------------------------------------------------------------------- summarising output

_DRY_PREFIX_RE = re.compile(r"^(?:i\s+)?\[dry-run\]\s+(.*)$")
_API_RE = re.compile(r"^gh api (\S+)(?: .*?-X (\w+))?")

_GIT_RULES: list[tuple[re.Pattern[str], Callable[[re.Match[str]], str]]] = [
    (re.compile(r"^git add -A"), lambda m: "変更をコミット対象に追加"),
    (re.compile(r"^git update-index --chmod=\+x"), lambda m: "git hooks を実行可能にする"),
    (re.compile(r"^git commit -m (.+)$"), lambda m: f"コミット: {m.group(1).strip(chr(39))}"),
    (re.compile(r"^git push (?:-u )?(\S+) (\S+)"), lambda m: f"{m.group(1)} に {m.group(2).replace('refs/tags/', 'タグ ')} をプッシュ"),
    (re.compile(r"^git fetch"), lambda m: "リモートの最新状態を取得"),
    (re.compile(r"^git switch -c (\S+)"), lambda m: f"ブランチ {m.group(1)} を作成して切り替え"),
    (re.compile(r"^git tag -a (\S+)"), lambda m: f"タグ {m.group(1)} を作成"),
    (re.compile(r"^git symbolic-ref HEAD refs/heads/(\S+)"), lambda m: f"既定ブランチ名を {m.group(1)} に設定"),
    (re.compile(r"^git config --(\w+) (\S+) (.+)$"), lambda m: f"git 設定（{m.group(1)}）{m.group(2)} = {m.group(3).strip(chr(39))}"),
    (re.compile(r"^git clone \S+ (\S+)"), lambda m: f"{m.group(1)} にクローン"),
    (re.compile(r"^gh repo create (\S+) --(\w+)"), lambda m: f"リポジトリ {m.group(1)} を作成（{m.group(2)}）"),
    (re.compile(r"^gh repo clone (\S+)"), lambda m: f"{m.group(1)} をローカルにクローン"),
    (re.compile(r"^gh pr create .*--title (\S+|'[^']*')"), lambda m: f"プルリクエストを作成: {m.group(1).strip(chr(39))}"),
    (re.compile(r"^gh release create (\S+)"), lambda m: f"リリース {m.group(1)} を公開"),
    (re.compile(r"^gh auth setup-git"), lambda m: "gh を git の認証ヘルパーとして設定"),
    (re.compile(r"^would write (.+)$"), lambda m: f"ファイルを作成: {m.group(1)}"),
    (re.compile(r"^would clone (\S+) into (.+)$"), lambda m: f"{m.group(1)} を {m.group(2)} にクローン"),
]


def _describe_api(endpoint: str, method: str) -> str | None:
    path = endpoint.split("?", 1)[0]
    parts = [unquote(p) for p in path.split("/")]
    if parts[0] == "repos" and len(parts) >= 3:
        owner, repo, rest = parts[1], parts[2], parts[3:]
        full = f"{owner}/{repo}"
        if not rest and method == "PATCH":
            return f"リポジトリ {full} の設定（マージ方式・機能の有効化）を更新"
        if rest == ["topics"]:
            return f"{full} のトピックを設定"
        if rest == ["labels"] and method == "POST":
            return f"{full} にラベルを作成"
        if len(rest) == 2 and rest[0] == "labels":
            verb = {"PATCH": "を更新", "DELETE": "を削除"}.get(method, "を変更")
            return f"{full} のラベル「{rest[1]}」{verb}"
        if rest == ["rulesets"] and method == "POST":
            return f"{full} にブランチ保護ルールを作成"
        if len(rest) == 2 and rest[0] == "rulesets":
            return f"{full} のブランチ保護ルールを更新"
        if len(rest) >= 3 and rest[0] == "branches" and rest[2] == "protection":
            if len(rest) == 4 and rest[3] == "required_signatures":
                return f"{full} のブランチ {rest[1]} の署名必須設定を{'有効化' if method == 'POST' else '解除'}"
            return f"{full} のブランチ {rest[1]} を保護"
        if len(rest) == 2 and rest[0] == "collaborators":
            return f"{rest[1]} を {full} のコラボレーターに追加（招待）"
    if parts[0] == "orgs" and len(parts) >= 2:
        org, rest = parts[1], parts[2:]
        if rest == ["teams"] and method == "POST":
            return f"組織 {org} にチームを作成"
        if len(rest) == 4 and rest[0] == "teams" and rest[2] == "memberships":
            return f"{rest[3]} をチーム {rest[1]} に追加（未参加なら招待）"
        if len(rest) == 5 and rest[0] == "teams" and rest[2] == "repos":
            return f"チーム {rest[1]} にリポジトリ {rest[4]} の権限を付与"
        if len(rest) == 2 and rest[0] == "memberships":
            return f"{rest[1]} を組織 {org} に招待"
    return None


def describe_command(line: str) -> str:
    """Turn a dry-run command line into a short Japanese description."""
    command = line.strip()
    api = _API_RE.match(command)
    if api:
        described = _describe_api(api.group(1), api.group(2) or "GET")
        if described:
            return described
    for pattern, render in _GIT_RULES:
        match = pattern.match(command)
        if match:
            return render(match)
    return command


_ERROR_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"not found on PATH", re.I), "必要なコマンドが見つかりません。git と gh（GitHub CLI）がインストールされているか確認してください。"),
    (re.compile(r"HTTP 401|Bad credentials|not logged in", re.I), "GitHub にログインできていません。ターミナルで `gh auth login` を実行してください。"),
    (re.compile(r"HTTP 404|not found on GitHub|Not Found", re.I), "見つかりませんでした。オーナー名・リポジトリ名・チーム名の綴りと、そのアカウントへのアクセス権を確認してください。組織のチームを扱う場合は `gh auth refresh -s admin:org` で gh の権限が必要なこともあります。"),
    (re.compile(r"HTTP 403|Resource not accessible|Must have admin", re.I), "権限が足りません。組織の管理者であることを確認し、`gh auth refresh -s admin:org` で gh の権限を追加してください。"),
    (re.compile(r"HTTP 422", re.I), "GitHub がこの設定を受け付けませんでした。すでに存在するか、現在のプラン / 可視性では使えない設定の可能性があります。"),
    (re.compile(r"no gitteam\.yaml", re.I), "設定ファイルがありません。「はじめに」ページで作成してください。"),
    (re.compile(r"not inside a git repository|not a git repository", re.I), "指定した場所は git リポジトリではありません。「ローカルリポジトリのパス」を確認してください。"),
    (re.compile(r"already exists", re.I), "同じ名前のものがすでに存在します。別の名前にするか、既存のものを利用してください。"),
    (re.compile(r"working tree is not clean", re.I), "コミットしていない変更が残っています。先にコミットするか、変更を退避してください。"),
    (re.compile(r"does not match pattern|violates naming", re.I), "名前がチームの命名規則に合っていません。「日々の作業」ページのブランチ名ビルダーで作り直せます。"),
    (re.compile(r"Conventional Commits|unknown type", re.I), "コミットメッセージの形式が規約と異なります（例: `feat: ログイン画面を追加`）。"),
    (re.compile(r"differs from origin", re.I), "ローカルとリモートの main がずれています。先に pull または push して揃えてください。"),
]


def friendly_error(message: str | None) -> str | None:
    if not message:
        return None
    for pattern, hint in _ERROR_HINTS:
        if pattern.search(message):
            return hint
    return None


def summarize(result: RunResult) -> Summary:
    summary = Summary(hint=friendly_error(result.error))
    for raw in result.output.splitlines():
        line = raw.rstrip()
        dry = _DRY_PREFIX_RE.match(line.strip())
        if dry:
            summary.operations.append(describe_command(dry.group(1)))
        elif line.startswith("OK "):
            summary.oks.append(line[3:].strip())
        elif line.startswith("WARN "):
            summary.warnings.append(line[5:].strip())
    return summary


def render_summary(result: RunResult, *, planned: bool) -> None:
    summary = summarize(result)
    if result.error:
        st.error(summary.hint or result.error, icon=":material/error:")
        if summary.hint:
            st.caption(f"詳細: {result.error}")
    if planned:
        if summary.operations:
            st.markdown(f"**これから行う操作（{len(summary.operations)} 件）**")
            for op in summary.operations:
                st.markdown(f"- {op}")
        elif result.ok:
            st.info("変更が必要な項目はありませんでした（すでに設定どおり、または対象なし）。", icon=":material/check_circle:")
    elif result.ok:
        st.success("完了しました。", icon=":material/check_circle:")
        for line in summary.oks:
            st.markdown(f"- :material/check: {line}")
    if summary.warnings:
        st.warning("**注意**\n\n" + "\n".join(f"- {w}" for w in summary.warnings), icon=":material/warning:")
    if result.output.strip():
        with st.expander("詳細ログ（実行したコマンドと出力）", icon=":material/terminal:"):
            st.code(result.output.rstrip(), language=None)


def render_action(key: str, *, execute_label: str = "この内容で実行する", empty_hint: str = "") -> None:
    """Show the staged plan, the execute button, and the final result for ``key``."""
    state = st.session_state.get(_state_key(key))
    if not isinstance(state, ActionState):
        if empty_hint:
            st.caption(empty_hint)
        return
    with st.container(border=True):
        if state.result is None:
            st.markdown("#### 確認結果")
            render_summary(state.plan, planned=True)
            with st.container(horizontal=True):
                if state.plan.ok and st.button(execute_label, type="primary", icon=":material/play_arrow:", key=f"{key}_exec"):
                    with st.spinner("実行中..."):
                        state.result = run_captured(
                            state.fn, make_context(dry_run=False), *state.args, cwd=state.cwd, **state.kwargs
                        )
                    st.rerun()
                if st.button("やり直す", icon=":material/undo:", key=f"{key}_reset"):
                    clear(key)
                    st.rerun()
        else:
            st.markdown("#### 実行結果")
            render_summary(state.result, planned=False)
            if st.button("閉じる", icon=":material/close:", key=f"{key}_close"):
                clear(key)
                st.rerun()


def render_direct(key: str, *, empty_hint: str = "") -> None:
    """Show the result of a read-only command (output is the content itself)."""
    result = st.session_state.get(_state_key(key))
    if not isinstance(result, RunResult):
        if empty_hint:
            st.caption(empty_hint)
        return
    if result.error:
        hint = friendly_error(result.error)
        st.error(hint or result.error, icon=":material/error:")
        if hint:
            st.caption(f"詳細: {result.error}")
    if result.output.strip():
        st.code(result.output.rstrip(), language=None)


# --------------------------------------------------------------------------- environment


@st.cache_data(ttl="5m", show_spinner=False)
def gh_login() -> str | None:
    if not shutil.which("gh"):
        return None
    proc = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, encoding="utf-8")
    return (proc.stdout.strip() or None) if proc.returncode == 0 else None


@st.cache_data(ttl="5m", show_spinner=False)
def tool_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for tool in ("git", "gh"):
        if not shutil.which(tool):
            versions[tool] = None
            continue
        proc = subprocess.run([tool, "--version"], capture_output=True, text=True, encoding="utf-8")
        versions[tool] = proc.stdout.strip().splitlines()[0] if proc.returncode == 0 and proc.stdout else None
    return versions


def refresh_environment() -> None:
    gh_login.clear()
    tool_versions.clear()


def local_repo_info(path: Path) -> dict[str, str | None]:
    """Branch / remote information for a local clone (None values when not a repo)."""
    runner = Runner()
    empty = {"is_repo": None, "branch": None, "remote": None, "toplevel": None}
    try:
        if not path.is_dir() or not Git.is_repo(path, runner):
            return empty
        git = Git(runner, path)
        return {
            "is_repo": "yes",
            "branch": git.current_branch() or "(detached)",
            "remote": git.remote_url(),
            "toplevel": str(git.toplevel()),
        }
    except GitTeamError:
        return empty
