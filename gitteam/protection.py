"""Builders for branch-protection payloads (classic API and repository rulesets)."""

from __future__ import annotations

from typing import Any

from .config import ProtectionConfig

RULESET_NAME_PREFIX = "gitteam:"
REPOSITORY_ROLE_ADMIN = 5  # RepositoryRole actor id for "admin" (fixed by GitHub)


def ruleset_name(branch: str) -> str:
    return f"{RULESET_NAME_PREFIX}{branch}"


def classic_payload(cfg: ProtectionConfig) -> dict[str, Any]:
    """Body for ``PUT /repos/{owner}/{repo}/branches/{branch}/protection``."""
    status_checks: dict[str, Any] | None
    if cfg.status_checks or cfg.strict_status_checks:
        status_checks = {
            "strict": cfg.strict_status_checks,
            "checks": [{"context": context} for context in cfg.status_checks],
        }
    else:
        status_checks = None
    reviews: dict[str, Any] | None = None
    if cfg.required_approvals > 0 or cfg.require_code_owner_reviews:
        reviews = {
            "required_approving_review_count": cfg.required_approvals,
            "dismiss_stale_reviews": cfg.dismiss_stale_reviews,
            "require_code_owner_reviews": cfg.require_code_owner_reviews,
            "require_last_push_approval": cfg.require_last_push_approval,
        }
    return {
        "required_status_checks": status_checks,
        "enforce_admins": cfg.enforce_admins,
        "required_pull_request_reviews": reviews,
        "restrictions": None,
        "required_linear_history": cfg.required_linear_history,
        "allow_force_pushes": cfg.allow_force_pushes,
        "allow_deletions": cfg.allow_deletions,
        "required_conversation_resolution": cfg.require_conversation_resolution,
        "lock_branch": False,
        "allow_fork_syncing": True,
    }


def ruleset_payload(cfg: ProtectionConfig, branch: str) -> dict[str, Any]:
    """Body for ``POST/PUT /repos/{owner}/{repo}/rulesets``.

    ``branch`` may be an fnmatch pattern such as ``release/*``.
    """
    rules: list[dict[str, Any]] = []
    if not cfg.allow_deletions:
        rules.append({"type": "deletion"})
    if not cfg.allow_force_pushes:
        rules.append({"type": "non_fast_forward"})
    if cfg.required_linear_history:
        rules.append({"type": "required_linear_history"})
    if cfg.require_signed_commits:
        rules.append({"type": "required_signatures"})
    if cfg.required_approvals > 0 or cfg.require_code_owner_reviews or cfg.require_conversation_resolution:
        rules.append(
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": cfg.required_approvals,
                    "dismiss_stale_reviews_on_push": cfg.dismiss_stale_reviews,
                    "require_code_owner_review": cfg.require_code_owner_reviews,
                    "require_last_push_approval": cfg.require_last_push_approval,
                    "required_review_thread_resolution": cfg.require_conversation_resolution,
                },
            }
        )
    if cfg.status_checks:
        rules.append(
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": cfg.strict_status_checks,
                    "required_status_checks": [{"context": context} for context in cfg.status_checks],
                },
            }
        )
    bypass_actors: list[dict[str, Any]] = []
    if not cfg.enforce_admins:
        bypass_actors.append(
            {"actor_id": REPOSITORY_ROLE_ADMIN, "actor_type": "RepositoryRole", "bypass_mode": "always"}
        )
    return {
        "name": ruleset_name(branch),
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": [f"refs/heads/{branch}"], "exclude": []}},
        "rules": rules,
        "bypass_actors": bypass_actors,
    }


def choose_engine(cfg: ProtectionConfig) -> str:
    """Resolve ``auto`` to a concrete engine. Rulesets are preferred: they support
    branch patterns, do not require the branch to exist, and are the API GitHub invests in."""
    return "ruleset" if cfg.engine == "auto" else cfg.engine
