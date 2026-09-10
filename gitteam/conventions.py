"""Pure functions implementing team conventions (branch names, commit messages, versions)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .config import ConventionsConfig
from .errors import ConventionError

_CC_RE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^()\s]+)\))?(?P<bang>!)?: (?P<desc>.+)$")
_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)
_ISSUE_IN_BRANCH_RE = re.compile(r"^[^/]+/(\d+)-")
_SCISSORS_RE = re.compile(r"^#\s*-+\s*>8\s*-+")  # `git commit -v`: the diff follows this comment line


@dataclass(frozen=True)
class ConventionalSubject:
    type: str
    scope: str | None
    breaking: bool
    description: str


def parse_conventional(subject: str) -> ConventionalSubject | None:
    match = _CC_RE.match(subject.strip())
    if not match:
        return None
    return ConventionalSubject(
        type=match.group("type"),
        scope=match.group("scope"),
        breaking=bool(match.group("bang")),
        description=match.group("desc"),
    )


def slugify(text: str, max_length: int = 50) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:max_length].rstrip("-")


def build_branch_name(conv: ConventionsConfig, branch_type: str, description: str, issue: int | None = None) -> str:
    if branch_type not in conv.branch_types:
        raise ConventionError(f"unknown branch type '{branch_type}' (allowed: {', '.join(conv.branch_types)})")
    slug = slugify(description)
    if not slug:
        raise ConventionError("branch description must contain at least one ASCII letter or digit")
    if issue is not None:
        slug = f"{issue}-{slug}"
    elif conv.require_issue_in_branch:
        raise ConventionError("an issue number is required for branch names (use --issue N)")
    name = f"{branch_type}/{slug}"
    problems = validate_branch_name(conv, name)
    if problems:
        raise ConventionError(f"generated branch name '{name}' is invalid: {'; '.join(problems)}")
    return name


def validate_branch_name(conv: ConventionsConfig, name: str) -> list[str]:
    if name in conv.protected_branches:
        return []
    problems: list[str] = []
    if not re.match(conv.branch_pattern, name):
        problems.append(f"does not match pattern {conv.branch_pattern}")
    if conv.require_issue_in_branch and not _ISSUE_IN_BRANCH_RE.match(name):
        problems.append("issue number missing (expected <type>/<issue>-<description>)")
    return problems


def issue_from_branch(name: str) -> int | None:
    match = _ISSUE_IN_BRANCH_RE.match(name)
    return int(match.group(1)) if match else None


def branch_type_of(conv: ConventionsConfig, name: str) -> str | None:
    head = name.split("/", 1)[0]
    return head if head in conv.branch_types else None


def _subject_of(message: str) -> tuple[str, list[str]]:
    lines: list[str] = []
    for line in message.splitlines():
        if _SCISSORS_RE.match(line):
            break
        if not line.startswith("#"):
            lines.append(line)
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return "", []
    return lines[0].rstrip(), lines


def validate_commit_message(conv: ConventionsConfig, message: str) -> list[str]:
    subject, lines = _subject_of(message)
    if not subject:
        return ["commit message is empty"]
    if subject.startswith(("Merge ", 'Revert "')):
        return []
    if subject.startswith(("fixup! ", "squash! ", "amend! ")):
        return ["fixup!/squash! commits must be squashed before they are pushed"]
    parsed = parse_conventional(subject)
    if parsed is None:
        return [
            "subject must follow Conventional Commits: <type>(<scope>)?: <description> "
            f"(types: {', '.join(conv.commit_types)})"
        ]
    problems: list[str] = []
    if parsed.type not in conv.commit_types:
        problems.append(f"unknown type '{parsed.type}' (allowed: {', '.join(conv.commit_types)})")
    if conv.require_scope and not parsed.scope:
        problems.append("a scope is required: <type>(<scope>): <description>")
    if conv.commit_scopes and parsed.scope and parsed.scope not in conv.commit_scopes:
        problems.append(f"unknown scope '{parsed.scope}' (allowed: {', '.join(conv.commit_scopes)})")
    if len(subject) > conv.commit_subject_max:
        problems.append(f"subject is {len(subject)} characters (max {conv.commit_subject_max})")
    if parsed.description.rstrip().endswith("."):
        problems.append("description must not end with a period")
    if len(lines) > 1 and lines[1].strip():
        problems.append("the second line must be blank (subject / blank line / body)")
    return problems


def normalize_version(conv: ConventionsConfig, version: str) -> tuple[str, str]:
    """Return ``(semver, tag)`` for a user-supplied version like ``1.2.0`` or ``v1.2.0``."""
    raw = version.strip()
    prefix = conv.tag_prefix
    if prefix and raw.startswith(prefix):
        raw = raw[len(prefix) :]
    if not _SEMVER_RE.match(raw):
        raise ConventionError(f"'{version}' is not a valid semantic version (expected MAJOR.MINOR.PATCH[-pre][+build])")
    return raw, f"{prefix}{raw}"


def is_prerelease(semver: str) -> bool:
    match = _SEMVER_RE.match(semver)
    return bool(match and match.group("pre"))


def _version_key(match: re.Match[str]) -> tuple:
    pre = match.group("pre")
    # A final release sorts above its own pre-releases; pre-release identifiers compare numerically when possible.
    pre_key = tuple((0, int(p)) if p.isdigit() else (1, p) for p in pre.split(".")) if pre else ()
    return (int(match.group("major")), int(match.group("minor")), int(match.group("patch")), 0 if pre else 1, pre_key)


def latest_version_tag(conv: ConventionsConfig, tags: list[str]) -> str | None:
    """Highest semantic-version tag carrying ``tag_prefix`` (``v1.10.0`` > ``v1.9.0``); other tags are ignored."""
    prefix = conv.tag_prefix
    best: tuple[tuple, str] | None = None
    for tag in tags:
        if prefix and not tag.startswith(prefix):
            continue
        match = _SEMVER_RE.match(tag[len(prefix) :])
        if not match:
            continue
        key = _version_key(match)
        if best is None or key > best[0]:
            best = (key, tag)
    return best[1] if best else None


def pr_title(conv: ConventionsConfig, branch: str, commit_subjects: list[str]) -> str:
    """Derive a Conventional-Commits style PR title from the commits or the branch name."""
    if len(commit_subjects) == 1 and parse_conventional(commit_subjects[0]):
        return commit_subjects[0]
    btype = branch_type_of(conv, branch)
    ctype = conv.branch_type_to_commit_type.get(btype or "", "chore")
    tail = branch.split("/", 1)[1] if "/" in branch else branch
    tail = re.sub(r"^\d+-", "", tail)
    words = tail.replace("-", " ").replace("_", " ").strip() or branch
    title = f"{ctype}: {words}"
    if len(title) > conv.commit_subject_max:
        cut = title[: conv.commit_subject_max]
        at_word = cut.rsplit(" ", 1)[0]
        # Keep a description after "<type>: " even when the first word alone exceeds the limit.
        title = (at_word if len(at_word) > len(ctype) + 2 else cut).rstrip(" .")
    return title


def pr_label(conv: ConventionsConfig, title: str) -> str | None:
    parsed = parse_conventional(title)
    if not parsed:
        return None
    return conv.pr_labels_by_type.get(parsed.type)
