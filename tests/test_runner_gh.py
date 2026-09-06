from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from gitteam.errors import CommandError, GhApiError
from gitteam.gh import Gh
from gitteam.gitcmd import Git
from gitteam.runner import Runner


def test_dry_run_skips_mutating_commands(tmp_path: Path):
    marker = tmp_path / "marker"
    cmd = [sys.executable, "-c", f"open(r'{marker}', 'w').close()"]
    Runner(dry_run=True).run(cmd)
    assert not marker.exists()
    Runner(dry_run=True).run(cmd, mutating=False)
    assert marker.exists()


def test_failed_command_raises():
    with pytest.raises(CommandError) as info:
        Runner().run([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"])
    assert info.value.returncode == 3
    assert "boom" in str(info.value)


class FakeRunner(Runner):
    """Runner that records gh invocations and returns canned output."""

    def __init__(self, responses: dict[str, tuple[int, str, str]]):
        super().__init__()
        self.responses = responses
        self.calls: list[list[str]] = []

    def run(self, cmd, *, input=None, check=True, mutating=True, cwd=None):  # type: ignore[override]
        self.calls.append(list(cmd))
        endpoint = cmd[2] if len(cmd) > 2 else ""
        code, out, err = self.responses.get(endpoint, (0, "{}", ""))
        return subprocess.CompletedProcess(list(cmd), code, out, err)


def test_gh_api_error_parsing():
    runner = FakeRunner({"repos/acme/nope": (1, json.dumps({"message": "Not Found"}), "gh: Not Found (HTTP 404)")})
    gh = Gh(runner)
    assert gh.repo_get("acme", "nope") is None
    runner.responses["repos/acme/nope"] = (1, json.dumps({"message": "Bad credentials"}), "gh: Bad credentials (HTTP 401)")
    with pytest.raises(GhApiError) as info:
        gh.repo_get("acme", "nope")
    assert info.value.status == 401 and "Bad credentials" in str(info.value)


def test_gh_paginate_flattens_pages():
    pages = json.dumps([[{"name": "a"}], [{"name": "b"}]])
    runner = FakeRunner({"repos/acme/x/labels?per_page=100": (0, pages, "")})
    assert [item["name"] for item in Gh(runner).labels("acme", "x")] == ["a", "b"]
    assert "--paginate" in runner.calls[0] and "--slurp" in runner.calls[0]


def test_gh_json_body_goes_through_stdin():
    runner = FakeRunner({})
    Gh(runner).repo_update("acme", "x", {"has_wiki": False})
    call = runner.calls[0]
    assert call[:3] == ["gh", "api", "repos/acme/x"]
    assert "--input" in call and "-X" in call and "PATCH" in call


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/acme/demo.git", ("acme", "demo")),
        ("https://github.com/acme/demo", ("acme", "demo")),
        ("git@github.com:acme/demo.git", ("acme", "demo")),
        ("ssh://git@github.com/acme/demo.git", ("acme", "demo")),
        ("https://gitlab.com/acme/demo.git", None),
    ],
)
def test_parse_github_remote(url, expected):
    assert Git.parse_github_remote(url) == expected
