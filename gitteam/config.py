from __future__ import annotations

import dataclasses
import os
import re
import types
import typing
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError

CONFIG_FILENAME = "gitteam.yaml"
ENV_CONFIG = "GITTEAM_CONFIG"

VISIBILITIES = ("private", "public", "internal")
PERMISSIONS = ("pull", "triage", "push", "maintain", "admin")
PROTECTION_ENGINES = ("auto", "ruleset", "classic")


class Mode(str, Enum):
    """How the team uses GitHub. Drives which features are available."""

    ORG = "org"  # Organization on Free or Team plan
    ORG_ENTERPRISE = "org-enterprise"  # Organization on Enterprise Cloud
    PERSONAL = "personal"  # Repositories under a personal account

    @property
    def is_org(self) -> bool:
        return self is not Mode.PERSONAL


class Plan(str, Enum):
    AUTO = "auto"
    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"

    @property
    def is_paid(self) -> bool:
        return self in (Plan.PRO, Plan.TEAM, Plan.ENTERPRISE)


@dataclass
class RepoDefaults:
    visibility: str = "private"
    default_branch: str = "main"
    description: str = ""
    delete_branch_on_merge: bool = True
    allow_squash_merge: bool = True
    allow_merge_commit: bool = False
    allow_rebase_merge: bool = False
    allow_auto_merge: bool = True
    allow_update_branch: bool = True
    squash_merge_commit_title: str = "PR_TITLE"
    squash_merge_commit_message: str = "PR_BODY"
    has_issues: bool = True
    has_wiki: bool = False
    has_projects: bool = False
    gitignore_templates: list[str] = field(default_factory=list)
    license: str | None = None
    topics: list[str] = field(default_factory=list)


@dataclass
class Label:
    name: str
    color: str
    description: str = ""


@dataclass
class ProtectionConfig:
    branches: list[str] = field(default_factory=lambda: ["main"])
    engine: str = "auto"  # auto | ruleset | classic
    required_approvals: int = 1
    dismiss_stale_reviews: bool = True
    require_code_owner_reviews: bool = True
    require_last_push_approval: bool = False
    require_conversation_resolution: bool = True
    required_linear_history: bool = True
    require_signed_commits: bool = False
    enforce_admins: bool = True
    status_checks: list[str] = field(default_factory=list)
    strict_status_checks: bool = True
    allow_force_pushes: bool = False
    allow_deletions: bool = False


@dataclass
class ScaffoldConfig:
    enabled: bool = True
    include: list[str] = field(
        default_factory=lambda: [
            "readme",
            "gitignore",
            "license",
            "editorconfig",
            "gitattributes",
            "codeowners",
            "pr_template",
            "issue_templates",
            "contributing",
            "workflows",
            "githooks",
        ]
    )
    # CODEOWNERS entries: path pattern -> owners. "{owner}" expands to the configured owner.
    codeowners: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class TeamConfig:
    name: str
    description: str = ""
    privacy: str = "closed"  # closed | secret
    members: list[str] = field(default_factory=list)
    maintainers: list[str] = field(default_factory=list)
    permission: str = "push"
    repos: list[str] = field(default_factory=lambda: ["*"])


@dataclass
class Collaborator:
    user: str
    permission: str = "push"
    repos: list[str] = field(default_factory=lambda: ["*"])


@dataclass
class ConventionsConfig:
    branch_types: list[str] = field(
        default_factory=lambda: ["feature", "fix", "hotfix", "chore", "docs", "refactor", "test", "release"]
    )
    branch_pattern: str = r"^(feature|fix|hotfix|chore|docs|refactor|test|release)/[a-z0-9][a-z0-9._-]*$"
    protected_branches: list[str] = field(default_factory=lambda: ["main", "develop"])
    require_issue_in_branch: bool = False
    commit_types: list[str] = field(
        default_factory=lambda: [
            "feat",
            "fix",
            "docs",
            "style",
            "refactor",
            "perf",
            "test",
            "build",
            "ci",
            "chore",
            "revert",
        ]
    )
    commit_scopes: list[str] = field(default_factory=list)
    require_scope: bool = False
    commit_subject_max: int = 72
    tag_prefix: str = "v"
    pr_reviewers: list[str] = field(default_factory=list)
    pr_labels_by_type: dict[str, str] = field(
        default_factory=lambda: {"feat": "enhancement", "fix": "bug", "docs": "documentation", "chore": "chore"}
    )
    branch_type_to_commit_type: dict[str, str] = field(
        default_factory=lambda: {
            "feature": "feat",
            "fix": "fix",
            "hotfix": "fix",
            "chore": "chore",
            "docs": "docs",
            "refactor": "refactor",
            "test": "test",
            "release": "chore",
        }
    )


