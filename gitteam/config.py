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

from .errors import ConfigError, UntrustedConfigError

CONFIG_FILENAME = "gitteam.yaml"
TRUST_FILENAME = "trusted-configs.txt"
ENV_CONFIG = "GITTEAM_CONFIG"
ENV_CONFIG_HOME = "GITTEAM_CONFIG_HOME"

VISIBILITIES = ("private", "public", "internal")
PERMISSIONS = ("pull", "triage", "push", "maintain", "admin")
PROTECTION_ENGINES = ("auto", "ruleset", "classic")
SQUASH_TITLES = ("PR_TITLE", "COMMIT_OR_PR_TITLE")
SQUASH_MESSAGES = ("PR_BODY", "COMMIT_MESSAGES", "BLANK")

# Values that end up inside generated shell hooks / workflow YAML must stay within a safe alphabet.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_SAFE_GLOB_RE = re.compile(r"^[A-Za-z0-9._/*?-]+$")
_SAFE_REGEX_RE = re.compile(r"^[A-Za-z0-9._/\\\-\[\]()^$*+?|{},:=!<>]+$")
_SAFE_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_SAFE_REPO_RE = re.compile(r"^(?!\.{1,2}$)[A-Za-z0-9_.-]+$")  # GitHub repository name, no path separators
_SAFE_TEMPLATE_NAME_RE = re.compile(r"^[A-Za-z0-9_.+-]+$")  # github/gitignore template names such as C++
_TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")  # GitHub topic: lowercase, digits, hyphens, max 50
_PATTERN_CHARS = "*?["
ORG_ROLES = ("member", "admin")

# git config keys `dev setup` may write. Anything that makes git execute a program
# (core.fsmonitor, core.sshCommand, credential.helper, core.hooksPath, core.pager, alias "!", ...) is excluded.
ALLOWED_GIT_CONFIG_KEYS = frozenset(
    key.lower()
    for key in (
        "init.defaultBranch",
        "pull.rebase",
        "pull.ff",
        "fetch.prune",
        "fetch.pruneTags",
        "push.autoSetupRemote",
        "push.default",
        "push.followTags",
        "rebase.autoStash",
        "rebase.autoSquash",
        "rebase.updateRefs",
        "rerere.enabled",
        "rerere.autoUpdate",
        "merge.conflictStyle",
        "merge.ff",
        "diff.algorithm",
        "diff.colorMoved",
        "diff.renames",
        "core.longpaths",
        "core.autocrlf",
        "core.eol",
        "core.safecrlf",
        "core.ignorecase",
        "core.whitespace",
        "core.fileMode",
        "core.quotePath",
        "color.ui",
        "column.ui",
        "commit.gpgsign",
        "commit.verbose",
        "tag.gpgsign",
        "tag.sort",
        "gpg.format",
        "user.signingkey",
        "branch.autoSetupRebase",
        "branch.sort",
        "status.showUntrackedFiles",
        "status.branch",
        "log.date",
        "help.autocorrect",
        "credential.useHttpPath",
        "submodule.recurse",
        "advice.detachedHead",
        "apply.whitespace",
    )
)


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


DEFAULT_BRANCH_TYPES = ("feature", "fix", "hotfix", "chore", "docs", "refactor", "test", "release")
_BRANCH_SLUG_RE = r"[a-z0-9][a-z0-9._-]*"


def branch_pattern_for(branch_types: list[str] | tuple[str, ...]) -> str:
    """Regex accepting ``<type>/<slug>`` for exactly the given branch types."""
    alternation = "|".join(re.escape(t) for t in branch_types) or "[a-z]+"
    return f"^({alternation})/{_BRANCH_SLUG_RE}$"


DEFAULT_BRANCH_PATTERN = branch_pattern_for(DEFAULT_BRANCH_TYPES)


