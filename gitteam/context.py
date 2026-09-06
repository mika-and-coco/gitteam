from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import capabilities as caps
from . import config as cfgmod
from .errors import ConfigError, GhApiError
from .gh import Gh
from .runner import Runner
from .ui import warn


@dataclass
class AppContext:
    """Shared state for one CLI invocation."""

    runner: Runner
    gh: Gh
    config_path: Path | None = None
    _config: cfgmod.Config | None = field(default=None, repr=False)
    _plan_cache: cfgmod.Plan | None = field(default=None, repr=False)

    @classmethod
    def create(cls, config_path: Path | None, dry_run: bool, verbose: bool) -> "AppContext":
        runner = Runner(dry_run=dry_run, verbose=verbose)
        return cls(runner=runner, gh=Gh(runner), config_path=config_path)

    @property
    def dry_run(self) -> bool:
        return self.runner.dry_run

    # ------------------------------------------------------------------ config

    def load_config(self) -> cfgmod.Config:
        if self._config is None:
            path = cfgmod.find_config(self.config_path)
            if path is None:
                raise ConfigError(
                    "no gitteam.yaml found (searched the current directory and parents, "
                    "~/.config/gitteam/ and %APPDATA%/gitteam/). Run `gitteam config init` first "
                    "or pass --config PATH."
                )
            self._config = cfgmod.load(path)
        return self._config

    @property
    def config(self) -> cfgmod.Config:
        return self.load_config()

    def config_or_default(self) -> cfgmod.Config:
        """Config if available, otherwise built-in defaults (for `dev setup` on a fresh machine)."""
        try:
            return self.load_config()
        except ConfigError:
            return cfgmod.default_config()

    # ------------------------------------------------------------------ plan / capabilities

    def resolve_plan(self) -> cfgmod.Plan:
        cfg = self.config
        if cfg.effective_plan is not cfgmod.Plan.AUTO:
            return cfg.effective_plan
        if self._plan_cache is not None:
            return self._plan_cache
        name: str | None = None
        try:
            name = self.gh.org_plan_name(cfg.owner) if cfg.mode.is_org else self.gh.user_plan_name()
        except GhApiError as exc:
            warn(f"could not read the billing plan from GitHub ({exc}); assuming 'free'. Set `plan:` to override.")
        if name is None and cfg.mode.is_org:
            warn("billing plan not visible for this organization (needs admin:org / read:org); assuming 'free'.")
        self._plan_cache = caps.plan_from_api_name(name, cfg.mode)
        return self._plan_cache

    def capabilities(self, visibility: str | None = None) -> caps.Capabilities:
        cfg = self.config
        return caps.resolve(cfg.mode, self.resolve_plan(), visibility or cfg.repo.visibility)