@dataclass
class DevSetupConfig:
    git_config: dict[str, str] = field(
        default_factory=lambda: {
            "init.defaultBranch": "main",
            "pull.rebase": "true",
            "fetch.prune": "true",
            "push.autoSetupRemote": "true",
            "rebase.autoStash": "true",
            "rerere.enabled": "true",
            "merge.conflictStyle": "zdiff3",
            "diff.algorithm": "histogram",
            "core.longpaths": "true",
        }
    )
    aliases: dict[str, str] = field(
        default_factory=lambda: {
            "st": "status -sb",
            "co": "checkout",
            "sw": "switch",
            "br": "branch",
            "lg": "log --oneline --graph --decorate --all",
            "last": "log -1 HEAD --stat",
            "unstage": "reset HEAD --",
        }
    )
    line_endings: str = "auto"  # auto | lf | crlf
    signing: str = "none"  # none | ssh | gpg
    shared_hooks: bool = True
    repos: list[str] = field(default_factory=list)


def default_labels() -> list[Label]:
    return [
        Label("bug", "d73a4a", "不具合・想定どおりに動作しない"),
        Label("enhancement", "a2eeef", "新機能・機能改善の要望"),
        Label("documentation", "0075ca", "ドキュメントの追加・修正"),
        Label("chore", "cfd3d7", "保守作業・ツール・依存関係の更新"),
        Label("refactor", "fbca04", "機能追加でもバグ修正でもないコード改善"),
        Label("question", "d876e3", "質問・追加情報が必要"),
        Label("good first issue", "7057ff", "初めての貢献に適した課題"),
        Label("help wanted", "008672", "協力者を募集中"),
        Label("duplicate", "cfd3d7", "既存の Issue / PR と重複"),
        Label("wontfix", "ffffff", "対応しない"),
        Label("priority: high", "b60205", "最優先で対応"),
        Label("priority: medium", "fbca04", "通常の優先度"),
        Label("priority: low", "0e8a16", "余裕があれば対応"),
        Label("status: blocked", "e11d21", "他の課題や外部要因により着手不可"),
        Label("breaking-change", "b60205", "後方互換性のない変更を含む"),
        Label("security", "ee0701", "セキュリティに関する事項"),
        Label("dependencies", "0366d6", "依存パッケージの更新"),
    ]


@dataclass
class Config:
    owner: str
    mode: Mode = Mode.ORG
    plan: Plan = Plan.AUTO
    repo: RepoDefaults = field(default_factory=RepoDefaults)
    labels: list[Label] = field(default_factory=default_labels)
    protection: ProtectionConfig = field(default_factory=ProtectionConfig)
    scaffold: ScaffoldConfig = field(default_factory=ScaffoldConfig)
    teams: list[TeamConfig] = field(default_factory=list)
    collaborators: list[Collaborator] = field(default_factory=list)
    conventions: ConventionsConfig = field(default_factory=ConventionsConfig)
    dev: DevSetupConfig = field(default_factory=DevSetupConfig)
    source_path: Path | None = field(default=None, init=False, compare=False)

    @property
    def effective_plan(self) -> Plan:
        if self.mode is Mode.ORG_ENTERPRISE:
            return Plan.ENTERPRISE
        return self.plan


# --------------------------------------------------------------------------- loading


def _coerce(tp: Any, value: Any, path: str) -> Any:
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin in (typing.Union, types.UnionType):
        if value is None:
            return None
        inner = [a for a in args if a is not type(None)]
        return _coerce(inner[0], value, path)
    if dataclasses.is_dataclass(tp) and isinstance(tp, type):
        if not isinstance(value, dict):
            raise ConfigError(f"{path}: expected a mapping")
        return _build(tp, value, path)
    if origin is list:
        if not isinstance(value, list):
            raise ConfigError(f"{path}: expected a list")
        return [_coerce(args[0], v, f"{path}[{i}]") for i, v in enumerate(value)]
    if origin is dict:
        if not isinstance(value, dict):
            raise ConfigError(f"{path}: expected a mapping")
        return {str(k): _coerce(args[1], v, f"{path}.{k}") for k, v in value.items()}
    if isinstance(tp, type) and issubclass(tp, Enum):
        try:
            return tp(value)
        except ValueError:
            allowed = ", ".join(e.value for e in tp)
            raise ConfigError(f"{path}: {value!r} is not one of: {allowed}") from None
    if tp is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{path}: expected true/false")
        return value
    if tp is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{path}: expected an integer")
        return value
    if tp is str:
        if value is None or isinstance(value, (dict, list)):
            raise ConfigError(f"{path}: expected a string")
        return str(value)
    return value


