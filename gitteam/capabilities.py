from __future__ import annotations

from dataclasses import dataclass

from .config import Mode, Plan


@dataclass(frozen=True)
class Capabilities:
    """Feature availability derived from mode, billing plan and repository visibility."""

    mode: Mode
    plan: Plan
    visibility: str
    teams: bool
    branch_protection: bool
    rulesets: bool
    org_rulesets: bool
    push_rulesets: bool
    required_workflows: bool
    internal_repos: bool
    codeowners_enforced: bool
    notes: tuple[str, ...]

    def as_rows(self) -> list[tuple[str, str]]:
        def yes_no(value: bool) -> str:
            return "yes" if value else "no"

        return [
            ("mode", self.mode.value),
            ("plan", self.plan.value),
            ("visibility", self.visibility),
            ("teams", yes_no(self.teams)),
            ("branch protection / rulesets", yes_no(self.branch_protection)),
            ("CODEOWNERS enforcement", yes_no(self.codeowners_enforced)),
            ("org-level rulesets", yes_no(self.org_rulesets)),
            ("push rulesets", yes_no(self.push_rulesets)),
            ("required workflows", yes_no(self.required_workflows)),
            ("internal repositories", yes_no(self.internal_repos)),
        ]


def resolve(mode: Mode, plan: Plan, visibility: str = "private") -> Capabilities:
    """Compute what the configured GitHub form can do.

    Rules (GitHub Free / Pro / Team / Enterprise Cloud):
      * Teams exist only in organizations.
      * Branch protection and repository rulesets are available on public repos for
        every plan, and on private repos only with Pro (personal), Team or Enterprise.
      * Org-level rulesets, push rulesets and required workflows need Enterprise Cloud.
    """
    if mode is Mode.ORG_ENTERPRISE:
        plan = Plan.ENTERPRISE
    if plan is Plan.AUTO:
        plan = Plan.FREE
    notes: list[str] = []
    is_public = visibility == "public"
    protection = is_public or plan.is_paid
    if not protection:
        notes.append(
            f"branch protection/rulesets are unavailable for {visibility} repositories on plan '{plan.value}'. "
            "Make the repository public or upgrade (Pro for personal accounts, Team/Enterprise for organizations)."
        )
    teams = mode.is_org
    if not teams:
        notes.append("teams are not available for personal accounts; collaborators are used instead.")
    enterprise = mode is Mode.ORG_ENTERPRISE
    return Capabilities(
        mode=mode,
        plan=plan,
        visibility=visibility,
        teams=teams,
        branch_protection=protection,
        rulesets=protection,
        org_rulesets=enterprise,
        push_rulesets=enterprise,
        required_workflows=enterprise,
        internal_repos=enterprise,
        codeowners_enforced=protection,
        notes=tuple(notes),
    )


def plan_from_api_name(name: str | None, mode: Mode) -> Plan:
    """Map the ``plan.name`` field returned by the GitHub API to :class:`Plan`."""
    if mode is Mode.ORG_ENTERPRISE:
        return Plan.ENTERPRISE
    if not name:
        return Plan.FREE
    normalized = name.strip().lower()
    if normalized == "free":
        return Plan.FREE
    if normalized == "pro":
        return Plan.PRO
    if normalized in ("team", "business"):
        return Plan.TEAM
    if normalized in ("enterprise", "enterprise_cloud"):
        return Plan.ENTERPRISE
    # Legacy per-seat plans (bronze/silver/gold/...) all include private-repo protection.
    return Plan.TEAM
