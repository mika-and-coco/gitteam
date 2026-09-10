from __future__ import annotations

from pathlib import Path
from string import Template

import yaml

from .. import config as cfgmod
from ..context import AppContext
from ..errors import ConfigError
from ..ui import DRY_RUN, info, ok, plain, table

EXAMPLE_TEMPLATE = Path(__file__).parent.parent / "templates" / "gitteam.example.yaml"

_ORG_TEAMS_EXAMPLE = """
  - name: core
    description: Core maintainers
    privacy: closed
    members: []          # GitHub logins
    maintainers: []
    permission: maintain # pull | triage | push | maintain | admin
    repos: ["*"]
  - name: developers
    description: All developers
    privacy: closed
    members: []
    permission: push
    repos: ["*"]"""


def render_example(owner: str, mode: cfgmod.Mode) -> str:
    template = Template(EXAMPLE_TEMPLATE.read_text(encoding="utf-8"))
    codeowner = f"@{owner}/core" if mode.is_org else f"@{owner}"
    return template.substitute(
        owner=owner,
        mode=mode.value,
        codeowner=codeowner,
        teams_example=_ORG_TEAMS_EXAMPLE if mode.is_org else "[]",
    )


def init(ctx: AppContext, owner: str, mode: cfgmod.Mode, output: Path, force: bool) -> Path:
    if output.exists() and not force:
        raise ConfigError(f"{output} already exists (use --force to overwrite)")
    content = render_example(owner, mode)
    # Validate what we are about to write so a broken template never ships.
    cfgmod.from_dict(yaml.safe_load(content))
    if ctx.dry_run:
        info(f"{DRY_RUN} would write {output}")
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    cfgmod.trust_path(output)  # created by this user, so it is trusted for discovery
    ok(f"wrote {output}")
    info("edit teams/labels/protection as needed, then run `gitteam doctor` to verify the setup.")
    return output


def trust(ctx: AppContext, path: Path | None) -> Path:
    target = path or cfgmod.find_config()
    if target is None or not target.is_file():
        raise ConfigError("no gitteam.yaml to trust; pass the path explicitly")
    cfgmod.load(target)  # must at least be a valid config before trusting it
    if ctx.dry_run:
        info(f"{DRY_RUN} would trust {target}")
        return target
    cfgmod.trust_path(target)
    ok(f"trusted {target.resolve()}")
    info(f"the list of trusted configs lives in {cfgmod.user_config_dir()}")
    return target


def untrust(ctx: AppContext, path: Path | None) -> None:
    target = path or cfgmod.find_config()
    if target is None:
        raise ConfigError("no gitteam.yaml given")
    if ctx.dry_run:
        info(f"{DRY_RUN} would untrust {target}")
        return
    if cfgmod.untrust_path(target):
        ok(f"removed {target.resolve()} from the trusted list")
    else:
        info(f"{target.resolve()} was not in the trusted list")


def show_trusted() -> None:
    entries = sorted(str(p) for p in cfgmod.trusted_paths())
    table("Trusted gitteam.yaml files", ["path"], [(p,) for p in entries])
    info("configs under " + ", ".join(str(d) for d in cfgmod.user_config_dirs()) + " are always trusted")


def validate(ctx: AppContext) -> cfgmod.Config:
    cfg = ctx.config
    ok(f"{cfg.source_path} is valid (owner={cfg.owner}, mode={cfg.mode.value})")
    return cfg


def show(ctx: AppContext) -> None:
    cfg = ctx.config
    info(f"source: {cfg.source_path}")
    plain(yaml.safe_dump(cfgmod.to_dict(cfg), sort_keys=False, allow_unicode=True))


def capabilities(ctx: AppContext, visibility: str | None) -> None:
    capabilities_ = ctx.capabilities(visibility)
    table("Capabilities", ["feature", "available"], capabilities_.as_rows())
    for note in capabilities_.notes:
        info(note)
