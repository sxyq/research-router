#!/usr/bin/env python3
"""Summarize local feedback records into compact JSON for route tuning."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1] / "records" / "feedback"
    output = Path(argv[2]) if len(argv) > 2 else Path(__file__).resolve().parents[1] / "records" / "summaries" / "feedback-summary.json"
    files = sorted(root.rglob("*.json")) if root.exists() else []
    skill_scores: dict[str, list[float]] = defaultdict(list)
    route_count = 0
    invalid = 0
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            skill_id = data["target_skill_id"]
            score = data["score"]
            if not isinstance(skill_id, str) or not skill_id.strip():
                raise ValueError
            if not isinstance(score, (int, float)) or not 0 <= score <= 10:
                raise ValueError
            skill_scores[skill_id].append(float(score))
            route_count += 1
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            invalid += 1

    def average(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    summary = {
        "feedback_records": route_count,
        "invalid_files": invalid,
        "skill_averages": {
            skill_id: average(values) for skill_id, values in sorted(skill_scores.items())
        },
        "interpretation": "Use repeated low scores as tuning evidence; do not change routing from one sample.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if invalid == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