@dataclass
class ConventionsConfig:
    branch_types: list[str] = field(default_factory=lambda: list(DEFAULT_BRANCH_TYPES))
    # Left at the default (or omitted), the pattern follows `branch_types`; set it to override.
    branch_pattern: str = DEFAULT_BRANCH_PATTERN
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
    conv = cfg.conventions
    if conv.branch_pattern == DEFAULT_BRANCH_PATTERN and list(conv.branch_types) != list(DEFAULT_BRANCH_TYPES):
        # `branch_types` was customised but the pattern was not: keep hooks/CI consistent with the builder.
        conv.branch_pattern = branch_pattern_for(conv.branch_types)


def validate(cfg: Config) -> None:
    problems: list[str] = []
    if not cfg.owner or not cfg.owner.strip():
        problems.append("owner: must be set to the GitHub organization or user login")
    if cfg.repo.visibility not in VISIBILITIES:
        problems.append(f"repo.visibility: must be one of {', '.join(VISIBILITIES)}")
    if cfg.repo.visibility == "internal" and cfg.mode is not Mode.ORG_ENTERPRISE:
        problems.append("repo.visibility: 'internal' is only available with mode 'org-enterprise'")
    if cfg.repo.squash_merge_commit_title not in SQUASH_TITLES:
        problems.append(f"repo.squash_merge_commit_title: must be one of {', '.join(SQUASH_TITLES)}")
    if cfg.repo.squash_merge_commit_message not in SQUASH_MESSAGES:
        problems.append(f"repo.squash_merge_commit_message: must be one of {', '.join(SQUASH_MESSAGES)}")
    if not (cfg.repo.allow_squash_merge or cfg.repo.allow_merge_commit or cfg.repo.allow_rebase_merge):
        problems.append("repo: at least one of allow_squash_merge / allow_merge_commit / allow_rebase_merge must be true")
    if cfg.protection.engine not in PROTECTION_ENGINES:
        problems.append(f"protection.engine: must be one of {', '.join(PROTECTION_ENGINES)}")
    if cfg.protection.required_approvals < 0 or cfg.protection.required_approvals > 6:
        problems.append("protection.required_approvals: must be between 0 and 6")
    seen_labels: set[str] = set()
    for label in cfg.labels:
        if not re.fullmatch(r"[0-9a-fA-F]{6}", label.color):
            problems.append(f"labels: '{label.name}' color must be a 6-digit hex without '#'")
        if not label.name.strip():
            problems.append("labels: every label needs a name")
        elif label.name.lower() in seen_labels:
            problems.append(f"labels: '{label.name}' is listed more than once (GitHub label names are case-insensitive)")
        seen_labels.add(label.name.lower())
    if cfg.protection.engine == "classic":
        for branch in cfg.protection.branches:
            if any(ch in branch for ch in _PATTERN_CHARS):
                problems.append(
                    f"protection.branches: '{branch}' is a pattern; classic protection only accepts branch names "
                    "(use engine: ruleset or auto)"
                )
    from .scaffold import COMPONENTS  # local import: scaffold depends on this module

    for component in cfg.scaffold.include:
        if component not in COMPONENTS:
            problems.append(f"scaffold.include: unknown component '{component}' (known: {', '.join(COMPONENTS)})")
    for team in cfg.teams:
        if not team.name.strip():
            problems.append("teams: every team needs a name")
        if team.permission not in PERMISSIONS:
            problems.append(f"teams.{team.name}.permission: must be one of {', '.join(PERMISSIONS)}")
        if team.privacy not in ("closed", "secret"):
            problems.append(f"teams.{team.name}.privacy: must be 'closed' or 'secret'")
        for login in team.members:
            if not _SAFE_LOGIN_RE.match(login):
                problems.append(f"teams.{team.name}.members: '{login}' is not a valid GitHub login")
        for login in team.maintainers:
            if not _SAFE_LOGIN_RE.match(login):
                problems.append(f"teams.{team.name}.maintainers: '{login}' is not a valid GitHub login")
        for repo in team.repos:
            if repo != "*" and not _SAFE_REPO_RE.match(repo):
                problems.append(f"teams.{team.name}.repos: '{repo}' is not a valid repository name (or '*')")
    for collab in cfg.collaborators:
        if not _SAFE_LOGIN_RE.match(collab.user):
            problems.append(f"collaborators: '{collab.user}' is not a valid GitHub login")
        if collab.permission not in PERMISSIONS:
            problems.append(f"collaborators.{collab.user}.permission: must be one of {', '.join(PERMISSIONS)}")
        for repo in collab.repos:
            if repo != "*" and not _SAFE_REPO_RE.match(repo):
                problems.append(f"collaborators.{collab.user}.repos: '{repo}' is not a valid repository name (or '*')")
    for topic in cfg.repo.topics:
        if not _TOPIC_RE.match(topic):
            problems.append(f"repo.topics: '{topic}' must be lowercase letters, digits and hyphens (max 50 characters)")
    if cfg.repo.license is not None and not _SAFE_TEMPLATE_NAME_RE.match(cfg.repo.license):
        problems.append(f"repo.license: '{cfg.repo.license}' is not a valid license key (e.g. mit, apache-2.0)")
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
    problems.extend(_safety_problems(cfg))
    if problems:
        raise ConfigError("invalid configuration:\n  - " + "\n  - ".join(problems))


