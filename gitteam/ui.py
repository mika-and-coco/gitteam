from __future__ import annotations

from contextlib import contextmanager
from typing import Iterable, Iterator, Sequence

from rich.console import Console
from rich.markup import escape
from rich.table import Table

console = Console()
err_console = Console(stderr=True)

# Plain text: the helpers below escape their message, so markup never leaks in.
DRY_RUN = "[dry-run]"

_redirect_stack: list[Console] = []


def get_console() -> Console:
    """Console used for normal output (swappable, e.g. captured by the web UI)."""
    return _redirect_stack[-1] if _redirect_stack else console


def get_err_console() -> Console:
    return _redirect_stack[-1] if _redirect_stack else err_console


@contextmanager
def redirected(target: Console) -> Iterator[Console]:
    """Route every message printed through this module to ``target`` while active."""
    _redirect_stack.append(target)
    try:
        yield target
    finally:
        _redirect_stack.pop()


def info(message: str) -> None:
    get_console().print(f"[cyan]i[/cyan] {escape(message)}")


def ok(message: str) -> None:
    get_console().print(f"[green]OK[/green] {escape(message)}")


def warn(message: str) -> None:
    get_console().print(f"[yellow]WARN[/yellow] {escape(message)}")


def fail(message: str) -> None:
    get_err_console().print(f"[red]ERROR[/red] {escape(message)}")


def step(title: str) -> None:
    get_console().rule(f"[bold]{escape(title)}[/bold]", align="left")


def plain(message: str, style: str | None = None) -> None:
    """Print ``message`` verbatim (no markup interpretation), optionally in ``style``."""
    text = escape(message)
    get_console().print(f"[{style}]{text}[/{style}]" if style else text)


def table(title: str, columns: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    t = Table(title=title, show_lines=False, title_justify="left")
    for col in columns:
        t.add_column(col)
    empty = True
    for row in rows:
        empty = False
        t.add_row(*[escape(str(c)) for c in row])
    if empty:
        t.add_row(*["-"] * len(columns))
    get_console().print(t)
