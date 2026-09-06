from __future__ import annotations

from typing import Any

from ..config import Mode
from ..context import AppContext
from ..errors import CapabilityError, GhApiError
from ..ui import info, ok, table, warn


def _team_index(ctx: AppContext, org: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    try:
        teams = ctx.gh.teams(org)
    except GhApiError as exc:
        if exc.status in (403, 404):
            raise CapabilityError(
                f"cannot list teams of '{org}' (HTTP {exc.status}). Check that the organization exists, "
                "that mode is 'org'/'org-enterprise', and that the gh token has the admin:org (or read:org) scope: "
                "gh auth refresh -s admin:org"
            ) from None
        raise
    for team in teams:
        index[str(team["name"]).lower()] = team
        index[str(team["slug"]).lower()] = team
    return index


def _target_repos(ctx: AppContext, patterns: list[str], repos_filter: list[str] | None, all_repos: list[str] | None) -> list[str]:
    if repos_filter:
        return [r for r in repos_filter if "*" in patterns or r in patterns]
    if "*" in patterns:
        return list(all_repos or [])
    return [p for p in patterns if p != "*"]


def sync(ctx: AppContext, repos_filter: list[str] | None, skip_repos: bool) -> None:
    cfg = ctx.config
    gh = ctx.gh
    if cfg.mode is Mode.PERSONAL:
        _sync_collaborators(ctx, repos_filter, skip_repos)
        return
    org = cfg.owner
    rows: list[tuple[str, str, str]] = []
    index = _team_index(ctx, org)
    all_repos: list[str] | None = None
    if not skip_repos and any("*" in t.repos for t in cfg.teams) and not repos_filter:
        all_repos = [r["name"] for r in gh.org_repos(org)]

    for team in cfg.teams:
        found = index.get(team.name.lower())
        if found is None:
            created = gh.team_create(org, team.name, team.description, team.privacy)
            slug = created["slug"] if created else team.name.lower().replace(" ", "-")
            rows.append((team.name, "team", "created"))
        else:
            slug = found["slug"]
            rows.append((team.name, "team", "exists"))
        current_members = set()
        if found is not None:
            current_members = {m["login"].lower() for m in gh.team_members(org, slug)}
        for login in team.maintainers:
            gh.team_add_member(org, slug, login, "maintainer")
            rows.append((team.name, f"maintainer {login}", "added" if login.lower() not in current_members else "ensured"))
        for login in team.members:
            if login in team.maintainers:
                continue
            gh.team_add_member(org, slug, login, "member")
            rows.append((team.name, f"member {login}", "added" if login.lower() not in current_members else "ensured"))
        if skip_repos:
            continue
        for repo in _target_repos(ctx, team.repos, repos_filter, all_repos):
            gh.team_add_repo(org, slug, org, repo, team.permission)
            rows.append((team.name, f"repo {repo}", team.permission))

    if cfg.collaborators:
        _sync_collaborators(ctx, repos_filter, skip_repos, rows)
    table(f"Team sync for {org}", ["team", "item", "result"], rows)
    ok("team sync complete" + (" (dry-run)" if ctx.dry_run else ""))
    info("users who are not yet organization members receive an invitation e-mail from GitHub.")


def _sync_collaborators(
    ctx: AppContext, repos_filter: list[str] | None, skip_repos: bool, rows: list[tuple[str, str, str]] | None = None
) -> None:
    cfg = ctx.config
    gh = ctx.gh
    own_rows: list[tuple[str, str, str]] = [] if rows is None else rows
    if skip_repos:
        return
    if not cfg.collaborators:
        warn("no collaborators configured (collaborators: [] in gitteam.yaml)")
        return
    all_repos: list[str] | None = None
    if any("*" in c.repos for c in cfg.collaborators) and not repos_filter:
        source = gh.org_repos(cfg.owner) if cfg.mode.is_org else gh.user_repos()
        all_repos = [r["name"] for r in source if str(r.get("owner", {}).get("login", cfg.owner)).lower() == cfg.owner.lower()]
    for collab in cfg.collaborators:
        for repo in _target_repos(ctx, collab.repos, repos_filter, all_repos):
            try:
                gh.collaborator_add(cfg.owner, repo, collab.user, collab.permission)
                own_rows.append(("collaborator", f"{collab.user} -> {repo}", collab.permission))
            except GhApiError as exc:
                own_rows.append(("collaborator", f"{collab.user} -> {repo}", f"failed: {exc.message}"))
    if rows is None:
        table(f"Collaborators for {cfg.owner}", ["kind", "item", "result"], own_rows)
        ok("collaborator sync complete" + (" (dry-run)" if ctx.dry_run else ""))


def invite(ctx: AppContext, user: str, team: str | None, role: str, repo: str | None, permission: str) -> None:
    cfg = ctx.config
    gh = ctx.gh
    if cfg.mode is Mode.PERSONAL:
        if not repo:
            raise CapabilityError("personal mode: pass --repo NAME to invite a collaborator to a repository")
        gh.collaborator_add(cfg.owner, repo, user, permission)
        ok(f"invited {user} to {cfg.owner}/{repo} with '{permission}' permission")
        return
    gh.org_add_member(cfg.owner, user, role)
    ok(f"{user}: organization membership '{role}' ensured (invitation sent if not yet a member)")
    if team:
        index = _team_index(ctx, cfg.owner)
        found = index.get(team.lower())
        if not found:
            raise CapabilityError(f"team '{team}' not found in {cfg.owner}; run `gitteam team sync` to create it")
        gh.team_add_member(cfg.owner, found["slug"], user, "member")
        ok(f"{user}: added to team {found['slug']}")
    if repo:
        gh.collaborator_add(cfg.owner, repo, user, permission)
        ok(f"{user}: '{permission}' on {cfg.owner}/{repo}")


def list_teams(ctx: AppContext) -> None:
    cfg = ctx.config
    if cfg.mode is Mode.PERSONAL:
        rows = [(c.user, c.permission, ", ".join(c.repos)) for c in cfg.collaborators]
        table(f"Configured collaborators ({cfg.owner})", ["user", "permission", "repos"], rows)
        return
    gh = ctx.gh
    rows = []
    for team in gh.teams(cfg.owner):
        members = gh.team_members(cfg.owner, team["slug"])
        rows.append((team["name"], team["slug"], team.get("privacy", ""), ", ".join(m["login"] for m in members) or "-"))
    table(f"Teams in {cfg.owner}", ["name", "slug", "privacy", "members"], rows)
