from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import labels as labelmod
from .. import protection as protmod
from .. import scaffold as scaffoldmod
from ..config import Mode
from ..context import AppContext
from ..errors import GhApiError, GitTeamError
from ..gitcmd import Git
from ..ui import DRY_RUN, info, ok, step, table, warn


@dataclass
class InitOptions:
    name: str | None
    visibility: str | None = None
    description: str | None = None
    directory: Path | None = None
    scaffold: bool = True
    settings: bool = True
    labels: bool = True
    protect: bool = True
    access: bool = True
    push: bool = True
    force: bool = False


@dataclass
class RepoTarget:
    owner: str
    name: str
    workdir: Path | None = None

    @property
    def full(self) -> str:
        return f"{self.owner}/{self.name}"


def _list_or_empty(ctx: AppContext, fetch):
    """In dry-run the repository may not exist yet; treat 404 on list endpoints as empty."""
    try:
        return fetch()
    except GhApiError as exc:
        if exc.status == 404 and ctx.dry_run:
            info("repository does not exist yet; assuming an empty state for planning")
            return []
        raise


def resolve_target(ctx: AppContext, name: str | None) -> RepoTarget:
    """Resolve ``owner/name``: explicit name, or the GitHub remote of the current repository."""
    cfg = ctx.config
    if name:
        if "/" in name:
            owner, repo = name.split("/", 1)
            if owner != cfg.owner:
                warn(f"repository owner '{owner}' differs from configured owner '{cfg.owner}'")
            return RepoTarget(owner, repo)
        return RepoTarget(cfg.owner, name)
    cwd = Path.cwd()
    if Git.is_repo(cwd, ctx.runner):
        git = Git(ctx.runner, cwd)
        owner, repo = git.github_repo()
        return RepoTarget(owner, repo, git.toplevel())
    raise GitTeamError("no repository name given and the current directory is not a git repository")


# --------------------------------------------------------------------------- init


def init_repo(ctx: AppContext, opts: InitOptions) -> None:
    cfg = ctx.config
    gh = ctx.gh
    target = resolve_target(ctx, opts.name)
    visibility = opts.visibility or cfg.repo.visibility
    summary: list[tuple[str, str]] = []

    step(f"Repository {target.full}")
    existing = gh.repo_get(target.owner, target.name)
    if existing is None:
        info(f"creating {visibility} repository {target.full}")
        gh.repo_create(target.owner, target.name, visibility, opts.description or cfg.repo.description)
        summary.append(("repository", f"created ({visibility})"))
    else:
        visibility = str(existing.get("visibility") or ("private" if existing.get("private") else "public"))
        info(f"repository exists ({visibility}); applying configuration")
        summary.append(("repository", f"exists ({visibility})"))

    if opts.scaffold and cfg.scaffold.enabled:
        step("Scaffold")
        summary.append(("scaffold", _scaffold(ctx, target, opts, existing is None)))
    if opts.settings:
        step("Repository settings")
        apply_settings(ctx, target)
        summary.append(("settings", "applied"))
    if opts.labels:
        step("Labels")
        summary.append(("labels", sync_labels(ctx, target, prune=False)))
    if opts.protect:
        step("Branch protection")
        summary.append(("protection", apply_protection(ctx, target, visibility)))
    if opts.access:
        step("Access")
        summary.append(("access", apply_access(ctx, target)))

    table(f"Summary for {target.full}", ["step", "result"], summary)
    ok(f"done: https://github.com/{target.full}")


