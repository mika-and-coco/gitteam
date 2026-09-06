from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from .. import conventions as conv
from .. import scaffold as scaffoldmod
from ..context import AppContext
from ..errors import ConventionError, GitTeamError
from ..gitcmd import Git
from ..ui import DRY_RUN, get_console, info, ok, warn


def _git(ctx: AppContext) -> Git:
    cwd = Path.cwd()
    if not Git.is_repo(cwd, ctx.runner):
        raise GitTeamError("not inside a git repository")
    git = Git(ctx.runner, cwd)
    return Git(ctx.runner, git.toplevel())


# --------------------------------------------------------------------------- branches


def branch_new(ctx: AppContext, branch_type: str, description: str, issue: int | None, base: str | None) -> str:
    cfg = ctx.config_or_default()
    git = _git(ctx)
    name = conv.build_branch_name(cfg.conventions, branch_type, description, issue)
    if git.branch_exists(name):
        raise ConventionError(f"branch '{name}' already exists")
    base_branch = base or cfg.repo.default_branch
    start_point: str | None = None
    if git.remote_url():
        git.fetch("origin", base_branch)
        start_point = f"origin/{base_branch}" if git.rev(f"refs/remotes/origin/{base_branch}") or ctx.dry_run else None
    if start_point is None and git.branch_exists(base_branch):
        start_point = base_branch
    git.switch_new(name, start_point)
    ok(f"switched to new branch {name}" + (f" (from {start_point})" if start_point else ""))
    return name


def branch_check(ctx: AppContext, name: str | None) -> bool:
    cfg = ctx.config_or_default()
    branch = name or _git(ctx).current_branch()
    if not branch:
        raise ConventionError("detached HEAD: no branch name to check")
    problems = conv.validate_branch_name(cfg.conventions, branch)
    if problems:
        for problem in problems:
            get_console().print(f"[red]x[/red] branch '{branch}': {problem}")
        info(f"example: {cfg.conventions.branch_types[0]}/123-short-description")
        return False
    ok(f"branch '{branch}' follows the naming convention")
    return True


# --------------------------------------------------------------------------- commits


def commit_check(ctx: AppContext, rev_range: str | None, message_file: Path | None, message: str | None) -> bool:
    cfg = ctx.config_or_default()
    messages: list[tuple[str, str]] = []
    if message is not None:
        messages.append(("<message>", message))
    elif message_file is not None:
        messages.append((str(message_file), message_file.read_text(encoding="utf-8", errors="replace")))
    else:
        git = _git(ctx)
        if rev_range is None:
            default = cfg.repo.default_branch
            upstream = f"origin/{default}" if git.rev(f"refs/remotes/origin/{default}") else default
            rev_range = f"{upstream}..HEAD"
        for commit in git.commits(rev_range):
            full = commit.subject + ("\n\n" + commit.body if commit.body else "")
            messages.append((commit.sha[:8], full))
        if not messages:
            ok(f"no commits to check in {rev_range}")
            return True
    failures = 0
    for label, text in messages:
        problems = conv.validate_commit_message(cfg.conventions, text)
        subject = text.strip().splitlines()[0] if text.strip() else ""
        if problems:
            failures += 1
            get_console().print(f"[red]x[/red] {label}: {subject}")
            for problem in problems:
                get_console().print(f"    - {problem}")
        elif ctx.runner.verbose:
            get_console().print(f"[green]ok[/green] {label}: {subject}")
    if failures:
        info(f"format: <type>(<scope>)?: <description>   types: {', '.join(cfg.conventions.commit_types)}")
        return False
    ok(f"{len(messages)} commit message(s) follow Conventional Commits")
    return True


# --------------------------------------------------------------------------- hooks


