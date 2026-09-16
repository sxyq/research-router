#!/usr/bin/env python3
"""Validate the Router registry, platform tiers, Skills, and local scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PLATFORM_FIELDS = (
    "platform_id",
    "display_name",
    "tier",
    "route_skills",
    "scripts",
    "adapter_type",
    "access_mode",
    "status",
    "capabilities",
    "depth_routes",
)
CATALOG_FIELDS = (
    "platform_id",
    "display_name",
    "tier",
    "route_skills",
    "scripts",
    "adapter_type",
    "access_mode",
    "status",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def add_missing_fields(errors: list[str], data: dict[str, Any], fields: tuple[str, ...], label: str) -> None:
    for field in fields:
        if field not in data:
            errors.append(f"{label}: missing {field}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    registry = root / "registry"
    errors: list[str] = []
    try:
        aliases = read_json(registry / "aliases.json")["aliases"]
        platforms_index = read_json(registry / "platforms.index.json")
        skills_index = read_json(registry / "skills.index.json")["skills"]
    except (OSError, UnicodeError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read registry: {exc}", file=sys.stderr)
        return 1

    platform_ids = platforms_index.get("platforms", [])
    if not isinstance(platform_ids, list) or not all(isinstance(item, str) for item in platform_ids):
        errors.append("platforms.index.json: platforms must be a string list")
        platform_ids = []
    active_platform_ids = set(platform_ids)

    catalog_entries = platforms_index.get("catalog_only_platforms", [])
    if not isinstance(catalog_entries, list):
        errors.append("platforms.index.json: catalog_only_platforms must be a list")
        catalog_entries = []
    catalog_ids: set[str] = set()
    for entry in catalog_entries:
        if not isinstance(entry, dict):
            errors.append("platforms.index.json: every catalog-only platform must be an object")
            continue
        label = f"catalog-only {entry.get('platform_id', '<unknown>')}"
        add_missing_fields(errors, entry, CATALOG_FIELDS, label)
        platform_id = entry.get("platform_id")
        if not isinstance(platform_id, str):
            continue
        if platform_id in active_platform_ids or platform_id in catalog_ids:
            errors.append(f"{label}: duplicate platform id")
        catalog_ids.add(platform_id)
        if entry.get("status") != "upstream-catalog-only":
            errors.append(f"{label}: status must be upstream-catalog-only")
        if entry.get("tier") not in (1, 2, 3):
            errors.append(f"{label}: tier must be 1, 2, or 3")
        if not isinstance(entry.get("route_skills"), list):
            errors.append(f"{label}: route_skills must be a list")
        if not isinstance(entry.get("scripts"), list):
            errors.append(f"{label}: scripts must be a list")

    all_platform_ids = active_platform_ids | catalog_ids
    scene_ids = set(platforms_index.get("scenes", []))
    skill_ids = {
        item.get("id")
        for item in skills_index
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    tier_map = platforms_index.get("platform_tiers")
    if not isinstance(tier_map, dict):
        errors.append("platforms.index.json: platform_tiers must be an object")
        tier_map = {}
    tier_members: dict[str, list[str]] = {}
    for tier in (1, 2, 3):
        key = f"tier-{tier}"
        members = tier_map.get(key)
        if not isinstance(members, list) or not all(isinstance(item, str) for item in members):
            errors.append(f"platforms.index.json: {key} must be a string list")
            tier_members[key] = []
            continue
        tier_members[key] = members
        if len(set(members)) != len(members):
            errors.append(f"platforms.index.json: {key} contains duplicate platform ids")
        for platform_id in members:
            if platform_id not in all_platform_ids:
                errors.append(f"platforms.index.json: {key} contains unknown platform {platform_id!r}")

    listed_tiers = [platform_id for members in tier_members.values() for platform_id in members]
    if set(listed_tiers) != all_platform_ids:
        missing = sorted(all_platform_ids - set(listed_tiers))
        extra = sorted(set(listed_tiers) - all_platform_ids)
        if missing:
            errors.append(f"platforms.index.json: platforms missing from tier map: {missing}")
        if extra:
            errors.append(f"platforms.index.json: tier map has unregistered platforms: {extra}")
    if len(listed_tiers) != len(set(listed_tiers)):
        errors.append("platforms.index.json: a platform must occur in exactly one tier")

    tier_by_platform = {
        platform_id: int(key.removeprefix("tier-"))
        for key, members in tier_members.items()
        for platform_id in members
    }

    if not isinstance(aliases, dict):
        errors.append("aliases must be an object")
    else:
        for alias, target in aliases.items():
            if target not in all_platform_ids and target not in scene_ids:
                errors.append(f"alias {alias!r} points to unknown target {target!r}")

    for entry in catalog_entries:
        if not isinstance(entry, dict):
            continue
        label = f"catalog-only {entry.get('platform_id', '<unknown>')}"
        if entry.get("tier") != tier_by_platform.get(entry.get("platform_id")):
            errors.append(f"{label}: tier does not match platform_tiers")
        route_skills = entry.get("route_skills")
        if isinstance(route_skills, list):
            for skill_id in route_skills:
                if skill_id not in skill_ids:
                    errors.append(f"{label}: unknown Skill {skill_id!r}")
        scripts = entry.get("scripts")
        if isinstance(scripts, list) and scripts:
            errors.append(f"{label}: catalog-only entries cannot claim local script paths")

    for path in sorted((registry / "platforms").glob("*.json")):
        try:
            data = read_json(path)
            if not isinstance(data, dict):
                errors.append(f"{path.name}: platform entry must be an object")
                continue
            add_missing_fields(errors, data, PLATFORM_FIELDS, path.name)
            platform_id = data.get("platform_id")
            if platform_id not in active_platform_ids:
                errors.append(f"{path.name}: platform_id not in platforms.index.json")
            if data.get("tier") != tier_by_platform.get(platform_id):
                errors.append(f"{path.name}: tier does not match platform_tiers")
            if data.get("tier") not in (1, 2, 3):
                errors.append(f"{path.name}: tier must be 1, 2, or 3")

            route_skills = data.get("route_skills")
            if not isinstance(route_skills, list):
                errors.append(f"{path.name}: route_skills must be a list")
                route_skills = []
            for skill_id in route_skills:
                if skill_id not in skill_ids:
                    errors.append(f"{path.name}: unknown route Skill {skill_id!r}")

            routes = data.get("depth_routes")
            if not isinstance(routes, dict):
                errors.append(f"{path.name}: depth_routes must be an object")
                routes = {}
            route_union: set[str] = set()
            for depth in ("light", "medium", "deep"):
                if depth not in routes or not isinstance(routes[depth], list):
                    errors.append(f"{path.name}: missing list depth_routes.{depth}")
                    continue
                for skill_id in routes[depth]:
                    route_union.add(skill_id)
                    if skill_id not in skill_ids:
                        errors.append(f"{path.name}: unknown Skill {skill_id!r}")
            if set(route_skills) != route_union:
                errors.append(f"{path.name}: route_skills must equal the union of depth routes")

            scripts = data.get("scripts")
            if not isinstance(scripts, list):
                errors.append(f"{path.name}: scripts must be a list")
            else:
                for script in scripts:
                    if not isinstance(script, str) or Path(script).is_absolute():
                        errors.append(f"{path.name}: scripts must contain relative paths")
                    elif not (root / script).is_file():
                        errors.append(f"{path.name}: local script does not exist: {script}")

            if platform_id == "52pojie":
                expected_script = "references/local/52pojie-research/scripts/fetch.py"
                if data.get("tier") != 2:
                    errors.append("52pojie must remain in tier-2")
                if "52pojie-research" not in route_skills:
                    errors.append("52pojie must route through 52pojie-research")
                if data.get("scripts") != [expected_script]:
                    errors.append("52pojie must map to its bundled fetch.py script")
        except (OSError, UnicodeError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")

    file_platform_ids = {path.stem for path in (registry / "platforms").glob("*.json")}
    missing_files = sorted(active_platform_ids - file_platform_ids)
    if missing_files:
        errors.append(f"missing platform JSON entries: {missing_files}")

    for entry in skills_index:
        if not isinstance(entry, dict):
            continue
        skill_id = entry.get("id", "<unknown>")
        platforms = entry.get("platforms", [])
        if not isinstance(platforms, list):
            errors.append(f"Skill {skill_id!r}: platforms must be a list")
            continue
        for platform_id in platforms:
            if platform_id not in all_platform_ids:
                errors.append(f"Skill {skill_id!r}: unknown platform {platform_id!r}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"OK: registry ({len(active_platform_ids)} registered platforms, "
        f"{len(catalog_ids)} catalog-only platforms, 3 tiers)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
