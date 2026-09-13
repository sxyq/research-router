#!/usr/bin/env python3
"""Validate a route or feedback JSON record without third-party dependencies."""

from __future__ import annotations

import json
import sys
from pathlib import Path


SCENES = {"bug-fix", "open-source", "academic"}
MODES = {"direct", "clarify"}
DEPTHS = {"light", "medium", "deep"}
STATUSES = {"planned", "running", "completed", "partial", "failed"}


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(value, dict):
        raise ValueError("top-level JSON value must be an object")
    return value


def validate_route(value: dict) -> list[str]:
    required = [
        "route_id",
        "created_at",
        "scene",
        "interaction_mode",
        "depth",
        "query_variants",
        "platforms",
        "final_leaf_skills",
        "status",
    ]
    errors = [f"missing field: {key}" for key in required if key not in value]
    if errors:
        return errors
    if not isinstance(value["route_id"], str) or not value["route_id"].strip():
        errors.append("route_id must be a non-empty string")
    if value["scene"] not in SCENES:
        errors.append(f"scene must be one of {sorted(SCENES)}")
    if value["interaction_mode"] not in MODES:
        errors.append(f"interaction_mode must be one of {sorted(MODES)}")
    if value["depth"] not in DEPTHS:
        errors.append(f"depth must be one of {sorted(DEPTHS)}")
    if value["status"] not in STATUSES:
        errors.append(f"status must be one of {sorted(STATUSES)}")
    if not isinstance(value["query_variants"], list) or not all(
        isinstance(item, str) and item.strip() for item in value["query_variants"]
    ):
        errors.append("query_variants must be a list of non-empty strings")
    if not isinstance(value["platforms"], list):
        errors.append("platforms must be a list")
    else:
        for index, platform in enumerate(value["platforms"]):
            if not isinstance(platform, dict):
                errors.append(f"platforms[{index}] must be an object")
                continue
            for key in ("platform_id", "agent_id", "skill_order"):
                if key not in platform:
                    errors.append(f"platforms[{index}] missing field: {key}")
            if "skill_order" in platform and not isinstance(platform["skill_order"], list):
                errors.append(f"platforms[{index}].skill_order must be a list")
    if not isinstance(value["final_leaf_skills"], list) or not all(
        isinstance(item, str) and item.strip() for item in value["final_leaf_skills"]
    ):
        errors.append("final_leaf_skills must be a list of non-empty strings")
    return errors


def validate_feedback(value: dict) -> list[str]:
    errors = [
        f"missing field: {key}"
        for key in ("feedback_id", "route_id", "created_at", "target_skill_id", "score")
        if key not in value
    ]
    if errors:
        return errors
    if not isinstance(value["target_skill_id"], str) or not value["target_skill_id"].strip():
        errors.append("target_skill_id must be a non-empty string")
    if not isinstance(value["score"], (int, float)) or not 0 <= value["score"] <= 10:
        errors.append("score must be a number from 0 to 10")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {Path(argv[0]).name} <route-or-feedback.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        value = load(path)
    except ValueError as exc:
        return fail(str(exc))
    if "feedback_id" in value:
        errors = validate_feedback(value)
    else:
        errors = validate_route(value)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
