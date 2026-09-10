from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import capabilities as caps
from . import config as cfgmod
from .errors import ConfigError, GhApiError, UntrustedConfigError
from .gh import Gh
from .runner import Runner
from .ui import warn


@dataclass
class AppContext:
    """Shared state for one CLI invocation."""

    runner: Runner
    gh: Gh
    config_path: Path | None = None
    discover: bool = True  # False: never search cwd/user dirs (the web UI decides the path itself)
    _config: cfgmod.Config | None = field(default=None, repr=False)
    _plan_cache: cfgmod.Plan | None = field(default=None, repr=False)

    @classmethod
    def create(cls, config_path: Path | None, dry_run: bool, verbose: bool, discover: bool = True) -> "AppContext":
        runner = Runner(dry_run=dry_run, verbose=verbose)
        return cls(runner=runner, gh=Gh(runner), config_path=config_path, discover=discover)

    def _discover(self) -> cfgmod.DiscoveredConfig | None:
        if self.config_path is None and not self.discover:
            return None
        return cfgmod.discover_config(self.config_path)

    @property
    def dry_run(self) -> bool:
        return self.runner.dry_run

    # ------------------------------------------------------------------ config

    def load_config(self) -> cfgmod.Config:
        if self._config is None:
            found = self._discover()
            if found is None:
                raise ConfigError(
                    "no gitteam.yaml found (searched the current directory and parents, "
                    "~/.config/gitteam/ and %APPDATA%/gitteam/). Run `gitteam config init` first "
                    "or pass --config PATH."
                )
            cfgmod.require_trusted(found)
            self._config = cfgmod.load(found.path)
        return self._config

    @property
    def config(self) -> cfgmod.Config:
        return self.load_config()

    def config_or_default(self) -> cfgmod.Config:
        """Config if available, otherwise built-in defaults (for `dev setup` on a fresh machine).

        An untrusted config is never silently ignored: the user must decide.
        """
        if self._config is None and self._discover() is None:
            return cfgmod.default_config()
        return self.load_config()  # a broken, missing (--config) or untrusted config is an error, not a silent default

    def is_trusted_config(self) -> bool:
        """True when a config is loaded or the discovered one may be loaded without a trust error."""
        if self._config is not None:
            return True
        found = self._discover()
        return found is not None and not (found.needs_trust and not cfgmod.is_trusted(found.path))

    def conventions_for_checks(self) -> cfgmod.ConventionsConfig:
        """Conventions for read-only checks (`branch check`, `commit check`, the git hooks).

        These commands have no side effects and only read ``conventions``, so an untrusted
        gitteam.yaml found in the working tree is used as well: the hooks that call them are
        themselves repository-controlled and embed the same values, hence no new trust surface.
        A short hint reminds the user to trust the file for everything else.
        """
        if self._config is not None:
            return self._config.conventions
        found = self._discover()
        if found is None:
            return cfgmod.default_config().conventions
        try:
            return self.load_config().conventions
        except UntrustedConfigError:
            warn(f"using conventions from untrusted {found.path} (read-only); run `gitteam config trust` to silence this")
            return cfgmod.load(found.path).conventions

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
        if name is None:
            if cfg.mode.is_org:
                warn("billing plan not visible for this organization (needs admin:org / read:org); assuming 'free'.")
            else:
                warn(
                    "billing plan not visible for this account (the gh token needs the 'user' scope); assuming 'free'. "
                    "Set `plan: pro` in gitteam.yaml if you pay for GitHub Pro."
                )
        self._plan_cache = caps.plan_from_api_name(name, cfg.mode)
        return self._plan_cache

    def capabilities(self, visibility: str | None = None) -> caps.Capabilities:
        cfg = self.config
        return caps.resolve(cfg.mode, self.resolve_plan(), visibility or cfg.repo.visibility)
