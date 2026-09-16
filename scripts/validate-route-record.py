#!/usr/bin/env python3
"""Validate a route or feedback JSON record without third-party dependencies."""

from __future__ import annotations

import json
import sys
from pathlib import Path


SCENES = {"bug-fix", "open-source", "academic", "community"}
MODES = {"direct", "clarify"}
DEPTHS = {"light", "medium", "deep"}
STATUSES = {"planned", "running", "completed", "partial", "failed"}
SOURCE_STATUSES = {"verified", "partial", "unavailable"}
EVALUATION_METHODS = {"manual", "heuristic", "combined"}


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


def validate_router_path(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["router_path must be a list"]
    errors: list[str] = []
    for index, event in enumerate(value):
        if not isinstance(event, dict):
            errors.append(f"router_path[{index}] must be an object")
            continue
        if not isinstance(event.get("stage"), str) or not event["stage"].strip():
            errors.append(f"router_path[{index}].stage must be a non-empty string")
        if "skill_ids" in event and not isinstance(event["skill_ids"], list):
            errors.append(f"router_path[{index}].skill_ids must be a list")
    return errors


def validate_source_coverage(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["source_coverage must be an object"]
    errors: list[str] = []
    if value.get("status") not in SOURCE_STATUSES:
        errors.append(f"source_coverage.status must be one of {sorted(SOURCE_STATUSES)}")
    for key in ("requested", "covered", "missing"):
        if not isinstance(value.get(key), list) or not all(isinstance(item, str) for item in value[key]):
            errors.append(f"source_coverage.{key} must be a string list")
    for key in ("source_count", "direct_source_count"):
        if key in value and (not isinstance(value[key], int) or value[key] < 0):
            errors.append(f"source_coverage.{key} must be a non-negative integer")
    if "recency_score" in value and value["recency_score"] is not None:
        if not isinstance(value["recency_score"], (int, float)) or not 0 <= value["recency_score"] <= 10:
            errors.append("source_coverage.recency_score must be null or a number from 0 to 10")
    return errors


def validate_route_evaluation(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["route_evaluation must be an object"]
    errors: list[str] = []
    for key in ("problem_coverage", "evidence_directness", "recency", "deduplication", "overall"):
        score = value.get(key)
        if score is not None and (not isinstance(score, (int, float)) or not 0 <= score <= 10):
            errors.append(f"route_evaluation.{key} must be null or a number from 0 to 10")
    if value.get("method") not in EVALUATION_METHODS:
        errors.append(f"route_evaluation.method must be one of {sorted(EVALUATION_METHODS)}")
    cost = value.get("execution_cost")
    if not isinstance(cost, dict):
        errors.append("route_evaluation.execution_cost must be an object")
    else:
        for key in ("query_count", "skill_calls", "agent_count"):
            if not isinstance(cost.get(key), int) or cost[key] < 0:
                errors.append(f"route_evaluation.execution_cost.{key} must be a non-negative integer")
        if "duration_seconds" in cost and cost["duration_seconds"] is not None:
            if not isinstance(cost["duration_seconds"], (int, float)) or cost["duration_seconds"] < 0:
                errors.append("route_evaluation.execution_cost.duration_seconds must be null or non-negative")
    if not isinstance(value.get("unconfirmed_items"), list) or not all(
        isinstance(item, str) for item in value["unconfirmed_items"]
    ):
        errors.append("route_evaluation.unconfirmed_items must be a string list")
    return errors


def validate_route(value: dict) -> list[str]:
    required = [
        "route_id",
        "created_at",
        "scene",
        "interaction_mode",
        "depth",
        "query_variants",
        "platforms",
        "router_path",
        "executed_leaf_skills",
        "final_leaf_skills",
        "source_coverage",
        "stop_reason",
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
    errors.extend(validate_router_path(value["router_path"]))
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
    if not isinstance(value["executed_leaf_skills"], list) or not all(
        isinstance(item, str) and item.strip() for item in value["executed_leaf_skills"]
    ):
        errors.append("executed_leaf_skills must be a list of non-empty strings")
    elif isinstance(value["final_leaf_skills"], list) and set(value["executed_leaf_skills"]) != set(value["final_leaf_skills"]):
        errors.append("executed_leaf_skills must match final_leaf_skills")
    if not isinstance(value["stop_reason"], str) or not value["stop_reason"].strip():
        errors.append("stop_reason must be a non-empty string")
    errors.extend(validate_source_coverage(value["source_coverage"]))
    if "route_evaluation" in value:
        errors.extend(validate_route_evaluation(value["route_evaluation"]))
    elif value["status"] in {"completed", "partial", "failed"}:
        errors.append("route_evaluation is required when status is completed, partial, or failed")
    return errors


def validate_feedback(value: dict) -> list[str]:
    errors = [
        f"missing field: {key}"
        for key in ("feedback_id", "route_id", "created_at", "scores")
        if key not in value
    ]
    if errors:
        return errors
    scores = value["scores"]
    if not isinstance(scores, dict):
        return ["scores must be an object"]
    if not isinstance(scores.get("router"), (int, float)) or not 0 <= scores["router"] <= 10:
        errors.append("scores.router must be a number from 0 to 10")
    skills = scores.get("skills")
    if not isinstance(skills, dict):
        errors.append("scores.skills must be an object")
    else:
        for skill_id, score in skills.items():
            if not isinstance(skill_id, str) or not isinstance(score, (int, float)) or not 0 <= score <= 10:
                errors.append(f"scores.skills[{skill_id!r}] must be a number from 0 to 10")
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
