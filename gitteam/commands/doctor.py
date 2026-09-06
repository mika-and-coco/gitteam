from __future__ import annotations

import re
import shutil

from ..config import Mode
from ..context import AppContext
from ..errors import ConfigError, GhApiError
from ..ui import info, table

_MIN_GIT = (2, 23)
_MIN_GH = (2, 44)


def _version(output: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", output)
    return tuple(int(g) for g in match.groups() if g) if match else (0,)


def run(ctx: AppContext) -> bool:
    rows: list[tuple[str, str, str]] = []
    healthy = True

    def add(check: str, ok_: bool | None, detail: str) -> None:
        nonlocal healthy
        status = "OK" if ok_ else ("WARN" if ok_ is None else "FAIL")
        if ok_ is False:
            healthy = False
        rows.append((check, status, detail))

    # git
    if shutil.which("git"):
        out = ctx.runner.run(["git", "--version"], mutating=False, check=False).stdout
        version = _version(out)
        add("git", version >= _MIN_GIT, out.strip() or "found")
    else:
        add("git", False, "not found on PATH")

    # gh
    if shutil.which("gh"):
        out = ctx.runner.run(["gh", "--version"], mutating=False, check=False).stdout
        version = _version(out)
        add("gh", version >= _MIN_GH, (out.strip().splitlines() or ["found"])[0])
        if ctx.gh.auth_ok():
            try:
                login = ctx.gh.viewer().get("login")
                add("gh auth", True, f"logged in as {login}")
            except GhApiError as exc:
                add("gh auth", False, exc.message)
        else:
            add("gh auth", False, "not logged in (run: gh auth login)")
    else:
        add("gh", False, "not found on PATH (https://cli.github.com)")

    # config
    try:
        cfg = ctx.config
        add("config", True, f"{cfg.source_path} (owner={cfg.owner}, mode={cfg.mode.value})")
    except ConfigError as exc:
        add("config", False, str(exc).splitlines()[0])
        table("gitteam doctor", ["check", "status", "detail"], rows)
        return False

    # owner type vs mode
    try:
        account = ctx.gh.account(cfg.owner)
        if account is None:
            add("owner", False, f"'{cfg.owner}' not found on GitHub")
        else:
            kind = account.get("type")
            expected = "Organization" if cfg.mode.is_org else "User"
            add("owner", kind == expected, f"{cfg.owner} is a {kind}; mode '{cfg.mode.value}' expects {expected}")
    except GhApiError as exc:
        add("owner", None, exc.message)

    # plan / capabilities
    try:
        plan = ctx.resolve_plan()
        add("plan", True, plan.value + (" (from config)" if cfg.plan.value != "auto" or cfg.mode is Mode.ORG_ENTERPRISE else " (detected)"))
        capabilities = ctx.capabilities()
        add("branch protection", True if capabilities.branch_protection else None,
            "available" if capabilities.branch_protection else "unavailable for private repos on this plan")
    except GhApiError as exc:
        add("plan", None, exc.message)

    # teams referenced in config
    if cfg.mode.is_org and cfg.teams:
        try:
            existing = {t["name"].lower() for t in ctx.gh.teams(cfg.owner)} | {t["slug"].lower() for t in ctx.gh.teams(cfg.owner)}
            missing = [t.name for t in cfg.teams if t.name.lower() not in existing]
            add("teams", None if missing else True, "missing: " + ", ".join(missing) if missing else f"{len(cfg.teams)} configured team(s) exist")
        except GhApiError as exc:
            add("teams", None, exc.message)

    table("gitteam doctor", ["check", "status", "detail"], rows)
    if healthy:
        info("all mandatory checks passed")
    return healthy
