"""Thin wrapper around the GitHub CLI (``gh``)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .errors import GhApiError
from .runner import Runner

_HTTP_STATUS_RE = re.compile(r"\(HTTP (\d{3})\)")
_API_HEADERS = ["-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2022-11-28"]


class Gh:
    def __init__(self, runner: Runner):
        self.runner = runner

    # ------------------------------------------------------------------ low level

    def api(
        self,
        endpoint: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        *,
        mutating: bool | None = None,
        paginate: bool = False,
    ) -> Any:
        cmd: list[str] = ["gh", "api", endpoint, *_API_HEADERS]
        if method != "GET":
            cmd += ["-X", method]
        if paginate:
            cmd += ["--paginate", "--slurp"]
        payload = None
        if body is not None:
            cmd += ["--input", "-"]
            payload = json.dumps(body)
        if mutating is None:
            mutating = method != "GET"
        proc = self.runner.run(cmd, input=payload, check=False, mutating=mutating)
        if self.runner.dry_run and mutating:
            return None
        if proc.returncode != 0:
            raise self._api_error(cmd, proc.returncode, proc.stdout, proc.stderr)
        text = proc.stdout.strip()
        if not text:
            return None
        data = json.loads(text)
        if paginate and isinstance(data, list) and all(isinstance(page, list) for page in data):
            return [item for page in data for item in page]
        return data

    def api_optional(self, endpoint: str) -> Any:
        try:
            return self.api(endpoint)
        except GhApiError as exc:
            if exc.status == 404:
                return None
            raise

    def _api_error(self, cmd: list[str], code: int, stdout: str, stderr: str) -> GhApiError:
        status_match = _HTTP_STATUS_RE.search(stderr)
        status = int(status_match.group(1)) if status_match else None
        message = stderr.strip().splitlines()[0] if stderr.strip() else "unknown error"
        message = re.sub(r"^gh:\s*", "", message)
        try:
            data = json.loads(stdout) if stdout.strip() else {}
            if isinstance(data, dict):
                if data.get("message"):
                    message = str(data["message"])
                errors = data.get("errors")
                if errors:
                    message += " " + json.dumps(errors, ensure_ascii=False)
        except ValueError:
            pass
        return GhApiError(Runner.display(cmd), code, stdout, stderr, status, message)

    def run(self, args: list[str], *, mutating: bool = True, check: bool = True, cwd: Path | None = None):
        return self.runner.run(["gh", *args], mutating=mutating, check=check, cwd=cwd)

    # ------------------------------------------------------------------ identity / plan

    def auth_ok(self) -> bool:
        proc = self.runner.run(["gh", "auth", "status"], check=False, mutating=False)
        return proc.returncode == 0

    def viewer(self) -> dict[str, Any]:
        return self.api("user")

    def account(self, login: str) -> dict[str, Any] | None:
        return self.api_optional(f"users/{login}")

    def org_plan_name(self, org: str) -> str | None:
        data = self.api_optional(f"orgs/{org}")
        if not data:
            return None
        plan = data.get("plan") or {}
        return plan.get("name")

    def user_plan_name(self) -> str | None:
        plan = self.viewer().get("plan") or {}
        return plan.get("name")

    # ------------------------------------------------------------------ repositories

    def repo_get(self, owner: str, name: str) -> dict[str, Any] | None:
        return self.api_optional(f"repos/{owner}/{name}")

    def repo_create(self, owner: str, name: str, visibility: str, description: str = "") -> None:
        args = ["repo", "create", f"{owner}/{name}", f"--{visibility}"]
        if description:
            args += ["--description", description]
        self.run(args)

    def repo_clone(self, owner: str, name: str, dest: Path) -> None:
        self.run(["repo", "clone", f"{owner}/{name}", str(dest)])

    def repo_update(self, owner: str, name: str, settings: dict[str, Any]) -> None:
        self.api(f"repos/{owner}/{name}", "PATCH", settings)

    def repo_set_topics(self, owner: str, name: str, topics: list[str]) -> None:
        self.api(f"repos/{owner}/{name}/topics", "PUT", {"names": topics})

    def branch_exists(self, owner: str, name: str, branch: str) -> bool:
        return self.api_optional(f"repos/{owner}/{name}/branches/{quote(branch, safe='')}") is not None

    def org_repos(self, org: str) -> list[dict[str, Any]]:
        return self.api(f"orgs/{org}/repos?per_page=100&type=all", paginate=True) or []

    def user_repos(self) -> list[dict[str, Any]]:
        return self.api("user/repos?per_page=100&affiliation=owner", paginate=True) or []

    # ------------------------------------------------------------------ labels

    def labels(self, owner: str, name: str) -> list[dict[str, Any]]:
        return self.api(f"repos/{owner}/{name}/labels?per_page=100", paginate=True) or []

    def label_create(self, owner: str, name: str, label: str, color: str, description: str) -> None:
        self.api(f"repos/{owner}/{name}/labels", "POST", {"name": label, "color": color, "description": description})

    def label_update(self, owner: str, name: str, current: str, label: str, color: str, description: str) -> None:
        self.api(
            f"repos/{owner}/{name}/labels/{quote(current, safe='')}",
            "PATCH",
            {"new_name": label, "color": color, "description": description},
        )

    def label_delete(self, owner: str, name: str, label: str) -> None:
        self.api(f"repos/{owner}/{name}/labels/{quote(label, safe='')}", "DELETE")

    # ------------------------------------------------------------------ protection

    def branch_protection_put(self, owner: str, name: str, branch: str, payload: dict[str, Any]) -> None:
        self.api(f"repos/{owner}/{name}/branches/{quote(branch, safe='')}/protection", "PUT", payload)

    def branch_required_signatures(self, owner: str, name: str, branch: str, enabled: bool) -> None:
        endpoint = f"repos/{owner}/{name}/branches/{quote(branch, safe='')}/protection/required_signatures"
        self.api(endpoint, "POST" if enabled else "DELETE")

    def rulesets(self, owner: str, name: str) -> list[dict[str, Any]]:
        return self.api(f"repos/{owner}/{name}/rulesets?per_page=100", paginate=True) or []

    def ruleset_create(self, owner: str, name: str, payload: dict[str, Any]) -> None:
        self.api(f"repos/{owner}/{name}/rulesets", "POST", payload)

    def ruleset_update(self, owner: str, name: str, ruleset_id: int, payload: dict[str, Any]) -> None:
        self.api(f"repos/{owner}/{name}/rulesets/{ruleset_id}", "PUT", payload)

    # ------------------------------------------------------------------ teams / access

    def teams(self, org: str) -> list[dict[str, Any]]:
        return self.api(f"orgs/{org}/teams?per_page=100", paginate=True) or []

    def team_create(self, org: str, name: str, description: str, privacy: str) -> dict[str, Any] | None:
        return self.api(f"orgs/{org}/teams", "POST", {"name": name, "description": description, "privacy": privacy})

    def team_members(self, org: str, slug: str) -> list[dict[str, Any]]:
        return self.api(f"orgs/{org}/teams/{slug}/members?per_page=100", paginate=True) or []

    def team_add_member(self, org: str, slug: str, user: str, role: str = "member") -> None:
        self.api(f"orgs/{org}/teams/{slug}/memberships/{user}", "PUT", {"role": role})

    def team_add_repo(self, org: str, slug: str, owner: str, repo: str, permission: str) -> None:
        self.api(f"orgs/{org}/teams/{slug}/repos/{owner}/{repo}", "PUT", {"permission": permission})

    def org_add_member(self, org: str, user: str, role: str = "member") -> None:
        self.api(f"orgs/{org}/memberships/{user}", "PUT", {"role": role})

    def collaborator_add(self, owner: str, repo: str, user: str, permission: str) -> None:
        self.api(f"repos/{owner}/{repo}/collaborators/{user}", "PUT", {"permission": permission})

    # ------------------------------------------------------------------ content helpers

    def gitignore_template(self, name: str) -> str | None:
        data = self.api_optional(f"gitignore/templates/{quote(name, safe='')}")
        return data.get("source") if data else None

    def license_text(self, key: str) -> str | None:
        data = self.api_optional(f"licenses/{quote(key, safe='')}")
        return data.get("body") if data else None

    # ------------------------------------------------------------------ PR / release

    def pr_create(
        self,
        *,
        base: str,
        title: str,
        body_file: Path,
        draft: bool,
        reviewers: list[str],
        labels: list[str],
        cwd: Path | None = None,
    ):
        args = ["pr", "create", "--base", base, "--title", title, "--body-file", str(body_file)]
        if draft:
            args.append("--draft")
        for reviewer in reviewers:
            args += ["--reviewer", reviewer]
        for label in labels:
            args += ["--label", label]
        return self.run(args, cwd=cwd)

    def release_create(
        self,
        tag: str,
        *,
        target: str,
        prerelease: bool,
        draft: bool,
        previous_tag: str | None,
        cwd: Path | None = None,
    ):
        args = ["release", "create", tag, "--title", tag, "--target", target, "--generate-notes"]
        if previous_tag:
            args += ["--notes-start-tag", previous_tag]
        if prerelease:
            args.append("--prerelease")
        if draft:
            args.append("--draft")
        return self.run(args, cwd=cwd)
