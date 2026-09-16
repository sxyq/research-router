#!/usr/bin/env python3
"""Derive per-Skill and per-platform JSONL experience from a route record."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


def load_route(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("route record must be an object")
    return value


def safe_id(value: str) -> str:
    result = SAFE_ID.sub("_", value).strip("._")
    if not result:
        raise ValueError("subject id cannot be empty")
    return result


def failure_list(
    route: dict[str, Any],
    subject_type: str,
    subject_id: str,
    platform_skill_ids: set[str] | None = None,
) -> list[Any]:
    failures = route.get("failures", [])
    if not isinstance(failures, list):
        return []
    selected: list[Any] = []
    for failure in failures:
        if isinstance(failure, str):
            selected.append(failure)
            continue
        if not isinstance(failure, dict):
            continue
        linked_skill = failure.get("skill_id")
        linked_platform = failure.get("platform_id")
        if not linked_skill and not linked_platform:
            selected.append(failure)
        elif subject_type == "skill" and linked_skill == subject_id:
            selected.append(failure)
        elif subject_type == "platform" and (
            linked_platform == subject_id
            or (platform_skill_ids and linked_skill in platform_skill_ids)
        ):
            selected.append(failure)
    return selected


def platform_rows(route: dict[str, Any]) -> list[dict[str, Any]]:
    rows = route.get("platforms", [])
    return [row for row in rows if isinstance(row, dict) and isinstance(row.get("platform_id"), str)]


def skill_rows(route: dict[str, Any]) -> list[dict[str, Any]]:
    rows = route.get("matched_skills", [])
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        skill_id = row.get("skill_id") or row.get("skill")
        if isinstance(skill_id, str) and skill_id:
            result.append({**row, "skill_id": skill_id})
    return result


def skill_platforms(rows: list[dict[str, Any]], skill_id: str) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        if skill_id in row.get("skill_order", []):
            result.append(row)
    return result


def base_record(route: dict[str, Any], subject_type: str, subject_id: str) -> dict[str, Any]:
    return {
        "experience_id": f"{route['route_id']}:{subject_type}:{subject_id}",
        "recorded_at": route.get("created_at"),
        "route_id": route["route_id"],
        "subject_type": subject_type,
        "subject_id": subject_id,
        "scene": route.get("scene"),
        "depth": route.get("depth"),
        "outcome": route.get("status"),
        "query_variants": route.get("query_variants", []),
        "source_coverage": route.get("source_coverage", {}),
        "route_evaluation": route.get("route_evaluation", {}),
        "failures": failure_list(route, subject_type, subject_id),
        "stop_reason": route.get("stop_reason", "unspecified"),
    }


def build_records(route: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    platforms = platform_rows(route)
    matched_skills = skill_rows(route)
    executed_skills = set(route.get("executed_leaf_skills", route.get("final_leaf_skills", [])))
    skill_records: list[dict[str, Any]] = []
    seen_skills: set[str] = set()
    for row in matched_skills:
        skill_id = row["skill_id"]
        if skill_id in seen_skills:
            continue
        seen_skills.add(skill_id)
        related_platforms = skill_platforms(platforms, skill_id)
        record = base_record(route, "skill", skill_id)
        record.update({
            "selected": True,
            "executed": bool(related_platforms) or skill_id in executed_skills,
            "platform_ids": [row["platform_id"] for row in related_platforms],
            "skill_ids": [skill_id],
            "skill_order": [skill_id],
        })
        skill_records.append(record)

    platform_records: list[dict[str, Any]] = []
    for row in platforms:
        platform_id = row["platform_id"]
        skill_order = [item for item in row.get("skill_order", []) if isinstance(item, str)]
        record = base_record(route, "platform", platform_id)
        record["failures"] = failure_list(route, "platform", platform_id, set(skill_order))
        record.update({
            "selected": True,
            "executed": bool(skill_order),
            "platform_ids": [platform_id],
            "skill_ids": skill_order,
            "skill_order": skill_order,
        })
        platform_records.append(record)
    return skill_records, platform_records


def append_unique(path: Path, records: list[dict[str, Any]], dry_run: bool) -> list[str]:
    existing: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and isinstance(item.get("experience_id"), str):
                existing.add(item["experience_id"])
    pending = [item for item in records if item["experience_id"] not in existing]
    if pending and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for item in pending:
                handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    return [item["experience_id"] for item in pending]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv[1:])
    try:
        route = load_route(args.route)
        output_root = args.output_root or Path(__file__).resolve().parents[1] / "records" / "experience"
        skill_records, platform_records = build_records(route)
        written: list[str] = []
        grouped_skills: dict[str, list[dict[str, Any]]] = {}
        for record in skill_records:
            grouped_skills.setdefault(record["subject_id"], []).append(record)
        grouped_platforms: dict[str, list[dict[str, Any]]] = {}
        for record in platform_records:
            grouped_platforms.setdefault(record["subject_id"], []).append(record)
        for subject_id, records in grouped_skills.items():
            path = output_root / "skills" / f"{safe_id(subject_id)}.jsonl"
            written.extend(append_unique(path, records, args.dry_run))
        for subject_id, records in grouped_platforms.items():
            path = output_root / "platforms" / f"{safe_id(subject_id)}.jsonl"
            written.extend(append_unique(path, records, args.dry_run))
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    mode = "would record" if args.dry_run else "recorded"
    print(json.dumps({"status": "ok", "mode": mode, "experience_ids": written}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