def hooks_install(ctx: AppContext, shared: bool | None) -> None:
    cfg = ctx.config_or_default()
    git = _git(ctx)
    root = git.toplevel()
    use_shared = cfg.dev.shared_hooks if shared is None else shared
    if use_shared:
        hooks_dir = root / ".githooks"
        result = scaffoldmod.materialize(root, cfg, root.name, components=["githooks"], dry_run=ctx.dry_run)
        verb = f"{DRY_RUN} would write" if ctx.dry_run else "wrote"
        for path in result.written:
            info(f"{verb} {path.relative_to(root)}")
        _make_executable(hooks_dir)
        git.config_set("core.hooksPath", ".githooks", scope="local")
        ok("core.hooksPath = .githooks (shared hooks enabled for this clone)")
        if result.written:
            info("commit the .githooks/ directory so the whole team shares these hooks")
        return
    hooks_dir = root / ".git" / "hooks"
    variables = scaffoldmod.template_variables(cfg, root.name)
    for relative in scaffoldmod.HOOK_FILES:
        target = hooks_dir / Path(relative).name
        content = scaffoldmod.render_template(relative, variables)
        if ctx.dry_run:
            info(f"{DRY_RUN} would write {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        info(f"wrote {target}")
    _make_executable(hooks_dir)
    ok("local hooks installed (.git/hooks)")


def _make_executable(directory: Path) -> None:
    if os.name == "nt" or not directory.exists():
        return
    for hook in directory.iterdir():
        if hook.is_file() and hook.suffix == "":
            hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# --------------------------------------------------------------------------- pull requests


def pr_create(
    ctx: AppContext,
    *,
    title: str | None,
    base: str | None,
    draft: bool,
    reviewers: list[str],
    labels: list[str],
    no_verify: bool,
) -> None:
    cfg = ctx.config
    git = _git(ctx)
    branch = git.current_branch()
    if not branch:
        raise GitTeamError("detached HEAD: switch to a branch before creating a pull request")
    base_branch = base or cfg.repo.default_branch
    if branch == base_branch:
        raise GitTeamError(f"you are on '{base_branch}'; create a feature branch first (gitteam ops branch new ...)")

    if not no_verify:
        problems = conv.validate_branch_name(cfg.conventions, branch)
        if problems:
            raise ConventionError(f"branch '{branch}': {'; '.join(problems)}")

    git.fetch("origin", base_branch)
    if git.upstream_of(branch) is None:
        info(f"pushing {branch} to origin")
        git.push("origin", branch, set_upstream=True)
    rev_range = f"origin/{base_branch}..HEAD" if git.rev(f"refs/remotes/origin/{base_branch}") else f"{base_branch}..HEAD"
    commits = git.commits(rev_range)
    if not commits and not ctx.dry_run:
        raise GitTeamError(f"no commits between {base_branch} and {branch}")
    if not no_verify:
        bad = [c for c in commits if conv.validate_commit_message(cfg.conventions, c.subject)]
        if bad:
            for c in bad:
                warn(f"{c.sha[:8]} {c.subject}")
            raise ConventionError(f"{len(bad)} commit(s) violate Conventional Commits (fix them or pass --no-verify)")

    final_title = title or conv.pr_title(cfg.conventions, branch, [c.subject for c in commits])
    if not no_verify:
        title_problems = conv.validate_commit_message(cfg.conventions, final_title)
        if title_problems:
            raise ConventionError(f"PR title '{final_title}': {'; '.join(title_problems)}")

    body = _pr_body(git.toplevel(), branch, commits)
    all_labels = list(dict.fromkeys(labels))
    auto_label = conv.pr_label(cfg.conventions, final_title)
    if auto_label and auto_label not in all_labels:
        all_labels.append(auto_label)
    all_reviewers = list(dict.fromkeys([*cfg.conventions.pr_reviewers, *reviewers]))

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
        handle.write(body)
        body_path = Path(handle.name)
    try:
        try:
            proc = ctx.gh.pr_create(
                base=base_branch,
                title=final_title,
                body_file=body_path,
                draft=draft,
                reviewers=all_reviewers,
                labels=all_labels,
                cwd=git.toplevel(),
            )
        except GitTeamError as exc:
            if all_labels and "label" in str(exc).lower():
                warn("some labels do not exist in the repository; retrying without labels")
                proc = ctx.gh.pr_create(
                    base=base_branch,
                    title=final_title,
                    body_file=body_path,
                    draft=draft,
                    reviewers=all_reviewers,
                    labels=[],
                    cwd=git.toplevel(),
                )
            else:
                raise
    finally:
        body_path.unlink(missing_ok=True)
    url = (proc.stdout or "").strip().splitlines()[-1] if (proc.stdout or "").strip() else ""
    ok(f"pull request created: {url}" if url else "pull request created")


def _pr_body(root: Path, branch: str, commits) -> str:
    template = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
    body = template.read_text(encoding="utf-8") if template.exists() else "## Summary\n\n\n## Changes\n\n"
    issue = conv.issue_from_branch(branch)
    if issue is not None:
        marker = "<!-- Closes #123 -->"
        body = body.replace(marker, f"Closes #{issue}") if marker in body else body + f"\n\nCloses #{issue}\n"
    if commits:
        listing = "\n".join(f"- {c.subject} ({c.sha[:8]})" for c in commits)
        if "## Changes\n\n-" in body:
            body = body.replace("## Changes\n\n-", f"## Changes\n\n{listing}", 1)
        else:
            body += f"\n\n## Commits\n\n{listing}\n"
    return body


# --------------------------------------------------------------------------- releases


def release(ctx: AppContext, version: str, *, prerelease: bool, draft: bool, allow_dirty: bool) -> None:
    cfg = ctx.config
    git = _git(ctx)
    semver, tag = conv.normalize_version(cfg.conventions, version)
    default = cfg.repo.default_branch
    branch = git.current_branch()
    if branch != default:
        raise GitTeamError(f"releases are cut from '{default}' (currently on '{branch or 'detached HEAD'}')")
    if not git.is_clean() and not allow_dirty:
        raise GitTeamError("working tree is not clean; commit or stash your changes (or pass --allow-dirty)")
    git.fetch("origin", default)
    local, remote = git.rev("HEAD"), git.rev(f"refs/remotes/origin/{default}")
    if remote and local != remote:
        raise GitTeamError(f"local {default} ({local[:8]}) differs from origin/{default} ({remote[:8]}); pull or push first")
    if git.tag_exists(tag):
        raise GitTeamError(f"tag {tag} already exists")
    previous = git.latest_tag(cfg.conventions.tag_prefix)
    is_pre = prerelease or conv.is_prerelease(semver)
    git.tag_annotated(tag, f"Release {tag}")
    git.push("origin", f"refs/tags/{tag}")
    ctx.gh.release_create(tag, target=default, prerelease=is_pre, draft=draft, previous_tag=previous, cwd=git.toplevel())
    ok(f"release {tag} published" + (" (pre-release)" if is_pre else "") + (f", notes since {previous}" if previous else ""))
