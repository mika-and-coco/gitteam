"""Label synchronisation planning (pure)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .config import Label


@dataclass(frozen=True)
class LabelChange:
    action: str  # create | update | delete | keep
    label: Label
    detail: str = ""


def plan_changes(existing: Iterable[dict[str, Any]], desired: Iterable[Label], prune: bool = False) -> list[LabelChange]:
    current = {str(item["name"]).lower(): item for item in existing}
    changes: list[LabelChange] = []
    wanted_names: set[str] = set()
    for label in desired:
        key = label.name.lower()
        wanted_names.add(key)
        found = current.get(key)
        if found is None:
            changes.append(LabelChange("create", label))
            continue
        diffs = []
        if str(found.get("color", "")).lower() != label.color.lower():
            diffs.append(f"color {found.get('color')} -> {label.color}")
        if (found.get("description") or "") != label.description:
            diffs.append("description")
        if found.get("name") != label.name:
            diffs.append(f"name {found.get('name')} -> {label.name}")
        if diffs:
            changes.append(LabelChange("update", label, ", ".join(diffs)))
        else:
            changes.append(LabelChange("keep", label))
    if prune:
        for key, item in current.items():
            if key not in wanted_names:
                changes.append(
                    LabelChange("delete", Label(str(item["name"]), str(item.get("color", "ffffff")), item.get("description") or ""))
                )
    return changes
