#!/usr/bin/env python3
"""Build a transparent heuristic route evaluation from a route JSON record."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("route record must be an object")
    return value


def source_rows(route: dict[str, Any]) -> list[dict[str, Any]]:
    rows = route.get("evidence")
    if not isinstance(rows, list):
        rows = route.get("sources", [])
    return [row for row in rows if isinstance(row, dict)]


def build_source_coverage(route: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    existing = route.get("source_coverage")
    existing = existing if isinstance(existing, dict) else {}
    statuses = [row.get("status") or row.get("evidence_status") for row in rows]
    direct_count = sum(status in {"verified", "available", "closed", "open"} for status in statuses)
    requested = existing.get("requested")
    if not isinstance(requested, list):
        requested = route.get("evidence_requirements", [])
    if not isinstance(requested, list):
        requested = []
    covered = existing.get("covered")
    if not isinstance(covered, list):
        covered = ["source evidence"] if rows else []
    missing = existing.get("missing")
    if not isinstance(missing, list):
        missing = []
    if existing.get("status") in {"verified", "partial", "unavailable"}:
        status = existing["status"]
    elif not rows:
        status = "unavailable"
    elif route.get("status") == "completed" and not missing:
        status = "verified"
    else:
        status = "partial"
    return {
        "status": status,
        "requested": requested,
        "covered": covered,
        "missing": missing,
        "source_count": len(rows),
        "direct_source_count": direct_count,
        "recency_score": existing.get("recency_score"),
    }


def build_evaluation(route: dict[str, Any], coverage: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    existing = route.get("route_evaluation")
    existing = existing if isinstance(existing, dict) else {}
    evidence_count = len(rows)
    direct_count = coverage["direct_source_count"]
    directness = round(10 * direct_count / evidence_count, 2) if evidence_count else 0
    if existing.get("evidence_directness") is not None:
        directness = existing["evidence_directness"]
    if existing.get("problem_coverage") is not None:
        problem_coverage = existing["problem_coverage"]
    elif coverage["status"] == "verified":
        problem_coverage = 10
    elif evidence_count:
        problem_coverage = 8
    else:
        problem_coverage = 0
    recency = existing.get("recency")
    if recency is None:
        recency = coverage.get("recency_score")
    duplicate_count = route.get("duplicate_source_count", 0)
    if not isinstance(duplicate_count, int) or duplicate_count < 0:
        duplicate_count = 0
    deduplication = max(0, 10 - duplicate_count * 2) if evidence_count else 0
    if existing.get("deduplication") is not None:
        deduplication = existing["deduplication"]
    dimensions = [problem_coverage, directness, recency, deduplication]
    rated = [score for score in dimensions if isinstance(score, (int, float))]
    overall = round(sum(rated) / len(rated), 2) if rated else None
    if existing.get("overall") is not None:
        overall = existing["overall"]
    unconfirmed = existing.get("unconfirmed_items")
    if not isinstance(unconfirmed, list):
        unconfirmed = list(coverage["missing"])
    platforms = route.get("platforms", [])
    agent_count = sum(isinstance(row, dict) and isinstance(row.get("agent_id"), str) for row in platforms)
    skill_calls = sum(
        len(row.get("skill_order", []))
        for row in platforms
        if isinstance(row, dict) and isinstance(row.get("skill_order"), list)
    )
    cost = existing.get("execution_cost")
    cost = cost if isinstance(cost, dict) else {}
    execution_cost = {
        "query_count": cost.get("query_count", len(route.get("query_variants", []))),
        "skill_calls": cost.get("skill_calls", skill_calls),
        "agent_count": cost.get("agent_count", agent_count),
        "duration_seconds": cost.get("duration_seconds"),
    }
    return {
        "problem_coverage": problem_coverage,
        "evidence_directness": directness,
        "recency": recency,
        "deduplication": deduplication,
        "execution_cost": execution_cost,
        "unconfirmed_items": unconfirmed,
        "overall": overall,
        "method": "combined" if existing else "heuristic",
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route", type=Path)
    parser.add_argument("--write", action="store_true", help="write source_coverage and route_evaluation to the route")
    args = parser.parse_args(argv[1:])
    try:
        route = load(args.route)
        rows = source_rows(route)
        coverage = build_source_coverage(route, rows)
        evaluation = build_evaluation(route, coverage, rows)
        result = {"source_coverage": coverage, "route_evaluation": evaluation}
        if args.write:
            route.update(result)
            args.route.write_text(json.dumps(route, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result["status"] = "written"
        else:
            result["status"] = "preview"
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
