from __future__ import annotations

import os
import platform
from pathlib import Path

from ..context import AppContext
from ..errors import GitTeamError
from ..gitcmd import Git
from ..ui import DRY_RUN, info, ok, table, warn
from . import ops as ops_cmd

RELEVANT_KEYS = (
    "user.name",
    "user.email",
    "init.defaultBranch",
    "pull.rebase",
    "fetch.prune",
    "push.autoSetupRemote",
    "core.autocrlf",
    "core.hooksPath",
    "commit.gpgsign",
    "gpg.format",
    "user.signingkey",
)


def _line_ending_value(setting: str) -> str:
    if setting == "auto":
        return "true" if platform.system() == "Windows" else "input"
    return {"lf": "input", "crlf": "true"}[setting]


def setup(
    ctx: AppContext,
    *,
    name: str | None,
    email: str | None,
    scope: str,
    signing_key: str | None,
    skip_gh: bool,
) -> None:
    cfg = ctx.config_or_default()
    git = Git(ctx.runner, Path.cwd())
    if scope == "local" and not Git.is_repo(Path.cwd(), ctx.runner):
        raise GitTeamError("--scope local requires running inside a git repository")
    rows: list[tuple[str, str]] = []

    def set_key(key: str, value: str) -> None:
        git.config_set(key, value, scope=scope)
        rows.append((key, value))

    if name:
        set_key("user.name", name)
    elif not git.config_get("user.name"):
        warn("user.name is not set; pass --name \"Your Name\"")
    if email:
        set_key("user.email", email)
    elif not git.config_get("user.email"):
        warn("user.email is not set; pass --email you@example.com")

    for key, value in cfg.dev.git_config.items():
        set_key(key, value)
    set_key("core.autocrlf", _line_ending_value(cfg.dev.line_endings))
    for alias, command in cfg.dev.aliases.items():
        set_key(f"alias.{alias}", command)

    if cfg.dev.signing != "none":
        if cfg.dev.signing == "ssh":
            set_key("gpg.format", "ssh")
        if signing_key:
            set_key("user.signingkey", signing_key)
            set_key("commit.gpgsign", "true")
            set_key("tag.gpgsign", "true")
        else:
            warn(f"dev.signing is '{cfg.dev.signing}' but no --signing-key was given; commit signing left unchanged")

    table(f"git config --{scope}", ["key", "value"], rows)

    if not skip_gh:
        if ctx.gh.auth_ok():
            ok("gh is authenticated")
            ctx.gh.run(["auth", "setup-git"])
            ok("git credential helper configured for github.com via gh")
        else:
            warn("gh is not authenticated. Run: gh auth login   (then re-run `gitteam dev setup`)")
    ok("developer setup complete" + (" (dry-run)" if ctx.dry_run else ""))


def onboard(ctx: AppContext, *, directory: Path, name: str | None, email: str | None, skip_gh: bool) -> None:
    cfg = ctx.config
    setup(ctx, name=name, email=email, scope="global", signing_key=None, skip_gh=skip_gh)
    if not cfg.dev.repos:
        info("dev.repos is empty in gitteam.yaml; nothing to clone")
        return
    if not ctx.dry_run:
        directory.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str]] = []
    for repo in cfg.dev.repos:
        dest = directory / repo
        if Git.is_repo(dest, ctx.runner):
            rows.append((repo, "already cloned"))
        else:
            if ctx.dry_run:
                info(f"{DRY_RUN} would clone {cfg.owner}/{repo} into {dest}")
            else:
                ctx.gh.repo_clone(cfg.owner, repo, dest)
            rows.append((repo, "cloned"))
        if dest.exists() and Git.is_repo(dest, ctx.runner):
            hooks_dir = dest / ".githooks"
            git = Git(ctx.runner, dest)
            if hooks_dir.is_dir():
                git.config_set("core.hooksPath", ".githooks", scope="local")
                rows.append((repo, "shared hooks enabled"))
            else:
                previous = Path.cwd()
                try:
                    os.chdir(dest)
                    ops_cmd.hooks_install(ctx, shared=False)
                finally:
                    os.chdir(previous)
                rows.append((repo, "local hooks installed"))
    table(f"Onboarding into {directory}", ["repository", "result"], rows)
    ok("onboarding complete" + (" (dry-run)" if ctx.dry_run else ""))


def show(ctx: AppContext) -> None:
    git = Git(ctx.runner, Path.cwd())
    rows = [(key, git.config_get(key) or "-") for key in RELEVANT_KEYS]
    table("Effective git configuration", ["key", "value"], rows)
    aliases = git._run("config", "--get-regexp", r"^alias\.", check=False).stdout.strip()
    if aliases:
        table("Aliases", ["alias", "command"], [tuple(line.split(" ", 1)) for line in aliases.splitlines()])