def is_valid_login(value: str) -> bool:
    return bool(_SAFE_LOGIN_RE.match(value or ""))


def is_valid_repo_name(value: str) -> bool:
    return bool(_SAFE_REPO_RE.match(value or ""))


def _safety_problems(cfg: Config) -> list[str]:
    """Reject values that could inject into generated hooks/workflows or make git run programs."""
    problems: list[str] = []
    if cfg.owner and not _SAFE_LOGIN_RE.match(cfg.owner):
        problems.append("owner: must be a GitHub login (letters, digits, hyphens)")
    if not _SAFE_REGEX_RE.match(cfg.conventions.branch_pattern):
        problems.append(
            "conventions.branch_pattern: contains characters that are not allowed in generated hooks "
            "(quotes, whitespace, ;, &, backticks, #). Allowed: letters, digits and . _ / \\ - [ ] ( ) ^ $ * + ? | { } , : = ! < >"
        )
    named: list[tuple[str, list[str]]] = [
        ("conventions.branch_types", cfg.conventions.branch_types),
        ("conventions.commit_types", cfg.conventions.commit_types),
        ("conventions.commit_scopes", cfg.conventions.commit_scopes),
        ("conventions.protected_branches", cfg.conventions.protected_branches),
    ]
    for label, values in named:
        for value in values:
            if not _SAFE_NAME_RE.match(value):
                problems.append(f"{label}: '{value}' may only contain letters, digits and . _ / -")
    for repo in cfg.dev.repos:
        if not _SAFE_REPO_RE.match(repo):
            problems.append(f"dev.repos: '{repo}' is not a valid repository name (letters, digits, . _ - only)")
    for name in cfg.repo.gitignore_templates:
        if not _SAFE_TEMPLATE_NAME_RE.match(name):
            problems.append(f"repo.gitignore_templates: '{name}' is not a valid template name")
    if cfg.conventions.tag_prefix and not _SAFE_NAME_RE.match(cfg.conventions.tag_prefix):
        problems.append("conventions.tag_prefix: may only contain letters, digits and . _ / -")
    if not _SAFE_NAME_RE.match(cfg.repo.default_branch):
        problems.append("repo.default_branch: may only contain letters, digits and . _ / -")
    for branch in cfg.protection.branches:
        if not _SAFE_GLOB_RE.match(branch):
            problems.append(f"protection.branches: '{branch}' may only contain letters, digits and . _ / - * ?")
    for key, value in cfg.dev.git_config.items():
        if key.lower() not in ALLOWED_GIT_CONFIG_KEYS:
            problems.append(
                f"dev.git_config: '{key}' is not an allowed key. gitteam only writes settings that cannot make git "
                f"execute programs. Allowed keys: {', '.join(sorted(ALLOWED_GIT_CONFIG_KEYS))}"
            )
        if "\n" in value or "\r" in value:
            problems.append(f"dev.git_config: '{key}' value must be a single line")
    for alias, command in cfg.dev.aliases.items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", alias):
            problems.append(f"dev.aliases: '{alias}' is not a valid alias name")
        if command.lstrip().startswith("!"):
            problems.append(f"dev.aliases: '{alias}' runs a shell command ('!...'); shell aliases are not allowed")
        if "\n" in command or "\r" in command:
            problems.append(f"dev.aliases: '{alias}' must be a single line")
    return problems


