from __future__ import annotations


class GitTeamError(Exception):
    """Base class for user-facing errors (printed without traceback)."""


class ConfigError(GitTeamError):
    """Invalid or missing configuration."""


class UntrustedConfigError(ConfigError):
    """A gitteam.yaml was discovered inside the working tree but has not been trusted yet."""


class CommandError(GitTeamError):
    """An external command (git/gh) failed."""

    def __init__(self, command: str, returncode: int, stdout: str = "", stderr: str = ""):
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        detail = (stderr or stdout).strip()
        super().__init__(f"command failed (exit {returncode}): {command}\n{detail}".rstrip())


class GhApiError(CommandError):
    """A GitHub API call made through `gh api` failed."""

    def __init__(self, command: str, returncode: int, stdout: str, stderr: str, status: int | None, message: str):
        self.status = status
        self.message = message
        CommandError.__init__(self, command, returncode, stdout, stderr)
        self.args = (f"GitHub API error{f' (HTTP {status})' if status else ''}: {message}",)

    def __str__(self) -> str:
        return self.args[0]


class CapabilityError(GitTeamError):
    """The requested operation is not available for the configured mode/plan."""


class ConventionError(GitTeamError):
    """A branch name, commit message, or version violates team conventions."""
