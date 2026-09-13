#!/usr/bin/env python3
"""Validate the router's JSON registry and platform depth maps."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


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

    platform_ids = set(platforms_index.get("platforms", []))
    skill_ids = {item.get("id") for item in skills_index if isinstance(item, dict)}
    depth_policy = platforms_index.get("depth_policy")
    expected_depth_policy = {
        "light": {"sub_agents": 0, "execution": "main-conversation"},
        "medium": {"sub_agents": {"default": 2, "max": 4}, "execution": "bounded-parallel"},
        "deep": {"sub_agents": "unbounded", "execution": "task-sized-parallel"},
    }
    if depth_policy != expected_depth_policy:
        errors.append("platforms.index.json: depth_policy must define light=0, medium=2..4, deep=unbounded")
    if not isinstance(aliases, dict):
        errors.append("aliases must be an object")
    else:
        for alias, target in aliases.items():
            if target not in platform_ids and target not in {"bug-fix", "academic", "stackoverflow"}:
                errors.append(f"alias {alias!r} points to unknown target {target!r}")

    for path in sorted((registry / "platforms").glob("*.json")):
        try:
            data = read_json(path)
            platform_id = data["platform_id"]
            if platform_id not in platform_ids:
                errors.append(f"{path.name}: platform_id not in platforms.index.json")
            routes = data["depth_routes"]
            for depth in ("light", "medium", "deep"):
                if depth not in routes or not isinstance(routes[depth], list):
                    errors.append(f"{path.name}: missing list depth_routes.{depth}")
                else:
                    for skill_id in routes[depth]:
                        if skill_id not in skill_ids:
                            errors.append(f"{path.name}: unknown skill {skill_id!r}")
        except (OSError, UnicodeError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("OK: registry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