# --------------------------------------------------------------------------- discovery & trust


def user_config_dir() -> Path:
    """Directory owned by the user for gitteam state (config, trusted list)."""
    env = os.environ.get(ENV_CONFIG_HOME)
    if env:
        return Path(env)
    return Path.home() / ".config" / "gitteam"


def user_config_dirs() -> list[Path]:
    dirs = [user_config_dir()]
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(Path(appdata) / "gitteam")
    return dirs


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except (ValueError, OSError):
        return False


def _trust_file() -> Path:
    return user_config_dir() / TRUST_FILENAME


def trusted_paths() -> set[Path]:
    file = _trust_file()
    if not file.is_file():
        return set()
    return {Path(line.strip()) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()}


def is_trusted(path: Path) -> bool:
    """Configs in user-owned directories are always trusted; others need an explicit `config trust`."""
    resolved = path.resolve()
    if any(_is_within(resolved, directory) for directory in user_config_dirs()):
        return True
    return resolved in trusted_paths()


def trust_path(path: Path) -> None:
    file = _trust_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    entries = trusted_paths()
    entries.add(path.resolve())
    file.write_text("\n".join(sorted(str(p) for p in entries)) + "\n", encoding="utf-8")


def untrust_path(path: Path) -> bool:
    entries = trusted_paths()
    resolved = path.resolve()
    if resolved not in entries:
        return False
    entries.discard(resolved)
    _trust_file().write_text("\n".join(sorted(str(p) for p in entries)) + ("\n" if entries else ""), encoding="utf-8")
    return True


@dataclass(frozen=True)
class DiscoveredConfig:
    path: Path
    source: str  # explicit | env | cwd | user

    @property
    def needs_trust(self) -> bool:
        return self.source == "cwd"


def candidate_paths(start: Path | None = None) -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get(ENV_CONFIG)
    if env:
        paths.append(Path(env))
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        paths.append(directory / CONFIG_FILENAME)
    for directory in user_config_dirs():
        paths.append(directory / CONFIG_FILENAME)
    return paths


def discover_config(explicit: Path | None = None, start: Path | None = None) -> DiscoveredConfig | None:
    """Locate gitteam.yaml and report where it came from.

    Order: --config (explicit) > GITTEAM_CONFIG (env) > current directory and its parents (cwd)
    > user config directories (user). Files found via ``cwd`` may have been shipped inside a
    cloned repository and therefore require :func:`is_trusted` before use.
    """
    if explicit:
        if not explicit.exists():
            raise ConfigError(f"config file not found: {explicit}")
        return DiscoveredConfig(explicit, "explicit")
    env = os.environ.get(ENV_CONFIG)
    if env and Path(env).is_file():
        return DiscoveredConfig(Path(env), "env")
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return DiscoveredConfig(candidate, "cwd")
    for directory in user_config_dirs():
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return DiscoveredConfig(candidate, "user")
    return None


def find_config(explicit: Path | None = None) -> Path | None:
    found = discover_config(explicit)
    return found.path if found else None


def require_trusted(found: DiscoveredConfig) -> None:
    if found.needs_trust and not is_trusted(found.path):
        raise UntrustedConfigError(
            f"gitteam.yaml found inside the working tree is not trusted yet: {found.path}\n"
            "A config shipped with a cloned repository can change git settings and generated hooks. "
            "Review it, then run `gitteam config trust` (or pass --config PATH to use it once)."
        )


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