def _scaffold(ctx: AppContext, target: RepoTarget, opts: InitOptions, newly_created: bool) -> str:
    cfg = ctx.config
    gh = ctx.gh
    workdir = target.workdir or opts.directory or (Path.cwd() / target.name)
    git = Git(ctx.runner, workdir)
    cloned_now = False
    if Git.is_repo(workdir, ctx.runner):
        remote = git.remote_url()
        parsed = Git.parse_github_remote(remote) if remote else None
        if parsed and parsed[1].lower() != target.name.lower():
            raise GitTeamError(f"{workdir} is a clone of {parsed[0]}/{parsed[1]}, not {target.full}")
    elif workdir.exists() and any(workdir.iterdir()):
        raise GitTeamError(f"{workdir} exists and is not empty; pass --dir to choose another location")
    else:
        if ctx.dry_run:
            info(f"{DRY_RUN} would clone {target.full} into {workdir}")
        else:
            info(f"cloning {target.full} into {workdir}")
            gh.repo_clone(target.owner, target.name, workdir)
        cloned_now = True
    can_touch_files = workdir.exists() and Git.is_repo(workdir, ctx.runner)
    if can_touch_files and not git.has_commits():
        git.set_head_branch(cfg.repo.default_branch)

    result = scaffoldmod.materialize(
        workdir,
        cfg,
        target.name,
        gitignore_source=gh.gitignore_template,
        license_source=gh.license_text,
        force=opts.force,
        dry_run=ctx.dry_run or not can_touch_files,
    )
    verb = f"{DRY_RUN} would write" if ctx.dry_run else "wrote"
    for path in result.written:
        info(f"{verb} {path.relative_to(workdir)}")
    if result.skipped and ctx.runner.verbose:
        info("kept existing: " + ", ".join(str(p.relative_to(workdir)) for p in result.skipped))
    if not result.changed:
        info("scaffold already up to date")
        return "up to date"
    if not opts.push:
        return f"{len(result.written)} file(s) written (not committed)"
    git.add_all()
    git.chmod_executable(*result.executable)
    message = "chore: initial project scaffold" if newly_created or cloned_now else "chore: add team conventions scaffold"
    git.commit(message)
    git.push("origin", cfg.repo.default_branch, set_upstream=True)
    return f"{len(result.written)} file(s) committed and pushed"


# --------------------------------------------------------------------------- settings


def settings_payload(ctx: AppContext, target: RepoTarget) -> dict[str, Any]:
    repo = ctx.config.repo
    payload: dict[str, Any] = {
        "delete_branch_on_merge": repo.delete_branch_on_merge,
        "allow_squash_merge": repo.allow_squash_merge,
        "allow_merge_commit": repo.allow_merge_commit,
        "allow_rebase_merge": repo.allow_rebase_merge,
        "allow_auto_merge": repo.allow_auto_merge,
        "allow_update_branch": repo.allow_update_branch,
        "has_issues": repo.has_issues,
        "has_wiki": repo.has_wiki,
        "has_projects": repo.has_projects,
    }
    if repo.allow_squash_merge:
        payload["squash_merge_commit_title"] = repo.squash_merge_commit_title
        payload["squash_merge_commit_message"] = repo.squash_merge_commit_message
    if ctx.gh.branch_exists(target.owner, target.name, repo.default_branch):
        payload["default_branch"] = repo.default_branch
    return payload


def apply_settings(ctx: AppContext, target: RepoTarget) -> None:
    cfg = ctx.config
    payload = settings_payload(ctx, target)
    ctx.gh.repo_update(target.owner, target.name, payload)
    enabled = [k.removeprefix("allow_") for k in ("allow_squash_merge", "allow_merge_commit", "allow_rebase_merge") if payload[k]]
    ok(f"merge methods: {', '.join(enabled) or 'none'}; delete branch on merge: {payload['delete_branch_on_merge']}")
    if cfg.repo.topics:
        ctx.gh.repo_set_topics(target.owner, target.name, cfg.repo.topics)
        ok(f"topics: {', '.join(cfg.repo.topics)}")


# --------------------------------------------------------------------------- labels


def sync_labels(ctx: AppContext, target: RepoTarget, prune: bool) -> str:
    cfg = ctx.config
    gh = ctx.gh
    existing = _list_or_empty(ctx, lambda: gh.labels(target.owner, target.name))
    current_names = {str(item["name"]).lower(): str(item["name"]) for item in existing}
    changes = labelmod.plan_changes(existing, cfg.labels, prune=prune)
    counts = {"create": 0, "update": 0, "delete": 0, "keep": 0}
    for change in changes:
        counts[change.action] += 1
        label = change.label
        if change.action == "create":
            gh.label_create(target.owner, target.name, label.name, label.color, label.description)
        elif change.action == "update":
            gh.label_update(
                target.owner, target.name, current_names[label.name.lower()], label.name, label.color, label.description
            )
        elif change.action == "delete":
            gh.label_delete(target.owner, target.name, label.name)
    rows = [(c.action, c.label.name, c.label.color, c.detail) for c in changes if c.action != "keep"]
    if rows:
        table("Label changes", ["action", "label", "color", "detail"], rows)
    result = f"{counts['create']} created, {counts['update']} updated, {counts['delete']} deleted, {counts['keep']} unchanged"
    ok(result)
    return result


