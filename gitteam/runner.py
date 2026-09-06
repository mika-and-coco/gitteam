from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .errors import CommandError, GitTeamError
from .ui import DRY_RUN, get_console


@dataclass
class Runner:
    """Executes external commands with dry-run and verbose support.

    Mutating commands are skipped in dry-run mode and only printed; read-only
    commands (``mutating=False``) still execute so that planning works.
    """

    dry_run: bool = False
    verbose: bool = False

    @staticmethod
    def display(cmd: Sequence[str]) -> str:
        return " ".join(shlex.quote(str(c)) for c in cmd)

    @staticmethod
    def require(executable: str) -> str:
        path = shutil.which(executable)
        if not path:
            raise GitTeamError(f"'{executable}' was not found on PATH. Install it and retry.")
        return path

    def run(
        self,
        cmd: Sequence[str],
        *,
        input: str | None = None,
        check: bool = True,
        mutating: bool = True,
        cwd: Path | str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        shown = self.display(cmd)
        if self.dry_run and mutating:
            get_console().print(f"[magenta]{DRY_RUN}[/magenta] {shown}", soft_wrap=True)
            if input:
                get_console().print(f"[dim]{self._pretty(input)}[/dim]")
            return subprocess.CompletedProcess(list(cmd), 0, "", "")
        if self.verbose:
            get_console().print(f"[dim]$ {shown}[/dim]", soft_wrap=True)
            if input:
                get_console().print(f"[dim]{self._pretty(input)}[/dim]")
        try:
            proc = subprocess.run(
                [str(c) for c in cmd],
                input=input,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(cwd) if cwd else None,
            )
        except FileNotFoundError as exc:
            raise GitTeamError(f"'{cmd[0]}' was not found on PATH. Install it and retry.") from exc
        if self.verbose and proc.stdout.strip():
            get_console().print(f"[dim]{proc.stdout.rstrip()}[/dim]")
        if check and proc.returncode != 0:
            raise CommandError(shown, proc.returncode, proc.stdout, proc.stderr)
        return proc

    @staticmethod
    def _pretty(text: str) -> str:
        try:
            return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except ValueError:
            return text
