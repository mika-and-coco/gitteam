"""Thin wrapper around the ``git`` command line."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import GitTeamError
from .runner import Runner

_REMOTE_RE = re.compile(r"(?:github\.com(?::\d+)?[:/])(?P<owner>[^/:]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    body: str


class Git:
    def __init__(self, runner: Runner, cwd: Path | None = None):
        self.runner = runner
        self.cwd = cwd

    def _run(self, *args: str, mutating: bool = False, check: bool = True):
        return self.runner.run(["git", *args], mutating=mutating, check=check, cwd=self.cwd)

    def _out(self, *args: str) -> str:
        return self._run(*args).stdout.strip()

    # ------------------------------------------------------------------ queries

    @staticmethod
    def is_repo(path: Path, runner: Runner | None = None) -> bool:
        if not path.is_dir():
            return False
        proc = (runner or Runner()).run(
            ["git", "rev-parse", "--is-inside-work-tree"], check=False, mutating=False, cwd=path
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    def toplevel(self) -> Path:
        return Path(self._out("rev-parse", "--show-toplevel"))

    def current_branch(self) -> str:
        return self._out("branch", "--show-current")

    def has_commits(self) -> bool:
        return self._run("rev-parse", "--verify", "-q", "HEAD", check=False).returncode == 0

    def is_clean(self) -> bool:
        return self._out("status", "--porcelain") == ""

    def remote_url(self, remote: str = "origin") -> str | None:
        proc = self._run("remote", "get-url", remote, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else None

    @staticmethod
    def parse_github_remote(url: str) -> tuple[str, str] | None:
        match = _REMOTE_RE.search(url.strip())
        if not match:
            return None
        return match.group("owner"), match.group("repo")

    def github_repo(self) -> tuple[str, str]:
        url = self.remote_url()
        parsed = self.parse_github_remote(url) if url else None
        if not parsed:
            raise GitTeamError("the current repository has no GitHub 'origin' remote")
        return parsed

    def upstream_of(self, branch: str) -> str | None:
        proc = self._run("rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}", check=False)
        return proc.stdout.strip() if proc.returncode == 0 else None

    def rev(self, ref: str) -> str | None:
        proc = self._run("rev-parse", "--verify", "-q", ref, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else None

    def branch_exists(self, name: str) -> bool:
        return self.rev(f"refs/heads/{name}") is not None

    def tag_exists(self, tag: str) -> bool:
        return self.rev(f"refs/tags/{tag}") is not None

    def tags(self, prefix: str = "") -> list[str]:
        out = self._out("tag", "--list", f"{prefix}*")
        return [line.strip() for line in out.splitlines() if line.strip()]

    def commits(self, *revisions: str, include_merges: bool = False) -> list[Commit]:
        """Commits selected by git-log revision arguments (e.g. ``"main..HEAD"`` or
        ``"abc123", "--not", "--remotes=origin"``). Raises CommandError for an invalid range."""
        args = ["log", "--format=%H%x1f%s%x1f%b%x1e", *revisions]
        if not include_merges:
            args.insert(1, "--no-merges")
        proc = self._run(*args, check=True)
        commits: list[Commit] = []
        for record in proc.stdout.split("\x1e"):
            record = record.strip("\r\n")
            if not record.strip():
                continue
            sha, subject, body = (record.split("\x1f") + ["", ""])[:3]
            commits.append(Commit(sha.strip(), subject.strip(), body.strip()))
        return commits

    def hooks_dir(self) -> Path:
        """Directory git actually reads hooks from (works for worktrees and submodules)."""
        out = self._out("rev-parse", "--git-path", "hooks")
        path = Path(out)
        return path if path.is_absolute() else self.toplevel() / path

    def config_get(self, key: str, scope: str | None = None) -> str | None:
        args = ["config"] + ([f"--{scope}"] if scope else []) + ["--get", key]
        proc = self._run(*args, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else None

    # ------------------------------------------------------------------ mutations

    def init(self, default_branch: str) -> None:
        self._run("init", "-b", default_branch, mutating=True)

    def clone(self, url: str, dest: Path) -> None:
        self._run("clone", url, str(dest), mutating=True)

    def set_head_branch(self, branch: str) -> None:
        self._run("symbolic-ref", "HEAD", f"refs/heads/{branch}", mutating=True)

    def fetch(self, remote: str = "origin", *refs: str) -> None:
        self._run("fetch", "--prune", remote, *refs, mutating=True)

    def switch_new(self, branch: str, start_point: str | None = None) -> None:
        args = ["switch", "-c", branch]
        if start_point:
            args += [start_point, "--no-track"]
        self._run(*args, mutating=True)

    def add_all(self) -> None:
        self._run("add", "-A", mutating=True)

    def add(self, *paths: str) -> None:
        if paths:
            self._run("add", "--", *paths, mutating=True)

    def chmod_executable(self, *paths: str) -> None:
        if paths:
            self._run("update-index", "--chmod=+x", "--", *paths, mutating=True)

    def commit(self, message: str) -> None:
        self._run("commit", "-m", message, mutating=True)

    def push(self, remote: str, ref: str, set_upstream: bool = False) -> None:
        args = ["push"] + (["-u"] if set_upstream else []) + [remote, ref]
        self._run(*args, mutating=True)

    def tag_annotated(self, tag: str, message: str) -> None:
        self._run("tag", "-a", tag, "-m", message, mutating=True)

    def config_set(self, key: str, value: str, scope: str = "global") -> None:
        self._run("config", f"--{scope}", key, value, mutating=True)

    def config_unset(self, key: str, scope: str = "global") -> None:
        self._run("config", f"--{scope}", "--unset", key, mutating=True, check=False)