# --------------------------------------------------------------------------- protection


def apply_protection(ctx: AppContext, target: RepoTarget, visibility: str) -> str:
    cfg = ctx.config
    gh = ctx.gh
    capabilities = ctx.capabilities(visibility)
    if not capabilities.branch_protection:
        for note in capabilities.notes:
            if "protection" in note:
                warn(note)
        return "skipped (not available on this plan/visibility)"
    engine = protmod.choose_engine(cfg.protection)
    applied: list[str] = []
    if engine == "ruleset":
        existing = {r["name"]: r for r in _list_or_empty(ctx, lambda: gh.rulesets(target.owner, target.name))}
        for branch in cfg.protection.branches:
            payload = protmod.ruleset_payload(cfg.protection, branch)
            found = existing.get(payload["name"])
            if found:
                gh.ruleset_update(target.owner, target.name, int(found["id"]), payload)
                applied.append(f"{branch} (updated)")
            else:
                gh.ruleset_create(target.owner, target.name, payload)
                applied.append(f"{branch} (created)")
        ok(f"rulesets: {', '.join(applied)}")
        return f"ruleset: {', '.join(applied)}"
    payload = protmod.classic_payload(cfg.protection)
    for branch in cfg.protection.branches:
        if any(ch in branch for ch in "*?["):
            warn(f"classic protection does not support patterns ('{branch}'); use protection.engine: ruleset")
            continue
        if not gh.branch_exists(target.owner, target.name, branch):
            warn(f"branch '{branch}' does not exist yet; classic protection needs an existing branch (skipped)")
            continue
        gh.branch_protection_put(target.owner, target.name, branch, payload)
        try:
            gh.branch_required_signatures(target.owner, target.name, branch, cfg.protection.require_signed_commits)
        except GhApiError as exc:
            if exc.status not in (404, 422):
                raise
        applied.append(branch)
    ok(f"classic protection: {', '.join(applied) or 'nothing applied'}")
    return f"classic: {', '.join(applied) or 'nothing applied'}"


# --------------------------------------------------------------------------- access


def _applies(patterns: list[str], repo: str) -> bool:
    return "*" in patterns or repo in patterns


def apply_access(ctx: AppContext, target: RepoTarget) -> str:
    cfg = ctx.config
    gh = ctx.gh
    granted: list[str] = []
    if cfg.mode.is_org:
        teams = [t for t in cfg.teams if _applies(t.repos, target.name)]
        if teams:
            existing = {t["name"].lower(): t for t in gh.teams(target.owner)}
            existing.update({t["slug"].lower(): t for t in list(existing.values())})
            for team in teams:
                found = existing.get(team.name.lower())
                if not found:
                    warn(f"team '{team.name}' does not exist yet; run `gitteam team sync` first")
                    continue
                gh.team_add_repo(target.owner, found["slug"], target.owner, target.name, team.permission)
                granted.append(f"@{target.owner}/{found['slug']}:{team.permission}")
    elif cfg.teams:
        warn("teams are configured but mode is 'personal'; only collaborators are applied")
    for collab in cfg.collaborators:
        if _applies(collab.repos, target.name):
            gh.collaborator_add(target.owner, target.name, collab.user, collab.permission)
            granted.append(f"{collab.user}:{collab.permission}")
    if not granted:
        info("no teams/collaborators configured for this repository")
        return "nothing to grant"
    ok("granted: " + ", ".join(granted))
    return ", ".join(granted)


def mode_hint(ctx: AppContext) -> str:
    return {
        Mode.ORG: "organization (Free/Team)",
        Mode.ORG_ENTERPRISE: "organization (Enterprise Cloud)",
        Mode.PERSONAL: "personal account",
    }[ctx.config.mode]