def _build(cls: type, data: dict[str, Any], path: str) -> Any:
    hints = typing.get_type_hints(cls)
    fields = [f for f in dataclasses.fields(cls) if f.init]
    known = {f.name for f in fields}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ConfigError(
            f"{path}: unknown key(s): {', '.join(unknown)} (allowed: {', '.join(sorted(known))})"
        )
    kwargs = {f.name: _coerce(hints[f.name], data[f.name], f"{path}.{f.name}") for f in fields if f.name in data}
    missing = [
        f.name
        for f in fields
        if f.name not in kwargs
        and f.default is dataclasses.MISSING
        and f.default_factory is dataclasses.MISSING  # type: ignore[misc]
    ]
    if missing:
        raise ConfigError(f"{path}: missing required key(s): {', '.join(missing)}")
    return cls(**kwargs)


def from_dict(data: dict[str, Any]) -> Config:
    if not isinstance(data, dict):
        raise ConfigError("config: top level must be a mapping")
    cfg: Config = _build(Config, data, "config")
    _apply_mode_defaults(cfg)
    validate(cfg)
    return cfg


def default_config(owner: str = "", mode: Mode = Mode.ORG) -> Config:
    cfg = Config(owner=owner, mode=mode)
    _apply_mode_defaults(cfg)
    return cfg


def _apply_mode_defaults(cfg: Config) -> None:
    if not cfg.scaffold.codeowners:
        cfg.scaffold.codeowners = {"*": ["@{owner}/core"] if cfg.mode.is_org else ["@{owner}"]}


def validate(cfg: Config) -> None:
    problems: list[str] = []
    if not cfg.owner or not cfg.owner.strip():
        problems.append("owner: must be set to the GitHub organization or user login")
    if cfg.repo.visibility not in VISIBILITIES:
        problems.append(f"repo.visibility: must be one of {', '.join(VISIBILITIES)}")
    if cfg.repo.visibility == "internal" and cfg.mode is not Mode.ORG_ENTERPRISE:
        problems.append("repo.visibility: 'internal' is only available with mode 'org-enterprise'")
    if cfg.protection.engine not in PROTECTION_ENGINES:
        problems.append(f"protection.engine: must be one of {', '.join(PROTECTION_ENGINES)}")
    if cfg.protection.required_approvals < 0 or cfg.protection.required_approvals > 6:
        problems.append("protection.required_approvals: must be between 0 and 6")
    for label in cfg.labels:
        if not re.fullmatch(r"[0-9a-fA-F]{6}", label.color):
            problems.append(f"labels: '{label.name}' color must be a 6-digit hex without '#'")
    for team in cfg.teams:
        if team.permission not in PERMISSIONS:
            problems.append(f"teams.{team.name}.permission: must be one of {', '.join(PERMISSIONS)}")
        if team.privacy not in ("closed", "secret"):
            problems.append(f"teams.{team.name}.privacy: must be 'closed' or 'secret'")
    for collab in cfg.collaborators:
        if collab.permission not in PERMISSIONS:
            problems.append(f"collaborators.{collab.user}.permission: must be one of {', '.join(PERMISSIONS)}")
    if cfg.mode is Mode.PERSONAL and cfg.teams:
        problems.append("teams: GitHub teams are not available for mode 'personal'; use 'collaborators' instead")
    try:
        re.compile(cfg.conventions.branch_pattern)
    except re.error as exc:
        problems.append(f"conventions.branch_pattern: invalid regex ({exc})")
    if cfg.conventions.commit_subject_max < 20:
        problems.append("conventions.commit_subject_max: must be at least 20")
    if cfg.dev.line_endings not in ("auto", "lf", "crlf"):
        problems.append("dev.line_endings: must be auto, lf or crlf")
    if cfg.dev.signing not in ("none", "ssh", "gpg"):
        problems.append("dev.signing: must be none, ssh or gpg")
    if problems:
        raise ConfigError("invalid configuration:\n  - " + "\n  - ".join(problems))


def candidate_paths(start: Path | None = None) -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get(ENV_CONFIG)
    if env:
        paths.append(Path(env))
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        paths.append(directory / CONFIG_FILENAME)
    home = Path.home()
    paths.append(home / ".config" / "gitteam" / CONFIG_FILENAME)
    appdata = os.environ.get("APPDATA")
    if appdata:
        paths.append(Path(appdata) / "gitteam" / CONFIG_FILENAME)
    return paths


def find_config(explicit: Path | None = None) -> Path | None:
    if explicit:
        if not explicit.exists():
            raise ConfigError(f"config file not found: {explicit}")
        return explicit
    for path in candidate_paths():
        if path.is_file():
            return path
    return None


def load(path: Path) -> Config:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: YAML parse error: {exc}") from exc
    try:
        cfg = from_dict(raw)
    except ConfigError as exc:
        raise ConfigError(f"{path}: {exc}") from None
    cfg.source_path = path
    return cfg


def to_dict(cfg: Config) -> dict[str, Any]:
    def convert(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Path):
            return str(value)
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {f.name: convert(getattr(value, f.name)) for f in dataclasses.fields(value) if f.init}
        if isinstance(value, list):
            return [convert(v) for v in value]
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        return value

    return convert(cfg)
