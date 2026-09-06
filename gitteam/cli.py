"""Command line interface for gitteam."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from typer.core import TyperGroup

from . import __version__
from .config import Mode
from .context import AppContext
from .errors import GitTeamError
from .ui import fail


class ErrorHandlingGroup(TyperGroup):
    """Print GitTeamError messages without a traceback and exit 1."""

    def invoke(self, ctx: typer.Context):
        try:
            return super().invoke(ctx)
        except GitTeamError as exc:
            fail(str(exc))
            raise typer.Exit(1) from None


app = typer.Typer(
    name="gitteam",
    cls=ErrorHandlingGroup,
    help="Git/GitHub team bootstrap and operations: repository setup, teams, conventions, onboarding.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
config_app = typer.Typer(help="Manage gitteam.yaml.", no_args_is_help=True)
repo_app = typer.Typer(help="Create and configure repositories.", no_args_is_help=True)
labels_app = typer.Typer(help="Synchronise labels.", no_args_is_help=True)
team_app = typer.Typer(help="Teams, members and permissions.", no_args_is_help=True)
ops_app = typer.Typer(help="Day-to-day operations: branches, commits, PRs, releases, hooks.", no_args_is_help=True)
branch_app = typer.Typer(help="Branch helpers.", no_args_is_help=True)
commit_app = typer.Typer(help="Commit message checks.", no_args_is_help=True)
pr_app = typer.Typer(help="Pull request helpers.", no_args_is_help=True)
hooks_app = typer.Typer(help="Git hooks.", no_args_is_help=True)
dev_app = typer.Typer(help="Developer environment setup and onboarding.", no_args_is_help=True)

app.add_typer(config_app, name="config")
app.add_typer(repo_app, name="repo")
repo_app.add_typer(labels_app, name="labels")
app.add_typer(team_app, name="team")
app.add_typer(ops_app, name="ops")
ops_app.add_typer(branch_app, name="branch")
ops_app.add_typer(commit_app, name="commit")
ops_app.add_typer(pr_app, name="pr")
ops_app.add_typer(hooks_app, name="hooks")
app.add_typer(dev_app, name="dev")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"gitteam {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(None, "--config", "-c", envvar="GITTEAM_CONFIG", help="Path to gitteam.yaml."),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Print mutating git/gh commands instead of running them."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show every external command."),
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True, help="Show version."),
) -> None:
    ctx.obj = AppContext.create(config_path=config, dry_run=dry_run, verbose=verbose)


def _ctx(ctx: typer.Context) -> AppContext:
    return ctx.obj


# --------------------------------------------------------------------------- doctor


@app.command()
def doctor(ctx: typer.Context) -> None:
    """Check git, gh, authentication, configuration and plan capabilities."""
    from .commands import doctor as doctor_cmd

    if not doctor_cmd.run(_ctx(ctx)):
        raise typer.Exit(1)


# --------------------------------------------------------------------------- config


@config_app.command("init")
def config_init(
    ctx: typer.Context,
    owner: str = typer.Option(..., "--owner", "-o", prompt="GitHub organization or user login", help="Repository owner."),
    mode: Mode = typer.Option(Mode.ORG, "--mode", "-m", prompt="Mode (org / org-enterprise / personal)", help="GitHub usage form."),
    output: Path = typer.Option(Path("gitteam.yaml"), "--output", help="Where to write the config."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file."),
) -> None:
    """Write a fully commented gitteam.yaml."""
    from .commands import config_cmd

    config_cmd.init(_ctx(ctx), owner, mode, output, force)


@config_app.command("validate")
def config_validate(ctx: typer.Context) -> None:
    """Validate gitteam.yaml."""
    from .commands import config_cmd

    config_cmd.validate(_ctx(ctx))


@config_app.command("show")
def config_show(ctx: typer.Context) -> None:
    """Print the effective configuration (defaults applied)."""
    from .commands import config_cmd

    config_cmd.show(_ctx(ctx))


@config_app.command("capabilities")
def config_capabilities(
    ctx: typer.Context,
    visibility: Optional[str] = typer.Option(None, "--visibility", help="private | public | internal (default: repo.visibility)."),
) -> None:
    """Show which GitHub features are available for the configured mode/plan."""
    from .commands import config_cmd

    config_cmd.capabilities(_ctx(ctx), visibility)


# --------------------------------------------------------------------------- repo


@repo_app.command("init")
def repo_init(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(None, help="Repository name (or owner/name). Defaults to the current repository."),
    visibility: Optional[str] = typer.Option(None, "--visibility", help="private | public | internal."),
    description: Optional[str] = typer.Option(None, "--description", "-d"),
    directory: Optional[Path] = typer.Option(None, "--dir", help="Where to clone / scaffold (default: ./NAME)."),
    no_scaffold: bool = typer.Option(False, "--no-scaffold", help="Skip community files, workflows and hooks."),
    no_settings: bool = typer.Option(False, "--no-settings", help="Skip merge/branch settings."),
    no_labels: bool = typer.Option(False, "--no-labels", help="Skip label sync."),
    no_protect: bool = typer.Option(False, "--no-protect", help="Skip branch protection."),
    no_access: bool = typer.Option(False, "--no-access", help="Skip team/collaborator permissions."),
    no_push: bool = typer.Option(False, "--no-push", help="Write scaffold files but do not commit/push."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing scaffold files."),
) -> None:
    """Create (or adopt) a repository and apply the full team configuration."""
    from .commands import repo as repo_cmd

    opts = repo_cmd.InitOptions(
        name=name,
        visibility=visibility,
        description=description,
        directory=directory,
        scaffold=not no_scaffold,
        settings=not no_settings,
        labels=not no_labels,
        protect=not no_protect,
        access=not no_access,
        push=not no_push,
        force=force,
    )
    repo_cmd.init_repo(_ctx(ctx), opts)


@repo_app.command("settings")
def repo_settings(ctx: typer.Context, name: Optional[str] = typer.Argument(None)) -> None:
    """Apply merge strategy / branch deletion / feature toggles from gitteam.yaml."""
    from .commands import repo as repo_cmd

    repo_cmd.apply_settings(_ctx(ctx), repo_cmd.resolve_target(_ctx(ctx), name))


@repo_app.command("protect")
def repo_protect(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(None),
    visibility: Optional[str] = typer.Option(None, "--visibility", help="Override detected visibility."),
) -> None:
    """Apply branch protection (rulesets or classic) to the configured branches."""
    from .commands import repo as repo_cmd

    app_ctx = _ctx(ctx)
    target = repo_cmd.resolve_target(app_ctx, name)
    detected = visibility
    if detected is None:
        data = app_ctx.gh.repo_get(target.owner, target.name)
        detected = str(data.get("visibility", "private")) if data else app_ctx.config.repo.visibility
    repo_cmd.apply_protection(app_ctx, target, detected)


@repo_app.command("access")
def repo_access(ctx: typer.Context, name: Optional[str] = typer.Argument(None)) -> None:
    """Grant configured teams / collaborators access to the repository."""
    from .commands import repo as repo_cmd

    repo_cmd.apply_access(_ctx(ctx), repo_cmd.resolve_target(_ctx(ctx), name))


@labels_app.command("sync")
def labels_sync(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(None),
    prune: bool = typer.Option(False, "--prune", help="Delete labels that are not in gitteam.yaml."),
) -> None:
    """Create/update labels to match gitteam.yaml."""
    from .commands import repo as repo_cmd

    repo_cmd.sync_labels(_ctx(ctx), repo_cmd.resolve_target(_ctx(ctx), name), prune)


# --------------------------------------------------------------------------- team


@team_app.command("sync")
def team_sync(
    ctx: typer.Context,
    repo: list[str] = typer.Option([], "--repo", "-r", help="Limit repository permissions to these repos."),
    skip_repos: bool = typer.Option(False, "--skip-repos", help="Only create teams and memberships."),
) -> None:
    """Create teams, add members and grant repository permissions from gitteam.yaml."""
    from .commands import team as team_cmd

    team_cmd.sync(_ctx(ctx), repo or None, skip_repos)


@team_app.command("invite")
def team_invite(
    ctx: typer.Context,
    user: str = typer.Argument(..., help="GitHub login."),
    team: Optional[str] = typer.Option(None, "--team", "-t", help="Team name or slug (org modes)."),
    role: str = typer.Option("member", "--role", help="Organization role: member | admin."),
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="Repository for direct collaborator access."),
    permission: str = typer.Option("push", "--permission", "-p", help="pull | triage | push | maintain | admin."),
) -> None:
    """Invite a user to the organization/team, or as a repository collaborator."""
    from .commands import team as team_cmd

    team_cmd.invite(_ctx(ctx), user, team, role, repo, permission)


@team_app.command("list")
def team_list(ctx: typer.Context) -> None:
    """List teams and members (or configured collaborators in personal mode)."""
    from .commands import team as team_cmd

    team_cmd.list_teams(_ctx(ctx))


# --------------------------------------------------------------------------- ops


@branch_app.command("new")
def branch_new(
    ctx: typer.Context,
    branch_type: str = typer.Argument(..., metavar="TYPE", help="feature | fix | hotfix | chore | docs | ..."),
    description: str = typer.Argument(..., help="Short description; converted to a slug."),
    issue: Optional[int] = typer.Option(None, "--issue", "-i", help="Issue number to embed."),
    base: Optional[str] = typer.Option(None, "--base", "-b", help="Base branch (default: repo.default_branch)."),
) -> None:
    """Create a branch that follows the naming convention, from the latest base."""
    from .commands import ops as ops_cmd

    ops_cmd.branch_new(_ctx(ctx), branch_type, description, issue, base)


@branch_app.command("check")
def branch_check(ctx: typer.Context, name: Optional[str] = typer.Argument(None, help="Defaults to the current branch.")) -> None:
    """Validate a branch name against the convention (exit 1 on violation)."""
    from .commands import ops as ops_cmd

    if not ops_cmd.branch_check(_ctx(ctx), name):
        raise typer.Exit(1)


@commit_app.command("check")
def commit_check(
    ctx: typer.Context,
    rev_range: Optional[str] = typer.Option(None, "--range", help="git revision range (default: origin/<default>..HEAD)."),
    message_file: Optional[Path] = typer.Option(None, "--message-file", help="Validate a commit message file (commit-msg hook)."),
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Validate a literal message."),
) -> None:
    """Validate commit messages against Conventional Commits (exit 1 on violation)."""
    from .commands import ops as ops_cmd

    if not ops_cmd.commit_check(_ctx(ctx), rev_range, message_file, message):
        raise typer.Exit(1)


@pr_app.command("create")
def pr_create(
    ctx: typer.Context,
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Defaults to the single commit subject or the branch name."),
    base: Optional[str] = typer.Option(None, "--base", "-b"),
    draft: bool = typer.Option(False, "--draft"),
    reviewer: list[str] = typer.Option([], "--reviewer", help="Additional reviewers (user or org/team)."),
    label: list[str] = typer.Option([], "--label", help="Additional labels."),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip branch/commit/title convention checks."),
) -> None:
    """Push the branch and open a pull request with the team template, labels and reviewers."""
    from .commands import ops as ops_cmd

    ops_cmd.pr_create(_ctx(ctx), title=title, base=base, draft=draft, reviewers=reviewer, labels=label, no_verify=no_verify)


@ops_app.command("release")
def release(
    ctx: typer.Context,
    version: str = typer.Argument(..., help="Semantic version, e.g. 1.4.0 or v1.4.0."),
    prerelease: bool = typer.Option(False, "--prerelease"),
    draft: bool = typer.Option(False, "--draft"),
    allow_dirty: bool = typer.Option(False, "--allow-dirty", help="Do not require a clean working tree."),
) -> None:
    """Tag the default branch and publish a GitHub Release with generated notes."""
    from .commands import ops as ops_cmd

    ops_cmd.release(_ctx(ctx), version, prerelease=prerelease, draft=draft, allow_dirty=allow_dirty)


@hooks_app.command("install")
def hooks_install(
    ctx: typer.Context,
    shared: Optional[bool] = typer.Option(None, "--shared/--local", help="Shared .githooks (default from config) or .git/hooks."),
) -> None:
    """Install commit-msg and pre-push hooks that enforce the conventions."""
    from .commands import ops as ops_cmd

    ops_cmd.hooks_install(_ctx(ctx), shared)


# --------------------------------------------------------------------------- dev


@dev_app.command("setup")
def dev_setup(
    ctx: typer.Context,
    name: Optional[str] = typer.Option(None, "--name", help="user.name"),
    email: Optional[str] = typer.Option(None, "--email", help="user.email"),
    scope: str = typer.Option("global", "--scope", help="global | local"),
    signing_key: Optional[str] = typer.Option(None, "--signing-key", help="SSH public key path or GPG key id."),
    skip_gh: bool = typer.Option(False, "--skip-gh", help="Do not touch gh authentication."),
) -> None:
    """Apply the team git configuration, aliases, line endings and gh credential helper."""
    from .commands import dev as dev_cmd

    if scope not in ("global", "local"):
        raise typer.BadParameter("--scope must be global or local")
    dev_cmd.setup(_ctx(ctx), name=name, email=email, scope=scope, signing_key=signing_key, skip_gh=skip_gh)


@dev_app.command("onboard")
def dev_onboard(
    ctx: typer.Context,
    directory: Path = typer.Option(Path.cwd(), "--dir", help="Directory to clone team repositories into."),
    name: Optional[str] = typer.Option(None, "--name"),
    email: Optional[str] = typer.Option(None, "--email"),
    skip_gh: bool = typer.Option(False, "--skip-gh"),
) -> None:
    """New member onboarding: dev setup + clone dev.repos + enable hooks."""
    from .commands import dev as dev_cmd

    dev_cmd.onboard(_ctx(ctx), directory=directory, name=name, email=email, skip_gh=skip_gh)


@dev_app.command("show")
def dev_show(ctx: typer.Context) -> None:
    """Show the effective git configuration relevant to the team workflow."""
    from .commands import dev as dev_cmd

    dev_cmd.show(_ctx(ctx))


# --------------------------------------------------------------------------- entry point


def run() -> None:
    try:
        app()
    except GitTeamError as exc:
        fail(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    run()
